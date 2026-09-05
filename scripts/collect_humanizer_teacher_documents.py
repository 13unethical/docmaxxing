#!/usr/bin/env python3
"""Collect offline document-level teacher pairs (dry-run safe; no production imports).

Large unattended runs:
  python scripts/collect_humanizer_teacher_documents.py \\
    --count 500 --seed 500 --resume \\
    --output-dir data/humanizer_training/teacher_raw_documents/collection_500 \\
    --max-attempts-per-document 2

Does NOT build the SFT dataset. Raw teacher archive + telemetry only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.humanizer_training.teacher.documents import (
    DocumentCollectorConfig,
    TeacherDocumentCollector,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect offline document-level teacher rewrite pairs (raw archive only)"
    )
    parser.add_argument("--count", type=int, default=10, help="Number of synthetic documents")
    parser.add_argument("--seed", type=int, default=300, help="Deterministic generation seed")
    parser.add_argument(
        "--output-dir",
        "--output",
        dest="output_dir",
        type=str,
        default="data/humanizer_training/teacher_raw_documents",
        help="Output directory for documents.jsonl, checkpoint, failures, summary",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted run in --output-dir (required if state already exists)",
    )
    parser.add_argument("--provider", type=str, default="stealthwriter", help="Teacher provider name")
    parser.add_argument("--model", type=str, default="Legacy 5.1", help="Teacher model")
    parser.add_argument("--level", type=int, default=8, help="StealthWriter rewrite level")
    parser.add_argument("--timeout", type=float, default=150.0, help="Provider timeout seconds")
    parser.add_argument(
        "--max-attempts-per-document",
        type=int,
        default=2,
        help="Collector attempt budget per document (capped at 2; provider internal retries=1)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=None,
        help="Deprecated alias for --max-attempts-per-document",
    )
    parser.add_argument("--delay", type=float, default=0.0, help="Delay between successful documents")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate documents and stats only; do not call StealthWriter",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    attempts = args.max_attempts_per_document
    if args.retries is not None:
        attempts = args.retries
    attempts = max(1, min(2, int(attempts)))

    cfg = DocumentCollectorConfig(
        count=max(1, int(args.count)),
        seed=int(args.seed),
        output_dir=str(Path(args.output_dir).resolve()),
        dry_run=bool(args.dry_run),
        resume=bool(args.resume),
        delay_s=max(0.0, float(args.delay)),
        max_provider_words=5000,
        provider_name=str(args.provider),
        model=str(args.model),
        level=int(args.level),
        timeout_s=float(args.timeout),
        max_attempts_per_document=attempts,
        max_retries=attempts,
    )
    result = TeacherDocumentCollector(cfg).run()
    print(
        json.dumps(
            {
                "sampling_plan": result.sampling_plan,
                "summary": result.summary,
                "manifest": result.manifest,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
