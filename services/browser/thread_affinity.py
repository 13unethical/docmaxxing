"""Funnel Playwright calls onto the single BrowserWorker thread.

Playwright's sync API is greenlet/thread-affine. Flask request threads must never
touch pages directly — register a submitter via ``set_browser_submitter`` when
the browser engine starts, then use ``run_on_browser_thread``.
"""

from __future__ import annotations

from typing import Any, Callable

_SubmitFn = Callable[..., Any]
_submitter: _SubmitFn | None = None


def set_browser_submitter(submitter: _SubmitFn | None) -> None:
    global _submitter
    _submitter = submitter


def run_on_browser_thread(fn: Callable[[], Any], *, timeout: float | None = 180) -> Any:
    """Run ``fn`` on the Playwright owner thread when a submitter is registered."""
    if _submitter is None:
        return fn()
    return _submitter(fn, timeout)
