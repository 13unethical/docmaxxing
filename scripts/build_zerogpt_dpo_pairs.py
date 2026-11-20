#!/usr/bin/env python3
"""Offline ZeroGPT labels → DPO pairs for the student humanizer (no runtime ZeroGPT).

Input JSONL rows (one candidate per line), same shape the Turnitin DPO path expects::

    {"essay": "...", "source": "<paragraph>", "text": "<candidate>", ...}

For each ``text`` we call ZeroGPT detect once, write ``ai_frac`` (0–1), then reuse
``humanizer_student.dpo.build_pairs`` so chosen/rejected match the Turnitin pipeline.

Usage::

    ZEROGPT_API_KEY=... python scripts/build_zerogpt_dpo_pairs.py \\
        --in candidates.jsonl --out-dir data/zerogpt_dpo/

This never runs in the request path — training data only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from humanizer_student.dpo import build_pairs, split_by_essay  # noqa: E402


def _ai_frac_from_detect(payload: dict) -> float:
    """Normalize ZeroGPT detect payloads to a 0–1 AI fraction."""
    for key in ("ai_percentage", "aiPercentage", "fakePercentage", "ai_prob"):
        if key in payload and payload[key] is not None:
            val = float(payload[key])
            return val / 100.0 if val > 1.0 else val
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for key in ("fakePercentage", "ai_percentage", "aiPercentage"):
        if key in data and data[key] is not None:
            val = float(data[key])
            return val / 100.0 if val > 1.0 else val
    raise ValueError(f"no AI% in ZeroGPT payload keys={sorted(payload.keys())}")


def label_rows(rows: list[dict], *, sleep_s: float = 0.4) -> list[dict]:
    from services.zerogpt_business.client import ZeroGPTClient

    client = ZeroGPTClient()
    out: list[dict] = []
    for i, row in enumerate(rows):
        text = row.get("text") or ""
        if not text.strip():
            continue
        raw = client.detect(text)
        frac = _ai_frac_from_detect(raw if isinstance(raw, dict) else {"ai_percentage": raw})
        labeled = {**row, "ai_frac": frac, "judge": "zerogpt"}
        out.append(labeled)
        if sleep_s > 0 and i + 1 < len(rows):
            time.sleep(sleep_s)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="inp", required=True, help="candidates JSONL")
    p.add_argument("--out-dir", required=True, help="writes pairs_train/val.jsonl + labeled.jsonl")
    p.add_argument("--sleep", type=float, default=0.4, help="seconds between ZeroGPT calls")
    p.add_argument("--max-per-source", type=int, default=4)
    p.add_argument("--skip-label", action="store_true", help="input already has ai_frac")
    args = p.parse_args()

    rows = []
    for line in Path(args.inp).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    labeled = rows if args.skip_label else label_rows(rows, sleep_s=args.sleep)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "labeled.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in labeled), encoding="utf-8"
    )
    pairs = build_pairs(labeled, max_per_source=args.max_per_source)
    train, val = split_by_essay(pairs)
    for name, part in (("pairs_train.jsonl", train), ("pairs_val.jsonl", val)):
        (out_dir / name).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in part), encoding="utf-8"
        )
    summary = {
        "candidates": len(labeled),
        "pairs_train": len(train),
        "pairs_val": len(val),
        "chosen_max_frac": 0.1,
        "rejected_min_frac": 0.5,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
