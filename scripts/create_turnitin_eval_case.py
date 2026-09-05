#!/usr/bin/env python3
"""Create an isolated Turnitin evaluation case BEFORE submission.

Stores original/humanized texts + deterministic hashes under
data/humanizer_training/turnitin_eval/cases/<eval_id>.json

Does not call Turnitin, Chrome, or production Humanizer APIs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.humanizer_training.turnitin_eval import (  # noqa: E402
    DEFAULT_EVAL_ROOT,
    TurnitinEvalError,
    create_eval_case,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create Turnitin eval case (pre-submission)")
    p.add_argument("--original-file", type=str, help="Path to original_text file")
    p.add_argument("--humanized-file", type=str, help="Path to humanized_text file")
    p.add_argument("--original-text", type=str, default=None)
    p.add_argument("--humanized-text", type=str, default=None)
    p.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_EVAL_ROOT),
        help="Eval root directory",
    )
    return p.parse_args()


def _load_text(*, file_path: str | None, inline: str | None, label: str) -> str:
    if inline is not None:
        return inline
    if file_path:
        return Path(file_path).read_text(encoding="utf-8")
    raise SystemExit(f"Missing {label}: pass --{label.replace('_', '-')}-file or --{label.replace('_', '-')}-text")


def main() -> int:
    args = parse_args()
    try:
        original = _load_text(
            file_path=args.original_file, inline=args.original_text, label="original_text"
        )
        humanized = _load_text(
            file_path=args.humanized_file, inline=args.humanized_text, label="humanized_text"
        )
        record = create_eval_case(
            original_text=original,
            humanized_text=humanized,
            root=Path(args.output_dir),
        )
    except TurnitinEvalError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "eval_id": record["eval_id"],
                "original_text_hash": record["original_text_hash"],
                "humanized_text_hash": record["humanized_text_hash"],
                "status": record["status"],
                "case_path": str(
                    Path(args.output_dir) / "cases" / f"{record['eval_id']}.json"
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
