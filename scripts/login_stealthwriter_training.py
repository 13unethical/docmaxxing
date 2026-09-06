#!/usr/bin/env python3
"""login_stealthwriter_training.py — Manual login helper for the training Chrome.

Steps
-----
1. Starts an isolated Chrome process (port 9333, separate user-data-dir).
2. Navigates to the StealthWriter sign-in page.
3. Waits for YOU to complete login / Turnstile manually.
4. Once you press Enter here, checks /dashboard and saves the session.
5. Exits — shuts down Chrome (and Xvfb when --headed-login started it).

ISOLATION GUARANTEES
--------------------
* Uses TRAINING_CDP_PORT (default 9333) — never touches production port 9222.
* Writes session to browser_profiles/training_sessions/stealthwriter.json.
* Never writes to browser_profiles/sessions/stealthwriter.json.
* Does NOT import app.py, BrowserService, JobManager, or dataset_logger.

USAGE
-----
    # Default (may be headless on Linux VPS without DISPLAY — CAPTCHA often fails)
    python3 scripts/login_stealthwriter_training.py

    # Recommended on VPS: headed via private Xvfb :99 (SSH tunnel to CDP for viewing)
    python3 scripts/login_stealthwriter_training.py --headed-login

Override paths/port via env vars:
    TRAINING_CDP_PORT=9333
    TRAINING_CHROME_USER_DATA_DIR=browser_profiles/training_chrome
    TRAINING_SESSION_DIR=browser_profiles/training_sessions
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make sure project root is on the path when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.humanizer_training.teacher.headed_login import (
    DEFAULT_XVFB_DISPLAY,
    assert_cdp_is_headed,
    cdp_user_agent,
    fetch_cdp_version,
    is_training_dashboard_url,
    launch_headed_training_chrome,
    require_xvfb_binary,
    start_xvfb,
)
from services.humanizer_training.teacher.stealthwriter_provider import (
    StealthWriterTeacherProvider,
    TrainingBrowserConfig,
    _SIGN_IN_URL,
    _DASHBOARD_URL,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual StealthWriter login for the isolated training Chrome profile."
    )
    parser.add_argument(
        "--headed-login",
        action="store_true",
        help=(
            "Start a private Xvfb display (:99) and launch headed training Chrome "
            "(no --headless). CDP stays on 127.0.0.1:9333 — view via SSH tunnel."
        ),
    )
    parser.add_argument(
        "--xvfb-display",
        default=DEFAULT_XVFB_DISPLAY,
        help=f"Xvfb display for --headed-login (default {DEFAULT_XVFB_DISPLAY}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = TrainingBrowserConfig()
    xvfb = None
    headed_chrome = None

    print("=" * 60)
    print("StealthWriter Training Login Helper")
    print("=" * 60)
    print(f"  CDP port       : {cfg.cdp_port}")
    print(f"  User data dir  : {cfg.user_data_dir}")
    print(f"  Session dir    : {cfg.session_dir}")
    print(f"  Headed login   : {bool(args.headed_login)}")
    print()

    provider: StealthWriterTeacherProvider | None = None
    exit_code = 0

    try:
        if args.headed_login:
            # Fail closed before launching anything if Xvfb is missing.
            require_xvfb_binary()
            xvfb = start_xvfb(display=str(args.xvfb_display))
            print(f"Xvfb display     : {xvfb.display} (started_by_us={xvfb.started_by_us})")
            # Launch headed Chrome OURSELVES — do not use ChromeLauncher.ensure_running(),
            # which silently reuses leftover HeadlessChrome on the same CDP port.
            headed_chrome = launch_headed_training_chrome(
                display=xvfb.display,
                user_data_dir=cfg.user_data_dir,
                port=int(cfg.cdp_port),
            )
            ver = assert_cdp_is_headed(port=int(cfg.cdp_port))
            print(f"CDP User-Agent   : {cdp_user_agent(ver)}")
            print("Chrome mode      : headed (verified, no HeadlessChrome)")
            print("View via Mac     : ssh -N -L 9333:127.0.0.1:9333 root@VPS")
            print("                  then chrome://inspect → localhost:9333")
            print()
            # Attach Playwright only (Chrome already running + headed).
            provider = StealthWriterTeacherProvider(cfg)
            provider.start()
        else:
            print("Starting training Chrome …")
            provider = StealthWriterTeacherProvider(cfg)
            provider.start()
            # Diagnostic only — default path may be headless on Linux VPS.
            ver = fetch_cdp_version(port=int(cfg.cdp_port))
            if ver:
                print(f"CDP User-Agent   : {cdp_user_agent(ver)}")

        print(f"Chrome started on port {cfg.cdp_port}.")
        print()
        print("Opening StealthWriter sign-in page …")

        page = provider._page()
        page.goto(_SIGN_IN_URL, wait_until="domcontentloaded")
        print()
        print(">>> The browser is now showing the StealthWriter sign-in page.")
        print(">>> Please complete the login (including Turnstile/CAPTCHA) manually.")
        print(">>> When you are fully logged in and see the Dashboard, press Enter here.")
        print()
        input("Press Enter after you have completed login … ")

        if args.headed_login:
            # Re-check before saving — refuse if something flipped to headless mid-flight.
            assert_cdp_is_headed(port=int(cfg.cdp_port))

        print("Checking login status …")
        page.goto(_DASHBOARD_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        url = page.url

        if not is_training_dashboard_url(url):
            print()
            print("ERROR: Still not logged in. Current URL:", url)
            print("Session was NOT saved.")
            print("Please try again.")
            exit_code = 1
        else:
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
                exit_code = 1

    except Exception as exc:  # noqa: BLE001
        print()
        print(f"ERROR: {exc}")
        exit_code = 1
    finally:
        print()
        print("Stopping training Playwright attach …")
        if provider is not None:
            try:
                # Disconnect Playwright; headed Chrome is owned by headed_chrome handle.
                if headed_chrome is not None and provider._pool is not None:
                    try:
                        provider._pool.disconnect_all()
                    except Exception:  # noqa: BLE001
                        pass
                    provider._pool = None
                    provider._started = False
                else:
                    provider.stop()
            except Exception:  # noqa: BLE001
                pass
        if headed_chrome is not None:
            print("Stopping headed training Chrome …")
            headed_chrome.stop()
        if xvfb is not None:
            print(f"Stopping Xvfb ({xvfb.display}) …")
            xvfb.stop()
        print("Done. You can now run the document teacher collector:")
        print()
        print("  python3 scripts/collect_humanizer_teacher_documents.py \\")
        print("      --count 5 --provider stealthwriter --seed 42")
        print()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
