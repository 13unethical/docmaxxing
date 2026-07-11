"""Delivery Engine service — packages pipeline outputs without modifying content."""

from __future__ import annotations

import uuid
from typing import Any

from services.assignment_pipeline.models import utc_now
from services.delivery_engine.packager import DeliveryPackager, RealDeliveryPackager
from services.delivery_engine.models import (
    DeliveryEngineInput,
    DeliveryPackage,
    DeliveryStatus,
)
from services.delivery_engine.store import DeliveryPackageStore


class DeliveryEngineService:
    def __init__(
        self,
        store: DeliveryPackageStore | None = None,
        packager: DeliveryPackager | None = None,
    ) -> None:
        self.store = store or DeliveryPackageStore()
        self.packager = packager or RealDeliveryPackager()

    def prepare_package(
        self,
        *,
        final_draft: dict[str, Any],
        requirement_json: dict[str, Any],
        research_plan: dict[str, Any],
        blueprint: dict[str, Any],
        review_report: dict[str, Any],
        detection_report: dict[str, Any],
        project_id: str | None = None,
        revision_attempts: int = 0,
        humanization_attempts: int = 0,
        completion_time: str = "—",
    ) -> DeliveryPackage:
        for key, value in {
            "final_draft": final_draft,
            "requirement_json": requirement_json,
            "research_plan": research_plan,
            "blueprint": blueprint,
            "review_report": review_report,
            "detection_report": detection_report,
        }.items():
            if not value:
                raise ValueError(f"{key} is required")

        payload = DeliveryEngineInput(
            final_draft=dict(final_draft),
            requirement_json=dict(requirement_json),
            research_plan=dict(research_plan),
            blueprint=dict(blueprint),
            review_report=dict(review_report),
            detection_report=dict(detection_report),
            project_id=project_id,
            revision_attempts=revision_attempts,
            humanization_attempts=humanization_attempts,
            completion_time=completion_time,
        )

        placeholder = DeliveryPackage(
            id=str(uuid.uuid4()),
            project_id=project_id,
            status=DeliveryStatus.PREPARING_FILES,
            files=[],
            project_summary=_empty_summary(),
            package_download_url=None,
            package_size_bytes=0,
            final_draft_id=str(final_draft.get("id") or ""),
            engine_version=RealDeliveryPackager.VERSION,
            prepared_at=utc_now(),
        )
        self.store.save(placeholder)

        placeholder.status = DeliveryStatus.GENERATING_REPORTS
        self.store.save(placeholder)

        placeholder.status = DeliveryStatus.PACKAGING
        self.store.save(placeholder)

        package = self.packager.package(payload)
        package.id = placeholder.id
        package.prepared_at = placeholder.prepared_at
        package.package_download_url = f"/api/delivery/packages/{package.id}/download"
        return self.store.save(package)

    def get_package(self, package_id: str) -> DeliveryPackage:
        return self.store.require(package_id)

    def get_package_by_project(self, project_id: str) -> DeliveryPackage:
        return self.store.require_by_project(project_id)

    def get_file(self, file_id: str):
        return self.store.require_file(file_id)

    def advance_status(self, package_id: str) -> DeliveryPackage:
        package = self.store.require(package_id)
        next_status = {
            DeliveryStatus.PREPARING_FILES: DeliveryStatus.GENERATING_REPORTS,
            DeliveryStatus.GENERATING_REPORTS: DeliveryStatus.PACKAGING,
            DeliveryStatus.PACKAGING: DeliveryStatus.READY,
        }.get(package.status)
        if next_status:
            package.status = next_status
            if next_status == DeliveryStatus.READY:
                package.ready_at = utc_now()
            self.store.save(package)
        return package


def _empty_summary():
    from services.delivery_engine.models import ProjectSummary

    return ProjectSummary(
        project_name="",
        assignment_type="",
        word_count=0,
        citation_style="",
        difficulty="",
        completion_time="",
        total_revisions=0,
        total_humanization_attempts=0,
        overall_review_score=0,
        final_ai_score=0.0,
        pipeline_completion_date="",
        overall_quality_score=0,
    )
