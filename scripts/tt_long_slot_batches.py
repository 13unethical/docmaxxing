#!/usr/bin/env python3
"""Run Turnitin slot rounds in batches of 4–5 on long (~27–29k) humanized docs.

Hard cap: never spend more than ``--max-slots`` (default 20), leaving the rest
of the PlagDetect balance untouched.

  python3 scripts/tt_long_slot_batches.py --batch-size 5 --max-slots 20 --tag longtt20261116
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _slots_available() -> int:
    sys.path.insert(0, str(ROOT))
    from services.plagdetect_api import PlagDetectAPIClient

    acct = PlagDetectAPIClient.from_env().get_account()
    return int(acct.get("slots_available") or 0)


def _count_long_pending(min_words: int) -> int:
    pending = ROOT / "data" / "humanizer_training" / "source_pool" / "pending"
    n = 0
    for path in pending.glob("src-*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        text = str(row.get("source_text") or "")
        if len(text.split()) >= min_words:
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch-size", type=int, default=5)
    ap.add_argument("--max-slots", type=int, default=20, help="Absolute max slots to spend this campaign")
    ap.add_argument("--leave-slots", type=int, default=10, help="Stop if balance would go below this")
    ap.add_argument("--min-words", type=int, default=25000)
    ap.add_argument("--max-words", type=int, default=29000)
    ap.add_argument("--tag", type=str, default="longtt" + time.strftime("%Y%m%d"))
    ap.add_argument("--timeout-s", type=int, default=180 * 60)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    spent = 0
    batch_i = 0
    while spent < args.max_slots:
        avail = _slots_available()
        room_leave = max(0, avail - args.leave_slots)
        room_cap = args.max_slots - spent
        take = min(args.batch_size, room_leave, room_cap)
        pending_long = _count_long_pending(args.min_words)
        print(
            json.dumps(
                {
                    "batch": batch_i,
                    "slots_available": avail,
                    "spent_so_far": spent,
                    "take": take,
                    "pending_long": pending_long,
                }
            ),
            flush=True,
        )
        if take <= 0:
            print(json.dumps({"stop": "no_room", "avail": avail, "leave": args.leave_slots}))
            break
        if pending_long < take:
            print(json.dumps({"stop": "need_more_sources", "have": pending_long, "need": take}))
            return 2
        if args.dry_run:
            print(json.dumps({"dry_run_would_submit": take}))
            return 0

        tag = f"{args.tag}_b{batch_i}"
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "tt_humanizer_slot_round.py"),
            "--limit",
            str(take),
            "--tag",
            tag,
            "--min-words",
            str(args.min_words),
            "--max-words",
            str(args.max_words),
            "--timeout-s",
            str(args.timeout_s),
        ]
        print(json.dumps({"step": "run", "cmd": cmd}), flush=True)
        rc = subprocess.call(cmd, cwd=str(ROOT))
        if rc != 0:
            print(json.dumps({"batch_failed": batch_i, "rc": rc}))
            return rc
        spent += take
        batch_i += 1
        time.sleep(5)

    print(json.dumps({"done": True, "batches": batch_i, "slots_spent_planned": spent}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
