"""Orchestrates Turnitin submissions and browser job completion."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable

from .store import REPORT_ROOT, TurnitinStore, UPLOAD_ROOT

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
        }

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
            timeout = int(os.environ.get("PLAGDETECT_JOB_TIMEOUT", "600")) + 90
            self.store.update(submission_id, status="running")
            try:
                job_manager.wait(job_id, timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                self.store.update(
                    submission_id,
                    status="failed",
                    error_message=str(exc),
                )
                refund_fn(user_id, cost, "turnitin", ref_id=submission_id)
                return

            job = job_manager.get(job_id)
            if job is None:
                self.store.update(submission_id, status="failed", error_message="Job not found")
                refund_fn(user_id, cost, "turnitin", ref_id=submission_id)
                return

            status = job.status.value if hasattr(job.status, "value") else str(job.status)
            if status == "COMPLETED":
                res = job.result or {}
                meta = {
                    "elapsed_seconds": res.get("elapsed_seconds"),
                    "external_id": res.get("external_id"),
                    "ai_score_display": res.get("ai_score_display"),
                    "similarity_display": res.get("similarity_display"),
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

                # If scores landed but PDFs did not, queue a follow-up download.
                need_sim = not res.get("similarity_report_path")
                need_ai = not res.get("ai_report_path")
                external_id = res.get("external_id")
                if external_id and (need_sim or need_ai):
                    try:
                        fetch_job = job_manager.create(
                            "plagdetect",
                            "fetch_reports",
                            {
                                "external_id": external_id,
                                "report_dir": str(self.report_dir(submission_id)),
                                "submission_id": submission_id,
                                "fetch_similarity": need_sim,
                                "fetch_ai": need_ai,
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
                return

            if status not in ("FAILED", "CANCELLED"):
                if self._requeue_check_job(
                    submission_id=submission_id,
                    user_id=user_id,
                    cost=cost,
                    job_manager=job_manager,
                    wallet=wallet,
                    refund_fn=refund_fn,
                ):
                    return
                self.store.update(
                    submission_id,
                    status="failed",
                    error_message="Check timed out before PlagDetect finished.",
                    meta_json=json.dumps({"error_code": "TIMEOUT"}),
                )
                refund_fn(user_id, cost, "turnitin", ref_id=submission_id)
                return

            code = job.error_code or "ERROR"
            message = job.error or code
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
            self.store.update(
                submission_id,
                status="failed",
                error_message=message,
                meta_json=json.dumps({"error_code": code}),
            )
            if code not in ("LOGIN_REQUIRED",):
                refund_fn(user_id, cost, "turnitin", ref_id=submission_id)

        threading.Thread(target=_run, name=f"turnitin-{submission_id[:8]}", daemon=True).start()

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
