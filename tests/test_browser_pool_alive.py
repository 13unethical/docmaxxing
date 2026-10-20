"""BrowserConnection must notice a context Chrome has already dropped."""

from __future__ import annotations

from services.browser.browser_pool import BrowserConnection


class _FakeBrowser:
    def __init__(self, contexts, connected=True):
        self.contexts = contexts
        self._connected = connected

    def is_connected(self):
        return self._connected


def _conn(browser, context):
    conn = BrowserConnection("http://127.0.0.1:9222")
    conn._pw = object()
    conn._browser = browser
    conn._context = context
    return conn


def test_alive_when_context_still_present():
    ctx = object()
    assert _conn(_FakeBrowser([ctx]), ctx).is_alive()


def test_dead_when_context_dropped():
    assert not _conn(_FakeBrowser([]), object()).is_alive()


def test_dead_when_browser_disconnected():
    ctx = object()
    assert not _conn(_FakeBrowser([ctx], connected=False), ctx).is_alive()
