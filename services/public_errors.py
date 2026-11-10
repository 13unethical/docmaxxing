"""Decide which exception text may reach an HTTP response.

Validation messages written for users ("Password must be at least 6 characters.") pass.
Anything that looks like internals is replaced by the caller's generic message: file paths,
tracebacks, SQL / SQLite errors, URLs, exception class names, code-like text, quoted
``KeyError`` keys, environment variable names and key/token-like strings. The full exception
always goes to the server log instead (never to the client).
"""

from __future__ import annotations

import re
from typing import Any

GENERIC_MESSAGE = "The request could not be completed. Please try again."
_MAX_LEN = 300

_INTERNAL = [re.compile(p, re.IGNORECASE) for p in (
    r"traceback|most recent call last|\bfile \"|\.py\b|\bline \d+",
    r"(?:^|[\s'\"(=:,])(?:~?/[\w.\-]+){2,}",
    r"\b[a-z]:\\",
    r"\b(select|insert|update|delete)\b.*\b(from|into|set|where)\b",
    r"\bsqlite3?\b|no such (table|column)|constraint failed|syntax error|database is locked",
    r"\b(operational|integrity|programming|attribute|type|key|index|name|value|runtime|os|io)error\b",
    r"https?://|\bwww\.",
    r"[{}<>`\\]|\$\{|\w+\(\)|\b\w+\([^)]*=|connectionpool|\bhost=",
    r"\b(api[_ -]?key|secret|bearer|authorization|cookie|private key|access[_ -]?token|csrf)\b",
    r"\b(sk|pk|rk|key|tok)[-_][A-Za-z0-9_\-]{8,}",
    r"[A-Za-z0-9+/_\-]{32,}",
    r"invalid literal for|object has no attribute|is not subscriptable|unexpected keyword",
)] + [
    re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b"),
]
_CLASS_NAME = re.compile(r"\b[A-Z]\w*(Error|Exception)\b")
_QUOTED_ONLY = re.compile(r"""^\s*(['"]).*\1\s*$""", re.DOTALL)


def is_public_text(text: Any) -> bool:
    value = str(text or "").strip()
    if not value or len(value) > _MAX_LEN:
        return False
    if any(ord(ch) < 0x20 for ch in value):
        return False
    if _QUOTED_ONLY.match(value) or _CLASS_NAME.search(value):
        return False
    if not any(ch.isalpha() for ch in value):
        return False
    return not any(p.search(value) for p in _INTERNAL)


def public_text(exc_or_text: Any, fallback: str = GENERIC_MESSAGE) -> str:
    """``str(exc)`` when it is safe user-facing copy, else ``fallback``."""
    value = str(exc_or_text or "").strip()
    return value if is_public_text(value) else fallback


def admin_detail(exc: BaseException) -> dict[str, str]:
    """Limited diagnostics for verified-admin endpoints: type and a filtered message, no traceback."""
    return {
        "exception_type": type(exc).__name__,
        "error": public_text(exc, "Internal error (details are in the server log)."),
    }
