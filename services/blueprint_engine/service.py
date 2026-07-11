"""Blueprint Engine service — independent planning layer for the Writer Engine."""

from __future__ import annotations

from typing import Any

from services.blueprint_engine.mock_engine import BlueprintAnalyzer, BlueprintEngine
from services.blueprint_engine.models import Blueprint, BlueprintEngineInput
from services.blueprint_engine.store import BlueprintStore


class BlueprintEngineService:
    def __init__(
        self,
        store: BlueprintStore | None = None,
        engine: BlueprintEngine | None = None,
    ) -> None:
        self.store = store or BlueprintStore()
        self.engine = engine or BlueprintAnalyzer()

    def build_blueprint(
        self,
        *,
        requirement_json: dict[str, Any],
        research_plan: dict[str, Any],
        project_id: str | None = None,
    ) -> Blueprint:
        if not requirement_json:
            raise ValueError("requirement_json is required")
        if not research_plan:
            raise ValueError("research_plan is required")
        payload = BlueprintEngineInput(
            requirement_json=dict(requirement_json),
            research_plan=dict(research_plan),
            project_id=project_id,
        )
        blueprint = self.engine.build_blueprint(payload)
        return self.store.save(blueprint)

    def get_blueprint(self, blueprint_id: str) -> Blueprint:
        return self.store.require(blueprint_id)

    def get_blueprint_by_project(self, project_id: str) -> Blueprint:
        return self.store.require_by_project(project_id)

    def update_blueprint(self, blueprint: Blueprint) -> Blueprint:
        return self.store.save(blueprint)

    def update_blueprint_from_dict(self, blueprint_id: str, payload: dict[str, Any]) -> Blueprint:
        existing = self.store.require(blueprint_id)
        merged = existing.to_dict()
        merged.update(payload)
        merged["id"] = existing.id
        merged["project_id"] = existing.project_id
        updated = Blueprint.from_dict(merged)
        return self.store.save(updated)
