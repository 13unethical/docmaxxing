#!/usr/bin/env python3
"""Top up the Claude-written source pool used by the nightly teacher collection.

Writes only to ``data/humanizer_training/source_pool``; does not call StealthWriter.
Scheduled via ``docmaxxing-humanizer-source-pool.timer`` a few hours before the
nightly collection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.humanizer_training.teacher.documents.source_pool import (  # noqa: E402
    DEFAULT_POOL_ROOT,
    DEFAULT_POOL_TARGET,
    SourcePool,
    fill_source_pool,
    parse_source_mix,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fill the Claude source pool for teacher collection")
    p.add_argument("--target", type=int, default=DEFAULT_POOL_TARGET, help="Pending documents to keep ready")
    p.add_argument("--max-new", type=int, default=None, help="Cap on documents generated this run")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--model", type=str, default=None, help="Claude model override (ignored with --mix)")
    p.add_argument(
        "--mix",
        type=str,
        default=os.environ.get("HUMANIZER_SOURCE_MIX") or None,
        help='Writer models by weight, e.g. "claude:claude-haiku-4-5:2,gemini:gemini-3.5-flash:3" '
        "(default: $HUMANIZER_SOURCE_MIX, else Claude only)",
    )
    p.add_argument("--root", type=str, default=str(DEFAULT_POOL_ROOT))
    p.add_argument("--status", action="store_true", help="Print pool counts only")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.status:
        pool = SourcePool(args.root)
        failed = len(list(pool.failed_dir.glob("*.json"))) if pool.failed_dir.is_dir() else 0
        print(json.dumps({"pending": pool.pending_count(), "used": pool.used_count(), "failed": failed}, indent=2))
        return 0
    result = fill_source_pool(
        target_pending=args.target,
        max_new=args.max_new,
        seed=args.seed,
        root=Path(args.root),
        workers=args.workers,
        model=args.model,
        mix=parse_source_mix(args.mix) if args.mix else None,
    )
    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    return 0 if result.generated or result.requested == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
