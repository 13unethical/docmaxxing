"""Research Engine service — independent planning layer for the Writer Engine."""

from __future__ import annotations

from typing import Any

from services.research_engine.mock_engine import ResearchAnalyzer, ResearchEngine
from services.research_engine.models import ParsedDocument, ResearchEngineInput, ResearchPlan
from services.research_engine.store import ResearchPlanStore


class ResearchEngineService:
    """Build and persist Research Plans from Requirement JSON + parsed documents."""

    def __init__(
        self,
        store: ResearchPlanStore | None = None,
        engine: ResearchEngine | None = None,
    ) -> None:
        self.store = store or ResearchPlanStore()
        self.engine = engine or ResearchAnalyzer()

    def build_plan(
        self,
        *,
        requirement_json: dict[str, Any],
        parsed_documents: list[ParsedDocument],
        project_id: str | None = None,
    ) -> ResearchPlan:
        if not requirement_json:
            raise ValueError("requirement_json is required")
        payload = ResearchEngineInput(
            requirement_json=dict(requirement_json),
            parsed_documents=list(parsed_documents),
            project_id=project_id,
        )
        plan = self.engine.build_plan(payload)
        return self.store.save(plan)

    def get_plan(self, plan_id: str) -> ResearchPlan:
        return self.store.require(plan_id)

    def get_plan_by_project(self, project_id: str) -> ResearchPlan:
        return self.store.require_by_project(project_id)

    def update_plan(self, plan: ResearchPlan) -> ResearchPlan:
        return self.store.save(plan)

    def update_plan_from_dict(self, plan_id: str, payload: dict[str, Any]) -> ResearchPlan:
        existing = self.store.require(plan_id)
        merged = existing.to_dict()
        merged.update(payload)
        merged["id"] = existing.id
        merged["project_id"] = existing.project_id
        updated = ResearchPlan.from_dict(merged)
        return self.store.save(updated)
