"""Project Engine: assignment lifecycle status + timeline with disk persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any

from services.assignment_pipeline.models import utc_now


class ProjectLifecycleStatus(StrEnum):
    UPLOADED = "UPLOADED"
    REQUIREMENTS_READY = "REQUIREMENTS_READY"
    RESEARCH_READY = "RESEARCH_READY"
    BLUEPRINT_READY = "BLUEPRINT_READY"
    WRITING = "WRITING"
    WRITING_COMPLETED = "WRITING_COMPLETED"
    SECTION_REVIEW = "SECTION_REVIEW"
    HUMANIZING = "HUMANIZING"
    AI_DETECTION = "AI_DETECTION"
    FINAL_REVIEW = "FINAL_REVIEW"
    EXPORTING = "EXPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


ORDERED_STEPS: list[ProjectLifecycleStatus] = [
    ProjectLifecycleStatus.UPLOADED,
    ProjectLifecycleStatus.REQUIREMENTS_READY,
    ProjectLifecycleStatus.RESEARCH_READY,
    ProjectLifecycleStatus.BLUEPRINT_READY,
    ProjectLifecycleStatus.WRITING,
    ProjectLifecycleStatus.WRITING_COMPLETED,
    ProjectLifecycleStatus.SECTION_REVIEW,
    ProjectLifecycleStatus.HUMANIZING,
    ProjectLifecycleStatus.AI_DETECTION,
    ProjectLifecycleStatus.FINAL_REVIEW,
    ProjectLifecycleStatus.EXPORTING,
    ProjectLifecycleStatus.COMPLETED,
]


@dataclass
class StageTimelineEntry:
    stage: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int = 0
    model_used: str | None = None
    success: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "model_used": self.model_used,
            "success": self.success,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StageTimelineEntry":
        return cls(
            stage=str(data.get("stage") or ""),
            status=str(data.get("status") or ""),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            duration_ms=int(data.get("duration_ms") or 0),
            model_used=data.get("model_used"),
            success=bool(data.get("success")),
            error=data.get("error"),
        )


@dataclass
class ProjectEngineState:
    project_id: str
    current_stage: str = ProjectLifecycleStatus.UPLOADED.value
    progress: int = 0
    timeline: list[StageTimelineEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "current_stage": self.current_stage,
            "progress": self.progress,
            "timeline": [item.to_dict() for item in self.timeline],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectEngineState":
        return cls(
            project_id=str(data.get("project_id") or ""),
            current_stage=str(data.get("current_stage") or ProjectLifecycleStatus.UPLOADED.value),
            progress=int(data.get("progress") or 0),
            timeline=[StageTimelineEntry.from_dict(x) for x in (data.get("timeline") or []) if isinstance(x, dict)],
        )


class ProjectEngine:
    def __init__(self, root_dir: str | None = None) -> None:
        self._root = Path(root_dir or "data/project_engine")
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._cache: dict[str, ProjectEngineState] = {}

    def init_project(self, project_id: str) -> ProjectEngineState:
        with self._lock:
            state = self._load(project_id)
            if state:
                return state
            state = ProjectEngineState(project_id=project_id)
            state.timeline.append(
                StageTimelineEntry(
                    stage=ProjectLifecycleStatus.UPLOADED.value,
                    status="completed",
                    started_at=utc_now().isoformat(),
                    finished_at=utc_now().isoformat(),
                    duration_ms=0,
                    success=True,
                )
            )
            state.progress = self._compute_progress(state.current_stage)
            self._save(state)
            return state

    def stage_start(self, project_id: str, stage: ProjectLifecycleStatus) -> StageTimelineEntry:
        with self._lock:
            state = self._require(project_id)
            entry = StageTimelineEntry(
                stage=stage.value,
                status="running",
                started_at=utc_now().isoformat(),
                success=False,
            )
            state.current_stage = stage.value
            state.timeline.append(entry)
            state.progress = self._compute_progress(state.current_stage)
            self._save(state)
            return entry

    def stage_finish(
        self,
        project_id: str,
        stage: ProjectLifecycleStatus,
        *,
        success: bool,
        model_used: str | None = None,
        error: str | None = None,
    ) -> StageTimelineEntry:
        with self._lock:
            state = self._require(project_id)
            entry = None
            for item in reversed(state.timeline):
                if item.stage == stage.value and item.status == "running":
                    entry = item
                    break
            if entry is None:
                entry = StageTimelineEntry(stage=stage.value, status="running", started_at=utc_now().isoformat())
                state.timeline.append(entry)

            finished = utc_now().isoformat()
            duration = _duration_ms(entry.started_at, finished)
            entry.finished_at = finished
            entry.duration_ms = duration
            entry.success = success
            entry.model_used = model_used
            entry.error = error
            entry.status = "completed" if success else "failed"

            if success:
                state.current_stage = stage.value
            else:
                state.current_stage = ProjectLifecycleStatus.FAILED.value
            state.progress = self._compute_progress(state.current_stage)
            self._save(state)
            return entry

    def get_timeline(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            state = self._require(project_id)
            return [item.to_dict() for item in state.timeline]

    def get_status(self, project_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._require(project_id)
            current = state.current_stage
            completed_steps = [x.stage for x in state.timeline if x.success]
            remaining = [s.value for s in ORDERED_STEPS if s.value not in completed_steps]
            return {
                "current_stage": current,
                "progress": state.progress,
                "completed_steps": completed_steps,
                "remaining_steps": remaining,
                "estimated_remaining_time": _estimate_remaining_time(state),
            }

    def resume_stage(self, project_id: str) -> str:
        with self._lock:
            state = self._require(project_id)
            completed = {x.stage for x in state.timeline if x.success}
            for step in ORDERED_STEPS:
                if step.value not in completed:
                    return step.value
            return ProjectLifecycleStatus.COMPLETED.value

    def _require(self, project_id: str) -> ProjectEngineState:
        state = self._cache.get(project_id) or self._load(project_id)
        if not state:
            raise KeyError(f"Project Engine state not found: {project_id}")
        self._cache[project_id] = state
        return state

    def _save(self, state: ProjectEngineState) -> None:
        self._cache[state.project_id] = state
        path = self._root / f"{state.project_id}.json"
        path.write_text(json.dumps(state.to_dict(), ensure_ascii=False), encoding="utf-8")

    def _load(self, project_id: str) -> ProjectEngineState | None:
        path = self._root / f"{project_id}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(payload, dict):
            return None
        state = ProjectEngineState.from_dict(payload)
        if not state.project_id:
            state.project_id = project_id
        return state

    def _compute_progress(self, current_stage: str) -> int:
        if current_stage == ProjectLifecycleStatus.FAILED.value:
            return 0
        if current_stage == ProjectLifecycleStatus.COMPLETED.value:
            return 100
        idx = 0
        for i, step in enumerate(ORDERED_STEPS):
            if step.value == current_stage:
                idx = i + 1
                break
        return int(round(100 * idx / len(ORDERED_STEPS)))


def _duration_ms(started_at: str | None, finished_at: str | None) -> int:
    if not started_at or not finished_at:
        return 0
    try:
        s = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        f = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, int((f - s).total_seconds() * 1000))


def _estimate_remaining_time(state: ProjectEngineState) -> str:
    durations = [item.duration_ms for item in state.timeline if item.success and item.duration_ms > 0]
    avg = int(sum(durations) / len(durations)) if durations else 12000
    completed = len([x for x in state.timeline if x.success and x.stage in {s.value for s in ORDERED_STEPS}])
    remain_count = max(0, len(ORDERED_STEPS) - completed)
    total_ms = remain_count * avg
    mins = max(0, round(total_ms / 60000))
    return f"{mins} min" if mins else "<1 min"
