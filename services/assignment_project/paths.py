"""Canonical assignment project storage paths (absolute, process-independent)."""

from __future__ import annotations

import os
from pathlib import Path

# Repo root: services/assignment_project/paths.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]


def assignment_storage_root() -> Path:
    """Return the absolute directory for persisted assignment project bundles."""
    override = (os.environ.get("PROJECT_STORAGE_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (_REPO_ROOT / "data" / "projects").resolve()


def assignment_trace_log_path() -> Path:
    """Return the absolute path for temporary assignment request tracing."""
    override = (os.environ.get("ASSIGNMENT_TRACE_LOG") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (_REPO_ROOT / "data" / "assignment-trace.log").resolve()


def project_engine_root() -> Path:
    override = (os.environ.get("PROJECT_ENGINE_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (_REPO_ROOT / "data" / "project_engine").resolve()


def project_files_dir(project_id: str) -> Path:
    return assignment_storage_root() / project_id / "files"
