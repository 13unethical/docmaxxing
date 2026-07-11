"""Tests for assignment project storage paths."""

from __future__ import annotations

import os
from pathlib import Path

from services.assignment_project.paths import assignment_storage_root, project_files_dir
from services.assignment_project.store import ProjectStore


def test_trace_accepts_lookup_diagnostics_spread(tmp_path):
    from services.assignment_project.trace_log import trace

    store = ProjectStore(root=tmp_path / "projects")
    trace("test.event", **store.lookup_diagnostics("missing-id"))


def test_assignment_storage_root_is_absolute(monkeypatch):
    monkeypatch.delenv("PROJECT_STORAGE_DIR", raising=False)
    root = assignment_storage_root()
    assert root.is_absolute()


def test_project_store_uses_same_root_regardless_of_cwd(tmp_path, monkeypatch):
    storage = tmp_path / "projects"
    storage.mkdir()
    monkeypatch.setenv("PROJECT_STORAGE_DIR", str(storage))

    store_a = ProjectStore()
    project_id = "test-project-1"
    bundle_path = store_a._bundle_path(project_id)

    from services.assignment_project.models import Project, ProjectStatus, RequirementJSON
    from services.assignment_pipeline.models import PipelineStage, utc_now

    now = utc_now()
    project = Project(
        id=project_id,
        user_id=None,
        title="Test",
        assignment_type=None,
        university=None,
        status=ProjectStatus.DRAFT,
        current_stage=PipelineStage.UPLOAD,
        progress=0,
        price=None,
        credits=None,
        estimated_word_count=None,
        citation_style=None,
        deadline=None,
        created_at=now,
        updated_at=now,
        note=None,
    )
    requirement = RequirementJSON(id="req-1", project_id=project_id)
    store_a.save_project(project)
    store_a.save_requirement(requirement)
    assert bundle_path.is_file()

    other_cwd = tmp_path / "other-cwd"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    store_b = ProjectStore()
    loaded = store_b.require_bundle(project_id)
    assert loaded.project.id == project_id
    assert store_b.storage_root == store_a.storage_root.resolve()
    assert project_files_dir(project_id).is_absolute()
