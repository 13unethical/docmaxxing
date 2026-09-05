#!/usr/bin/env python3
"""Synthetic daily Humanizer training backfill (isolated teacher path).

Uses the shared site-wide daily Humanizer allowance
(``site_settings.humanizer_daily_limit`` / ``daily_stats.humanizer_requests_count``,
Asia/Tashkent).

Default: dry-run only shows budget + intended document count.
Live collection: ``--execute`` (used by systemd timer
``docmaxxing-humanizer-training-daily.timer``). Idempotent per Tashkent day.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.humanizer_training.synthetic_daily import (  # noqa: E402
    DEFAULT_MINUTES_BEFORE_RESET,
    DEFAULT_SYNTHETIC_ROOT,
    run_daily_backfill,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily synthetic Humanizer training backfill")
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show budget/plan only (default)",
    )
    p.add_argument(
        "--execute",
        action="store_true",
        help="Actually run teacher collection (disables dry-run)",
    )
    p.add_argument(
        "--minutes-before-reset",
        type=float,
        default=DEFAULT_MINUTES_BEFORE_RESET,
        help="Only run when within this many minutes of Tashkent 05:00 reset",
    )
    p.add_argument("--max-documents", type=int, default=None)
    p.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (Tashkent day)")
    p.add_argument(
        "--force-window",
        action="store_true",
        help="Ignore the minutes-before-reset gate (still respects remaining budget)",
    )
    p.add_argument(
        "--output-root",
        type=str,
        default=str(DEFAULT_SYNTHETIC_ROOT),
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    dry_run = not bool(args.execute)
    result = run_daily_backfill(
        dry_run=dry_run,
        minutes_before_reset=float(args.minutes_before_reset),
        max_documents=args.max_documents,
        date=args.date,
        force_window=bool(args.force_window),
        output_root=Path(args.output_root),
        execute_collector=not dry_run,
    )
    payload = result.as_dict()
    # Friendly dry-run summary fields at top level
    budget = result.plan.budget
    print(
        json.dumps(
            {
                "dry_run": result.plan.dry_run,
                "daily_limit": budget.daily_limit,
                "used": budget.used_today,
                "remaining": budget.remaining,
                "reset_at": budget.reset_at,
                "minutes_until_reset": budget.minutes_until_reset,
                "within_window": result.plan.within_window,
                "documents_that_would_be_attempted": result.plan.documents_to_attempt,
                "reason": result.plan.reason,
                "output_dir": str(result.plan.output_dir),
                "full": payload,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
