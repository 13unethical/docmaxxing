"""Project store with in-memory cache and disk persistence.

Concurrency model (several gunicorn workers share one bundle.json per project):

* Every write holds the project's cross-process bundle lock, re-reads the bundle from disk
  and writes the whole bundle atomically (temp file, fsync, rename, directory fsync).
* Each loaded ``Project`` / ``RequirementJSON`` remembers the bundle revision and text it was
  read from. Saving an object whose revision is still current writes it as is; otherwise
  only the caller's own changes (against that base) are applied on top of the latest bundle,
  and a field both sides changed differently raises ``ProjectUpdateConflictError`` instead
  of overwriting the newer value. ``update_project`` applies a mutation to the latest state
  under the lock and is the preferred way to change a few fields.
* SQLite (payments, refunds, output evidence, plan versions) is not part of this: it stays
  the authority for money, and nothing here spans a JSON write and a SQLite transaction.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import contextmanager
from dataclasses import fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterator

from services.assignment_project.models import Project, ProjectBundle, ProjectFile, RequirementJSON
from services.assignment_project.paths import assignment_storage_root
from services.assignment_project.project_lock import BUNDLE_LOCK, project_file_lock
from services.assignment_project.trace_log import trace


class ProjectUpdateConflictError(ValueError):
    """A save would overwrite a value another request changed since this copy was read."""

    code = "PROJECT_UPDATE_CONFLICT"

    def __init__(self, project_id: str, detail: str) -> None:
        self.project_id = project_id
        self.detail = detail
        super().__init__("This assignment was changed by another request. Reload it and try again.")


class ProjectBundleCorruptError(KeyError):
    """bundle.json exists but is not a readable bundle; it is never overwritten automatically."""


_BASE_ATTR = "_bundle_base"
_MISSING = object()
# The output-evidence timestamp only ever appears: no save removes it, a stale copy can't move it.
_STICKY_PROJECT_PATHS = {("artifacts", "output_generated_at")}
# Mirrors of the in-memory pipeline that every worker rewrites; the later save wins.
_LATEST_WINS_PROJECT_PATHS = {("current_stage",), ("progress",)}


def _base_of(obj: Any) -> tuple[int, str, str] | None:
    return getattr(obj, _BASE_ATTR, None)


def _set_base(obj: Any, project_id: str, revision: int, text: str) -> None:
    object.__setattr__(obj, _BASE_ATTR, (revision, text, project_id))


def bundle_revision(obj: Any) -> int | None:
    """The bundle revision ``obj`` was read at (or last saved as); None for unsaved objects."""
    base = _base_of(obj)
    return base[0] if base else None


def _later_timestamp(a: Any, b: Any) -> Any:
    try:
        return a if datetime.fromisoformat(str(a)) >= datetime.fromisoformat(str(b)) else b
    except (TypeError, ValueError):
        return a


def _merge3(base: Any, mine: Any, theirs: Any, path: tuple, rules: dict, conflicts: list) -> Any:
    """Apply the change from ``base`` to ``mine`` onto ``theirs`` (the latest stored value)."""
    if path in rules.get("sticky", ()) and theirs is not _MISSING:
        return theirs
    if mine == base:
        return theirs
    if theirs == base or mine == theirs:
        return mine
    if base is _MISSING and isinstance(mine, dict) and isinstance(theirs, dict):
        base = {}
    if isinstance(base, dict) and isinstance(mine, dict) and isinstance(theirs, dict):
        merged: dict = {}
        for key in list(theirs) + [k for k in mine if k not in theirs]:
            value = _merge3(
                base.get(key, _MISSING), mine.get(key, _MISSING), theirs.get(key, _MISSING),
                path + (key,), rules, conflicts,
            )
            if value is not _MISSING:
                merged[key] = value
        return merged
    if path in rules.get("latest", ()):
        return mine
    if path == ("updated_at",) and mine is not _MISSING and theirs is not _MISSING:
        return _later_timestamp(mine, theirs)
    conflicts.append(".".join(str(p) for p in path))
    return theirs


def _sync_dict(target: dict, source: dict) -> None:
    """Make ``target`` equal ``source`` in place, keeping nested dicts callers may hold."""
    for key in [k for k in target if k not in source]:
        del target[key]
    for key, value in source.items():
        current = target.get(key, _MISSING)
        if isinstance(current, dict) and isinstance(value, dict) and current is not value:
            _sync_dict(current, value)
        else:
            target[key] = value


def _keep_sticky(project: Project, latest: Project) -> None:
    """A stored sticky value is never dropped by a save, stale or not."""
    for _artifacts, key in _STICKY_PROJECT_PATHS:
        if key in latest.artifacts:
            project.artifacts.setdefault(key, latest.artifacts[key])


def _sync_object(target: Any, source: Any) -> None:
    for item in dataclass_fields(target):
        new = getattr(source, item.name)
        old = getattr(target, item.name)
        if isinstance(old, dict) and isinstance(new, dict):
            _sync_dict(old, new)
        else:
            setattr(target, item.name, new)


class ProjectStore:
    """Thread-safe project repository backed by JSON files under data/projects/."""

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = (Path(root) if root is not None else assignment_storage_root()).resolve()
        self._projects: dict[str, Project] = {}
        self._files: dict[str, list[ProjectFile]] = {}
        self._requirements: dict[str, RequirementJSON] = {}
        self._revisions: dict[str, int] = {}
        self._texts: dict[str, str] = {}
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
        revision = self._revisions.get(project_id, 0) + 1
        payload = {
            "revision": revision,
            "project": project.to_dict(),
            "files": [item.to_dict() for item in self._files.get(project_id, [])],
            "requirement": requirement.to_dict(),
        }
        text = json.dumps(payload, ensure_ascii=False)
        self._atomic_write(path, text)
        self._revisions[project_id] = revision
        self._texts[project_id] = text
        _set_base(project, project_id, revision, text)
        _set_base(requirement, project_id, revision, text)
        trace(
            "store.persist.ok",
            project_id=project_id,
            bundle_path=str(path.resolve()),
            bundle_bytes=path.stat().st_size,
            revision=revision,
        )

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        """Replace ``path`` with ``text``: readers see the old or the new file, never a part.

        Runs under the bundle lock, so any temp file left next to the bundle belongs to a
        writer that died mid-write and is removed first.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        for leftover in path.parent.glob(f".{path.name}.*.tmp"):
            try:
                leftover.unlink()
            except OSError:
                pass
        try:
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            mode = 0o644
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        data = text.encode("utf-8")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.chmod(tmp, mode)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)

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
        text = path.read_text(encoding="utf-8")
        try:
            payload = json.loads(text)
            project = Project.from_dict(payload["project"])
            requirement = RequirementJSON.from_dict(payload["requirement"])
            files = [ProjectFile.from_dict(item) for item in (payload.get("files") or [])]
            revision = int(payload.get("revision") or 0)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            trace("store.load.corrupt", project_id=project_id, error_type=type(exc).__name__)
            raise ProjectBundleCorruptError(f"Project bundle is unreadable: {project_id}") from None
        if project.id != project_id:
            trace("store.load.identity_mismatch", project_id=project_id)
            raise ProjectBundleCorruptError(f"Project bundle is unreadable: {project_id}")
        _set_base(project, project_id, revision, text)
        _set_base(requirement, project_id, revision, text)
        self._projects[project_id] = project
        self._requirements[project_id] = requirement
        self._files[project_id] = files
        self._revisions[project_id] = revision
        self._texts[project_id] = text
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

    @contextmanager
    def _write(self, project_id: str) -> Iterator[None]:
        """One bundle read-modify-write: the parts a save does not replace come from disk.

        Another worker may have written since this worker cached the bundle; without the
        re-read a save of one part would put that worker's older copies of the others back.
        """
        with self._lock, project_file_lock(project_id, name=BUNDLE_LOCK, root=self._root):
            if self._bundle_path(project_id).is_file():
                self._load_locked(project_id)
            yield

    def _reconcile_locked(self, obj: Any, part: str, latest: Any, rules: dict) -> None:
        """Bring the caller's ``obj`` to: latest stored value + the caller's own changes.

        ``latest`` was just re-read under the bundle lock. Raises ProjectUpdateConflictError,
        writing nothing, when ``obj`` was not read from this bundle or both sides changed the
        same field to different values.
        """
        project_id = getattr(obj, "project_id", None) if part == "requirement" else obj.id
        base = _base_of(obj)
        if latest is None:
            if base is not None:
                raise ProjectUpdateConflictError(str(project_id), "bundle no longer exists")
            return
        if base is None:
            raise ProjectUpdateConflictError(str(project_id), f"{part} was not read from the stored bundle")
        revision, text, base_pid = base
        if base_pid != project_id:
            raise ProjectUpdateConflictError(str(project_id), "copy belongs to another project")
        if text == self._texts.get(project_id):
            return
        base_dict = json.loads(text)[part]
        mine = json.loads(json.dumps(obj.to_dict(), ensure_ascii=False))
        theirs = json.loads(json.dumps(latest.to_dict(), ensure_ascii=False))
        conflicts: list[str] = []
        merged = _merge3(base_dict, mine, theirs, (), rules, conflicts)
        if conflicts:
            trace("store.update.conflict", project_id=project_id, part=part, fields=conflicts[:20])
            raise ProjectUpdateConflictError(str(project_id), ", ".join(conflicts[:20]))
        _sync_object(obj, type(obj).from_dict(merged))
        trace("store.update.merged", project_id=project_id, part=part, base_revision=revision)

    def save_project(self, project: Project) -> Project:
        """Store ``project``'s changes; see the module docstring for the stale-copy rules."""
        rules = {"sticky": _STICKY_PROJECT_PATHS, "latest": _LATEST_WINS_PROJECT_PATHS}
        with self._write(project.id):
            exists = self._bundle_path(project.id).is_file()
            latest = self._projects.get(project.id) if exists else None
            self._reconcile_locked(project, "project", latest, rules)
            if latest is not None:
                _keep_sticky(project, latest)
            self._projects[project.id] = project
            self._persist_locked(project.id)
            return project

    def update_project(
        self,
        project_id: str,
        mutate: Callable[[Project], Any],
        *,
        expected_revision: int | None = None,
    ) -> Project:
        """Apply ``mutate`` to the latest stored project under the bundle lock and persist it.

        ``mutate`` must only change fields (no AI, provider, network or other lock calls). It
        may return False to skip the write. ``expected_revision`` refuses the update when the
        bundle changed since the caller's read.
        """
        with self._write(project_id):
            if not self._bundle_path(project_id).is_file():
                raise KeyError(f"Project not found: {project_id}")
            current = self._revisions.get(project_id, 0)
            if expected_revision is not None and expected_revision != current:
                raise ProjectUpdateConflictError(project_id, f"revision {expected_revision} != {current}")
            project = self._projects[project_id]
            sticky_source = Project.from_dict(project.to_dict())
            if mutate(project) is False:
                return project
            _keep_sticky(project, sticky_source)
            if project.id != project_id:
                raise ProjectUpdateConflictError(project_id, "project identity changed")
            rules = {"sticky": _STICKY_PROJECT_PATHS, "latest": _LATEST_WINS_PROJECT_PATHS}
            self._reconcile_locked(project, "project", self._projects.get(project_id), rules)
            self._projects[project_id] = project
            self._persist_locked(project_id)
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
        """Load projects owned by user_id, newest first.

        Peeks user_id from the start of each bundle before a full parse so listing
        does not block gunicorn workers on huge writer_session artifacts.
        """
        uid = str(user_id or "").strip()
        if not uid:
            return []
        user_id_re = re.compile(r'"user_id"\s*:\s*(null|"((?:\\.|[^"\\])*)")')
        projects: list[Project] = []
        for project_id in self.list_project_ids():
            path = self._bundle_path(project_id)
            if path.is_file():
                try:
                    head = path.read_bytes()[:16384].decode("utf-8", errors="ignore")
                except OSError:
                    continue
                match = user_id_re.search(head)
                if match is not None:
                    peeked = "" if match.group(1) == "null" else (match.group(2) or "")
                    if peeked != uid:
                        continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                proj_data = payload.get("project")
                if not isinstance(proj_data, dict):
                    continue
                if str(proj_data.get("user_id") or "") != uid:
                    continue
                artifacts = proj_data.get("artifacts") if isinstance(proj_data.get("artifacts"), dict) else {}
                slim = dict(proj_data)
                slim_artifacts: dict = {}
                delivery = artifacts.get("delivery_package")
                if isinstance(delivery, dict) and delivery:
                    slim_artifacts["delivery_package"] = {"present": True}
                chat = artifacts.get("revision_chat")
                if isinstance(chat, dict):
                    slim_artifacts["revision_chat"] = {
                        "rounds_used": int(chat.get("rounds_used") or 0),
                    }
                if artifacts.get("payment_refunded"):
                    slim_artifacts["payment_refunded"] = True
                slim["artifacts"] = slim_artifacts
                try:
                    projects.append(Project.from_dict(slim))
                except Exception:  # noqa: BLE001
                    continue
                continue
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
        with self._write(file_record.project_id):
            bucket = self._files.setdefault(file_record.project_id, [])
            bucket.append(file_record)
            self._persist_locked(file_record.project_id)
            return file_record

    def list_files(self, project_id: str) -> list[ProjectFile]:
        with self._lock:
            self._ensure_loaded_locked(project_id)
            return list(self._files.get(project_id, []))

    def save_requirement(self, requirement: RequirementJSON, *, replace: bool = False) -> RequirementJSON:
        """Store ``requirement``'s changes, like ``save_project``.

        ``replace`` stores it whole: for a freshly built requirement (analysis output) that
        the caller applies under the billing lock after checking the inputs are editable.
        """
        with self._write(requirement.project_id):
            if not replace:
                exists = self._bundle_path(requirement.project_id).is_file()
                latest = self._requirements.get(requirement.project_id) if exists else None
                self._reconcile_locked(requirement, "requirement", latest, {})
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
