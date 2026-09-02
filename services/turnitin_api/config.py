"""Environment for the official Turnitin Core API."""

from __future__ import annotations

import os


def _strip(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def api_key() -> str:
    return _strip("TURNITIN_API_KEY")


def api_secret() -> str:
    return _strip("TURNITIN_API_SECRET")


def api_token() -> str:
    """TCA Authorization value (the integration API key).

    Admin screens label two codes: API Key and API Secret. The Secret is the
    TCA token. If only one code exists, it can go in either variable.
    """
    return api_secret() or api_key()


def api_base() -> str:
    """Root including ``/api/v1``.

    Accepts a tenant host (``https://foo.turnitin.com``), ``.../api``, or the
    full ``.../api/v1`` path.
    """
    raw = (
        _strip("TURNITIN_API_BASE")
        or _strip("TURNITIN_API_URL")
        or "https://app-us.turnitin.com"
    )
    raw = raw.rstrip("/\\")
    if raw.endswith("/api/v1"):
        return raw
    if raw.endswith("/api"):
        return f"{raw}/v1"
    return f"{raw}/api/v1"


def integration_name() -> str:
    return _strip("TURNITIN_INTEGRATION_NAME") or "DocMaxxing"


def integration_version() -> str:
    return _strip("TURNITIN_INTEGRATION_VERSION") or "1.0.0"


def add_to_index() -> bool:
    raw = _strip("TURNITIN_ADD_TO_INDEX").lower()
    return raw in ("1", "true", "yes", "on")


def authorization_header(token: str | None = None, *, scheme: str | None = None) -> str:
    """TCA OpenAPI puts the key in Authorization with no prefix by default."""
    value = (token if token is not None else api_token()).strip()
    style = (scheme if scheme is not None else _strip("TURNITIN_AUTH_SCHEME")).strip().lower()
    if style in ("bearer",):
        return f"Bearer {value}"
    if style in ("token",):
        return f"Token {value}"
    return value


def is_configured() -> bool:
    return bool(api_token())


def prefer_official_api() -> bool:
    """True only when TCA is explicitly enabled.

    PlagDetect Key/Secret pairs are stored in the same env names; they must
    not be sent to app-us.turnitin.com unless ``TURNITIN_USE_TCA=1``.
    """
    enabled = _strip("TURNITIN_USE_TCA").lower() in ("1", "true", "yes", "on")
    if not enabled:
        return False
    if not is_configured():
        return False
    forced = _strip("TURNITIN_USE_BROWSER").lower()
    if forced in ("1", "true", "yes", "on"):
        return False
    return True
