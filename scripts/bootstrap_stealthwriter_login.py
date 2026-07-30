#!/usr/bin/env python3
"""One-time StealthWriter login with a visible Chrome window.

After login, exports Playwright storageState via BrowserService/SessionStore.
Upload browser_profiles/sessions/stealthwriter.json to the VPS.

IMPORTANT: while you type email/password + Cloudflare, this script must NOT
navigate the tab. Older versions polled with page.goto(dashboard) every few
seconds and constantly refreshed the sign-in page.
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
    PROVIDER_NAME,
    _is_sign_in_url,
    _page,
    start_interactive_login,
)

PROVIDER = "stealthwriter"


def _peek_logged_in() -> bool:
    """Read current tab URL only — never navigate (so login form stays put)."""
    try:
        page = _page()
        url = (page.url or "").strip()
    except Exception:  # noqa: BLE001
        return False
    if not url or _is_sign_in_url(url):
        return False
    return "/dashboard" in url.lower()


def main() -> int:
    print("Starting Chrome for StealthWriter login…", flush=True)
    svc = BrowserService.instance()
    svc.start()
    print(f"Profile: {svc.user_data_dir.resolve()}", flush=True)
    print(f"CDP: {svc.cdp_url}", flush=True)

    result = start_interactive_login()
    print(result.get("message") or result, flush=True)

    if _peek_logged_in():
        if _save_and_report(svc):
            return 0

    print(
        "\nChrome is open on the StealthWriter sign-in page.",
        flush=True,
    )
    print(
        "Finish login there (email/password + Cloudflare checkbox).",
        flush=True,
    )
    print(
        "This script will wait quietly — it will NOT refresh the page.",
        flush=True,
    )
    print(
        "When you land on /dashboard, it auto-saves the session.",
        flush=True,
    )
    print("Waiting up to 10 minutes…\n", flush=True)

    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(2)
        if _peek_logged_in():
            # Give the SPA a moment to settle cookies, then export.
            time.sleep(1.5)
            if _save_and_report(svc):
                return 0

    print("\nStill not logged in (timed out).", flush=True)
    print("Tip: after you reach the dashboard, run:", flush=True)
    print("  python3 scripts/export_stealthwriter_session.py", flush=True)
    return 1


def _save_and_report(svc: BrowserService) -> bool:
    if not _peek_logged_in():
        return False
    if not svc.save_session(PROVIDER):
        if not svc.save_session(PROVIDER_NAME):
            print("Logged in but could not export storageState.", flush=True)
            return False
    path = ROOT / "browser_profiles" / "sessions" / f"{PROVIDER}.json"
    if not path.is_file():
        print("Logged in but session file missing.", flush=True)
        return False
    print(f"\nOK — session saved to {path} ({path.stat().st_size} bytes)", flush=True)
    print(
        "\nUpload to VPS:\n"
        f"  bash scripts/push_stealthwriter_session_to_vps.sh root@76.13.248.62\n"
        "Then on VPS:\n"
        "  sudo systemctl restart docmaxxing\n"
        "  curl -sS http://127.0.0.1:8000/api/browser/providers/stealthwriter/status\n",
        flush=True,
    )
    return True


if __name__ == "__main__":
    raise SystemExit(main())
