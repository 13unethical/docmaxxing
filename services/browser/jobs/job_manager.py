"""JobManager — creates, tracks, and finalizes jobs.

Thread-safe. Holds job state, structured logs, and per-job completion events so
callers can wait synchronously for a result.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable

from services.browser.jobs.models import Job, JobStatus, TERMINAL_STATES


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobManager:
    def __init__(
        self,
        *,
        enqueue: Callable[[str], None] | None = None,
        metrics: Any | None = None,
        max_jobs: int = 500,
    ) -> None:
        self._lock = threading.RLock()
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._events: dict[str, threading.Event] = {}
        self._enqueue = enqueue
        self._metrics = metrics
        self._max_jobs = max_jobs

    def attach_enqueue(self, enqueue: Callable[[str], None]) -> None:
        self._enqueue = enqueue

    # ------------------------------------------------------------------ create
    def create(
        self,
        provider: str,
        operation: str,
        payload: dict[str, Any] | None = None,
        *,
        max_retries: int = 3,
    ) -> Job:
        job = Job(
            provider=provider,
            operation=operation,
            payload=payload or {},
            max_retries=max_retries,
        )
        with self._lock:
            self._jobs[job.id] = job
            self._events[job.id] = threading.Event()
            self._evict_if_needed()
        job.log("Job created", f"provider={provider} operation={operation}")
        if self._metrics is not None:
            self._metrics.record_created()
        if self._enqueue is not None:
            self._enqueue(job.id)
        return job

    def _evict_if_needed(self) -> None:
        while len(self._jobs) > self._max_jobs:
            old_id, old_job = next(iter(self._jobs.items()))
            if not old_job.is_terminal:
                break
            self._jobs.pop(old_id, None)
            self._events.pop(old_id, None)

    # ------------------------------------------------------------------ reads
    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if not j.is_terminal)

    # ------------------------------------------------------------------ updates
    def update_status(self, job: Job, status: JobStatus, progress: str | None = None) -> None:
        with self._lock:
            job.status = status
            if progress is not None:
                job.progress = progress

    def set_current(self, job: Job, *, provider: str | None = None, browser: str | None = None) -> None:
        with self._lock:
            if provider is not None:
                job.current_provider = provider
            if browser is not None:
                job.current_browser = browser

    def mark_started(self, job: Job) -> None:
        with self._lock:
            job.started_at = job.started_at or _now()
            job.status = JobStatus.STARTING
            job.progress = "starting"
        job.log("Job started")

    def log(self, job: Job, event: str, message: str = "", level: str = "info") -> None:
        job.log(event, message, level)

    # ------------------------------------------------------------------ finalize
    def complete(self, job: Job, result: dict[str, Any]) -> None:
        with self._lock:
            job.result = result
            job.status = JobStatus.COMPLETED
            job.progress = "completed"
            job.finished_at = _now()
        job.log("Completed", f"elapsed {job.elapsed_seconds}s")
        job.log("Elapsed time", f"{job.elapsed_seconds}s")
        if self._metrics is not None:
            self._metrics.record_execution(job.elapsed_seconds)
        self._signal(job.id)

    def fail(
        self,
        job: Job,
        error: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            job.error = error
            job.error_code = code
            job.error_details = details
            job.status = JobStatus.FAILED
            job.progress = "failed"
            job.finished_at = _now()
        job.log("Failed", f"{code or 'ERROR'}: {error}", level="error")
        job.log("Elapsed time", f"{job.elapsed_seconds}s")
        if self._metrics is not None:
            self._metrics.record_failure()
        self._signal(job.id)

    def cancel(self, job_id: str) -> bool:
        """Request cancellation. Queued jobs are cancelled immediately."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.is_terminal:
                return False
            job.cancel_requested = True
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELLED
                job.progress = "cancelled"
                job.finished_at = _now()
                terminal = True
            else:
                terminal = False
        if terminal:
            job.log("Cancelled", "cancelled while queued")
            if self._metrics is not None:
                self._metrics.record_cancelled()
            self._signal(job_id)
        else:
            job.log("Cancel requested", "will stop after current step")
        return True

    def finalize_cancelled(self, job: Job) -> None:
        with self._lock:
            job.status = JobStatus.CANCELLED
            job.progress = "cancelled"
            job.finished_at = _now()
        job.log("Cancelled")
        if self._metrics is not None:
            self._metrics.record_cancelled()
        self._signal(job.id)

    # ------------------------------------------------------------------ waiting
    def wait(self, job_id: str, timeout: float | None = None) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            event = self._events.get(job_id)
        if job is None:
            return None
        if event is not None and not job.is_terminal:
            event.wait(timeout)
        return job

    def _signal(self, job_id: str) -> None:
        with self._lock:
            event = self._events.get(job_id)
        if event is not None:
            event.set()
