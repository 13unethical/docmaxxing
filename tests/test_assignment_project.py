"""Tests for assignment project data architecture."""

from __future__ import annotations

import pytest

from services.assignment_pipeline.models import PipelineStage
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project import ProjectFileType, ProjectService, ProjectStatus
from services.assignment_project.requirement_analyzer import MockRequirementAnalyzer
from services.assignment_project.store import ProjectStore


def test_create_project_initializes_models():
    pipeline = AssignmentPipelineService()
    service = ProjectService(pipeline=pipeline)
    bundle = service.create_project(
        title="Ethics Essay",
        university="Example University",
        deadline="2026-03-15T23:59:00+00:00",
        files=[
            {
                "file_type": "assignment_brief",
                "original_filename": "brief.pdf",
            }
        ],
    )

    project = bundle.project
    assert project.title == "Ethics Essay"
    assert project.university == "Example University"
    assert project.status == ProjectStatus.DRAFT
    assert project.current_stage == PipelineStage.REQUIREMENT_ANALYSIS
    assert len(bundle.files) == 1
    assert bundle.files[0].file_type == ProjectFileType.ASSIGNMENT_BRIEF
    assert bundle.requirement.project_id == project.id
    assert bundle.requirement.word_count is None


def test_every_project_has_exactly_one_requirement_json():
    service = ProjectService()
    bundle = service.create_project()
    store = service.store
    assert store.get_requirement(bundle.project.id) is not None
    with pytest.raises(KeyError):
        store.require_requirement("missing")


def test_analyze_requirements_populates_mock_json_and_project_fields():
    service = ProjectService()
    bundle = service.create_project(
        title="Literature Review",
        note="literature review on climate policy",
        files=[
            {"file_type": "assignment_brief", "original_filename": "brief.pdf"},
            {"file_type": "rubric", "original_filename": "rubric.pdf"},
        ],
    )
    analyzed = service.analyze_requirements(bundle.project.id)

    req = analyzed.requirement
    assert req.assignment_type == "Literature Review"
    assert req.word_count == 3000
    assert req.citation_style == "APA 7"
    assert req.required_sections
    assert req.rubric
    assert req.learning_outcomes
    assert req.minimum_sources == 15
    assert req.formatting.font_family == "Times New Roman"
    assert req.analyzer_version == MockRequirementAnalyzer.VERSION
    assert req.analyzed_at is not None

    project = analyzed.project
    assert project.assignment_type == "Literature Review"
    assert project.estimated_word_count == 3000
    assert project.citation_style == "APA 7"
    assert project.status == ProjectStatus.ACTIVE
    assert project.current_stage == PipelineStage.PRICING


def test_add_file_supports_all_file_types():
    service = ProjectService()
    bundle = service.create_project()
    project_id = bundle.project.id

    for file_type in ProjectFileType:
        service.add_file(
            project_id,
            file_type=file_type.value,
            original_filename=f"{file_type.value}.pdf",
        )

    updated = service.get_project(project_id)
    assert len(updated.files) == len(ProjectFileType)


def test_bundle_to_dict_shape():
    service = ProjectService()
    bundle = service.create_project(files=[{"file_type": "assignment_brief", "original_filename": "a.pdf"}])
    payload = bundle.to_dict()
    assert set(payload.keys()) == {"project", "files", "requirement"}
    assert payload["requirement"]["project_id"] == payload["project"]["id"]


def test_create_project_shares_id_with_pipeline():
    pipeline = AssignmentPipelineService()
    service = ProjectService(pipeline=pipeline)
    bundle = service.create_project()
    pipeline_state = pipeline.get_project(bundle.project.id)
    assert pipeline_state.id == bundle.project.id


def test_unsupported_file_type_raises():
    service = ProjectService()
    bundle = service.create_project()
    with pytest.raises(ValueError):
        service.add_file(bundle.project.id, file_type="unknown", original_filename="x.pdf")
