#!/usr/bin/env python3
"""login_stealthwriter_training.py — Manual login helper for the training Chrome.

Steps
-----
1. Starts an isolated Chrome process (port 9333, separate user-data-dir).
2. Navigates to the StealthWriter sign-in page.
3. Waits for YOU to complete login / Turnstile manually.
4. Once you press Enter here, checks /dashboard and saves the session.
5. Exits — leaves Chrome running only while needed, then shuts it down.

ISOLATION GUARANTEES
--------------------
* Uses TRAINING_CDP_PORT (default 9333) — never touches production port 9222.
* Writes session to browser_profiles/training_sessions/stealthwriter.json.
* Never writes to browser_profiles/sessions/stealthwriter.json.
* Does NOT import app.py, BrowserService, JobManager, or dataset_logger.

USAGE
-----
    python scripts/login_stealthwriter_training.py

Override paths/port via env vars:
    TRAINING_CDP_PORT=9333
    TRAINING_CHROME_USER_DATA_DIR=browser_profiles/training_chrome
    TRAINING_SESSION_DIR=browser_profiles/training_sessions
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make sure project root is on the path when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.humanizer_training.teacher.stealthwriter_provider import (
    StealthWriterTeacherProvider,
    TrainingBrowserConfig,
    _SIGN_IN_URL,
    _DASHBOARD_URL,
    _is_sign_in_url,
)


def main() -> None:
    cfg = TrainingBrowserConfig()

    print("=" * 60)
    print("StealthWriter Training Login Helper")
    print("=" * 60)
    print(f"  CDP port       : {cfg.cdp_port}")
    print(f"  User data dir  : {cfg.user_data_dir}")
    print(f"  Session dir    : {cfg.session_dir}")
    print()
    print("Starting training Chrome …")

    provider = StealthWriterTeacherProvider(cfg)
    provider.start()

    print(f"Chrome started on port {cfg.cdp_port}.")
    print()
    print("Opening StealthWriter sign-in page …")

    try:
        page = provider._page()
        page.goto(_SIGN_IN_URL, wait_until="domcontentloaded")
        print()
        print(">>> The browser is now showing the StealthWriter sign-in page.")
        print(">>> Please complete the login (including Turnstile/CAPTCHA) manually.")
        print(">>> When you are fully logged in and see the Dashboard, press Enter here.")
        print()
        input("Press Enter after you have completed login … ")

        # Verify login
        print("Checking login status …")
        page.goto(_DASHBOARD_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        url = page.url

        if _is_sign_in_url(url) or "/dashboard" not in url.lower():
            print()
            print("ERROR: Still not logged in. Current URL:", url)
            print("Please try again.")
            sys.exit(1)

        # Save session
        saved = provider.save_session()
        if saved:
            session_path = Path(cfg.session_dir) / "stealthwriter.json"
            print()
            print("✓ Login confirmed!")
            print(f"✓ Session saved to: {session_path}")
        else:
            print()
            print("WARNING: Login detected but session could not be saved.")
            print("         Check write permissions for:", cfg.session_dir)
            sys.exit(1)

    finally:
        print()
        print("Stopping training Chrome …")
        provider.stop()
        print("Done. You can now run the document teacher collector:")
        print()
        print("  python scripts/collect_humanizer_teacher_documents.py \\")
        print("      --count 5 --provider stealthwriter --seed 42")
        print()


if __name__ == "__main__":
    main()
