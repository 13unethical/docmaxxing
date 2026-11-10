"""The site's canonical public origin, from ``PUBLIC_BASE_URL`` only.

Links that leave the request (emails, the packed Veil extension, referral links) must never be
built from ``Host`` / ``X-Forwarded-Host`` / ``X-Forwarded-Proto``: those are client-controlled
unless a proxy rewrites them, so one request could plant an attacker origin in someone's email.

Production needs ``PUBLIC_BASE_URL=https://<host>[:port]`` (no path, query, fragment or
credentials). Local development may use ``http://localhost[:port]`` / ``http://127.0.0.1[:port]``
only together with ``DEV_INSECURE_COOKIES=1`` (the ``python app.py`` dev-server switch).
Missing or invalid configuration raises :class:`PublicOriginError`; callers fail closed.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")
_DEV_HOSTS = frozenset({"localhost", "127.0.0.1"})


class PublicOriginError(RuntimeError):
    """PUBLIC_BASE_URL is missing or not a valid canonical origin."""


def _dev_http_allowed() -> bool:
    return (os.environ.get("DEV_INSECURE_COOKIES") or "").strip() == "1"


def normalize_public_base_url(raw: str | None, *, allow_dev_http: bool = False) -> str:
    """Return ``scheme://host[:port]`` (lower-case) or raise :class:`PublicOriginError`."""
    value = (raw or "").strip()
    if not value:
        raise PublicOriginError("PUBLIC_BASE_URL is not set")
    if any(ord(ch) < 0x21 or ord(ch) > 0x7E for ch in value) or "\\" in value:
        raise PublicOriginError("PUBLIC_BASE_URL contains invalid characters")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise PublicOriginError("PUBLIC_BASE_URL is not a valid URL") from exc
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower()
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise PublicOriginError("PUBLIC_BASE_URL must not contain credentials")
    if parts.path not in ("", "/") or parts.query or parts.fragment or value.endswith("?") or value.endswith("#"):
        raise PublicOriginError("PUBLIC_BASE_URL must be an origin without path, query or fragment")
    if not host or not _HOST_RE.match(host):
        raise PublicOriginError("PUBLIC_BASE_URL has an invalid host")
    if scheme == "https":
        pass
    elif scheme == "http" and allow_dev_http and host in _DEV_HOSTS:
        pass
    else:
        raise PublicOriginError("PUBLIC_BASE_URL must use https")
    netloc = host if port is None else f"{host}:{port}"
    return f"{scheme}://{netloc}"


def canonical_origin() -> str:
    """The configured public origin; raises :class:`PublicOriginError` when unusable."""
    return normalize_public_base_url(
        os.environ.get("PUBLIC_BASE_URL"), allow_dev_http=_dev_http_allowed()
    )


def configuration_problem() -> str | None:
    """Human-readable reason the origin is unusable (for startup logs), or ``None``."""
    try:
        canonical_origin()
    except PublicOriginError as exc:
        return str(exc)
    return None
