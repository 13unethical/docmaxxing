#!/usr/bin/env python3
"""One-shot migration: ensure every user has an id + referral fields.

Users already use INTEGER PRIMARY KEY ids. This script runs the economy DB
migrations (referral columns, withdrawal_requests, referral_code backfill).

Usage:
  python scripts/migrate_referral_system.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_db_module():
    """Load services.economy.db without importing the economy package __init__."""
    path = ROOT / "services" / "economy" / "db.py"
    spec = importlib.util.spec_from_file_location("economy_db_migrate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    db = _load_db_module()
    print(f"Economy DB: {db.DB_PATH}")
    db.init_db()
    with db.connect() as conn:
        users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        with_code = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE referral_code IS NOT NULL AND referral_code != ''"
        ).fetchone()["n"]
        withdrawals = conn.execute(
            "SELECT COUNT(*) AS n FROM withdrawal_requests"
        ).fetchone()["n"]
    print(f"Users: {users} (with referral_code: {with_code})")
    print(f"Withdrawal requests table OK ({withdrawals} rows)")
    print("Migration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
