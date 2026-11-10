"""Validation for user-supplied post-login redirect targets (``?next=``).

Only same-origin local paths pass: they must start with exactly one ``/`` and be plain
printable ASCII. Anything a browser could resolve to another host (absolute URLs,
``//host``, ``/\\host``, schemes, embedded tabs/newlines, percent-encoded slashes,
backslashes or control characters, malformed escapes) is rejected rather than repaired.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

_MAX_LEN = 2048
_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_PRINTABLE_ASCII = re.compile(r"^[\x21-\x7e]+$")


def safe_local_path(value: object) -> str | None:
    """Return ``value`` if it is a safe local redirect path, else ``None``."""
    if not isinstance(value, str) or not value or len(value) > _MAX_LEN:
        return None
    if not _PRINTABLE_ASCII.match(value) or "\\" in value or _BAD_ESCAPE.search(value):
        return None
    if not value.startswith("/") or value.startswith("//"):
        return None
    decoded = unquote(value)
    if "\\" in decoded or decoded.startswith("//") or not _PRINTABLE_ASCII.match(decoded.replace(" ", "!")):
        return None
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or not parts.path.startswith("/"):
        return None
    return value
