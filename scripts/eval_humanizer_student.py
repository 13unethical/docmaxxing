#!/usr/bin/env python3
"""Generate student rewrites on a held-out split and compare them with StealthWriter.

Writes ``predictions.jsonl`` (resumable) and ``report.json`` into ``--out``.
``--score-only`` re-scores existing predictions without loading a model.
Run once with ``--no-adapter`` into a separate dir to get the untuned base-model baseline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_student.evaluate import generate_predictions, score_predictions  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-model", default="Qwen/Qwen3-8B")
    p.add_argument("--adapter", default="data/humanizer_training/student_runs/qwen3_8b_lora_v1/adapter")
    p.add_argument("--no-adapter", action="store_true", help="Evaluate the untuned base model")
    p.add_argument("--split", type=Path, default=Path("data/humanizer_training/section_sft/test.jsonl"))
    p.add_argument("--out", type=Path, default=Path("data/humanizer_training/student_runs/qwen3_8b_lora_v1/eval_test"))
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--load-in-4bit", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--score-only", action="store_true")
    args = p.parse_args()

    predictions = args.out / "predictions.jsonl"
    if not args.score_only:
        written = generate_predictions(
            base_model=args.base_model,
            adapter_dir=None if args.no_adapter else args.adapter,
            split_path=args.split,
            out_path=predictions,
            limit=args.limit,
            batch_size=args.batch_size,
            temperature=args.temperature,
            load_in_4bit=args.load_in_4bit,
        )
        print(json.dumps({"generated": written, "predictions": str(predictions)}))
    report = score_predictions(predictions)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
