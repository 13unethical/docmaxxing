"""Stage handler protocol and registry for future AI / service integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from services.assignment_pipeline.models import AssignmentProject, PipelineStage


@dataclass
class StageContext:
    """Shared context passed to every stage handler."""

    project: AssignmentProject
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StageResult:
    """Normalized handler output — stored on the stage record."""

    output: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    requirement_json: dict[str, Any] | None = None
    pricing: dict[str, Any] | None = None


class StageHandler(Protocol):
    """Implement one handler per pipeline stage when wiring real services."""

    stage: PipelineStage

    def run(self, context: StageContext) -> StageResult:
        """Execute stage logic. Not called until a handler is registered."""
        ...


class StageHandlerRegistry:
    """Maps pipeline stages to concrete handlers (Gemini, Claude, etc.)."""

    def __init__(self) -> None:
        self._handlers: dict[PipelineStage, StageHandler] = {}

    def register(self, handler: StageHandler) -> None:
        self._handlers[handler.stage] = handler

    def get(self, stage: PipelineStage) -> StageHandler | None:
        return self._handlers.get(stage)

    def has(self, stage: PipelineStage) -> bool:
        return stage in self._handlers

    def registered_stages(self) -> tuple[PipelineStage, ...]:
        return tuple(self._handlers.keys())
