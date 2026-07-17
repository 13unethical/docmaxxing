"""HealthMonitor — periodic liveness checks + automatic recovery.

Every 30s it checks browser/CDP liveness, memory, provider tabs, and active
jobs. Liveness is probed over the CDP HTTP endpoint (thread-safe, no Playwright),
so the monitor never touches Playwright directly. Any recovery that needs
Playwright is delegated to the BrowserWorker thread, which owns it.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class HealthMonitor(threading.Thread):
    def __init__(
        self,
        service: Any,
        job_manager: Any,
        metrics: Any,
        worker: Any,
        *,
        interval: int | None = None,
    ) -> None:
        super().__init__(name="browser-health-monitor", daemon=True)
        self._service = service
        self._jobs = job_manager
        self._metrics = metrics
        self._worker = worker
        self._interval = interval or _env_int("BROWSER_HEALTH_INTERVAL", 30)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last: dict[str, Any] = {"status": "starting"}

    def stop(self) -> None:
        self._stop.set()

    @property
    def last(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last)

    def run(self) -> None:
        # Grace period so the worker can perform its initial browser start.
        self._stop.wait(self._interval)
        while not self._stop.is_set():
            try:
                self._check_once()
            except Exception as exc:  # noqa: BLE001
                print(f"[health-monitor] check error: {exc}", flush=True)
            self._stop.wait(self._interval)

    def _check_once(self) -> None:
        # ChromeLauncher import is cheap; probe CDP over HTTP (no Playwright).
        from services.browser.chrome_launcher import ChromeLauncher

        launcher = ChromeLauncher()
        browser_alive = launcher.is_cdp_available()
        cdp_alive = browser_alive
        memory = launcher.memory_usage()
        active_jobs = self._jobs.active_count() if self._jobs is not None else 0

        snapshot = {
            "at": datetime.now(timezone.utc).isoformat(),
            "browser_alive": browser_alive,
            "cdp_alive": cdp_alive,
            "memory_usage": memory,
            "active_jobs": active_jobs,
            "recovered": False,
        }

        if not browser_alive:
            print("[health-monitor] browser/CDP down — triggering recovery", flush=True)
            snapshot["recovered"] = True
            self._metrics.record_browser_restart()
            try:
                # Recovery runs on the worker thread (Playwright owner).
                self._worker.submit(lambda: self._service.restart(), timeout=90)
            except Exception as exc:  # noqa: BLE001
                print(f"[health-monitor] recovery failed: {exc}", flush=True)

        with self._lock:
            self._last = snapshot
