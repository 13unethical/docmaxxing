"""Job model for the production execution engine.

Every humanize request becomes a Job. Jobs are provider-agnostic so the same
engine can run StealthWriter, Turnitin, GPTZero, etc.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = {JobStatus.FAILED, JobStatus.COMPLETED, JobStatus.CANCELLED}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


@dataclass
class JobLogEntry:
    event: str
    message: str = ""
    level: str = "info"
    at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "message": self.message,
            "level": self.level,
            "at": _iso(self.at),
        }


@dataclass
class Job:
    provider: str
    operation: str
    payload: dict[str, Any] = field(default_factory=dict)
    max_retries: int = 3

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: JobStatus = JobStatus.QUEUED
    progress: str = "queued"

    attempts: int = 0
    error: str | None = None
    error_code: str | None = None
    error_details: dict[str, Any] | None = None
    result: dict[str, Any] | None = None

    current_provider: str | None = None
    current_browser: str | None = None

    created_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    # Runtime-only flags (not serialized directly).
    cancel_requested: bool = False
    timed_out: bool = False
    logs: list[JobLogEntry] = field(default_factory=list)

    # ------------------------------------------------------------------ helpers
    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or _now()
        return round((end - self.started_at).total_seconds(), 3)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    def log(self, event: str, message: str = "", level: str = "info") -> JobLogEntry:
        entry = JobLogEntry(event=event, message=message, level=level)
        self.logs.append(entry)
        print(
            f"[job {self.id[:8]}] {event}"
            + (f" — {message}" if message else ""),
            flush=True,
        )
        return entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "operation": self.operation,
            "status": self.status.value,
            "progress": self.progress,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "error": self.error,
            "error_code": self.error_code,
            "error_details": self.error_details,
            "result": self.result,
            "current_provider": self.current_provider,
            "current_browser": self.current_browser,
            "elapsed_seconds": self.elapsed_seconds,
            "created_at": _iso(self.created_at),
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "logs": [entry.to_dict() for entry in self.logs],
        }
