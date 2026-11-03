"""Serve the AI-text detector (DeBERTa-v3-large fine-tuned on Turnitin highlights) on Modal.

The weights live on the ``tt-detector`` volume. ``/models/prod`` is what the site uses;
``promote`` copies a trained model (e.g. ``final``) there; ai_detector/train_modal.py does
the same weekly when a retrained model passes its checks.

One-time setup (local machine):
    modal secret create ai-detector-api-key AI_DETECTOR_API_KEY=<random key>
    modal run ai_detector/serve_modal.py::promote --name final

Deploy:
    modal deploy ai_detector/serve_modal.py

The site posts ``{"texts": [...]}`` to ``<url>/score`` with ``Authorization: Bearer <key>``
and gets ``{"probs": [...], "model": "<version>"}`` back (see services/ai_detector.py).
"""

from __future__ import annotations

import os

import modal

APP_NAME = os.environ.get("AI_DETECTOR_APP_NAME", "docmaxxing-ai-detector")
# Fallbacks in order: a lone GPU type is sometimes out of capacity for minutes.
GPU = [g for g in os.environ.get("AI_DETECTOR_GPU", "L4,A10G,L40S").split(",") if g]
SCALEDOWN_SECONDS = int(os.environ.get("AI_DETECTOR_SCALEDOWN_SECONDS", "120"))
MIN_CONTAINERS = int(os.environ.get("AI_DETECTOR_MIN_CONTAINERS", "0"))
MODEL_DIR = "/data/models/prod"
MAX_LEN = 384
MAX_TEXTS = 512

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", "transformers", "sentencepiece", "protobuf", "fastapi")
)

app = modal.App(APP_NAME)
data = modal.Volume.from_name("tt-detector", create_if_missing=True)

with image.imports():
    import torch
    import torch.nn as nn
    from transformers import AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel

    class Desklib(PreTrainedModel):
        """desklib/ai-text-detector head: mean-pooled DeBERTa states -> one logit."""

        config_class = AutoConfig

        def __init__(self, config):
            super().__init__(config)
            self.model = AutoModel.from_config(config)
            self.classifier = nn.Linear(config.hidden_size, 1)
            self.post_init()

        def forward(self, input_ids, attention_mask):
            hidden = self.model(input_ids, attention_mask=attention_mask)[0]
            mask = attention_mask.unsqueeze(-1).float()
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            return self.classifier(pooled).squeeze(-1)

    def load_model(path: str):
        """Weights read fully into memory: from_pretrained memory-maps them, and an open file
        on the volume makes every later ``data.reload()`` fail, so promotions never show up."""
        from safetensors.torch import load as load_safetensors

        model = Desklib(AutoConfig.from_pretrained(path))
        with open(f"{path}/model.safetensors", "rb") as fh:
            model.load_state_dict(load_safetensors(fh.read()))
        return AutoTokenizer.from_pretrained(path), model.eval()


@app.function(image=image, volumes={"/data": data}, timeout=600)
def promote(name: str = "final") -> str:
    import shutil
    from datetime import datetime, timezone

    src = f"/data/models/{name}"
    tmp = f"{MODEL_DIR}.new"
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(src, tmp, ignore=shutil.ignore_patterns("*.jsonl"))
    with open(f"{tmp}/VERSION", "w") as fh:
        fh.write(f"{name}-{datetime.now(timezone.utc):%Y%m%d%H%M}")
    shutil.rmtree(MODEL_DIR, ignore_errors=True)
    os.rename(tmp, MODEL_DIR)
    data.commit()
    return open(f"{MODEL_DIR}/VERSION").read()


@app.cls(
    image=image,
    gpu=GPU,
    timeout=10 * 60,
    scaledown_window=SCALEDOWN_SECONDS,
    min_containers=MIN_CONTAINERS,
    volumes={"/data": data},
    secrets=[modal.Secret.from_name("ai-detector-api-key")],
    enable_memory_snapshot=True,
)
@modal.concurrent(max_inputs=16)
class Detector:
    @modal.enter(snap=True)
    def load(self) -> None:
        import threading

        self.tok, self.model = load_model(MODEL_DIR)
        self.version = open(f"{MODEL_DIR}/VERSION").read().strip()
        self.lock = threading.Lock()

    @modal.enter(snap=False)
    def to_gpu(self) -> None:
        # The snapshot holds the weights of its deploy; weekly retraining may have promoted newer ones.
        try:
            data.reload()
            current = open(f"{MODEL_DIR}/VERSION").read().strip()
        except Exception as exc:  # noqa: BLE001
            print(f"detector: volume reload failed, serving snapshot {self.version}: {exc!r}")
            current = self.version
        if current != self.version:
            self.tok, self.model = load_model(MODEL_DIR)
            self.version = current
        self.model = self.model.cuda()
        self.probs(["Warm-up sentence for the detector."])

    def probs(self, texts: list[str]) -> list[float]:
        out: list[float] = []
        with self.lock, torch.no_grad():
            for i in range(0, len(texts), 32):
                enc = self.tok(
                    texts[i : i + 32], truncation=True, max_length=MAX_LEN, padding=True, return_tensors="pt"
                ).to("cuda")
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    logits = self.model(enc["input_ids"], enc["attention_mask"]).float()
                out.extend(torch.sigmoid(logits).tolist())
        return out

    @modal.asgi_app()
    def serve(self):
        from fastapi import FastAPI, Header, HTTPException
        from fastapi.concurrency import run_in_threadpool

        web = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @web.post("/score")
        async def score(body: dict, authorization: str = Header(default="")):
            if authorization != f"Bearer {os.environ['AI_DETECTOR_API_KEY']}":
                raise HTTPException(status_code=401)
            texts = body.get("texts")
            if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
                raise HTTPException(status_code=422, detail="texts must be a list of strings")
            if len(texts) > MAX_TEXTS:
                raise HTTPException(status_code=413, detail=f"at most {MAX_TEXTS} texts")
            return {"probs": await run_in_threadpool(self.probs, texts), "model": self.version}

        return web
