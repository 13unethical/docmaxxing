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
        self._sw_last_logged_in: bool | None = None

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
        sw_health = self._probe_stealthwriter_health(active_jobs=active_jobs)
        sw_logged_in = sw_health.get("logged_in")
        sw_url = sw_health.get("current_url")

        snapshot = {
            "at": datetime.now(timezone.utc).isoformat(),
            "browser_alive": browser_alive,
            "cdp_alive": cdp_alive,
            "memory_usage": memory,
            "active_jobs": active_jobs,
            "stealthwriter_logged_in": sw_logged_in,
            "stealthwriter_url": sw_url,
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

        self._handle_stealthwriter_session_alerts(
            logged_in=sw_logged_in,
            current_url=sw_url,
            active_jobs=active_jobs,
        )

        with self._lock:
            self._last = snapshot

    def _probe_stealthwriter_health(self, *, active_jobs: int) -> dict[str, Any]:
        """Read provider tab status on the browser worker thread.

        Skip probes while jobs are active to avoid competing with an in-flight
        workflow on the shared browser thread.
        """
        if active_jobs > 0 or self._worker is None:
            return {}

        def _read() -> dict[str, Any]:
            providers = self._service.providers() if self._service is not None else {}
            provider = providers.get("stealthwriter")
            if provider is None:
                return {}
            if hasattr(provider, "health"):
                data = provider.health()
                if isinstance(data, dict):
                    return data
            return {}

        try:
            result = self._worker.submit(_read, timeout=8)
            return result if isinstance(result, dict) else {}
        except Exception as exc:  # noqa: BLE001
            print(f"[health-monitor] stealthwriter probe failed: {exc}", flush=True)
            return {}

    def _handle_stealthwriter_session_alerts(
        self,
        *,
        logged_in: Any,
        current_url: Any,
        active_jobs: int,
    ) -> None:
        if not isinstance(logged_in, bool):
            return

        previous = self._sw_last_logged_in
        self._sw_last_logged_in = logged_in

        try:
            from services.alerts.telegram_alerts import (
                notify_stealthwriter_session_down,
                notify_stealthwriter_session_restored,
            )
        except Exception:  # noqa: BLE001
            return

        if logged_in is False and previous is not False:
            notify_stealthwriter_session_down(
                current_url=str(current_url or ""),
                active_jobs=active_jobs,
            )
        elif logged_in is True and previous is False:
            notify_stealthwriter_session_restored(current_url=str(current_url or ""))
