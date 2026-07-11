"""Tests for assignment project data architecture."""

from __future__ import annotations

import pytest

from services.assignment_pipeline.models import PipelineStage, utc_now
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project import ProjectFileType, ProjectService, ProjectStatus
from services.assignment_project.models import RequirementFormatting
from services.assignment_project.store import ProjectStore


class _StubRequirementAnalyzer:
    VERSION = "mock-v1"

    def analyze(self, payload):
        req = payload.requirement
        req.assignment_type = "Literature Review"
        req.word_count = 3000
        req.citation_style = "APA 7"
        req.required_sections = ["Introduction", "Conclusion"]
        req.rubric = []
        req.learning_outcomes = []
        req.minimum_sources = 15
        req.formatting = RequirementFormatting(font_family="Times New Roman")
        req.analyzer_version = self.VERSION
        req.analyzed_at = utc_now()
        return req


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
    service = ProjectService(analyzer=_StubRequirementAnalyzer())
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
    assert req.minimum_sources == 15
    assert req.formatting.font_family == "Times New Roman"
    assert req.analyzer_version == _StubRequirementAnalyzer.VERSION
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


def test_store_reload_from_disk_after_external_write(tmp_path):
    """Simulate another gunicorn worker saving pricing while this worker holds stale cache."""
    store_a = ProjectStore(root=tmp_path / "projects")
    store_b = ProjectStore(root=tmp_path / "projects")
    pipeline = AssignmentPipelineService()
    service_a = ProjectService(store=store_a, pipeline=pipeline, analyzer=_StubRequirementAnalyzer())

    bundle = service_a.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    project_id = bundle.project.id
    service_a.analyze_requirements(project_id)

    # Worker B loads project into its cache before pricing runs.
    store_b.require_bundle(project_id)
    assert store_b.require_bundle(project_id).project.price is None

    service_a.calculate_pricing(project_id)

    # Worker B must see the price written by worker A, not its stale cache.
    assert store_b.require_bundle(project_id).project.price is not None


def test_confirm_payment_restores_pipeline_from_disk(tmp_path):
    """Simulate a new gunicorn worker that has no in-memory pipeline state."""
    store = ProjectStore(root=tmp_path / "projects")
    pipeline_a = AssignmentPipelineService()
    service_a = ProjectService(store=store, pipeline=pipeline_a, analyzer=_StubRequirementAnalyzer())

    bundle = service_a.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    service_a.analyze_requirements(bundle.project.id)
    service_a.calculate_pricing(bundle.project.id)

    pipeline_b = AssignmentPipelineService()
    service_b = ProjectService(store=store, pipeline=pipeline_b, analyzer=_StubRequirementAnalyzer())

    confirmed = service_b.confirm_payment(bundle.project.id)
    assert confirmed.project.artifacts.get("payment_confirmed") is True


def test_calculate_pricing_restores_pipeline_from_disk(tmp_path):
    store = ProjectStore(root=tmp_path / "projects")
    pipeline_a = AssignmentPipelineService()
    service_a = ProjectService(store=store, pipeline=pipeline_a, analyzer=_StubRequirementAnalyzer())

    bundle = service_a.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    service_a.analyze_requirements(bundle.project.id)

    pipeline_b = AssignmentPipelineService()
    service_b = ProjectService(store=store, pipeline=pipeline_b, analyzer=_StubRequirementAnalyzer())

    priced = service_b.calculate_pricing(bundle.project.id)
    assert priced.project.price is not None
    pricing_state = pipeline_b.get_project(bundle.project.id).stage_state(PipelineStage.PRICING)
    assert pricing_state.status.value == "completed"
