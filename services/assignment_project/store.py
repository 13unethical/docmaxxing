"""In-memory project, file, and requirement storage."""

from __future__ import annotations

from threading import RLock

from services.assignment_project.models import Project, ProjectBundle, ProjectFile, RequirementJSON


class ProjectStore:
    """Thread-safe in-memory store (replace with database later)."""

    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}
        self._files: dict[str, list[ProjectFile]] = {}
        self._requirements: dict[str, RequirementJSON] = {}
        self._lock = RLock()

    def save_project(self, project: Project) -> Project:
        with self._lock:
            self._projects[project.id] = project
            return project

    def get_project(self, project_id: str) -> Project | None:
        with self._lock:
            return self._projects.get(project_id)

    def require_project(self, project_id: str) -> Project:
        project = self.get_project(project_id)
        if project is None:
            raise KeyError(f"Project not found: {project_id}")
        return project

    def list_project_ids(self) -> list[str]:
        with self._lock:
            return list(self._projects.keys())

    def save_file(self, file_record: ProjectFile) -> ProjectFile:
        with self._lock:
            bucket = self._files.setdefault(file_record.project_id, [])
            bucket.append(file_record)
            return file_record

    def list_files(self, project_id: str) -> list[ProjectFile]:
        with self._lock:
            return list(self._files.get(project_id, []))

    def save_requirement(self, requirement: RequirementJSON) -> RequirementJSON:
        with self._lock:
            self._requirements[requirement.project_id] = requirement
            return requirement

    def get_requirement(self, project_id: str) -> RequirementJSON | None:
        with self._lock:
            return self._requirements.get(project_id)

    def require_requirement(self, project_id: str) -> RequirementJSON:
        requirement = self.get_requirement(project_id)
        if requirement is None:
            raise KeyError(f"Requirement JSON not found for project: {project_id}")
        return requirement

    def get_bundle(self, project_id: str) -> ProjectBundle | None:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return None
            requirement = self._requirements.get(project_id)
            if requirement is None:
                return None
            return ProjectBundle(
                project=project,
                files=list(self._files.get(project_id, [])),
                requirement=requirement,
            )

    def require_bundle(self, project_id: str) -> ProjectBundle:
        bundle = self.get_bundle(project_id)
        if bundle is None:
            raise KeyError(f"Project bundle not found: {project_id}")
        return bundle
