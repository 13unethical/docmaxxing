"""Orchestrates Turnitin submissions and browser job completion."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .store import REPORT_ROOT, TurnitinStore, UPLOAD_ROOT

log = logging.getLogger(__name__)

_TRANSIENT_JOB_CODES = frozenset(
    {
        "STALE_PAGE",
        "TIMEOUT",
        "AUTOMATION_ERROR",
        "SELECTOR_NOT_FOUND",
        "NAVIGATION_FAILED",
    }
)


class TurnitinService:
    def __init__(self, store: TurnitinStore | None = None) -> None:
        self.store = store or TurnitinStore()

    def save_upload(self, submission_id: str, filename: str, data: bytes) -> str:
        safe_name = Path(filename).name
        dest_dir = UPLOAD_ROOT / submission_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / safe_name
        dest.write_bytes(data)
        return str(dest.resolve())

    def report_dir(self, submission_id: str) -> Path:
        dest = REPORT_ROOT / submission_id
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def _extract_upload_text(self, row: dict[str, Any]) -> str:
        """Best-effort plain text from the stored Turnitin upload (raw for ML)."""
        upload_path = (row.get("upload_path") or "").strip()
        if not upload_path:
            return ""
        path = Path(upload_path)
        if not path.is_file():
            return ""
        try:
            data = path.read_bytes()
        except OSError:
            return ""
        # Plain text files
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md"}:
            try:
                return data.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                return ""
        try:
            from formatter.document_io import extract_text_from_document_bytes

            return extract_text_from_document_bytes(data, filename=path.name) or ""
        except Exception:  # noqa: BLE001
            try:
                return data.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                return ""

    def _log_detector_sample(
        self,
        *,
        user_id: int | None,
        row: dict[str, Any],
        ai_percentage: float | int | None,
        capture_type: str,
        ai_segments: list[Any] | None = None,
        human_segments: list[Any] | None = None,
    ) -> None:
        try:
            from services.dataset_logger import log_detection_event

            full_text = self._extract_upload_text(row)
            if not full_text.strip():
                # Still record a stub so we keep the score even if extraction fails.
                full_text = f"[turnitin_submission:{row.get('id')}|file:{row.get('filename')}]"
            log_detection_event(
                user_id,
                full_text,
                ai_percentage,
                ai_segments or [],
                human_segments or [],
                capture_type,
            )
        except Exception:  # noqa: BLE001
            pass

    def to_api_row(self, row: dict[str, Any]) -> dict[str, Any]:
        meta = row.get("meta") or {}
        ai_display = meta.get("ai_score_display")
        sim_display = meta.get("similarity_display")
        ai_score = row.get("ai_score")
        similarity = row.get("similarity")
        if not ai_display and ai_score is not None:
            ai_display = f"{int(ai_score) if ai_score == int(ai_score) else ai_score:g}%"
        if not sim_display and similarity is not None:
            sim_display = f"{int(similarity) if similarity == int(similarity) else similarity:g}%"
        hl_display = meta.get("ai_highlights_display")
        hl_score = row.get("ai_highlights")
        if not hl_display and hl_score is not None:
            hl_display = f"{int(hl_score) if hl_score == int(hl_score) else hl_score:g}%"
        return {
            "id": row["id"],
            "filename": row["filename"],
            "similarity": similarity,
            "similarityDisplay": sim_display,
            "aiScore": ai_score,
            "aiScoreDisplay": ai_display,
            "aiHighlights": hl_score,
            "aiHighlightsDisplay": hl_display,
            "status": row.get("status") or "queued",
            "createdAt": row.get("created_at"),
            "hasReport": bool(row.get("has_report")),
            "hasSimilarityReport": bool(row.get("has_similarity_report")),
            "hasAiReport": bool(row.get("has_ai_report")),
            "hasHighlightsReport": bool(row.get("has_highlights_report")),
            "highlightsStatus": row.get("highlights_status"),
            "errorMessage": row.get("error_message"),
            "externalId": row.get("external_id"),
            "aiUnavailable": meta.get("ai_unavailable") or None,
            "provider": meta.get("provider") or "plagdetect",
        }

    def _checkpoint_external_id(self, submission_id: str) -> str | None:
        try:
            from services.browser.providers.plagdetect import _load_checkpoint

            cp = _load_checkpoint(submission_id) or {}
        except Exception:  # noqa: BLE001
            return None
        ext = str(cp.get("external_id") or "").strip()
        return ext or None

    def _plagdetect_slot_consumed(self, submission_id: str, job: Any | None) -> bool:
        """True if a file already landed on PlagDetect — do not refund."""
        res = (job.result or {}) if job is not None else {}
        if res.get("similarity") is not None or str(res.get("external_id") or "").strip():
            return True
        row = self.store.get(submission_id) or {}
        if str(row.get("external_id") or "").strip():
            return True
        return bool(self._checkpoint_external_id(submission_id))

    def _queue_fetch_reports(
        self,
        *,
        submission_id: str,
        external_id: str,
        job_manager: Any,
        fetch_similarity: bool,
        fetch_ai: bool,
    ) -> None:
        if not external_id or (not fetch_similarity and not fetch_ai):
            return
        try:
            fetch_job = job_manager.create(
                "plagdetect",
                "fetch_reports",
                {
                    "external_id": external_id,
                    "report_dir": str(self.report_dir(submission_id)),
                    "submission_id": submission_id,
                    "fetch_similarity": fetch_similarity,
                    "fetch_ai": fetch_ai,
                    "fetch_highlights": False,
                },
                max_retries=1,
            )
            self.watch_fetch_reports_job(
                submission_id=submission_id,
                job_id=fetch_job.id,
                job_manager=job_manager,
            )
        except Exception:  # noqa: BLE001
            pass

    def _complete_without_refund(
        self,
        *,
        submission_id: str,
        job: Any | None,
        job_manager: Any,
        note: str | None = None,
    ) -> None:
        """Keep the charge: PlagDetect already has (or will have) the result."""
        res = (job.result or {}) if job is not None else {}
        row = self.store.get(submission_id) or {}
        external_id = (
            str(res.get("external_id") or "").strip()
            or str(row.get("external_id") or "").strip()
            or self._checkpoint_external_id(submission_id)
            or None
        )
        ai_unavailable = res.get("ai_unavailable")
        meta = dict(row.get("meta") or {})
        meta.update(
            {
                "elapsed_seconds": res.get("elapsed_seconds") or meta.get("elapsed_seconds"),
                "external_id": external_id,
                "ai_score_display": res.get("ai_score_display") or meta.get("ai_score_display"),
                "similarity_display": res.get("similarity_display")
                or meta.get("similarity_display"),
                "ai_unavailable": ai_unavailable or meta.get("ai_unavailable"),
                "salvaged": True,
            }
        )
        if note:
            meta["salvage_note"] = note
        has_scores = res.get("similarity") is not None or res.get("ai_score") is not None
        self.store.update(
            submission_id,
            status="completed" if has_scores else "running",
            similarity=res.get("similarity"),
            ai_score=res.get("ai_score"),
            external_id=external_id,
            similarity_report_path=res.get("similarity_report_path"),
            ai_report_path=res.get("ai_report_path"),
            error_message=None if has_scores else (note or "Waiting for PlagDetect reports."),
            meta_json=json.dumps(meta),
            completed_at=(
                job.finished_at.isoformat()
                if job is not None and getattr(job, "finished_at", None) and has_scores
                else None
            ),
        )
        if has_scores:
            try:
                from services.economy.site_settings import record_turnitin_success

                record_turnitin_success()
            except Exception:  # noqa: BLE001
                pass
        if external_id:
            need_sim = not res.get("similarity_report_path")
            need_ai = (not res.get("ai_report_path")) and not ai_unavailable
            self._queue_fetch_reports(
                submission_id=submission_id,
                external_id=external_id,
                job_manager=job_manager,
                fetch_similarity=need_sim,
                fetch_ai=need_ai,
            )

    def _maybe_refund(
        self,
        *,
        submission_id: str,
        user_id: int,
        cost: int,
        job: Any | None,
        job_manager: Any,
        refund_fn: Callable[..., None],
        error_message: str,
        error_code: str | None = None,
    ) -> None:
        if self._plagdetect_slot_consumed(submission_id, job):
            self._complete_without_refund(
                submission_id=submission_id,
                job=job,
                job_manager=job_manager,
                note=error_message,
            )
            return
        row = self.store.get(submission_id) or {}
        meta = dict(row.get("meta") or {})
        if error_code:
            meta["error_code"] = error_code
        self.store.update(
            submission_id,
            status="failed",
            error_message=error_message,
            meta_json=json.dumps(meta),
        )
        refund_fn(user_id, cost, "turnitin", ref_id=submission_id)

    def _requeue_check_job(
        self,
        *,
        submission_id: str,
        user_id: int,
        cost: int,
        job_manager: Any,
        wallet: Any,
        refund_fn: Callable[..., None],
    ) -> bool:
        """One automatic re-submit for transient PlagDetect failures (no extra charge)."""
        from services.browser.jobs.retry import MAX_RETRIES

        row = self.store.get(submission_id) or {}
        upload_path = (row.get("upload_path") or "").strip()
        if not upload_path or not Path(upload_path).is_file():
            return False
        # File already on PlagDetect — re-upload would duplicate + look like extra checks.
        if self._plagdetect_slot_consumed(submission_id, None):
            return False
        meta = dict(row.get("meta") or {})
        if int(meta.get("service_requeue_count") or 0) >= 1:
            return False
        meta["service_requeue_count"] = 1
        report_dir = str(self.report_dir(submission_id))
        job = job_manager.create(
            "plagdetect",
            "check",
            {
                "file_path": upload_path,
                "exclude_bibliography": bool(row.get("exclude_bibliography")),
                "exclude_quotes": bool(row.get("exclude_quotes")),
                "report_dir": report_dir,
                "submission_id": submission_id,
            },
            max_retries=MAX_RETRIES,
        )
        self.store.update(
            submission_id,
            status="queued",
            job_id=job.id,
            error_message=None,
            meta_json=json.dumps(meta),
        )
        self.watch_job(
            submission_id=submission_id,
            job_id=job.id,
            user_id=user_id,
            cost=cost,
            job_manager=job_manager,
            wallet=wallet,
            refund_fn=refund_fn,
        )
        return True

    def watch_job(
        self,
        *,
        submission_id: str,
        job_id: str,
        user_id: int,
        cost: int,
        job_manager: Any,
        wallet: Any,
        refund_fn: Callable[..., None],
    ) -> None:
        """Background thread: wait for browser job, persist result, refund on failure."""

        def _run() -> None:
            # Worker retries are (MAX_RETRIES + 1) * job timeout. The old
            # 690s cap refunded while Chrome was still polling, then started a
            # second upload in the same browser (~23 min charge+refund loops).
            from services.browser.jobs.retry import MAX_RETRIES

            job_timeout = int(os.environ.get("PLAGDETECT_JOB_TIMEOUT", "600"))
            process_timeout = job_timeout * (MAX_RETRIES + 1) + 180
            queue_timeout = int(os.environ.get("PLAGDETECT_QUEUE_WAIT", "10800"))
            self.store.update(submission_id, status="running")
            job = None
            deadline = time.monotonic() + queue_timeout + process_timeout
            started_running_at: float | None = None
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Check timed out waiting in the Turnitin queue.")
                    job = job_manager.get(job_id)
                    if job is None:
                        break
                    status_now = (
                        job.status.value if hasattr(job.status, "value") else str(job.status)
                    )
                    if getattr(job, "is_terminal", False) or status_now in (
                        "COMPLETED",
                        "FAILED",
                        "CANCELLED",
                    ):
                        break
                    if status_now not in ("QUEUED", "queued") and started_running_at is None:
                        started_running_at = time.monotonic()
                    if started_running_at is not None:
                        if time.monotonic() - started_running_at > process_timeout:
                            raise TimeoutError("Check timed out before PlagDetect finished.")
                    slice_s = min(20.0, max(1.0, remaining))
                    job_manager.wait(job_id, timeout=slice_s)
            except Exception as exc:  # noqa: BLE001
                job = job_manager.get(job_id)
                self._maybe_refund(
                    submission_id=submission_id,
                    user_id=user_id,
                    cost=cost,
                    job=job,
                    job_manager=job_manager,
                    refund_fn=refund_fn,
                    error_message=str(exc),
                    error_code="TIMEOUT",
                )
                return

            job = job_manager.get(job_id)
            if job is None:
                self._maybe_refund(
                    submission_id=submission_id,
                    user_id=user_id,
                    cost=cost,
                    job=None,
                    job_manager=job_manager,
                    refund_fn=refund_fn,
                    error_message="Job not found",
                    error_code="ERROR",
                )
                return

            status = job.status.value if hasattr(job.status, "value") else str(job.status)
            if status == "COMPLETED":
                res = job.result or {}
                ai_unavailable = res.get("ai_unavailable")
                meta = {
                    "elapsed_seconds": res.get("elapsed_seconds"),
                    "external_id": res.get("external_id"),
                    "ai_score_display": res.get("ai_score_display"),
                    "similarity_display": res.get("similarity_display"),
                    "ai_unavailable": ai_unavailable,
                }
                self.store.update(
                    submission_id,
                    status="completed",
                    similarity=res.get("similarity"),
                    ai_score=res.get("ai_score"),
                    external_id=res.get("external_id"),
                    similarity_report_path=res.get("similarity_report_path"),
                    ai_report_path=res.get("ai_report_path"),
                    meta_json=json.dumps(meta),
                    completed_at=job.finished_at.isoformat() if job.finished_at else None,
                )
                try:
                    from services.economy.site_settings import record_turnitin_success

                    record_turnitin_success()
                except Exception:  # noqa: BLE001
                    pass

                need_sim = not res.get("similarity_report_path")
                need_ai = (not res.get("ai_report_path")) and not ai_unavailable
                external_id = res.get("external_id")
                if external_id and (need_sim or need_ai):
                    self._queue_fetch_reports(
                        submission_id=submission_id,
                        external_id=str(external_id),
                        job_manager=job_manager,
                        fetch_similarity=need_sim,
                        fetch_ai=need_ai,
                    )
                return

            if status not in ("FAILED", "CANCELLED"):
                # Still running/queued — never start a second upload. That fights
                # the live Chrome job and is what produced today's double refunds.
                self._maybe_refund(
                    submission_id=submission_id,
                    user_id=user_id,
                    cost=cost,
                    job=job,
                    job_manager=job_manager,
                    refund_fn=refund_fn,
                    error_message="Check timed out before PlagDetect finished.",
                    error_code="TIMEOUT",
                )
                return

            code = job.error_code or "ERROR"
            message = job.error or code
            res = job.result or {}
            if res.get("similarity") is not None or self._plagdetect_slot_consumed(
                submission_id, job
            ):
                self._complete_without_refund(
                    submission_id=submission_id,
                    job=job,
                    job_manager=job_manager,
                    note=None if res.get("similarity") is not None else message,
                )
                return
            if code in _TRANSIENT_JOB_CODES and code not in ("LOGIN_REQUIRED",):
                if self._requeue_check_job(
                    submission_id=submission_id,
                    user_id=user_id,
                    cost=cost,
                    job_manager=job_manager,
                    wallet=wallet,
                    refund_fn=refund_fn,
                ):
                    return
            if code == "LOGIN_REQUIRED":
                self.store.update(
                    submission_id,
                    status="failed",
                    error_message=message,
                    meta_json=json.dumps({"error_code": code}),
                )
                return
            self._maybe_refund(
                submission_id=submission_id,
                user_id=user_id,
                cost=cost,
                job=job,
                job_manager=job_manager,
                refund_fn=refund_fn,
                error_message=message,
                error_code=code,
            )

        threading.Thread(target=_run, name=f"turnitin-{submission_id[:8]}", daemon=True).start()

    def start_tca_check(
        self,
        *,
        submission_id: str,
        user_id: int,
        cost: int,
        refund_fn: Callable[..., None],
    ) -> None:
        """Background thread: official Turnitin Core API, no browser login."""

        def _run() -> None:
            self._run_tca_check(
                submission_id=submission_id,
                user_id=user_id,
                cost=cost,
                refund_fn=refund_fn,
            )

        threading.Thread(
            target=_run,
            name=f"turnitin-tca-{submission_id[:8]}",
            daemon=True,
        ).start()

    @staticmethod
    def uses_plagdetect_http(row: dict[str, Any] | None) -> bool:
        meta = (row or {}).get("meta") or {}
        if meta.get("provider") == "turnitin":
            return False
        if str(meta.get("transport") or "").strip().lower() == "browser":
            return False
        if str(meta.get("transport") or "").strip().lower() == "api":
            return True
        from services.plagdetect_api import prefer_plagdetect_api

        return prefer_plagdetect_api()

    def start_plagdetect_api_check(
        self,
        *,
        submission_id: str,
        user_id: int,
        cost: int,
        refund_fn: Callable[..., None],
    ) -> None:
        def _run() -> None:
            self._run_plagdetect_api_check(
                submission_id=submission_id,
                user_id=user_id,
                cost=cost,
                refund_fn=refund_fn,
            )

        threading.Thread(
            target=_run,
            name=f"turnitin-pdapi-{submission_id[:8]}",
            daemon=True,
        ).start()

    def _run_plagdetect_api_check(
        self,
        *,
        submission_id: str,
        user_id: int,
        cost: int,
        refund_fn: Callable[..., None],
    ) -> None:
        from services.plagdetect_api.client import PlagDetectAPIClient, PlagDetectAPIError

        self.store.update(submission_id, status="running")
        row = self.store.get(submission_id) or {}
        upload_path = (row.get("upload_path") or "").strip()
        filename = row.get("filename") or "submission"
        meta = dict(row.get("meta") or {})
        meta["provider"] = "plagdetect"
        meta["transport"] = "api"
        self.store.update(submission_id, meta_json=json.dumps(meta))
        external_id = str(row.get("external_id") or "").strip() or None
        started = time.monotonic()
        try:
            client = PlagDetectAPIClient.from_env()

            def _on_created(pd_id: str) -> None:
                nonlocal external_id
                external_id = pd_id
                latest = dict((self.store.get(submission_id) or {}).get("meta") or {})
                latest["provider"] = "plagdetect"
                latest["transport"] = "api"
                latest["external_id"] = pd_id
                self.store.update(
                    submission_id,
                    external_id=pd_id,
                    meta_json=json.dumps(latest),
                )

            result = client.check_file(
                file_path=upload_path,
                filename=filename,
                exclude_bibliography=bool(row.get("exclude_bibliography")),
                exclude_quotes=bool(row.get("exclude_quotes")),
                report_dir=self.report_dir(submission_id),
                on_created=_on_created,
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc) or "PlagDetect API check failed."
            if isinstance(exc, PlagDetectAPIError) and exc.status_code in (401, 403):
                message = (
                    "PlagDetect rejected the API credentials (HTTP "
                    f"{exc.status_code}). Open plagdetect.org → API → API Keys "
                    "and confirm the Key and Secret are active."
                )
            latest = dict((self.store.get(submission_id) or {}).get("meta") or {})
            latest["provider"] = "plagdetect"
            latest["transport"] = "api"
            latest["error_code"] = getattr(exc, "status_code", None) or "ERROR"
            if external_id:
                latest["salvage_note"] = message
                self.store.update(
                    submission_id,
                    status="failed",
                    error_message=message,
                    external_id=external_id,
                    meta_json=json.dumps(latest),
                )
                return
            self.store.update(
                submission_id,
                status="failed",
                error_message=message,
                meta_json=json.dumps(latest),
            )
            refund_fn(user_id, cost, "turnitin", ref_id=submission_id)
            return

        elapsed = int(time.monotonic() - started)
        meta = dict((self.store.get(submission_id) or {}).get("meta") or {})
        meta.update(
            {
                "provider": "plagdetect",
                "transport": "api",
                "elapsed_seconds": elapsed,
                "external_id": result.get("external_id"),
                "similarity_display": result.get("similarity_display"),
                "ai_score_display": result.get("ai_score_display"),
                "ai_unavailable": result.get("ai_unavailable"),
                "word_count": result.get("word_count"),
                "sandbox": result.get("sandbox"),
            }
        )
        self.store.update(
            submission_id,
            status="completed",
            similarity=result.get("similarity"),
            ai_score=result.get("ai_score"),
            external_id=result.get("external_id"),
            similarity_report_path=result.get("similarity_report_path"),
            ai_report_path=result.get("ai_report_path"),
            error_message=None,
            meta_json=json.dumps(meta),
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        try:
            from services.economy.site_settings import record_turnitin_success

            record_turnitin_success()
        except Exception:  # noqa: BLE001
            pass

    def fetch_plagdetect_api_reports(
        self,
        submission_id: str,
        *,
        fetch_similarity: bool = True,
        fetch_ai: bool = True,
        fetch_highlights: bool = False,
    ) -> dict[str, Any]:
        from services.plagdetect_api.client import PlagDetectAPIClient

        row = self.store.get(submission_id) or {}
        external_id = str(row.get("external_id") or "").strip()
        if not external_id:
            return {"success": False, "error": "Submission id missing."}
        client = PlagDetectAPIClient.from_env()
        result = client.fetch_reports(
            submission_id=external_id,
            report_dir=self.report_dir(submission_id),
            fetch_similarity=fetch_similarity,
            fetch_ai=fetch_ai,
            fetch_highlights=fetch_highlights,
        )
        fields: dict[str, Any] = {}
        if result.get("similarity_report_path"):
            fields["similarity_report_path"] = result["similarity_report_path"]
        if result.get("ai_report_path"):
            fields["ai_report_path"] = result["ai_report_path"]
        if result.get("ai_highlights_report_path"):
            fields["ai_highlights_report_path"] = result["ai_highlights_report_path"]
            fields["highlights_status"] = "completed"
        if fields:
            self.store.update(submission_id, **fields)
        return {"success": True, "report": self.to_api_row(self.store.get(submission_id) or row)}

    def start_plagdetect_api_highlights(
        self,
        *,
        submission_id: str,
        retry: bool | None = None,
    ) -> None:
        row = self.store.get(submission_id) or {}
        prev = str(row.get("highlights_status") or "").strip().lower()
        use_retry = bool(retry) if retry is not None else prev == "failed"
        self.store.update(submission_id, highlights_status="running")

        def _run() -> None:
            self._run_plagdetect_api_highlights(submission_id=submission_id, retry=use_retry)

        threading.Thread(
            target=_run,
            name=f"turnitin-pdapi-hl-{submission_id[:8]}",
            daemon=True,
        ).start()

    def _run_plagdetect_api_highlights(
        self,
        *,
        submission_id: str,
        retry: bool = False,
    ) -> dict[str, Any]:
        from services.plagdetect_api.client import PlagDetectAPIClient, PlagDetectAPIError

        self.store.update(submission_id, highlights_status="running")
        row = self.store.get(submission_id) or {}
        external_id = str(row.get("external_id") or "").strip()
        if not external_id:
            self.store.update(
                submission_id,
                highlights_status="failed",
                error_message="PlagDetect submission id missing.",
            )
            return {"success": False}
        try:
            client = PlagDetectAPIClient.from_env()
            result = client.fetch_highlights(
                submission_id=external_id,
                report_dir=self.report_dir(submission_id),
                retry=retry,
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc) or "Could not fetch AI Highlights."
            if isinstance(exc, PlagDetectAPIError) and exc.status_code in (401, 403):
                message = (
                    "PlagDetect rejected the API credentials. "
                    "Confirm Key/Secret on plagdetect.org → API Keys."
                )
            self.store.update(
                submission_id,
                highlights_status="failed",
                error_message=message,
            )
            return {"success": False, "error": message}

        meta = dict((self.store.get(submission_id) or {}).get("meta") or {})
        meta["provider"] = "plagdetect"
        meta["transport"] = "api"
        if result.get("ai_score_display"):
            meta["ai_score_display"] = result["ai_score_display"]
        if result.get("ai_highlights_display"):
            meta["ai_highlights_display"] = result["ai_highlights_display"]
        hl_path = result.get("ai_highlights_report_path")
        fields: dict[str, Any] = {
            "meta_json": json.dumps(meta),
            "highlights_status": "completed" if hl_path else "failed",
        }
        if result.get("ai_score") is not None:
            fields["ai_score"] = result["ai_score"]
        if result.get("ai_highlights") is not None:
            fields["ai_highlights"] = result["ai_highlights"]
        if hl_path:
            fields["ai_highlights_report_path"] = hl_path
        if not hl_path:
            fields["error_message"] = "PlagDetect did not return a highlights PDF."
        self.store.update(submission_id, **fields)
        return {
            "success": bool(hl_path),
            "report": self.to_api_row(self.store.get(submission_id) or row),
        }

    def _run_tca_check(
        self,
        *,
        submission_id: str,
        user_id: int,
        cost: int,
        refund_fn: Callable[..., None],
    ) -> None:
        from services.turnitin_api.client import TurnitinAPIError, TurnitinCoreClient

        self.store.update(submission_id, status="running")
        row = self.store.get(submission_id) or {}
        upload_path = (row.get("upload_path") or "").strip()
        filename = row.get("filename") or "submission"
        meta = dict(row.get("meta") or {})
        meta["provider"] = "turnitin"
        self.store.update(submission_id, meta_json=json.dumps(meta))
        external_id = str(row.get("external_id") or "").strip() or None
        started = time.monotonic()
        try:
            client = TurnitinCoreClient.from_env()

            def _on_created(tca_id: str) -> None:
                nonlocal external_id
                external_id = tca_id
                latest = dict((self.store.get(submission_id) or {}).get("meta") or {})
                latest["provider"] = "turnitin"
                latest["external_id"] = tca_id
                self.store.update(
                    submission_id,
                    external_id=tca_id,
                    meta_json=json.dumps(latest),
                )

            result = client.check_file(
                file_path=upload_path,
                filename=filename,
                owner_id=f"user_{user_id}",
                exclude_bibliography=bool(row.get("exclude_bibliography")),
                exclude_quotes=bool(row.get("exclude_quotes")),
                report_dir=self.report_dir(submission_id),
                on_created=_on_created,
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc) or "Turnitin API check failed."
            if isinstance(exc, TurnitinAPIError) and exc.status_code in (401, 403):
                message = (
                    "Turnitin rejected the API credentials (HTTP "
                    f"{exc.status_code}). These Key/Secret pairs are often LTI "
                    "keys. In Turnitin admin → Integrations, use "
                    "Generate TCA Scope (not LTI Scope) and paste that Secret. "
                    "If you already have a TCA key, set TURNITIN_API_BASE to "
                    "your account host, e.g. https://app-us.turnitin.com"
                )
            latest = dict((self.store.get(submission_id) or {}).get("meta") or {})
            latest["provider"] = "turnitin"
            latest["error_code"] = getattr(exc, "status_code", None) or "ERROR"
            if external_id:
                latest["salvage_note"] = message
                self.store.update(
                    submission_id,
                    status="failed",
                    error_message=message,
                    external_id=external_id,
                    meta_json=json.dumps(latest),
                )
                return
            self.store.update(
                submission_id,
                status="failed",
                error_message=message,
                meta_json=json.dumps(latest),
            )
            refund_fn(user_id, cost, "turnitin", ref_id=submission_id)
            return

        elapsed = int(time.monotonic() - started)
        meta = dict((self.store.get(submission_id) or {}).get("meta") or {})
        meta.update(
            {
                "provider": "turnitin",
                "elapsed_seconds": elapsed,
                "external_id": result.get("external_id"),
                "similarity_display": result.get("similarity_display"),
                "ai_score_display": result.get("ai_score_display"),
                "ai_highlights_display": result.get("ai_highlights_display"),
                "ai_unavailable": result.get("ai_unavailable"),
            }
        )
        hl_path = result.get("ai_highlights_report_path") or result.get("ai_report_path")
        self.store.update(
            submission_id,
            status="completed",
            similarity=result.get("similarity"),
            ai_score=result.get("ai_score"),
            ai_highlights=result.get("ai_highlights"),
            external_id=result.get("external_id"),
            similarity_report_path=result.get("similarity_report_path"),
            ai_report_path=result.get("ai_report_path") or hl_path,
            ai_highlights_report_path=hl_path,
            highlights_status="completed" if hl_path else None,
            error_message=None,
            meta_json=json.dumps(meta),
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        try:
            from services.economy.site_settings import record_turnitin_success

            record_turnitin_success()
        except Exception:  # noqa: BLE001
            pass

    def fetch_tca_similarity_pdf(self, submission_id: str) -> str | None:
        """Re-download the similarity PDF for an official Turnitin submission."""
        from services.turnitin_api.client import TurnitinCoreClient

        row = self.store.get(submission_id) or {}
        external_id = str(row.get("external_id") or "").strip()
        if not external_id:
            return None
        client = TurnitinCoreClient.from_env()
        pdf_id = client.request_similarity_pdf(external_id)
        pdf_bytes = client.wait_for_pdf(external_id, pdf_id)
        dest = self.report_dir(submission_id) / "similarity_report.pdf"
        dest.write_bytes(pdf_bytes)
        path = str(dest.resolve())
        self.store.update(submission_id, similarity_report_path=path)
        return path

    def start_tca_highlights(self, *, submission_id: str, user_id: int) -> dict[str, Any]:
        """Open Turnitin Cloud Viewer (AI highlights) and fetch the PDF in the background."""
        from services.turnitin_api.client import TurnitinCoreClient

        row = self.store.get(submission_id) or {}
        external_id = str(row.get("external_id") or "").strip()
        viewer_url = None
        if external_id:
            try:
                client = TurnitinCoreClient.from_env()
                viewer_url = client.create_viewer_url(external_id, f"user_{user_id}")
            except Exception as exc:  # noqa: BLE001
                log.warning("Turnitin viewer URL failed: %s", exc)
        self.store.update(submission_id, highlights_status="running")

        def _run() -> None:
            self._run_tca_highlights(submission_id=submission_id, user_id=user_id)

        threading.Thread(
            target=_run,
            name=f"turnitin-tca-hl-{submission_id[:8]}",
            daemon=True,
        ).start()
        return {"viewer_url": viewer_url}

    def _run_tca_highlights(self, *, submission_id: str, user_id: int) -> dict[str, Any]:
        from services.turnitin_api.client import TurnitinCoreClient

        self.store.update(submission_id, highlights_status="running")
        row = self.store.get(submission_id) or {}
        external_id = str(row.get("external_id") or "").strip()
        if not external_id:
            self.store.update(
                submission_id,
                highlights_status="failed",
                error_message="Turnitin submission id missing.",
            )
            return {"success": False}
        try:
            client = TurnitinCoreClient.from_env()
            result = client.fetch_ai_highlights(
                tca_submission_id=external_id,
                owner_id=f"user_{user_id}",
                report_dir=self.report_dir(submission_id),
                include_viewer=True,
            )
        except Exception as exc:  # noqa: BLE001
            self.store.update(
                submission_id,
                highlights_status="failed",
                error_message=str(exc) or "Could not fetch AI Highlights.",
            )
            return {"success": False, "error": str(exc)}

        meta = dict((self.store.get(submission_id) or {}).get("meta") or {})
        if result.get("ai_score_display"):
            meta["ai_score_display"] = result["ai_score_display"]
        if result.get("ai_highlights_display"):
            meta["ai_highlights_display"] = result["ai_highlights_display"]
        if result.get("ai_unavailable"):
            meta["ai_unavailable"] = result["ai_unavailable"]
        elif "ai_unavailable" in meta:
            meta.pop("ai_unavailable", None)

        hl_path = result.get("ai_highlights_report_path") or result.get("ai_report_path")
        has_artifact = bool(hl_path or result.get("viewer_url") or result.get("ai_highlights_display"))
        fields: dict[str, Any] = {
            "meta_json": json.dumps(meta),
            "highlights_status": "completed" if has_artifact else "failed",
        }
        if result.get("ai_score") is not None:
            fields["ai_score"] = result["ai_score"]
        if result.get("ai_highlights") is not None:
            fields["ai_highlights"] = result["ai_highlights"]
        if result.get("ai_report_path") or hl_path:
            fields["ai_report_path"] = result.get("ai_report_path") or hl_path
        if hl_path:
            fields["ai_highlights_report_path"] = hl_path
        if not has_artifact:
            fields["error_message"] = (
                result.get("ai_unavailable")
                or "Turnitin did not return an AI highlights report for this file."
            )
        self.store.update(submission_id, **fields)
        return {
            "success": has_artifact,
            "viewer_url": result.get("viewer_url"),
            "report": self.to_api_row(self.store.get(submission_id) or row),
        }

    def watch_highlights_job(
        self,
        *,
        submission_id: str,
        job_id: str,
        job_manager: Any,
    ) -> None:
        """Background thread: wait for highlights job and persist result."""

        def _run() -> None:
            timeout = int(os.environ.get("PLAGDETECT_HIGHLIGHTS_TIMEOUT", "180")) + 60
            self.store.update(submission_id, highlights_status="running")
            try:
                job_manager.wait(job_id, timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                self.store.update(
                    submission_id,
                    highlights_status="failed",
                    error_message=str(exc),
                )
                return

            job = job_manager.get(job_id)
            if job is None:
                self.store.update(submission_id, highlights_status="failed")
                return

            status = job.status.value if hasattr(job.status, "value") else str(job.status)
            if status == "COMPLETED":
                res = job.result or {}
                row = self.store.get(submission_id) or {}
                meta = dict(row.get("meta") or {})
                if res.get("ai_highlights_display"):
                    meta["ai_highlights_display"] = res.get("ai_highlights_display")
                self.store.update(
                    submission_id,
                    highlights_status="completed",
                    ai_highlights=res.get("ai_highlights"),
                    ai_highlights_report_path=res.get("ai_highlights_report_path"),
                    meta_json=json.dumps(meta),
                )
                try:
                    updated = self.store.get(submission_id) or row
                    hl_pct = res.get("ai_highlights")
                    if hl_pct is None:
                        hl_pct = updated.get("ai_highlights")
                    if hl_pct is None:
                        hl_pct = updated.get("ai_score")
                    self._log_detector_sample(
                        user_id=updated.get("user_id"),
                        row=updated,
                        ai_percentage=hl_pct,
                        capture_type="manual_highlights",
                        ai_segments=[],
                        human_segments=[],
                    )
                except Exception:  # noqa: BLE001
                    pass
                return

            message = job.error or job.error_code or "Highlights failed"
            self.store.update(
                submission_id,
                highlights_status="failed",
                error_message=message,
            )

        threading.Thread(
            target=_run,
            name=f"turnitin-hl-{submission_id[:8]}",
            daemon=True,
        ).start()

    def watch_fetch_reports_job(
        self,
        *,
        submission_id: str,
        job_id: str,
        job_manager: Any,
    ) -> None:
        """Background thread: wait for report re-download and persist paths."""

        def _run() -> None:
            timeout = int(os.environ.get("PLAGDETECT_HIGHLIGHTS_TIMEOUT", "180")) + 90
            try:
                job_manager.wait(job_id, timeout=timeout)
            except Exception:  # noqa: BLE001
                return

            job = job_manager.get(job_id)
            if job is None:
                return
            status = job.status.value if hasattr(job.status, "value") else str(job.status)
            if status != "COMPLETED":
                return

            res = job.result or {}
            row = self.store.get(submission_id) or {}
            meta = dict(row.get("meta") or {})
            if res.get("ai_highlights_display"):
                meta["ai_highlights_display"] = res.get("ai_highlights_display")

            fields: dict[str, Any] = {"meta_json": json.dumps(meta)}
            if res.get("similarity_report_path"):
                fields["similarity_report_path"] = res["similarity_report_path"]
            if res.get("ai_report_path"):
                fields["ai_report_path"] = res["ai_report_path"]
            if res.get("ai_highlights") is not None:
                fields["ai_highlights"] = res["ai_highlights"]
            if res.get("ai_highlights_report_path"):
                fields["ai_highlights_report_path"] = res["ai_highlights_report_path"]
                fields["highlights_status"] = "completed"
            self.store.update(submission_id, **fields)

        threading.Thread(
            target=_run,
            name=f"turnitin-fetch-{submission_id[:8]}",
            daemon=True,
        ).start()
