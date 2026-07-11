"""In-memory assignment project store."""

from __future__ import annotations

from threading import RLock

from services.assignment_pipeline.models import AssignmentProject


class AssignmentProjectStore:
    """Thread-safe in-memory project repository (replace with DB later)."""

    def __init__(self) -> None:
        self._projects: dict[str, AssignmentProject] = {}
        self._lock = RLock()

    def save(self, project: AssignmentProject) -> AssignmentProject:
        with self._lock:
            self._projects[project.id] = project
            return project

    def get(self, project_id: str) -> AssignmentProject | None:
        with self._lock:
            return self._projects.get(project_id)

    def require(self, project_id: str) -> AssignmentProject:
        project = self.get(project_id)
        if project is None:
            raise KeyError(f"Assignment project not found: {project_id}")
        return project

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._projects.keys())
