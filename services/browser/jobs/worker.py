"""BrowserWorker — the single thread that owns Playwright and executes jobs.

Playwright's sync API is thread-affine: every browser call must happen on the
thread that started it. This worker is that thread. All browser access — job
execution AND synchronous endpoint calls (status/login/health) — is funneled
here via ``submit()`` / the job queue, which also serializes access to the one
Chrome instance.

Only one worker runs today. Multiple workers (each bound to its own pool
connection) can be added later without changing this contract.
"""

from __future__ import annotations

import os
import queue
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable

from services.browser.jobs.models import Job, JobStatus
from services.browser.jobs.retry import (
    JobTimeout,
    error_code_for,
    escalation_for_attempt,
    is_retryable_exception,
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class BrowserWorker(threading.Thread):
    def __init__(
        self,
        service: Any,
        job_manager: Any,
        metrics: Any,
        *,
        worker_id: str = "worker-1",
    ) -> None:
        super().__init__(name=f"browser-{worker_id}", daemon=True)
        self._service = service
        self._jobs = job_manager
        self._metrics = metrics
        self._worker_id = worker_id

        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._ready = threading.Event()
        self._stop = threading.Event()

        self._job_timeout = _env_int("BROWSER_JOB_TIMEOUT", 120)

    # ------------------------------------------------------------------ wiring
    def attach_job_manager(self, job_manager: Any) -> None:
        self._jobs = job_manager

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def job_timeout(self) -> int:
        return self._job_timeout

    def is_ready(self) -> bool:
        return self._ready.is_set()

    # ------------------------------------------------------------------ submit
    def submit(self, fn: Callable[[], Any], timeout: float | None = None) -> Any:
        """Run ``fn`` on the browser thread and return its result (blocking)."""
        if threading.current_thread() is self:
            return fn()
        if not self._ready.wait(60):
            raise RuntimeError("Browser worker is not ready")
        fut: "Future[Any]" = Future()
        self._queue.put(("call", fn, fut))
        return fut.result(timeout)

    def enqueue_job(self, job_id: str) -> None:
        self._queue.put(("job", job_id))

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ thread
    def run(self) -> None:
        try:
            self._service.start()  # binds Playwright to THIS thread
            print(f"[{self.name}] browser service started", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[{self.name}] initial start failed (will recover lazily): {exc}", flush=True)
        finally:
            self._ready.set()

        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            kind = item[0]
            try:
                if kind == "call":
                    _, fn, fut = item
                    if fut.set_running_or_notify_cancel():
                        try:
                            fut.set_result(fn())
                        except Exception as exc:  # noqa: BLE001
                            fut.set_exception(exc)
                elif kind == "job":
                    self._execute_job(item[1])
            except Exception as exc:  # noqa: BLE001
                print(f"[{self.name}] work item error: {exc}", flush=True)

    # ------------------------------------------------------------------ jobs
    def _browser_label(self) -> str:
        try:
            return f"{self._service.cdp_url}#0"
        except Exception:  # noqa: BLE001
            return "cdp"

    def _timeout_for(self, job: Job) -> int:
        if job.provider == "plagdetect":
            if job.operation == "highlights":
                return _env_int("PLAGDETECT_HIGHLIGHTS_TIMEOUT", 180)
            return _env_int("PLAGDETECT_JOB_TIMEOUT", 600)
        return self._job_timeout

    def _execute_job(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        if job.cancel_requested:
            self._jobs.finalize_cancelled(job)
            return

        self._jobs.mark_started(job)
        self._jobs.set_current(job, provider=job.provider, browser=self._browser_label())

        max_attempts = job.max_retries + 1
        attempt = 0
        while True:
            attempt += 1
            job.attempts = attempt
            job.timed_out = False
            self._jobs.update_status(
                job,
                JobStatus.RUNNING if attempt == 1 else JobStatus.RETRYING,
                progress=f"attempt {attempt}/{max_attempts}",
            )

            try:
                self._jobs.log(job, "Provider opened", f"{job.provider} (attempt {attempt})")
                self._jobs.log(job, "Workflow started", f"{job.provider}/{job.operation}")
                self._jobs.log(job, "Waiting result", f"timeout {self._timeout_for(job)}s")

                result = self._run_with_timeout(job, lambda: self._dispatch(job), timeout=self._timeout_for(job))

                if isinstance(result, dict) and result.get("success"):
                    self._jobs.log(job, "Result received", "success")
                    self._jobs.complete(job, result)
                    return

                # Non-exception failures from the workflow.
                code = (result or {}).get("error") if isinstance(result, dict) else "ERROR"
                if code == "LOGIN_REQUIRED":
                    self._jobs.log(job, "Result received", "LOGIN_REQUIRED")
                    message = (result or {}).get("message") or "LOGIN_REQUIRED"
                    self._jobs.fail(job, message, code="LOGIN_REQUIRED")
                    return
                if code == "NO_CHANGE":
                    # StealthWriter produced no change (daily limit / already human).
                    # Not retryable — retrying would only burn more quota.
                    self._jobs.log(job, "Result received", "NO_CHANGE")
                    message = (result or {}).get("message") or "NO_CHANGE"
                    self._jobs.fail(job, message, code="NO_CHANGE")
                    return
                # e.g. "text is required" — not retryable.
                self._jobs.fail(job, str(code), code="ERROR")
                return

            except JobTimeout:
                exc: BaseException = JobTimeout(f"exceeded {self._job_timeout}s")
                code = "TIMEOUT"
                retryable = True
                details = None
            except Exception as e:  # noqa: BLE001
                exc = e
                code = error_code_for(e)
                retryable = is_retryable_exception(e)
                details = getattr(e, "diagnostics", None)

            if job.cancel_requested:
                self._jobs.finalize_cancelled(job)
                return

            if (not retryable) or attempt >= max_attempts:
                self._jobs.fail(job, str(exc), code=code, details=details)
                return

            step = escalation_for_attempt(attempt)
            self._metrics.record_retry()
            self._jobs.log(
                job,
                "Retrying",
                f"attempt {attempt} failed ({code}); recovery: {step}",
                level="warn",
            )
            self._jobs.update_status(job, JobStatus.RETRYING, progress=f"recovery: {step}")
            self._escalate(step, job)

    def _dispatch(self, job: Job) -> dict[str, Any]:
        """Invoke the UNMODIFIED provider workflow for this job."""
        if job.provider == "stealthwriter":
            from services.browser.providers import stealthwriter as sw

            if job.operation == "humanize":
                return sw.humanize_text(str(job.payload.get("text") or ""))
            raise NotImplementedError(f"Unsupported stealthwriter operation: {job.operation!r}")
        if job.provider == "plagdetect":
            from services.browser.providers import plagdetect as pd

            if job.operation == "check":
                return pd.submit_check(
                    str(job.payload.get("file_path") or ""),
                    exclude_bibliography=bool(job.payload.get("exclude_bibliography")),
                    exclude_quotes=bool(job.payload.get("exclude_quotes")),
                    report_dir=job.payload.get("report_dir"),
                    submission_id=job.payload.get("submission_id"),
                )
            if job.operation == "highlights":
                return pd.submit_highlights(
                    external_id=str(job.payload.get("external_id") or ""),
                    report_dir=str(job.payload.get("report_dir") or ""),
                    submission_id=job.payload.get("submission_id"),
                )
            if job.operation == "fetch_reports":
                return pd.fetch_reports(
                    external_id=str(job.payload.get("external_id") or ""),
                    report_dir=str(job.payload.get("report_dir") or ""),
                    submission_id=job.payload.get("submission_id"),
                    fetch_similarity=bool(job.payload.get("fetch_similarity", True)),
                    fetch_ai=bool(job.payload.get("fetch_ai", True)),
                    fetch_highlights=bool(job.payload.get("fetch_highlights", False)),
                )
            raise NotImplementedError(f"Unsupported plagdetect operation: {job.operation!r}")
        raise NotImplementedError(f"Unsupported provider: {job.provider!r}")

    def _run_with_timeout(self, job: Job, fn: Callable[[], Any], *, timeout: int | None = None) -> Any:
        """Bound an attempt to the job timeout via a watchdog.

        The provider workflow is left untouched and all of its Playwright calls
        are timeout-bounded, so it returns within a finite window. The watchdog
        flags timeout; the escalation ladder then reopens/restarts as needed.
        """
        done = threading.Event()
        limit = timeout if timeout is not None else self._job_timeout

        def _watchdog() -> None:
            if not done.wait(limit):
                job.timed_out = True

        wd = threading.Thread(target=_watchdog, name=f"{self.name}-wd", daemon=True)
        wd.start()
        try:
            result = fn()
        finally:
            done.set()
        if job.timed_out:
            raise JobTimeout(f"attempt exceeded {limit}s")
        return result

    def _escalate(self, step: str | None, job: Job) -> None:
        if step == "refresh":
            try:
                page = self._service.get_or_create_page(job.provider)
                page.reload(wait_until="domcontentloaded")
            except Exception:  # noqa: BLE001
                pass
        elif step == "reopen":
            try:
                page = self._service.get_or_create_page(job.provider)
                page.close()
            except Exception:  # noqa: BLE001
                pass
            self._metrics.record_provider_restart()
        elif step == "restart":
            try:
                self._service.restart()
            except Exception:  # noqa: BLE001
                pass
            self._metrics.record_browser_restart()
