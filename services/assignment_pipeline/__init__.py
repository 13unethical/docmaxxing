"""Assignment project pipeline — workflow architecture for paid assignments."""

from services.assignment_pipeline.handlers import StageHandler, StageHandlerRegistry
from services.assignment_pipeline.models import (
    AssignmentProject,
    PipelineStage,
    StageProvider,
    StageState,
    StageStatus,
)
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_pipeline.stages import PIPELINE_STAGE_SPECS, stage_index

__all__ = [
    "AssignmentPipelineService",
    "AssignmentProject",
    "PIPELINE_STAGE_SPECS",
    "PipelineStage",
    "StageHandler",
    "StageHandlerRegistry",
    "StageProvider",
    "StageState",
    "StageStatus",
    "stage_index",
]
