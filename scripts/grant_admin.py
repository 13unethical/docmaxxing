#!/usr/bin/env python3
"""Grant admin to an existing account whose email is already verified (first-admin bootstrap).

Run on the server by the operator; the web app never grants admin from ``ADMIN_EMAIL``.
The account must have signed up and confirmed its email with the OTP first.

Usage:
  python scripts/grant_admin.py owner@example.com
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    from services.economy.admin import AdminError, grant_admin_to_verified_account
    from services.economy.db import init_db

    init_db()
    try:
        granted = grant_admin_to_verified_account(argv[1])
    except AdminError as exc:
        print(f"Not granted: {exc}")
        return 1
    print(f"Admin granted to user {granted['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
