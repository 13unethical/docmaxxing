#!/usr/bin/env python3
"""Attach an existing Turnitin result to a prior eval case (hash fail-closed).

Requires the same original/humanized hashes captured at case creation.
Does not call Turnitin or Chrome. Does not invent AI spans.
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
    attach_turnitin_result,
    text_sha256,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Attach Turnitin report metadata to an eval case")
    p.add_argument("--eval-id", type=str, required=True)
    p.add_argument("--original-text-hash", type=str, default=None)
    p.add_argument("--humanized-text-hash", type=str, default=None)
    p.add_argument("--original-file", type=str, default=None, help="Recompute original hash from file")
    p.add_argument("--humanized-file", type=str, default=None, help="Recompute humanized hash from file")
    p.add_argument("--submission-id", type=str, default=None)
    p.add_argument("--ai-score", type=float, default=None)
    p.add_argument("--similarity", type=float, default=None)
    p.add_argument("--ai-highlights", type=float, default=None)
    p.add_argument("--report-path", type=str, default=None)
    p.add_argument("--ai-report-path", type=str, default=None)
    p.add_argument("--ai-highlights-report-path", type=str, default=None)
    p.add_argument("--similarity-report-path", type=str, default=None)
    p.add_argument("--provider", type=str, default=None)
    p.add_argument("--output-dir", type=str, default=str(DEFAULT_EVAL_ROOT))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        o_hash = args.original_text_hash
        h_hash = args.humanized_text_hash
        if args.original_file:
            o_hash = text_sha256(Path(args.original_file).read_text(encoding="utf-8"))
        if args.humanized_file:
            h_hash = text_sha256(Path(args.humanized_file).read_text(encoding="utf-8"))
        if not o_hash or not h_hash:
            raise TurnitinEvalError(
                "original and humanized hashes are required "
                "(pass --*-text-hash or --*-file)"
            )
        record = attach_turnitin_result(
            args.eval_id,
            original_text_hash=o_hash,
            humanized_text_hash=h_hash,
            turnitin_submission_id=args.submission_id,
            ai_score=args.ai_score,
            similarity=args.similarity,
            report_path=args.report_path,
            ai_report_path=args.ai_report_path,
            ai_highlights_report_path=args.ai_highlights_report_path,
            similarity_report_path=args.similarity_report_path,
            ai_highlights=args.ai_highlights,
            provider=args.provider,
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
                "status": record["status"],
                "turnitin_submission_id": record.get("turnitin_submission_id"),
                "ai_score": record.get("ai_score"),
                "similarity": record.get("similarity"),
                "report_path": record.get("report_path"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
