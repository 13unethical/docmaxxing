"""Train the student humanizer on Modal: detector-filtered SFT on teacher section pairs.

Data lives on the ``humanizer-sft`` volume as ``/<name>/{train,val,test}.jsonl`` (section_sft
format). Adapters are written to ``humanizer-adapters`` as ``/qwen3_8b_lora_<run>`` so that
``serve_modal.py`` (HUMANIZER_MODEL_VERSION=<run>) can merge and serve them.

    modal volume put humanizer-sft <section_sft dir> /sft_v3
    modal run humanizer_student/train_modal.py::score --name sft_v3
    modal run humanizer_student/train_modal.py::prepare --src sft_v3 --dst sft_v3f --drop-share 0.35
    modal run --detach humanizer_student/train_modal.py::train --data sft_v3f --run v3
"""

from __future__ import annotations

import json
import os

import modal

APP_NAME = "docmaxxing-humanizer-train"
DETECTOR_DIR = "/det/models/prod"
DETECTOR_MAX_LEN = 384

app = modal.App(APP_NAME)
sft = modal.Volume.from_name("humanizer-sft", create_if_missing=True)
adapters = modal.Volume.from_name("humanizer-adapters", create_if_missing=True)
hf_cache = modal.Volume.from_name("humanizer-hf-cache", create_if_missing=True)
detector = modal.Volume.from_name("tt-detector", create_if_missing=True)

score_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", "transformers", "sentencepiece", "protobuf")
    .add_local_python_source("humanizer_student")
)
train_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch>=2.5", "transformers>=5.0", "peft>=0.15", "trl>=1.0", "bitsandbytes>=0.45",
        "accelerate>=1.6", "datasets>=3.5", "huggingface_hub[hf_transfer]",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .add_local_python_source("humanizer_student")
)


def _read(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _write(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


@app.function(image=score_image, gpu="L40S", timeout=4 * 3600, volumes={"/sft": sft, "/det": detector})
def score(name: str) -> dict:
    """Detector AI probability of every assistant target -> /<name>/scores_<split>.jsonl."""
    import torch
    import torch.nn as nn
    from transformers import AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel

    from humanizer_student.filtering import target_text, word_windows

    class Desklib(PreTrainedModel):
        config_class = AutoConfig

        def __init__(self, config):
            super().__init__(config)
            self.model = AutoModel.from_config(config)
            self.classifier = nn.Linear(config.hidden_size, 1)
            self.post_init()

        def forward(self, input_ids, attention_mask):
            hidden = self.model(input_ids, attention_mask=attention_mask)[0]
            mask = attention_mask.unsqueeze(-1).float()
            return self.classifier((hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)).squeeze(-1)

    tok = AutoTokenizer.from_pretrained(DETECTOR_DIR)
    model = Desklib.from_pretrained(DETECTOR_DIR).eval().cuda()
    version = open(f"{DETECTOR_DIR}/VERSION").read().strip()

    @torch.no_grad()
    def probs(texts: list[str]) -> list[float]:
        out: list[float] = []
        for i in range(0, len(texts), 64):
            enc = tok(texts[i : i + 64], truncation=True, max_length=DETECTOR_MAX_LEN, padding=True,
                      return_tensors="pt").to("cuda")
            with torch.autocast("cuda", dtype=torch.bfloat16):
                out.extend(torch.sigmoid(model(enc["input_ids"], enc["attention_mask"]).float()).tolist())
        return out

    sft.reload()
    summary: dict = {"detector": version}
    for split in ("train", "val", "test"):
        path = f"/sft/{name}/{split}.jsonl"
        if not os.path.exists(path):
            continue
        rows = _read(path)
        windows, owners = [], []
        for i, row in enumerate(rows):
            for text, words in word_windows(target_text(row)):
                windows.append(text)
                owners.append((i, words))
        ps = probs(windows)
        acc = [[0.0, 0, 0.0] for _ in rows]
        for (i, words), p in zip(owners, ps):
            acc[i][0] += p * words
            acc[i][1] += words
            acc[i][2] = max(acc[i][2], p)
        out = [{"i": i, "p": round(s / max(1, w), 4), "max": round(m, 4)} for i, (s, w, m) in enumerate(acc)]
        _write(f"/sft/{name}/scores_{split}.jsonl", out)
        summary[split] = {"rows": len(rows), "mean_p": round(sum(o["p"] for o in out) / max(1, len(out)), 4)}
    sft.commit()
    print(json.dumps(summary))
    return summary


@app.function(image=score_image, timeout=1800, volumes={"/sft": sft})
def prepare(src: str, dst: str, drop_share: float = 0.35) -> dict:
    """Copy ``src`` to ``dst`` keeping only the most human-looking train targets per level."""
    import shutil

    from humanizer_student.filtering import select_rows

    sft.reload()
    rows = _read(f"/sft/{src}/train.jsonl")
    scores = [s["p"] for s in sorted(_read(f"/sft/{src}/scores_train.jsonl"), key=lambda s: s["i"])]
    kept, stats = select_rows(rows, scores, drop_share=drop_share)
    _write(f"/sft/{dst}/train.jsonl", kept)
    for split in ("val", "test"):
        shutil.copy(f"/sft/{src}/{split}.jsonl", f"/sft/{dst}/{split}.jsonl")
    report = {"src": src, "drop_share": drop_share, "train_rows": len(rows), "kept": len(kept), "by_level": stats}
    with open(f"/sft/{dst}/prepare_report.json", "w") as fh:
        json.dump(report, fh, indent=2)
    sft.commit()
    print(json.dumps(report))
    return report


@app.function(
    image=train_image,
    gpu="H100",
    timeout=24 * 3600,
    volumes={"/sft": sft, "/adapters": adapters, "/root/.cache/huggingface": hf_cache},
)
def train(data: str, run: str, epochs: float = 2.0, learning_rate: float = 1e-4, limit: int = 0) -> dict:
    import shutil

    from humanizer_student.train import TrainConfig
    from humanizer_student.train import train as run_training

    sft.reload()
    work = f"/tmp/run_{run}"
    cfg = TrainConfig(
        data_dir=f"/sft/{data}",
        output_dir=work,
        epochs=epochs,
        learning_rate=learning_rate,
        load_in_4bit=False,
        batch_size=4,
        grad_accum=4,
        eval_steps=200,
        limit=limit or None,
    )
    summary = run_training(cfg)
    dest = f"/adapters/qwen3_8b_lora_{run}"
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(f"{work}/adapter", dest)
    with open(f"{dest}/train_summary.json", "w") as fh:
        json.dump({**summary, "data": data}, fh, indent=2, default=str)
    adapters.commit()
    hf_cache.commit()
    print(json.dumps({k: summary[k] for k in ("train_loss", "eval")}, default=str))
    return summary
