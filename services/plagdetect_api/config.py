"""Environment for the PlagDetect HTTP API (X-API-Key + X-API-Secret)."""

from __future__ import annotations

import os


def _strip(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _flag(name: str) -> bool:
    return _strip(name).lower() in ("1", "true", "yes", "on")


def api_key() -> str:
    return _strip("PLAGDETECT_API_KEY") or _strip("TURNITIN_API_KEY")


def api_secret() -> str:
    return _strip("PLAGDETECT_API_SECRET") or _strip("TURNITIN_API_SECRET")


def api_base() -> str:
    raw = (
        _strip("PLAGDETECT_API_BASE")
        or _strip("PLAGDETECT_API_URL")
        or "https://plagdetect.org/api/v1"
    )
    raw = raw.rstrip("/\\")
    if raw.endswith("/api/v1"):
        return raw
    if raw.endswith("/api"):
        return f"{raw}/v1"
    return f"{raw}/api/v1"


def is_configured() -> bool:
    return bool(api_key() and api_secret())


def prefer_plagdetect_api() -> bool:
    """HTTP API wins over the browser when Key+Secret are set.

    Official Turnitin TCA is opt-in via ``TURNITIN_USE_TCA`` so PlagDetect
    Key/Secret pairs are not sent to app-us.turnitin.com.
    """
    if not is_configured():
        return False
    if _flag("TURNITIN_USE_BROWSER"):
        return False
    if _flag("TURNITIN_USE_TCA"):
        return False
    return True
