"""Map provider exceptions to student-safe assignment API payloads."""

from __future__ import annotations

from typing import Any

_STUDENT_PAUSE = "Something went wrong. Please try again."


def humanizer_fail_payload(exc: BaseException) -> dict[str, Any]:
    """JSON for a failed assignment rewrite step.

    Students must not see provider names, login state, or pipeline internals.
    Operators get the real exception from application logs / Admin preflight.
    """
    text = str(exc or "").strip() or "failed"
    upper = text.upper()
    lower = text.lower()
    retryable = True
    if "LOGIN_REQUIRED" in upper or "not logged in" in lower:
        retryable = False
    elif "NO_CHANGE" in upper or "unchanged" in lower:
        retryable = False
    return {
        "error": "GENERATION_PAUSED",
        "message": _STUDENT_PAUSE,
        "retryable": retryable,
    }
