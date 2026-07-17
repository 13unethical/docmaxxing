"""Long-lived Playwright browser service — attaches to Chrome via CDP (no launch)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

_DEFAULT_CDP_URL = "http://127.0.0.1:9222"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def resolve_cdp_url() -> str:
    return (os.environ.get("BROWSER_CDP_URL") or _DEFAULT_CDP_URL).strip()


class BrowserRuntime:
    """Attach to an already-running Google Chrome via CDP. Process-wide singleton."""

    _instance: ClassVar[BrowserRuntime | None] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> BrowserRuntime:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._configured = False  # type: ignore[attr-defined]
        return cls._instance

    def __init__(
        self,
        *,
        cdp_url: str | None = None,
        timeout_ms: int | None = None,
        # Kept for call-site compatibility; ignored under CDP (Chrome owns the profile).
        headless: bool | None = None,
        profile_dir: str | Path | None = None,
        executable_path: str | Path | None = None,
    ) -> None:
        if getattr(self, "_configured", False):
            return
        self._configured = True

        self._cdp_url = (cdp_url or resolve_cdp_url()).rstrip("/")
        self._timeout_ms = timeout_ms if timeout_ms is not None else _env_int("BROWSER_TIMEOUT", 30000)
        # Compatibility stubs (Chrome is started manually with --user-data-dir).
        self._headless = False
        self._profile_dir = Path(
            profile_dir
            or os.environ.get("BROWSER_PROFILE_DIR")
            or Path.home() / "ChromeAutomation"
        )
        self._executable_path: str | None = None
        self._using_bundled_chromium = False
        self._using_system_chrome_profile = True
        self._chrome_profile_name: str | None = None

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._tracked_pages: set[Page] = set()
        self._ever_connected = False

    @classmethod
    def get_instance(
        cls,
        *,
        cdp_url: str | None = None,
        timeout_ms: int | None = None,
        headless: bool | None = None,
        profile_dir: str | Path | None = None,
        executable_path: str | Path | None = None,
    ) -> BrowserRuntime:
        """Return the process-wide BrowserRuntime singleton."""
        return cls(
            cdp_url=cdp_url,
            timeout_ms=timeout_ms,
            headless=headless,
            profile_dir=profile_dir,
            executable_path=executable_path,
        )

    @classmethod
    def reset_instance(cls) -> None:
        """Drop the singleton after an explicit disconnect (tests / teardown)."""
        if cls._instance is not None:
            try:
                cls._instance.stop()
            except Exception:  # noqa: BLE001
                pass
        cls._instance = None

    @property
    def profile_dir(self) -> Path:
        return self._profile_dir

    @property
    def cdp_url(self) -> str:
        return self._cdp_url

    def is_running(self) -> bool:
        return self._browser_alive()

    def is_connected(self) -> bool:
        return self._browser_alive()

    def connect(self) -> dict[str, Any]:
        """Ensure CDP attachment and return connection diagnostics."""
        self.start()
        contexts = 0
        pages = 0
        browser_name = "Google Chrome"
        if self._browser is not None:
            try:
                contexts = len(self._browser.contexts)
                pages = sum(len(ctx.pages) for ctx in self._browser.contexts)
            except Exception:  # noqa: BLE001
                contexts = 1 if self._context is not None else 0
                pages = len(self._context.pages) if self._context is not None else 0
            try:
                version = self._browser.version or ""
                if version:
                    browser_name = f"Google Chrome {version}" if "Chrome" not in version else version
            except Exception:  # noqa: BLE001
                pass
        return {
            "success": True,
            "connected": True,
            "contexts": contexts,
            "pages": pages,
            "browser": browser_name,
            "cdp_url": self._cdp_url,
        }

    def get_context(self) -> BrowserContext:
        self.start()
        self._recover_if_needed()
        if self._context is None:
            raise RuntimeError("Browser context is not available — is Chrome running with --remote-debugging-port?")
        return self._context

    def get_page(self) -> Page:
        """Return a live page from the attached Chrome (connects over CDP if needed)."""
        return self.ensure_page()

    def ensure_page(self) -> Page:
        """Return a live page, creating one only if the context has none usable."""
        self.start()
        self._recover_if_needed()
        if self._page is not None and self._page_alive(self._page):
            return self._page
        assert self._context is not None
        # Prefer an existing open tab before creating a new one.
        try:
            for existing in self._context.pages:
                if self._page_alive(existing):
                    self._page = existing
                    self._tracked_pages.add(existing)
                    return self._page
        except Exception:  # noqa: BLE001
            pass
        self._page = self._context.new_page()
        self._tracked_pages.add(self._page)
        return self._page

    def start(self) -> None:
        """Connect over CDP once; subsequent calls reuse the live browser."""
        if self._browser_alive():
            print("Browser reused", flush=True)
            return
        if self._ever_connected:
            print("Browser reconnected", flush=True)
            self._connect_cdp()
            return
        print("Browser connected (CDP)", flush=True)
        self._connect_cdp()

    def stop(self) -> None:
        """Disconnect Playwright from Chrome. Does not close the Chrome process."""
        self._page = None
        self._tracked_pages.clear()
        self._context = None
        # Do not call browser.close() — that can tear down remote Chrome depending on version.
        self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None

    def initialize(self) -> None:
        """Backward-compatible alias for start()."""
        self.start()

    def shutdown(self) -> None:
        """No-op for long-lived service.

        API/provider finally blocks still call shutdown(); ignore them so Chrome
        stays alive across requests. Call stop() only to disconnect Playwright.
        """
        print("Browser reused", flush=True)

    def new_page(self) -> Page:
        """Create an additional page tab (prefer get_page for the shared tab)."""
        context = self.get_context()
        page = context.new_page()
        self._tracked_pages.add(page)
        if self._page is None or not self._page_alive(self._page):
            self._page = page
        return page

    def close_page(self, page: Page) -> None:
        """Close a page tab. Does not disconnect from Chrome."""
        try:
            if not page.is_closed():
                page.close()
        except Exception:  # noqa: BLE001
            pass
        self._tracked_pages.discard(page)
        if self._page is page:
            self._page = None

    def health(self) -> dict[str, Any]:
        """Return runtime health metrics."""
        alive = self._browser_alive()
        pages_open = 0
        contexts = 0
        if alive and self._browser is not None:
            try:
                contexts = len(self._browser.contexts)
                pages_open = sum(len(ctx.pages) for ctx in self._browser.contexts)
            except Exception:  # noqa: BLE001
                pages_open = len(self._context.pages) if self._context is not None else 0
                contexts = 1 if self._context is not None else 0
        return {
            "browser_running": alive,
            "connected": alive,
            "context_loaded": alive and self._context is not None,
            "pages_open": pages_open,
            "contexts": contexts,
            "cdp_url": self._cdp_url,
            "profile_exists": self._profile_dir.exists(),
            "executable_path": self._executable_path,
            "using_bundled_chromium": False,
            "using_system_chrome_profile": True,
            "chrome_profile": self._chrome_profile_name,
            "headless": False,
            "persistent_session_enabled": True,
            "mode": "cdp",
        }

    def _connect_cdp(self) -> None:
        # Drop stale local handles without closing Chrome.
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._tracked_pages.clear()

        print(f"CDP endpoint: {self._cdp_url}", flush=True)
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(self._cdp_url)
        except Exception as exc:  # noqa: BLE001
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None
            raise RuntimeError(
                f"Failed to connect over CDP at {self._cdp_url}. "
                "Start Google Chrome with --remote-debugging-port=9222 "
                f"(and --user-data-dir). Underlying error: {exc}"
            ) from exc

        if not self._browser.contexts:
            raise RuntimeError(
                "CDP Chrome has no browser contexts. "
                "Open at least one window/tab in the debugged Chrome instance."
            )
        self._context = self._browser.contexts[0]

        self._tracked_pages = set(self._context.pages)
        self._page = self._context.pages[0] if self._context.pages else None
        if self._page is None:
            self._page = self._context.new_page()
            self._tracked_pages.add(self._page)
        self._ever_connected = True

    def _recover_if_needed(self) -> None:
        if self._browser_alive():
            return
        print("Browser recovered (CDP reconnect)", flush=True)
        self._connect_cdp()

    def _browser_alive(self) -> bool:
        if self._playwright is None or self._browser is None:
            return False
        try:
            _ = self._browser.contexts
            if self._context is None and self._browser.contexts:
                self._context = self._browser.contexts[0]
            return self._context is not None
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _page_alive(page: Page) -> bool:
        try:
            return not page.is_closed()
        except Exception:  # noqa: BLE001
            return False


def get_shared_runtime(
    *,
    cdp_url: str | None = None,
    headless: bool | None = None,
    profile_dir: str | Path | None = None,
) -> BrowserRuntime:
    """Convenience accessor for the process-wide BrowserRuntime."""
    return BrowserRuntime.get_instance(
        cdp_url=cdp_url,
        headless=headless,
        profile_dir=profile_dir,
    )
