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

The site calls ``<url>/v1/chat/completions`` with model ``humanizer-v1`` and
``Authorization: Bearer <HUMANIZER_API_KEY>`` (see services/humanizer_engine/student_humanizer.py).
"""

from __future__ import annotations

import json
import os

import modal

BASE_MODEL = "Qwen/Qwen3-8B"
ADAPTER_PATH = "/adapters/qwen3_8b_lora_v1"
MERGED_PATH = "/adapters/merged/qwen3_8b_humanizer_v1"
SERVED_NAME = "humanizer-v1"
PORT = 8000
GPU = os.environ.get("HUMANIZER_GPU", "L40S")
SCALEDOWN_SECONDS = int(os.environ.get("HUMANIZER_SCALEDOWN_SECONDS", str(15 * 60)))
MIN_CONTAINERS = int(os.environ.get("HUMANIZER_MIN_CONTAINERS", "0"))
SPECULATIVE = {"method": "ngram", "num_speculative_tokens": 6, "prompt_lookup_min": 2, "prompt_lookup_max": 5}

serve_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm", "huggingface_hub[hf_transfer]")
    # The slim image has no nvcc, and the FlashInfer sampler JIT-compiles on first use.
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_USE_FLASHINFER_SAMPLER": "0"})
)
merge_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", "transformers", "peft", "accelerate", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App("docmaxxing-humanizer")

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


@app.function(
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
)
@modal.concurrent(max_inputs=64)
@modal.web_server(port=PORT, startup_timeout=15 * 60)
def serve() -> None:
    import subprocess

    cmd = [
        "vllm", "serve", MERGED_PATH,
        "--served-model-name", SERVED_NAME,
        "--quantization", "fp8",
        "--speculative-config", json.dumps(SPECULATIVE),
        "--max-model-len", "8192",
        "--gpu-memory-utilization", "0.92",
        "--api-key", os.environ["HUMANIZER_API_KEY"],
        "--host", "0.0.0.0",
        "--port", str(PORT),
    ]
    subprocess.Popen(cmd)
