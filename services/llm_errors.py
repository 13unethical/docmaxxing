"""Map LLM provider failures to HTTP status codes and user-facing messages."""

from __future__ import annotations


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
    msg = (message or "").strip()
    lower = msg.lower()
    if "credits are depleted" in lower or "credit balance" in lower or "insufficient" in lower:
        if "claude" in lower or "anthropic" in lower:
            return (
                "Claude API credits are depleted. Top up at https://console.anthropic.com "
                "or set ASSIGNMENT_LLM=gemini to use Gemini for writing."
            )
        return (
            "Gemini API credits are depleted. Top up at https://ai.studio/projects "
            "or ensure ANTHROPIC_API_KEY is valid so Claude can write sections."
        )
    if "quota" in lower or "rate limit" in lower or "429" in lower:
        return "AI provider rate limit reached. Wait a minute and press Retry."
    if "claude:" in lower and "gemini:" in lower:
        return msg
    if msg:
        return msg
    return "AI generation failed. Check API keys and try again."
