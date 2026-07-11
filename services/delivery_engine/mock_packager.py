"""Mock delivery packager — assembles files without generating assignment content."""

from __future__ import annotations

import re
import uuid
from typing import Any, Protocol

from services.assignment_pipeline.models import utc_now
from services.delivery_engine.models import (
    DeliveryEngineInput,
    DeliveryFile,
    DeliveryPackage,
    DeliveryStatus,
    ProjectSummary,
)


class DeliveryPackager(Protocol):
    def package(self, payload: DeliveryEngineInput) -> DeliveryPackage:
        ...


class MockDeliveryPackager:
    VERSION = "mock-1.0"

    def package(self, payload: DeliveryEngineInput) -> DeliveryPackage:
        draft = payload.final_draft
        req = payload.requirement_json
        review = payload.review_report
        detection = payload.detection_report
        project_id = payload.project_id or "local"

        title = _safe_filename(
            str(draft.get("title") or req.get("title") or req.get("assignment_type") or "Assignment")
        )
        summary = _build_summary(payload, title, review, detection)
        base_path = f"data/projects/{project_id}/delivery"

        files = [
            _file(
                label="Final Assignment",
                filename=f"{title}.docx",
                file_type="final_assignment_docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                size=48_000 + int(draft.get("total_words") or 0) * 6,
                storage_path=f"{base_path}/{title}.docx",
            ),
            _file(
                label="Final Assignment",
                filename=f"{title}.pdf",
                file_type="final_assignment_pdf",
                mime_type="application/pdf",
                size=62_000 + int(draft.get("total_words") or 0) * 5,
                storage_path=f"{base_path}/{title}.pdf",
            ),
            _file(
                label="Requirements Report",
                filename="Requirements-Report.pdf",
                file_type="requirements_report",
                mime_type="application/pdf",
                size=24_000,
                storage_path=f"{base_path}/requirements-report.pdf",
            ),
            _file(
                label="Academic Review Report",
                filename="Review-Report.pdf",
                file_type="review_report",
                mime_type="application/pdf",
                size=28_000,
                storage_path=f"{base_path}/review-report.pdf",
            ),
            _file(
                label="AI Detection Report",
                filename="AI-Detection-Report.pdf",
                file_type="detection_report",
                mime_type="application/pdf",
                size=22_000,
                storage_path=f"{base_path}/ai-detection-report.pdf",
            ),
            _file(
                label="Project Summary",
                filename="Project-Summary.pdf",
                file_type="project_summary",
                mime_type="application/pdf",
                size=16_000,
                storage_path=f"{base_path}/project-summary.pdf",
            ),
        ]

        package_size = sum(item.size_bytes for item in files) + 12_000
        now = utc_now()

        return DeliveryPackage(
            id=str(uuid.uuid4()),
            project_id=payload.project_id,
            status=DeliveryStatus.READY,
            files=files,
            project_summary=summary,
            package_download_url=f"/api/delivery/packages/{project_id}/download",
            package_size_bytes=package_size,
            final_draft_id=str(draft.get("id") or ""),
            engine_version=self.VERSION,
            prepared_at=now,
            ready_at=now,
        )


def _build_summary(
    payload: DeliveryEngineInput,
    title: str,
    review: dict[str, Any],
    detection: dict[str, Any],
) -> ProjectSummary:
    req = payload.requirement_json
    plan = payload.research_plan
    draft = payload.final_draft
    review_score = int(review.get("overall_score") or 0)
    ai_score = float(detection.get("overall_ai_score") or detection.get("average_score") or 0)
    overall_quality = int(round((review_score + max(0, 100 - ai_score)) / 2))
    return ProjectSummary(
        project_name=title,
        assignment_type=str(req.get("assignment_type") or req.get("assignmentType") or "Essay"),
        word_count=int(draft.get("total_words") or req.get("word_count") or 0),
        citation_style=str(req.get("citation_style") or req.get("citationStyle") or "APA 7"),
        difficulty=str(req.get("difficulty") or plan.get("estimated_difficulty") or "—"),
        completion_time=payload.completion_time,
        total_revisions=int(payload.revision_attempts),
        total_humanization_attempts=int(payload.humanization_attempts),
        overall_review_score=review_score,
        final_ai_score=ai_score,
        pipeline_completion_date=utc_now().date().isoformat(),
        overall_quality_score=overall_quality,
    )


def _file(
    *,
    label: str,
    filename: str,
    file_type: str,
    mime_type: str,
    size: int,
    storage_path: str,
) -> DeliveryFile:
    file_id = str(uuid.uuid4())
    return DeliveryFile(
        id=file_id,
        label=label,
        filename=filename,
        file_type=file_type,
        mime_type=mime_type,
        size_bytes=size,
        storage_path=storage_path,
        download_url=f"/api/delivery/files/{file_id}",
        ready=True,
    )


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return cleaned or "Assignment"
