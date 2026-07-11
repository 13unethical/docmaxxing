"""Core data models for assignment project pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class PipelineStage(StrEnum):
    UPLOAD = "upload"
    REQUIREMENT_ANALYSIS = "requirement_analysis"
    PRICING = "pricing"
    WAITING_FOR_PAYMENT = "waiting_for_payment"
    RESEARCH = "research"
    BLUEPRINT = "blueprint"
    WRITING = "writing"
    MERGE = "merge"
    STYLE_REVIEW = "style_review"
    CITATION_GENERATION = "citation_generation"
    REQUIREMENT_VALIDATION = "requirement_validation"
    REVISION = "revision"
    HUMANIZATION = "humanization"
    AI_DETECTION = "ai_detection"
    DELIVERY = "delivery"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageProvider(StrEnum):
    """Integration slot for future AI / external services."""

    INTERNAL = "internal"
    GEMINI = "gemini"
    CLAUDE = "claude"
    HUMANIZER = "humanizer"
    TURNITIN = "turnitin"
    CHECK_PIPELINE = "check_pipeline"
    CITATION_ENGINE = "citation_engine"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StageState:
    stage: PipelineStage
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    output: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "output": dict(self.output),
        }


@dataclass
class AssignmentProject:
    """One assignment order tracked through the full production pipeline."""

    id: str
    stages: list[StageState]
    current_stage: PipelineStage
    progress: int
    created_at: datetime
    updated_at: datetime
    upload_manifest: dict[str, Any] = field(default_factory=dict)
    requirement_json: dict[str, Any] | None = None
    pricing: dict[str, Any] | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)

    def stage_state(self, stage: PipelineStage) -> StageState:
        for item in self.stages:
            if item.stage == stage:
                return item
        raise KeyError(f"Unknown stage: {stage}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "current_stage": self.current_stage.value,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "upload_manifest": dict(self.upload_manifest),
            "requirement_json": self.requirement_json,
            "pricing": self.pricing,
            "artifacts": dict(self.artifacts),
            "stages": [stage.to_dict() for stage in self.stages],
        }
