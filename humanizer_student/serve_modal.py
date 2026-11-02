"""Serve the student humanizer on Modal as an OpenAI-compatible vLLM endpoint.

The LoRA adapter is merged into Qwen3-8B once (``merge``) so vLLM can serve the plain
model with FP8 weights and n-gram speculative decoding: rewrites copy many n-grams
from the source, so prompt-lookup drafts are accepted often.

One-time setup (local machine):
    pip install modal && modal setup
    modal volume create humanizer-adapters
    modal volume put humanizer-adapters <adapter dir> /qwen3_8b_lora_v1
    modal secret create humanizer-api-key HUMANIZER_API_KEY=<random key>
    modal run humanizer_student/serve_modal.py::merge

Deploy (GPU is read at deploy time):
    HUMANIZER_GPU=L40S modal deploy humanizer_student/serve_modal.py

Containers start from a CPU+GPU memory snapshot (~10 s instead of ~1 min). The first cold
start after a deploy builds the snapshot, so it is slow once.

The site calls ``<url>/v1/chat/completions`` with model ``humanizer-v1`` and
``Authorization: Bearer <HUMANIZER_API_KEY>`` (see services/humanizer_engine/student_humanizer.py).
"""

from __future__ import annotations

import json
import os

import modal

BASE_MODEL = "Qwen/Qwen3-8B"
# Baked into the images below so containers resolve the same paths as the deploying shell.
MODEL_VERSION = os.environ.get("HUMANIZER_MODEL_VERSION", "v1")
ADAPTER_PATH = f"/adapters/qwen3_8b_lora_{MODEL_VERSION}"
MERGED_PATH = f"/adapters/merged/qwen3_8b_humanizer_{MODEL_VERSION}"
SERVED_NAME = f"humanizer-{MODEL_VERSION}"
# vLLM listens only inside the container; the public endpoint is a proxy that forwards
# /v1/* alone, because sleep mode adds unauthenticated /sleep and /wake_up routes.
VLLM_PORT = 8001
APP_NAME = os.environ.get("HUMANIZER_APP_NAME", "docmaxxing-humanizer")
GPU = os.environ.get("HUMANIZER_GPU", "L40S")
# Idle GPU time is the main cost: a lone request otherwise pays for the whole window.
SCALEDOWN_SECONDS = int(os.environ.get("HUMANIZER_SCALEDOWN_SECONDS", "60"))
MIN_CONTAINERS = int(os.environ.get("HUMANIZER_MIN_CONTAINERS", "0"))
SPECULATIVE = {"method": "ngram", "num_speculative_tokens": 6, "prompt_lookup_min": 2, "prompt_lookup_max": 5}

serve_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm", "huggingface_hub[hf_transfer]", "fastapi", "httpx")
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            # The slim image has no nvcc, and the FlashInfer sampler JIT-compiles on first use.
            "VLLM_USE_FLASHINFER_SAMPLER": "0",
            # Sleep mode (needed for GPU memory snapshots) lives behind dev mode.
            "VLLM_SERVER_DEV_MODE": "1",
            "TORCHINDUCTOR_COMPILE_THREADS": "1",
            "HUMANIZER_MODEL_VERSION": MODEL_VERSION,
        }
    )
)
merge_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", "transformers", "peft", "accelerate", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "HUMANIZER_MODEL_VERSION": MODEL_VERSION})
)

app = modal.App(APP_NAME)

hf_cache = modal.Volume.from_name("humanizer-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("humanizer-vllm-cache", create_if_missing=True)
adapters = modal.Volume.from_name("humanizer-adapters", create_if_missing=True)


@app.function(
    image=merge_image,
    cpu=8,
    memory=48 * 1024,
    timeout=60 * 60,
    volumes={"/root/.cache/huggingface": hf_cache, "/adapters": adapters},
)
def merge() -> str:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=torch.bfloat16)
    merged = PeftModel.from_pretrained(base, ADAPTER_PATH).merge_and_unload()
    merged.save_pretrained(MERGED_PATH, safe_serialization=True)
    AutoTokenizer.from_pretrained(ADAPTER_PATH).save_pretrained(MERGED_PATH)
    adapters.commit()
    return MERGED_PATH


WARMUP_TEXT = (
    "Remote work has reshaped how organisations measure productivity. Before 2020, most firms "
    "tracked presence in the office as a proxy for effort, but the shift to home working forced "
    "managers to rely on outputs instead (Bloom et al., 2015)."
)


def _local(path: str) -> str:
    return f"http://127.0.0.1:{VLLM_PORT}{path}"


def _wait_ready(proc, timeout: float = 15 * 60) -> None:
    import time

    import requests

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"vLLM exited with code {proc.returncode}")
        try:
            if requests.get(_local("/health"), timeout=5).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise TimeoutError("vLLM did not become ready")


def _warmup() -> None:
    """Compile kernels and capture CUDA graphs before the snapshot, so restores skip it."""
    import requests

    for _ in range(3):
        requests.post(
            _local("/v1/chat/completions"),
            headers={"Authorization": f"Bearer {os.environ['HUMANIZER_API_KEY']}"},
            json={
                "model": SERVED_NAME,
                "messages": [{"role": "user", "content": WARMUP_TEXT}],
                "max_tokens": 128,
                "temperature": 1.0,
                "top_p": 0.9,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=300,
        ).raise_for_status()


def _proxy_app():
    import httpx
    from starlette.applications import Starlette
    from starlette.responses import Response
    from starlette.routing import Route

    client = httpx.AsyncClient(base_url=_local(""), timeout=300)

    async def forward(request):
        headers = {k: v for k, v in request.headers.items() if k.lower() in ("authorization", "content-type")}
        upstream = await client.request(
            request.method, f"/v1/{request.path_params['path']}", content=await request.body(), headers=headers
        )
        return Response(upstream.content, status_code=upstream.status_code, media_type=upstream.headers.get("content-type"))

    return Starlette(routes=[Route("/v1/{path:path}", forward, methods=["GET", "POST"])])


@app.cls(
    image=serve_image,
    gpu=GPU,
    timeout=60 * 60,
    scaledown_window=SCALEDOWN_SECONDS,
    min_containers=MIN_CONTAINERS,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/root/.cache/vllm": vllm_cache,
        "/adapters": adapters,
    },
    secrets=[modal.Secret.from_name("humanizer-api-key")],
    # Restoring CPU+GPU memory skips model load, compilation and CUDA graph capture.
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
@modal.concurrent(max_inputs=64)
class Humanizer:
    @modal.enter(snap=True)
    def start(self) -> None:
        import subprocess

        import requests

        cmd = [
            "vllm", "serve", MERGED_PATH,
            "--served-model-name", SERVED_NAME,
            "--quantization", "fp8",
            "--speculative-config", json.dumps(SPECULATIVE),
            "--max-model-len", "8192",
            "--gpu-memory-utilization", "0.92",
            "--enable-sleep-mode",
            "--api-key", os.environ["HUMANIZER_API_KEY"],
            "--host", "127.0.0.1",
            "--port", str(VLLM_PORT),
        ]
        self.proc = subprocess.Popen(cmd)
        _wait_ready(self.proc)
        _warmup()
        requests.post(_local("/sleep?level=1"), timeout=120).raise_for_status()

    @modal.enter(snap=False)
    def wake(self) -> None:
        import requests

        requests.post(_local("/wake_up"), timeout=120).raise_for_status()
        _wait_ready(self.proc)

    @modal.asgi_app()
    def serve(self):
        return _proxy_app()

    @modal.exit()
    def stop(self) -> None:
        self.proc.terminate()
