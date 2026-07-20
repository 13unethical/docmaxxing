"""BrowserPool — manages one or more CDP browser connections.

Pool size is 1 for now, but the architecture supports N browser instances
(Browser 1, Browser 2, ...) behind acquire()/release() without changing callers.
"""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, BrowserContext, Playwright, sync_playwright

from services.browser.cdp_compat import connect_over_cdp_compat
from services.browser.page_manager import PageManager


class BrowserConnection:
    """A single Playwright<->Chrome CDP attachment plus its page manager."""

    def __init__(self, cdp_url: str, *, timeout_ms: int = 30000, index: int = 0) -> None:
        self._cdp_url = cdp_url
        self._timeout_ms = timeout_ms
        self._index = index

        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._pages = PageManager(None)

    @property
    def index(self) -> int:
        return self._index

    @property
    def pages(self) -> PageManager:
        return self._pages

    def connect(self) -> None:
        """(Re)connect over CDP and rebind the page manager to the live context."""
        self._teardown_playwright()

        self._pw = sync_playwright().start()
        try:
            # `no_defaults=True` avoids the browser-wide Browser.setDownloadBehavior
            # command that newer Chrome rejects with "Browser context management is
            # not supported"; we reuse the existing context (never new_context()).
            self._browser = connect_over_cdp_compat(
                self._pw.chromium, self._cdp_url, timeout_ms=self._timeout_ms
            )
        except Exception as exc:  # noqa: BLE001
            self._teardown_playwright()
            raise RuntimeError(
                f"Failed to connect over CDP at {self._cdp_url}: {exc}"
            ) from exc

        if not self._browser.contexts:
            raise RuntimeError(
                "CDP Chrome has no browser contexts. Open a window in the debugged Chrome."
            )
        self._context = self._browser.contexts[0]
        self._pages.bind_context(self._context, restore=True)

    def ensure(self) -> None:
        if not self.is_alive():
            self.connect()

    def reconnect(self) -> None:
        self.connect()

    def is_alive(self) -> bool:
        if self._pw is None or self._browser is None or self._context is None:
            return False
        try:
            _ = self._browser.contexts
            return True
        except Exception:  # noqa: BLE001
            return False

    @property
    def browser(self) -> Browser:
        self.ensure()
        assert self._browser is not None
        return self._browser

    @property
    def context(self) -> BrowserContext:
        self.ensure()
        assert self._context is not None
        return self._context

    def get_or_create_page(self, name: str | None = None) -> Any:
        self.ensure()
        return self._pages.get_or_create_page(name)

    def new_page(self) -> Any:
        self.ensure()
        return self._pages.new_page()

    def health(self) -> dict[str, Any]:
        alive = self.is_alive()
        contexts = 0
        pages = 0
        if alive and self._browser is not None:
            try:
                contexts = len(self._browser.contexts)
                pages = sum(len(ctx.pages) for ctx in self._browser.contexts)
            except Exception:  # noqa: BLE001
                contexts = 1 if self._context is not None else 0
                pages = self._pages.count()
        return {
            "index": self._index,
            "connected": alive,
            "contexts": contexts,
            "pages": pages,
            "provider_tabs": self._pages.names(),
            "cdp_url": self._cdp_url,
        }

    def disconnect(self) -> None:
        self._teardown_playwright()

    def _teardown_playwright(self) -> None:
        # Never call browser.close(); that could tear down the remote Chrome.
        self._browser = None
        self._context = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
            self._pw = None


class BrowserPool:
    def __init__(self, cdp_url: str, *, timeout_ms: int = 30000, size: int = 1) -> None:
        self._cdp_url = cdp_url
        self._timeout_ms = timeout_ms
        self._size = max(1, size)
        self._connections = [
            BrowserConnection(cdp_url, timeout_ms=timeout_ms, index=i)
            for i in range(self._size)
        ]
        self._rr = 0

    @property
    def size(self) -> int:
        return self._size

    @property
    def connections(self) -> list[BrowserConnection]:
        return list(self._connections)

    def connect_all(self) -> None:
        for conn in self._connections:
            conn.connect()

    def acquire(self) -> BrowserConnection:
        """Return a live connection (round-robin across the pool)."""
        n = len(self._connections)
        for _ in range(n):
            conn = self._connections[self._rr % n]
            self._rr = (self._rr + 1) % n
            try:
                conn.ensure()
                return conn
            except Exception:  # noqa: BLE001
                continue
        # All failed: force a reconnect on the first slot and surface the error.
        conn = self._connections[0]
        conn.connect()
        return conn

    def release(self, connection: BrowserConnection) -> None:
        """No-op for the size-1 pool; placeholder for future checkout accounting."""
        return None

    def is_healthy(self) -> bool:
        return any(conn.is_alive() for conn in self._connections)

    def disconnect_all(self) -> None:
        for conn in self._connections:
            conn.disconnect()

    def health(self) -> dict[str, Any]:
        return {
            "size": self._size,
            "healthy": self.is_healthy(),
            "connections": [conn.health() for conn in self._connections],
        }
