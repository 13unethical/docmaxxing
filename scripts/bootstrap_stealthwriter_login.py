#!/usr/bin/env python3
"""One-time StealthWriter login with a visible Chrome window.

After login, exports Playwright storageState via BrowserService/SessionStore.
Upload browser_profiles/sessions/stealthwriter.json to the VPS.
"""

from __future__ import annotations

import os
import sys
import time
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
from services.browser.providers.stealthwriter import (  # noqa: E402
    get_session_status,
    start_interactive_login,
)

PROVIDER = "stealthwriter"


def main() -> int:
    print("Starting Chrome for StealthWriter login…", flush=True)
    svc = BrowserService.instance()
    svc.start()
    print(f"Profile: {svc.user_data_dir.resolve()}", flush=True)
    print(f"CDP: {svc.cdp_url}", flush=True)

    result = start_interactive_login()
    print(result.get("message") or result, flush=True)

    if _save_and_report(svc):
        return 0

    print(
        "\nIf a Chrome window opened, finish sign-in there (email/password + Cloudflare).",
        flush=True,
    )
    print("Waiting up to 5 minutes…", flush=True)

    deadline = time.time() + 300
    while time.time() < deadline:
        time.sleep(3)
        status = get_session_status()
        if status.get("logged_in"):
            if _save_and_report(svc):
                return 0

    print("\nStill not logged in.", flush=True)
    return 1


def _save_and_report(svc: BrowserService) -> bool:
    status = get_session_status()
    if not status.get("logged_in"):
        return False
    if not svc.save_session(PROVIDER):
        print("Logged in but could not export storageState.", flush=True)
        return False
    path = ROOT / "browser_profiles" / "sessions" / f"{PROVIDER}.json"
    print(f"\nOK — session saved to {path} ({path.stat().st_size} bytes)", flush=True)
    print(
        "\nUpload to VPS:\n"
        f"  bash scripts/push_stealthwriter_session_to_vps.sh root@YOUR_VPS_IP\n"
        "Then on VPS:\n"
        "  sudo systemctl restart docmaxxing\n"
        "  curl -sS http://127.0.0.1:8000/api/browser/providers/stealthwriter/status\n",
        flush=True,
    )
    return True


if __name__ == "__main__":
    raise SystemExit(main())
