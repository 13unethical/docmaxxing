"""Compatibility shim.

StealthWriter now lives in the generic Browser Automation Platform at
``services.browser.providers.stealthwriter``. This module re-exports the public
API so any older imports keep working. New code should import from
``services.browser.providers.stealthwriter``.
"""

from __future__ import annotations

from pathlib import Path

from services.browser.providers.stealthwriter import (  # noqa: F401
    PROVIDER_NAME,
    StealthWriterAutomationError,
    StealthWriterProvider,
    check_interactive_login,
    get_session_status,
    humanize_text,
    open_manual_login_browser,
    start_interactive_login,
)

# Legacy constant kept for backward compatibility with older callers.
STEALTHWRITER_PROFILE_DIR = Path("browser_profiles/chrome_user_data")

__all__ = [
    "PROVIDER_NAME",
    "STEALTHWRITER_PROFILE_DIR",
    "StealthWriterAutomationError",
    "StealthWriterProvider",
    "check_interactive_login",
    "get_session_status",
    "humanize_text",
    "open_manual_login_browser",
    "start_interactive_login",
]
