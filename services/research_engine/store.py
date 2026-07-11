"""In-memory research plan storage."""

from __future__ import annotations

from threading import RLock

from services.research_engine.models import ResearchPlan


class ResearchPlanStore:
    def __init__(self) -> None:
        self._plans: dict[str, ResearchPlan] = {}
        self._by_project: dict[str, str] = {}
        self._lock = RLock()

    def save(self, plan: ResearchPlan) -> ResearchPlan:
        with self._lock:
            self._plans[plan.id] = plan
            if plan.project_id:
                self._by_project[plan.project_id] = plan.id
            return plan

    def get(self, plan_id: str) -> ResearchPlan | None:
        with self._lock:
            return self._plans.get(plan_id)

    def get_by_project(self, project_id: str) -> ResearchPlan | None:
        with self._lock:
            plan_id = self._by_project.get(project_id)
            if not plan_id:
                return None
            return self._plans.get(plan_id)

    def require(self, plan_id: str) -> ResearchPlan:
        plan = self.get(plan_id)
        if plan is None:
            raise KeyError(f"Research plan not found: {plan_id}")
        return plan

    def require_by_project(self, project_id: str) -> ResearchPlan:
        plan = self.get_by_project(project_id)
        if plan is None:
            raise KeyError(f"Research plan not found for project: {project_id}")
        return plan
