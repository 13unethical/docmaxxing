"""Project store with in-memory cache and disk persistence."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from services.assignment_project.models import Project, ProjectBundle, ProjectFile, RequirementJSON
from services.assignment_project.paths import assignment_storage_root
from services.assignment_project.trace_log import trace


class ProjectStore:
    """Thread-safe project repository backed by JSON files under data/projects/."""

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = (Path(root) if root is not None else assignment_storage_root()).resolve()
        self._projects: dict[str, Project] = {}
        self._files: dict[str, list[ProjectFile]] = {}
        self._requirements: dict[str, RequirementJSON] = {}
        self._lock = RLock()
        trace(
            "store.init",
            storage_root=str(self._root),
            storage_root_exists=self._root.is_dir(),
            configured_from_env=bool((root is None)),
        )

    @property
    def storage_root(self) -> Path:
        return self._root

    def _bundle_path(self, project_id: str) -> Path:
        return self._root / project_id / "bundle.json"

    def _persist_locked(self, project_id: str) -> None:
        project = self._projects.get(project_id)
        requirement = self._requirements.get(project_id)
        path = self._bundle_path(project_id)
        if project is None or requirement is None:
            trace(
                "store.persist.skipped",
                project_id=project_id,
                bundle_path=str(path),
                has_project=project is not None,
                has_requirement=requirement is not None,
            )
            return
        payload = {
            "project": project.to_dict(),
            "files": [item.to_dict() for item in self._files.get(project_id, [])],
            "requirement": requirement.to_dict(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        trace(
            "store.persist.ok",
            project_id=project_id,
            bundle_path=str(path.resolve()),
            bundle_bytes=path.stat().st_size,
        )

    def _load_locked(self, project_id: str) -> bool:
        path = self._bundle_path(project_id)
        if not path.is_file():
            trace(
                "store.load.miss",
                project_id=project_id,
                bundle_path=str(path.resolve()),
                bundle_exists=False,
            )
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
        project = Project.from_dict(payload["project"])
        requirement = RequirementJSON.from_dict(payload["requirement"])
        files = [ProjectFile.from_dict(item) for item in (payload.get("files") or [])]
        self._projects[project_id] = project
        self._requirements[project_id] = requirement
        self._files[project_id] = files
        trace(
            "store.load.ok",
            project_id=project_id,
            bundle_path=str(path.resolve()),
            bundle_bytes=path.stat().st_size,
            price=project.price,
        )
        return True

    def _ensure_loaded_locked(self, project_id: str) -> bool:
        # Always prefer on-disk state when a bundle exists so multiple gunicorn
        # workers see writes performed by other processes.
        if self._bundle_path(project_id).is_file():
            return self._load_locked(project_id)
        loaded = project_id in self._projects and project_id in self._requirements
        if not loaded:
            trace(
                "store.ensure_loaded.miss",
                project_id=project_id,
                bundle_path=str(self._bundle_path(project_id).resolve()),
                bundle_exists=False,
                in_memory_project=project_id in self._projects,
                in_memory_requirement=project_id in self._requirements,
            )
        return loaded

    def lookup_diagnostics(self, project_id: str) -> dict[str, object]:
        bundle_path = self._bundle_path(project_id)
        resolved = bundle_path.resolve()
        root_listing: list[str] = []
        if self._root.is_dir():
            root_listing = sorted(child.name for child in self._root.iterdir())[:20]
        return {
            "project_id": project_id,
            "storage_root": str(self._root),
            "bundle_path": str(resolved),
            "bundle_exists": resolved.is_file(),
            "in_memory_project": project_id in self._projects,
            "in_memory_requirement": project_id in self._requirements,
            "storage_root_listing": root_listing,
        }

    def save_project(self, project: Project) -> Project:
        with self._lock:
            self._projects[project.id] = project
            self._persist_locked(project.id)
            return project

    def get_project(self, project_id: str) -> Project | None:
        with self._lock:
            self._ensure_loaded_locked(project_id)
            return self._projects.get(project_id)

    def require_project(self, project_id: str) -> Project:
        trace("store.require_project", **self.lookup_diagnostics(project_id))
        project = self.get_project(project_id)
        if project is None:
            reason = f"Project not found: {project_id}"
            trace("store.require_project.fail", project_id=project_id, reason=reason)
            raise KeyError(reason)
        return project

    def list_project_ids(self) -> list[str]:
        with self._lock:
            ids = set(self._projects.keys())
            if self._root.is_dir():
                for child in self._root.iterdir():
                    if child.is_dir() and (child / "bundle.json").is_file():
                        ids.add(child.name)
            return list(ids)

    def list_projects_for_user(self, user_id: str) -> list[Project]:
        """Load projects owned by user_id, newest first."""
        uid = str(user_id or "").strip()
        if not uid:
            return []
        projects: list[Project] = []
        for project_id in self.list_project_ids():
            try:
                project = self.get_project(project_id)
            except Exception:  # noqa: BLE001
                continue
            if project is None:
                continue
            if str(project.user_id or "") != uid:
                continue
            projects.append(project)
        projects.sort(key=lambda p: p.updated_at or p.created_at, reverse=True)
        return projects

    def save_file(self, file_record: ProjectFile) -> ProjectFile:
        with self._lock:
            bucket = self._files.setdefault(file_record.project_id, [])
            bucket.append(file_record)
            self._persist_locked(file_record.project_id)
            return file_record

    def list_files(self, project_id: str) -> list[ProjectFile]:
        with self._lock:
            self._ensure_loaded_locked(project_id)
            return list(self._files.get(project_id, []))

    def save_requirement(self, requirement: RequirementJSON) -> RequirementJSON:
        with self._lock:
            self._requirements[requirement.project_id] = requirement
            self._persist_locked(requirement.project_id)
            return requirement

    def get_requirement(self, project_id: str) -> RequirementJSON | None:
        with self._lock:
            self._ensure_loaded_locked(project_id)
            return self._requirements.get(project_id)

    def require_requirement(self, project_id: str) -> RequirementJSON:
        requirement = self.get_requirement(project_id)
        if requirement is None:
            reason = f"Requirement JSON not found for project: {project_id}"
            trace("store.require_requirement.fail", project_id=project_id, reason=reason)
            raise KeyError(reason)
        return requirement

    def get_bundle(self, project_id: str) -> ProjectBundle | None:
        with self._lock:
            if not self._ensure_loaded_locked(project_id):
                return None
            project = self._projects.get(project_id)
            requirement = self._requirements.get(project_id)
            if project is None or requirement is None:
                return None
            return ProjectBundle(
                project=project,
                files=list(self._files.get(project_id, [])),
                requirement=requirement,
            )

    def require_bundle(self, project_id: str) -> ProjectBundle:
        trace("store.require_bundle", **self.lookup_diagnostics(project_id))
        bundle = self.get_bundle(project_id)
        if bundle is None:
            reason = f"Project bundle not found: {project_id}"
            trace("store.require_bundle.fail", reason=reason, **self.lookup_diagnostics(project_id))
            raise KeyError(reason)
        return bundle
