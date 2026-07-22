#!/usr/bin/env python3
"""Export StealthWriter Playwright storageState for VPS upload."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

os.environ.setdefault("BROWSER_EXTRA_ARGS", "")

from services.browser.browser_service import BrowserService  # noqa: E402
from services.browser.providers.stealthwriter import get_session_status  # noqa: E402

PROVIDER = "stealthwriter"


def main() -> int:
    svc = BrowserService.instance()
    svc.start()
    status = get_session_status()
    if not status.get("logged_in"):
        print("Not logged in locally. Run: python3 scripts/bootstrap_stealthwriter_login.py", flush=True)
        return 1
    if not svc.save_session(PROVIDER):
        print("Could not save storageState.", flush=True)
        return 1
    path = ROOT / "browser_profiles" / "sessions" / f"{PROVIDER}.json"
    print(f"Saved: {path}", flush=True)
    print(f"Size: {path.stat().st_size} bytes", flush=True)
    print("\nUpload to VPS:", flush=True)
    print(f"  bash scripts/push_stealthwriter_session_to_vps.sh root@YOUR_VPS_IP", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
