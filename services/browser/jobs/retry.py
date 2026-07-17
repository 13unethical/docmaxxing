"""Retry engine — classification + escalation strategy.

Retryable causes: selector not found, timeout, navigation failed, stale page.

Escalation ladder (max 3 retries → 4 attempts total):
    attempt 1 fails → refresh page   → retry
    attempt 2 fails → reopen page    → retry
    attempt 3 fails → restart browser→ retry
    attempt 4 fails → give up (FAIL)
"""

from __future__ import annotations

from typing import Any

MAX_RETRIES = 3


class JobTimeout(Exception):
    """Raised when a job attempt exceeds the provider execution timeout."""


# Escalation steps keyed by the attempt number that just failed.
_ESCALATION = {1: "refresh", 2: "reopen", 3: "restart"}


def escalation_for_attempt(failed_attempt: int) -> str | None:
    """Return the recovery step to run after ``failed_attempt`` failed."""
    return _ESCALATION.get(failed_attempt)


def _text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}".lower()


def is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, JobTimeout):
        return True
    # StealthWriter automation failures carry a diagnostic "step".
    step = getattr(exc, "diagnostics", None)
    if isinstance(step, dict):
        failing = str(step.get("step", "")).lower()
        if failing in {
            "locate_textarea",
            "locate_humanize_button",
            "paste_text",
            "click_humanize",
            "wait_for_output",
            "navigate_humanizer",
        }:
            return True
    blob = _text(exc)
    retry_markers = (
        "timeout",
        "timed out",
        "selector",
        "waiting for",
        "navigation",
        "net::",
        "err_",
        "target closed",
        "target page, context or browser has been closed",
        "page has been closed",
        "execution context was destroyed",
        "not attached to the dom",
        "element is not attached",
        "stale",
        "connection closed",
        "websocket",
        "cdp",
    )
    return any(marker in blob for marker in retry_markers)


def error_code_for(exc: BaseException) -> str:
    if isinstance(exc, JobTimeout):
        return "TIMEOUT"
    if getattr(exc, "diagnostics", None) is not None:
        return "AUTOMATION_ERROR"
    blob = _text(exc)
    if "timeout" in blob or "timed out" in blob:
        return "TIMEOUT"
    if "navigation" in blob or "net::" in blob or "err_" in blob:
        return "NAVIGATION_FAILED"
    if "closed" in blob or "websocket" in blob or "cdp" in blob or "context was destroyed" in blob:
        return "STALE_PAGE"
    if "selector" in blob or "waiting for" in blob or "not attached" in blob:
        return "SELECTOR_NOT_FOUND"
    return "ERROR"
