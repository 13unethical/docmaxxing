"""BrowserService — the long-lived, singleton browser infrastructure.

Think of it like a database connection pool: the browser is started once and
kept alive for the life of the process. It is never launched or closed per
request. BrowserService owns the entire browser lifecycle; providers only ask
it for a page.

Responsibilities:
  * singleton
  * start Chrome automatically (via ChromeLauncher)
  * connect over CDP automatically (via BrowserPool)
  * restart automatically if Chrome crashes / CDP drops / a tab disappears
  * never close during normal operation
  * own cookies/sessions (via SessionStore)
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, ClassVar

from services.browser.browser_pool import BrowserPool
from services.browser.chrome_launcher import ChromeLauncher
from services.browser.session_store import SessionStore


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class BrowserService:
    _instance: ClassVar[BrowserService | None] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._launcher = ChromeLauncher()
        self._timeout_ms = _env_int("BROWSER_TIMEOUT", 30000)
        self._pool = BrowserPool(
            self._launcher.cdp_url,
            timeout_ms=self._timeout_ms,
            size=_env_int("BROWSER_POOL_SIZE", 1),
        )
        self._sessions = SessionStore()
        self._providers: dict[str, Any] = {}
        self._started_at: float | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ singleton
    @classmethod
    def instance(cls) -> BrowserService:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        if cls._instance is not None:
            try:
                cls._instance.stop()
            except Exception:  # noqa: BLE001
                pass
        cls._instance = None

    # ------------------------------------------------------------------ accessors
    @property
    def cdp_url(self) -> str:
        return self._launcher.cdp_url

    @property
    def user_data_dir(self) -> Path:
        return self._launcher.user_data_dir

    @property
    def sessions(self) -> SessionStore:
        return self._sessions

    def register_provider(self, provider: Any) -> None:
        name = getattr(provider, "name", None)
        if name:
            self._providers[name] = provider

    def providers(self) -> dict[str, Any]:
        return dict(self._providers)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> dict[str, Any]:
        """Start Chrome (or reuse) and connect the pool. Idempotent."""
        with self._lock:
            launch_info = self._launcher.ensure_running()
            self._pool.connect_all()
            self._restore_sessions()
            if self._started_at is None:
                self._started_at = time.time()
            return {
                "success": True,
                "connected": self._pool.is_healthy(),
                "chrome": launch_info,
                "cdp_url": self.cdp_url,
            }

    def stop(self) -> None:
        """Disconnect Playwright and terminate Chrome only if we launched it."""
        with self._lock:
            self._pool.disconnect_all()
            self._launcher.stop()
            self._started_at = None

    def restart(self) -> dict[str, Any]:
        """Full recovery: relaunch Chrome, reconnect, restore pages + sessions."""
        with self._lock:
            self._pool.disconnect_all()
            self._launcher.restart()
            self._pool.connect_all()
            self._restore_sessions()
            self._started_at = self._started_at or time.time()
            return {"success": True, "connected": self._pool.is_healthy()}

    def is_running(self) -> bool:
        return self._launcher.is_running() and self._pool.is_healthy()

    def ensure_running(self) -> None:
        """Guarantee a usable browser, recovering transparently if needed."""
        with self._lock:
            if not self._launcher.is_running():
                # Chrome process is gone → relaunch and reconnect.
                self._launcher.ensure_running()
                self._pool.connect_all()
                self._restore_sessions()
            elif not self._pool.is_healthy():
                # CDP dropped but Chrome is alive → reconnect only.
                self._pool.connect_all()
                self._restore_sessions()
            if self._started_at is None:
                self._started_at = time.time()

    def _restore_sessions(self) -> None:
        # New CDP context → storageState must be re-applied to pages.
        self._sessions.clear_applied()
        if not self._sessions.list():
            return
        try:
            context = self._pool.acquire().context
        except Exception:  # noqa: BLE001
            return
        for name in self._sessions.list():
            self._sessions.apply(name, context)

    # ------------------------------------------------------------------ pages
    def browser(self) -> Any:
        self.ensure_running()
        return self._pool.acquire().browser

    def context(self) -> Any:
        self.ensure_running()
        return self._pool.acquire().context

    def page(self) -> Any:
        return self.get_or_create_page("default")

    def new_page(self) -> Any:
        self.ensure_running()
        return self._pool.acquire().new_page()

    def get_or_create_page(self, name: str) -> Any:
        self.ensure_running()
        page = self._pool.acquire().get_or_create_page(name)
        self._sessions.apply_to_page(name, page)
        return page

    def invalidate_page(self, name: str) -> None:
        """Drop a cached provider tab so the next get_or_create opens a fresh one."""
        try:
            conn = self._pool.acquire()
            conn.pages.invalidate(name)
        except Exception:  # noqa: BLE001
            pass

    def reopen_page(self, name: str) -> Any:
        """Close/drop a provider tab and return a brand-new page (same browser)."""
        with self._lock:
            self.ensure_running()
            try:
                conn = self._pool.acquire()
                existing = conn.pages.peek(name)
                if existing is not None:
                    try:
                        if not existing.is_closed():
                            existing.close()
                    except Exception:  # noqa: BLE001
                        pass
                conn.pages.invalidate(name)
            except Exception:  # noqa: BLE001
                pass
            # Allow session restore again after tab death / reconnect.
            self._sessions.mark_unapplied(name)
            return self.get_or_create_page(name)

    def save_session(self, name: str) -> bool:
        try:
            return self._sessions.save(name, self._pool.acquire().context)
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------ diagnostics
    def health(self) -> dict[str, Any]:
        running = self._launcher.is_running()
        connected = self._pool.is_healthy()
        pool_health = self._pool.health()
        contexts = sum(c.get("contexts", 0) for c in pool_health.get("connections", []))
        pages = sum(c.get("pages", 0) for c in pool_health.get("connections", []))

        providers: dict[str, Any] = {}
        for name, provider in self._providers.items():
            try:
                providers[name] = provider.health()
            except Exception as exc:  # noqa: BLE001
                providers[name] = {"provider": name, "error": str(exc)}

        uptime = round(time.time() - self._started_at, 1) if self._started_at else 0

        return {
            "browser_running": running,
            "chrome_pid": self._launcher.pid,
            "connected": connected,
            "contexts": contexts,
            "pages": pages,
            "providers": providers,
            "memory_usage": self._launcher.memory_usage(),
            "uptime": uptime,
            "cdp_url": self.cdp_url,
            "user_data_dir": str(self.user_data_dir.resolve()),
            "pool": pool_health,
        }


def get_browser_service() -> BrowserService:
    """Convenience accessor for the process-wide BrowserService singleton."""
    return BrowserService.instance()
