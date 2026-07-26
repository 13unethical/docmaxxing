"""Pipeline orchestration — state machine without stage implementations."""

from __future__ import annotations

import uuid
from typing import Any

from services.assignment_pipeline.handlers import StageContext, StageHandlerRegistry, StageResult
from services.assignment_pipeline.models import (
    AssignmentProject,
    PipelineStage,
    StageState,
    StageStatus,
    utc_now,
)
from services.assignment_pipeline.stages import PIPELINE_STAGES
from services.assignment_pipeline.store import AssignmentProjectStore


def _initial_stages() -> list[StageState]:
    return [StageState(stage=stage) for stage in PIPELINE_STAGES]


def _completed_count(stages: list[StageState]) -> int:
    return sum(1 for stage in stages if stage.status == StageStatus.COMPLETED)


def compute_progress(stages: list[StageState]) -> int:
    if not stages:
        return 0
    return int(round(100 * _completed_count(stages) / len(stages)))


def resolve_current_stage(stages: list[StageState]) -> PipelineStage:
    for stage in stages:
        if stage.status != StageStatus.COMPLETED:
            return stage.stage
    return PipelineStage.DELIVERY


def _touch(project: AssignmentProject) -> None:
    project.updated_at = utc_now()
    project.progress = compute_progress(project.stages)
    project.current_stage = resolve_current_stage(project.stages)


class AssignmentPipelineService:
    """Create and advance assignment projects through the pipeline."""

    def __init__(
        self,
        store: AssignmentProjectStore | None = None,
        handlers: StageHandlerRegistry | None = None,
    ) -> None:
        self.store = store or AssignmentProjectStore()
        self.handlers = handlers or StageHandlerRegistry()

    def create_project(
        self,
        upload_manifest: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> AssignmentProject:
        now = utc_now()
        project = AssignmentProject(
            id=project_id or str(uuid.uuid4()),
            stages=_initial_stages(),
            current_stage=PipelineStage.UPLOAD,
            progress=0,
            created_at=now,
            updated_at=now,
            upload_manifest=dict(upload_manifest or {}),
        )
        self._complete_stage(project, PipelineStage.UPLOAD, StageResult(output={"received": True}))
        return self.store.save(project)

    def get_project(self, project_id: str) -> AssignmentProject:
        return self.store.require(project_id)

    def start_stage(
        self,
        project_id: str,
        stage: PipelineStage,
        *,
        force: bool = False,
    ) -> AssignmentProject:
        project = self.store.require(project_id)
        record = project.stage_state(stage)
        if record.status == StageStatus.COMPLETED and not force:
            return project
        if force and record.status in {StageStatus.COMPLETED, StageStatus.FAILED}:
            record.output = {}
            record.completed_at = None
        record.status = StageStatus.RUNNING
        record.started_at = utc_now()
        record.error = None
        _touch(project)
        return self.store.save(project)

    def reset_stage(self, project_id: str, stage: PipelineStage) -> AssignmentProject:
        """Clear one stage so it can be retried without touching earlier stages."""
        project = self.store.require(project_id)
        record = project.stage_state(stage)
        record.status = StageStatus.PENDING
        record.started_at = None
        record.completed_at = None
        record.error = None
        record.output = {}
        _touch(project)
        return self.store.save(project)

    def complete_stage(
        self,
        project_id: str,
        stage: PipelineStage,
        result: StageResult | None = None,
    ) -> AssignmentProject:
        project = self.store.require(project_id)
        self._complete_stage(project, stage, result)
        return self.store.save(project)

    def fail_stage(self, project_id: str, stage: PipelineStage, error: str) -> AssignmentProject:
        project = self.store.require(project_id)
        record = project.stage_state(stage)
        record.status = StageStatus.FAILED
        record.error = error
        record.completed_at = utc_now()
        _touch(project)
        return self.store.save(project)

    def run_stage(self, project_id: str, stage: PipelineStage | None = None) -> AssignmentProject:
        """Run a registered handler for a stage. No-op if handler is not wired yet."""
        project = self.store.require(project_id)
        target = stage or project.current_stage
        handler = self.handlers.get(target)
        self.start_stage(project_id, target)
        project = self.store.require(project_id)

        if handler is None:
            return project

        try:
            result = handler.run(StageContext(project=project))
        except Exception as exc:  # noqa: BLE001 — surface stage failure to caller
            return self.fail_stage(project_id, target, str(exc))

        return self.complete_stage(project_id, target, result)

    def attach_requirement_json(
        self,
        project_id: str,
        requirement_json: dict[str, Any],
    ) -> AssignmentProject:
        project = self.store.require(project_id)
        project.requirement_json = dict(requirement_json)
        _touch(project)
        return self.store.save(project)

    def attach_pricing(self, project_id: str, pricing: dict[str, Any]) -> AssignmentProject:
        project = self.store.require(project_id)
        project.pricing = dict(pricing)
        _touch(project)
        return self.store.save(project)

    def _complete_stage(
        self,
        project: AssignmentProject,
        stage: PipelineStage,
        result: StageResult | None,
    ) -> None:
        record = project.stage_state(stage)
        record.status = StageStatus.COMPLETED
        record.completed_at = utc_now()
        record.error = None
        if result:
            record.output = dict(result.output)
            if result.requirement_json is not None:
                project.requirement_json = dict(result.requirement_json)
            if result.pricing is not None:
                project.pricing = dict(result.pricing)
            if result.artifacts:
                project.artifacts.update(result.artifacts)
        _touch(project)
