"""In-memory blueprint storage."""

from __future__ import annotations

from threading import RLock

from services.blueprint_engine.models import Blueprint


class BlueprintStore:
    def __init__(self) -> None:
        self._blueprints: dict[str, Blueprint] = {}
        self._by_project: dict[str, str] = {}
        self._lock = RLock()

    def save(self, blueprint: Blueprint) -> Blueprint:
        with self._lock:
            self._blueprints[blueprint.id] = blueprint
            if blueprint.project_id:
                self._by_project[blueprint.project_id] = blueprint.id
            return blueprint

    def get(self, blueprint_id: str) -> Blueprint | None:
        with self._lock:
            return self._blueprints.get(blueprint_id)

    def get_by_project(self, project_id: str) -> Blueprint | None:
        with self._lock:
            blueprint_id = self._by_project.get(project_id)
            if not blueprint_id:
                return None
            return self._blueprints.get(blueprint_id)

    def require(self, blueprint_id: str) -> Blueprint:
        blueprint = self.get(blueprint_id)
        if blueprint is None:
            raise KeyError(f"Blueprint not found: {blueprint_id}")
        return blueprint

    def require_by_project(self, project_id: str) -> Blueprint:
        blueprint = self.get_by_project(project_id)
        if blueprint is None:
            raise KeyError(f"Blueprint not found for project: {project_id}")
        return blueprint
