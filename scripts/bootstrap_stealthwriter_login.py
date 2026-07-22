#!/usr/bin/env python3
"""One-time StealthWriter login with a visible Chrome window.

StealthWriter uses Cloudflare Turnstile on sign-in. Headless VPS auto-login
often fails even with correct STEALTHWRITER_EMAIL/PASSWORD.

Run this on your Mac (with a screen), log in manually in the Chrome window,
then copy the browser profile to the VPS:

  rsync -avz browser_profiles/chrome_user_data/ \\
    root@YOUR_VPS:~/docmaxxing/browser_profiles/chrome_user_data/

Then on VPS: sudo systemctl restart docmaxxing
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

# Headed Chrome — do not force headless on Linux if DISPLAY is set.
os.environ.setdefault("BROWSER_EXTRA_ARGS", "")

from services.browser.browser_service import BrowserService  # noqa: E402
from services.browser.providers.stealthwriter import (  # noqa: E402
    get_session_status,
    start_interactive_login,
)


def main() -> int:
    print("Starting Chrome for StealthWriter login…", flush=True)
    BrowserService.instance().start()
    print(f"Profile: {BrowserService.instance().user_data_dir.resolve()}", flush=True)
    print(f"CDP: {BrowserService.instance().cdp_url}", flush=True)

    result = start_interactive_login()
    print(result.get("message") or result, flush=True)

    if result.get("logged_in"):
        print("\nOK — StealthWriter session is logged in.", flush=True)
        _print_rsync_hint()
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
            print(f"\nOK — logged in ({status.get('username') or 'dashboard ready'}).", flush=True)
            _print_rsync_hint()
            return 0

    print("\nStill not logged in. Check credentials or complete Turnstile in Chrome.", flush=True)
    return 1


def _print_rsync_hint() -> None:
    profile = BrowserService.instance().user_data_dir.resolve()
    print(
        "\nCopy this profile to the VPS (replace YOUR_VPS):\n"
        f"  rsync -avz {profile}/ root@YOUR_VPS:~/docmaxxing/browser_profiles/chrome_user_data/\n"
        "Then on VPS:\n"
        "  sudo systemctl restart docmaxxing\n"
        "  curl -sS http://127.0.0.1:8000/api/browser/providers/stealthwriter/status\n",
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
