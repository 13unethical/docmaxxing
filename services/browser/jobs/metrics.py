"""Metrics — process-wide counters for the browser execution engine."""

from __future__ import annotations

import threading
import time
from typing import Any


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start = time.time()
        self.jobs_created = 0
        self.jobs_completed = 0
        self.jobs_failed = 0
        self.jobs_cancelled = 0
        self.browser_restarts = 0
        self.provider_restarts = 0
        self.retry_count = 0
        self._exec_times: list[float] = []

    def record_created(self) -> None:
        with self._lock:
            self.jobs_created += 1

    def record_execution(self, seconds: float) -> None:
        with self._lock:
            self.jobs_completed += 1
            self._exec_times.append(float(seconds))

    def record_failure(self) -> None:
        with self._lock:
            self.jobs_failed += 1

    def record_cancelled(self) -> None:
        with self._lock:
            self.jobs_cancelled += 1

    def record_retry(self) -> None:
        with self._lock:
            self.retry_count += 1

    def record_browser_restart(self) -> None:
        with self._lock:
            self.browser_restarts += 1

    def record_provider_restart(self) -> None:
        with self._lock:
            self.provider_restarts += 1

    @property
    def uptime(self) -> float:
        return round(time.time() - self._start, 1)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg = round(sum(self._exec_times) / len(self._exec_times), 3) if self._exec_times else 0.0
            return {
                "uptime": self.uptime,
                "jobs_created": self.jobs_created,
                "jobs_completed": self.jobs_completed,
                "jobs_failed": self.jobs_failed,
                "jobs_cancelled": self.jobs_cancelled,
                "average_execution_time": avg,
                "browser_restarts": self.browser_restarts,
                "provider_restarts": self.provider_restarts,
                "retry_count": self.retry_count,
            }
