#!/usr/bin/env python3
"""Export StealthWriter cookies from local Chrome → JSON for VPS upload."""

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
from services.browser.providers.stealthwriter import (  # noqa: E402
    _page,
    get_session_status,
    save_storage_state,
)


def main() -> int:
    BrowserService.instance().start()
    status = get_session_status()
    if not status.get("logged_in"):
        print("Not logged in locally. Run: python3 scripts/bootstrap_stealthwriter_login.py", flush=True)
        return 1
    path = save_storage_state(_page())
    print(f"Saved: {path}", flush=True)
    print(f"Size: {path.stat().st_size} bytes", flush=True)
    print("\nUpload to VPS:", flush=True)
    print(f"  scp {path} root@YOUR_VPS:~/docmaxxing/browser_profiles/", flush=True)
    print("Then on VPS: sudo systemctl restart docmaxxing", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
