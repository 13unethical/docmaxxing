"""Tests for assignment project pipeline architecture."""

from __future__ import annotations

import pytest

from services.assignment_pipeline.handlers import StageContext, StageHandlerRegistry, StageResult
from services.assignment_pipeline.models import PipelineStage, StageProvider, StageStatus
from services.assignment_pipeline.service import AssignmentPipelineService, compute_progress
from services.assignment_pipeline.stages import PIPELINE_STAGE_SPECS, PIPELINE_STAGES, stage_after


def test_pipeline_has_sixteen_ordered_stages():
    assert len(PIPELINE_STAGES) == 16
    assert PIPELINE_STAGES[0] == PipelineStage.UPLOAD
    assert PIPELINE_STAGES[-1] == PipelineStage.DELIVERY
    assert stage_after(PipelineStage.UPLOAD) == PipelineStage.REQUIREMENT_ANALYSIS
    assert stage_after(PipelineStage.DELIVERY) is None


def test_stage_specs_map_providers_for_future_integrations():
    providers = {spec.stage: spec.provider for spec in PIPELINE_STAGE_SPECS}
    assert providers[PipelineStage.REQUIREMENT_ANALYSIS] == StageProvider.GEMINI
    assert providers[PipelineStage.BLUEPRINT] == StageProvider.CLAUDE
    assert providers[PipelineStage.WRITING] == StageProvider.CLAUDE
    assert providers[PipelineStage.HUMANIZATION] == StageProvider.HUMANIZER
    assert providers[PipelineStage.AI_DETECTION] == StageProvider.INTERNAL
    assert providers[PipelineStage.REQUIREMENT_VALIDATION] == StageProvider.GEMINI
    assert providers[PipelineStage.CITATION_GENERATION] == StageProvider.CITATION_ENGINE
    assert providers[PipelineStage.FORMATTING] == StageProvider.FORMAT_ENGINE
    assert providers[PipelineStage.STYLE_REVIEW] == StageProvider.GEMINI
    assert providers[PipelineStage.REVISION] == StageProvider.GEMINI


def test_create_project_marks_upload_complete_and_advances():
    service = AssignmentPipelineService()
    project = service.create_project(
        {
            "files": [{"name": "brief.pdf", "source": "Assignment Brief"}],
            "priority": "standard",
        }
    )

    upload = project.stage_state(PipelineStage.UPLOAD)
    assert upload.status == StageStatus.COMPLETED
    assert project.current_stage == PipelineStage.REQUIREMENT_ANALYSIS
    assert project.progress == compute_progress(project.stages)
    assert project.created_at <= project.updated_at
    assert project.upload_manifest["priority"] == "standard"


def test_all_stages_start_pending_except_upload():
    project = AssignmentPipelineService().create_project()
    for stage in project.stages:
        if stage.stage == PipelineStage.UPLOAD:
            assert stage.status == StageStatus.COMPLETED
        else:
            assert stage.status == StageStatus.PENDING


def test_start_and_complete_stage_updates_progress():
    service = AssignmentPipelineService()
    project = service.create_project()
    project_id = project.id

    service.start_stage(project_id, PipelineStage.REQUIREMENT_ANALYSIS)
    project = service.get_project(project_id)
    req = project.stage_state(PipelineStage.REQUIREMENT_ANALYSIS)
    assert req.status == StageStatus.RUNNING
    assert req.started_at is not None

    service.complete_stage(
        project_id,
        PipelineStage.REQUIREMENT_ANALYSIS,
        StageResult(requirement_json={"assignmentType": "Essay", "estimatedWordCount": 2500}),
    )
    project = service.get_project(project_id)
    assert project.requirement_json["assignmentType"] == "Essay"
    assert project.current_stage == PipelineStage.PRICING
    assert project.stage_state(PipelineStage.REQUIREMENT_ANALYSIS).status == StageStatus.COMPLETED


def test_fail_stage_sets_failed_status():
    service = AssignmentPipelineService()
    project = service.create_project()
    service.fail_stage(project.id, PipelineStage.REQUIREMENT_ANALYSIS, "brief unreadable")
    project = service.get_project(project.id)
    record = project.stage_state(PipelineStage.REQUIREMENT_ANALYSIS)
    assert record.status == StageStatus.FAILED
    assert record.error == "brief unreadable"
    assert project.current_stage == PipelineStage.REQUIREMENT_ANALYSIS


def test_run_stage_without_handler_leaves_stage_running():
    service = AssignmentPipelineService()
    project = service.create_project()
    service.run_stage(project.id, PipelineStage.REQUIREMENT_ANALYSIS)
    project = service.get_project(project.id)
    assert project.stage_state(PipelineStage.REQUIREMENT_ANALYSIS).status == StageStatus.RUNNING
    assert project.current_stage == PipelineStage.REQUIREMENT_ANALYSIS


def test_run_stage_with_registered_handler_completes_stage():
    class _MockRequirementHandler:
        stage = PipelineStage.REQUIREMENT_ANALYSIS

        def run(self, context: StageContext) -> StageResult:
            return StageResult(
                requirement_json={"assignmentType": "Report"},
                output={"analyzer": "mock"},
            )

    registry = StageHandlerRegistry()
    registry.register(_MockRequirementHandler())
    service = AssignmentPipelineService(handlers=registry)
    project = service.create_project()
    service.run_stage(project.id, PipelineStage.REQUIREMENT_ANALYSIS)
    project = service.get_project(project.id)
    assert project.requirement_json == {"assignmentType": "Report"}
    assert project.current_stage == PipelineStage.PRICING


def test_project_to_dict_is_json_ready():
    project = AssignmentPipelineService().create_project({"note": "test"})
    payload = project.to_dict()
    assert payload["id"] == project.id
    assert payload["current_stage"] == PipelineStage.REQUIREMENT_ANALYSIS.value
    assert len(payload["stages"]) == 16
    assert payload["upload_manifest"]["note"] == "test"


def test_get_missing_project_raises():
    service = AssignmentPipelineService()
    with pytest.raises(KeyError):
        service.get_project("missing-id")
