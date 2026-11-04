"""Weekly retraining of the AI-text detector on fresh Turnitin labels (Modal).

Data on the ``tt-detector`` volume:
  /labels_vps.jsonl   windows from stored Turnitin AI reports (uploaded nightly by the VPS,
                      scripts/tt_detector_labels.py --upload); never leaves the server/GPU.
  /tt_labels_ours.jsonl, /batch_*.jsonl   Turnitin labels of our own rewrites.
  /extra_*.jsonl, /ext.jsonl              open human/AI corpora (guards against false positives).
  /chatgpt_*.jsonl, /rawai_*.jsonl        raw ChatGPT / Claude / Gemini documents (AI examples).

Every Monday ``retrain`` trains two models in parallel: one with 20% of the reports held out (to
measure) and one on everything (to serve). The serving model is replaced only when the held-out
numbers are not worse than the ones recorded for the current production model.

One-time setup (local machine):
    modal secret create tt-upload UPLOAD_TOKEN=<random token>
    modal deploy ai_detector/train_modal.py
Manual run:
    modal run ai_detector/train_modal.py::retrain
"""

from __future__ import annotations

import json
import os

import modal

APP_NAME = os.environ.get("AI_DETECTOR_TRAIN_APP_NAME", "docmaxxing-ai-detector-train")
BASE = "desklib/ai-text-detector-v1.01"
MAX_LEN = 384
EPOCHS = 2
LR = 1e-5
HOLDOUT = 0.2
EXT_MAX = int(os.environ.get("AI_DETECTOR_EXT_MAX", "100000"))
# Open-corpus AI text makes the model call any formal prose AI; a small sample keeps recall on raw
# chatbot output while Turnitin labels stay the main AI signal.
EXT_AI_MAX = int(os.environ.get("AI_DETECTOR_EXT_AI_MAX", "1500"))
# Same as AI_DETECTOR_THRESHOLD on the site (services/ai_detector.py).
FLAG_THRESHOLD = 0.5
# Human corpora closest to what students paste; their mean false-positive rate gates promotion.
GATED_HUMAN = ("essays_human", "arxiv_human", "daigt_human", "hc3_human", "wiki_human", "raid_human")
# Promotion gate: held-out Turnitin AUC and per-report correlation with Turnitin's % may not drop,
# human false positives may not rise, by more than these, and all must stay within the absolute limits.
MAX_AUC_DROP = 0.01
MAX_FP_RISE = 0.01
MIN_AUC = 0.85
MAX_HUMAN_FP = 0.04
MIN_TT_CORR = 0.8
MAX_CORR_DROP = 0.03
# Raw ChatGPT documents (/data/chatgpt_*.jsonl, scripts/gen_chatgpt_corpus.py): windows used for
# training, and the share of held-out documents shown as AI may not drop by more than this.
CHATGPT_MAX = int(os.environ.get("AI_DETECTOR_CHATGPT_MAX", "4000"))
CHATGPT_GROUP = "openai_chatgpt"
MAX_CHATGPT_RECALL_DROP = 0.02
# Raw Claude/Gemini documents (/data/rawai_*.jsonl): same use, own cap so they don't crowd out ChatGPT.
RAWAI_MAX = int(os.environ.get("AI_DETECTOR_RAWAI_MAX", "3000"))
# Turnitin labels of humanized text (/tt_labels_ours.jsonl, /batch_*.jsonl) are ~5% of the windows
# but the only examples of what humanizers leave behind; each is repeated this many times.
OURS_REPEAT = 1
# Turnitin labels of the golden set (/data/eval_golden*.jsonl): humanized text, evaluation only.
GOLDEN_GLOB = "eval_golden"
# Held-out models per retrain (training seeds 0..N-1, same held-out reports); the gate uses their mean.
HOLDOUT_SEEDS = 3
PROD_DIR = "/data/models/prod"

app = modal.App(APP_NAME)
data = modal.Volume.from_name("tt-detector", create_if_missing=True)
hf_cache = modal.Volume.from_name("humanizer-hf-cache", create_if_missing=True)

web_image = modal.Image.debian_slim(python_version="3.12").pip_install("fastapi[standard]")
gpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch", "transformers", "accelerate", "sentencepiece", "protobuf", "scikit-learn", "numpy",
        "huggingface_hub[hf_transfer]",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

with web_image.imports():
    from fastapi import HTTPException, Request


@app.function(image=web_image, volumes={"/data": data}, secrets=[modal.Secret.from_name("tt-upload")])
@modal.fastapi_endpoint(method="POST")
async def upload(request: Request):
    """Replace /labels_vps.jsonl with the full label set sent by the VPS."""
    import hmac

    if not hmac.compare_digest(request.headers.get("x-token", ""), os.environ["UPLOAD_TOKEN"]):
        raise HTTPException(status_code=403)
    body = await request.body()
    rows = 0
    reports = set()
    for line in body.decode().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row.get("text"), str) or "ai_frac" not in row or "report" not in row:
            raise HTTPException(status_code=422, detail=f"bad row {rows + 1}")
        rows += 1
        reports.add(row["report"])
    if rows == 0:
        raise HTTPException(status_code=422, detail="empty upload")
    tmp = "/data/labels_vps.jsonl.new"
    with open(tmp, "wb") as fh:
        fh.write(body)
    os.replace(tmp, "/data/labels_vps.jsonl")
    data.commit()
    return {"rows": rows, "reports": len(reports)}


def _read(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _auc(y, s):
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(y, s)) if len(set(y)) == 2 else None


def _within_doc_auc(rows, scores, key):
    groups: dict = {}
    for r, s in zip(rows, scores):
        groups.setdefault(r[key], []).append((r["ai"], s))
    aucs = [_auc([a for a, _ in g], [s for _, s in g]) for g in groups.values()]
    aucs = [a for a in aucs if a is not None]
    return sum(aucs) / len(aucs) if aucs else None


def _group(r) -> str:
    src = r["source"]
    if src.startswith("raid_"):
        return ("raid_ai_" + src.rsplit("_", 1)[1]) if r["ai"] else "raid_human"
    return src if src.endswith(("_human", "_ai", "_chatgpt")) else f"{src}_{'ai' if r['ai'] else 'human'}"


def _doc_rates(rows, scores, t: float = FLAG_THRESHOLD) -> dict:
    """Per corpus group: share of documents that would show as AI (>=20% of their windows above t)."""
    docs: dict = {}
    for r, p in zip(rows, scores):
        docs.setdefault((_group(r), r.get("doc", r["text"][:40])), []).append(p)
    groups: dict = {}
    for (g, _), ps in docs.items():
        n, k = groups.get(g, (0, 0))
        groups[g] = (n + 1, k + (sum(p > t for p in ps) / len(ps) >= 0.2))
    return {g: round(k / n, 4) for g, (n, k) in sorted(groups.items())}


@app.function(image=gpu_image, gpu="L40S", timeout=4 * 3600,
              volumes={"/data": data, "/root/.cache/huggingface": hf_cache})
def fit(final: bool, name: str, seed: int = 0, epochs: int = EPOCHS, ext_max: int = EXT_MAX,
        batches: str = "", train_seed: int = -1, ours_repeat: int = OURS_REPEAT) -> dict:
    """``batches``: comma list of batch_<name>.jsonl to use ("none" = no batches, "" = all).
    ``train_seed``: shuffling/initialisation seed (default ``seed``); the held-out split always follows ``seed``."""
    import random

    import torch
    import torch.nn as nn
    from transformers import AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel, get_linear_schedule_with_warmup

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
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            return self.classifier(pooled).squeeze(-1)

    data.reload()
    rng = random.Random(seed)
    vps = _read("/data/labels_vps.jsonl")
    reports = sorted({r["report"] for r in vps})
    rng.shuffle(reports)
    held = set() if final else set(reports[: int(len(reports) * HOLDOUT)])
    train_rows = [r for r in vps if r["report"] not in held]
    vps_test = [r for r in vps if r["report"] in held]
    if train_seed >= 0:
        rng = random.Random(train_seed)
    ours = _read("/data/tt_labels_ours.jsonl")
    allowed = None if not batches else {b.strip() for b in batches.split(",") if b.strip() and b.strip() != "none"}
    for fname in sorted(os.listdir("/data")):
        if fname.startswith("batch_") and fname.endswith(".jsonl"):
            if allowed is None or fname[len("batch_"):-len(".jsonl")] in allowed:
                ours += _read(f"/data/{fname}")
    train_rows += ours * max(1, ours_repeat)
    train_rows += [r for r in _read("/data/extra_train.jsonl") if not r["ai"]]
    ext = _read("/data/ext.jsonl")
    ext_train = [r for r in ext if r["split"] == "train" and not r["ai"]]
    ext_ai = [r for r in ext if r["split"] == "train" and r["ai"]]
    ext_train += rng.sample(ext_ai, min(EXT_AI_MAX, len(ext_ai)))
    train_rows += rng.sample(ext_train, min(ext_max, len(ext_train)))
    corpus_test = _read("/data/extra_test.jsonl") + [r for r in ext if r["split"] == "test"]
    chat = []
    for fname in sorted(os.listdir("/data")):
        if fname.startswith("chatgpt_") and fname.endswith(".jsonl"):
            chat += _read(f"/data/{fname}")
    chat_train = [r for r in chat if r.get("split") != "test"]
    train_rows += rng.sample(chat_train, min(CHATGPT_MAX, len(chat_train)))
    corpus_test += [r for r in chat if r.get("split") == "test"]
    rawai = []
    for fname in sorted(os.listdir("/data")):
        if fname.startswith("rawai_") and fname.endswith(".jsonl"):
            rawai += _read(f"/data/{fname}")
    rawai_train = [r for r in rawai if r.get("split") != "test"]
    train_rows += rng.sample(rawai_train, min(RAWAI_MAX, len(rawai_train)))
    corpus_test += [r for r in rawai if r.get("split") == "test"]
    print(f"{name}: train {len(train_rows)} windows, held-out {len(vps_test)} windows from {len(held)} reports")

    tok = AutoTokenizer.from_pretrained(BASE)
    model = Desklib.from_pretrained(BASE).cuda()

    @torch.no_grad()
    def predict(texts, bs=32):
        model.eval()
        out = []
        for i in range(0, len(texts), bs):
            enc = tok(texts[i : i + bs], truncation=True, max_length=MAX_LEN, padding=True, return_tensors="pt").to("cuda")
            with torch.autocast("cuda", dtype=torch.bfloat16):
                out.extend(torch.sigmoid(model(enc["input_ids"], enc["attention_mask"]).float()).tolist())
        return out

    torch.manual_seed(train_seed if train_seed >= 0 else seed)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    bs = 16
    steps = epochs * ((len(train_rows) + bs - 1) // bs)
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)
    # Unweighted: up-weighting the AI class raised false positives on human text.
    loss_fn = nn.BCEWithLogitsLoss()
    for epoch in range(epochs):
        model.train()
        order = list(range(len(train_rows)))
        rng.shuffle(order)
        total = 0.0
        for i in range(0, len(order), bs):
            batch = [train_rows[j] for j in order[i : i + bs]]
            enc = tok([r["text"] for r in batch], truncation=True, max_length=MAX_LEN, padding=True, return_tensors="pt").to("cuda")
            target = torch.tensor([float(r["ai_frac"]) for r in batch], device="cuda")
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(enc["input_ids"], enc["attention_mask"]).float()
            loss = loss_fn(logits, target)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            total += loss.item() * len(batch)
        print(f"{name}: epoch {epoch + 1} loss {total / len(train_rows):.4f}")

    metrics: dict = {"name": name, "reports": len(reports), "train_windows": len(train_rows)}
    if vps_test:
        s = predict([r["text"] for r in vps_test])
        metrics["vps_auc"] = _auc([r["ai"] for r in vps_test], s)
        metrics["vps_within_doc_auc"] = _within_doc_auc(vps_test, s, "report")
        metrics["tt_doc_corr"] = _turnitin_doc_corr(vps_test, s)
    if corpus_test:
        rates = _doc_rates(corpus_test, predict([r["text"] for r in corpus_test]))
        metrics["corpus"] = rates
        human = [rates[g] for g in GATED_HUMAN if g in rates]
        metrics["human_fp"] = round(sum(human) / len(human), 4) if human else None
        metrics["chatgpt_recall"] = rates.get(CHATGPT_GROUP)
    golden = [r for f in sorted(os.listdir("/data")) if f.startswith(GOLDEN_GLOB) and f.endswith(".jsonl")
              for r in _read(f"/data/{f}")]
    if golden:
        s = predict([r["text"] for r in golden])
        flagged = [p for r, p in zip(golden, s) if r["ai"]]
        clean = [p for r, p in zip(golden, s) if not r["ai"]]
        metrics["golden_auc"] = _auc([r["ai"] for r in golden], s)
        metrics["golden_recall"] = sum(p > FLAG_THRESHOLD for p in flagged) / max(1, len(flagged))
        metrics["golden_fp"] = sum(p > FLAG_THRESHOLD for p in clean) / max(1, len(clean))
    print(json.dumps(metrics))
    if not final:
        return metrics
    model.save_pretrained(f"/data/models/{name}")
    tok.save_pretrained(f"/data/models/{name}")
    with open(f"/data/models/{name}/METRICS.json", "w") as fh:
        json.dump(metrics, fh)
    data.commit()
    return metrics


def _turnitin_doc_corr(rows, scores, t: float = FLAG_THRESHOLD):
    """Correlation of our per-report AI % (word share of windows above t) with Turnitin's number."""
    import numpy as np

    reports: dict = {}
    for r, p in zip(rows, scores):
        words = len(r["text"].split())
        item = reports.setdefault(r["report"], [str(r["doc_score"]), 0, 0])
        item[1] += words * (p > t)
        item[2] += words
    pairs = [(100 * f / max(w, 1), float(tt)) for tt, f, w in reports.values() if tt.replace(".", "").isdigit()]
    return float(np.corrcoef(*zip(*pairs))[0, 1]) if len(pairs) > 2 else None


def average_metrics(runs: list[dict], name: str) -> dict:
    """Mean of numeric held-out metrics over runs that differ only in training seed."""
    out: dict = {"name": name, "seeds": len(runs), "runs": runs}
    keys = {k for r in runs for k, v in r.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    for k in sorted(keys):
        vals = [r[k] for r in runs if isinstance(r.get(k), (int, float))]
        out[k] = sum(vals) / len(vals) if vals else None
    corpora = {g for r in runs for g in (r.get("corpus") or {})}
    out["corpus"] = {
        g: round(sum(r["corpus"][g] for r in runs if g in (r.get("corpus") or {}))
                 / sum(1 for r in runs if g in (r.get("corpus") or {})), 4)
        for g in sorted(corpora)
    }
    return out


def gate(new: dict, prod: dict | None) -> tuple[bool, str]:
    """Whether held-out metrics of a candidate are good enough to replace production.

    Relative limits apply only against production metrics averaged over as many training seeds:
    one run swings by several points on ~24 held-out reports.
    """
    if prod and int(prod.get("seeds") or 1) < int(new.get("seeds") or 1):
        prod = None
    auc, fp, corr = new.get("vps_auc"), new.get("human_fp"), new.get("tt_doc_corr")
    if auc is None or fp is None or corr is None:
        return False, "missing held-out metrics"
    if auc < MIN_AUC:
        return False, f"vps_auc {auc:.3f} < {MIN_AUC}"
    if fp > MAX_HUMAN_FP:
        return False, f"human_fp {fp:.3f} > {MAX_HUMAN_FP}"
    if corr < MIN_TT_CORR:
        return False, f"tt_doc_corr {corr:.3f} < {MIN_TT_CORR}"
    if prod and prod.get("tt_doc_corr") is not None and corr < prod["tt_doc_corr"] - MAX_CORR_DROP:
        return False, f"tt_doc_corr {corr:.3f} vs prod {prod['tt_doc_corr']:.3f}"
    if prod and prod.get("vps_auc") is not None and auc < prod["vps_auc"] - MAX_AUC_DROP:
        return False, f"vps_auc {auc:.3f} vs prod {prod['vps_auc']:.3f}"
    if prod and prod.get("human_fp") is not None and fp > prod["human_fp"] + MAX_FP_RISE:
        return False, f"human_fp {fp:.3f} vs prod {prod['human_fp']:.3f}"
    recall, prod_recall = new.get("chatgpt_recall"), (prod or {}).get("chatgpt_recall")
    if recall is not None and prod_recall is not None and recall < prod_recall - MAX_CHATGPT_RECALL_DROP:
        return False, f"chatgpt_recall {recall:.3f} vs prod {prod_recall:.3f}"
    return True, "ok"


@app.function(image=gpu_image, volumes={"/data": data}, timeout=600)
def promote(name: str, holdout_metrics: dict) -> str:
    """Copy /models/<name> to /models/prod with VERSION and the held-out metrics it was judged by."""
    import shutil
    from datetime import datetime, timezone

    data.reload()
    tmp = f"{PROD_DIR}.new"
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(f"/data/models/{name}", tmp, ignore=shutil.ignore_patterns("*.jsonl"))
    version = f"{name}-{datetime.now(timezone.utc):%Y%m%d%H%M}"
    with open(f"{tmp}/VERSION", "w") as fh:
        fh.write(version)
    with open(f"{tmp}/METRICS.json", "w") as fh:
        json.dump(holdout_metrics, fh)
    old = f"{PROD_DIR}.old"
    shutil.rmtree(old, ignore_errors=True)
    if os.path.exists(PROD_DIR):
        os.rename(PROD_DIR, old)
    os.rename(tmp, PROD_DIR)
    data.commit()
    return version


@app.function(image=gpu_image, volumes={"/data": data}, timeout=6 * 3600, schedule=modal.Cron("0 22 * * 0"))
def retrain(force: bool = False, promote_model: bool = True, ours_repeat: int = OURS_REPEAT, tag: str = "") -> dict:
    """Weekly (Monday 03:00 Tashkent): train held-out + full models, promote the full one if the gate passes.

    ``promote_model=False``: train and judge only; promote later with ``promote`` if wanted."""
    from datetime import datetime, timezone

    stamp = f"{datetime.now(timezone.utc):%Y%m%d}{tag}"
    holdout_calls = [
        fit.spawn(final=False, name=f"auto_holdout_{stamp}_s{s}", train_seed=s, ours_repeat=ours_repeat)
        for s in range(HOLDOUT_SEEDS)
    ]
    final_call = fit.spawn(final=True, name=f"auto_{stamp}", ours_repeat=ours_repeat)
    holdout = average_metrics([c.get() for c in holdout_calls], name=f"auto_holdout_{stamp}")
    final = final_call.get()
    data.reload()
    prod = None
    if os.path.exists(f"{PROD_DIR}/METRICS.json"):
        with open(f"{PROD_DIR}/METRICS.json") as fh:
            prod = json.load(fh)
    ok, reason = gate(holdout, prod)
    report = {"at": stamp, "holdout": holdout, "final": final.get("name"), "prod_before": prod,
              "promoted": False, "reason": reason}
    if promote_model and (ok or force):
        report["promoted"] = promote.local(final["name"], holdout)
    import shutil

    for old in sorted(d for d in os.listdir("/data/models") if d.startswith("auto_"))[:-2]:
        shutil.rmtree(f"/data/models/{old}", ignore_errors=True)
    with open("/data/retrain_log.jsonl", "a") as fh:
        fh.write(json.dumps(report) + "\n")
    data.commit()
    print(json.dumps(report))
    return report
