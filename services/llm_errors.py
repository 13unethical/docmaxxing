"""Map LLM provider failures to HTTP status codes and user-facing messages.

The raw provider text (keys, account state, endpoints, request ids) stays in the server log;
users only see one of the fixed messages below.
"""

from __future__ import annotations

_UNAVAILABLE = "The AI service is temporarily unavailable. Please try again later."
_RATE_LIMITED = "AI provider rate limit reached. Wait a minute and press Retry."
_TIMEOUT = "AI took too long on this step. Press Retry — progress is kept."
_FAILED = "AI generation failed. Please try again."


def llm_error_http_status(message: str) -> int:
    msg = (message or "").lower()
    if any(
        token in msg
        for token in (
            "credits are depleted",
            "quota",
            "rate limit",
            "resource_exhausted",
            "too many requests",
            " 429",
            "status=429",
        )
    ):
        return 429
    return 502


def user_friendly_llm_error(message: str) -> str:
    lower = (message or "").strip().lower()
    if "credits are depleted" in lower or "credit balance" in lower or "insufficient" in lower:
        return _UNAVAILABLE
    if "quota" in lower or "rate limit" in lower or "429" in lower:
        return _RATE_LIMITED
    if (
        "timed out" in lower
        or "timeout" in lower
        or "read timeout" in lower
        or "httpsconnectionpool" in lower
    ):
        return _TIMEOUT
    return _FAILED
