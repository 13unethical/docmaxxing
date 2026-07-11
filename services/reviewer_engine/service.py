"""Reviewer Engine service — produces review reports without modifying drafts."""

from __future__ import annotations

from typing import Any

from services.reviewer_engine.mock_reviewer import AcademicReviewer, MockAcademicReviewer
from services.reviewer_engine.models import ReviewEngineInput, ReviewReport
from services.reviewer_engine.store import ReviewReportStore


class ReviewerEngineService:
    def __init__(
        self,
        store: ReviewReportStore | None = None,
        reviewer: AcademicReviewer | None = None,
    ) -> None:
        self.store = store or ReviewReportStore()
        self.reviewer = reviewer or MockAcademicReviewer()

    def review_draft(
        self,
        *,
        requirement_json: dict[str, Any],
        research_plan: dict[str, Any],
        blueprint: dict[str, Any],
        draft: dict[str, Any],
        project_id: str | None = None,
    ) -> ReviewReport:
        for key, value in {
            "requirement_json": requirement_json,
            "research_plan": research_plan,
            "blueprint": blueprint,
            "draft": draft,
        }.items():
            if not value:
                raise ValueError(f"{key} is required")
        payload = ReviewEngineInput(
            requirement_json=dict(requirement_json),
            research_plan=dict(research_plan),
            blueprint=dict(blueprint),
            draft=dict(draft),
            project_id=project_id,
        )
        report = self.reviewer.review(payload)
        return self.store.save(report)

    def get_report(self, report_id: str) -> ReviewReport:
        return self.store.require(report_id)

    def get_report_by_project(self, project_id: str) -> ReviewReport:
        return self.store.require_by_project(project_id)
