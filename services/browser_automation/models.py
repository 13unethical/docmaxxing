"""Dataclasses for the Browser Automation Framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class BrowserProviderType(str, Enum):
    STEALTHWRITER = "stealthwriter"
    TURNITIN = "turnitin"
    GRAMMARLY = "grammarly"
    GPTZERO = "gptzero"
    COPYLEAKS = "copyleaks"


class BrowserTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BrowserTask:
    id: str
    provider_type: BrowserProviderType
    operation: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: BrowserTaskStatus = BrowserTaskStatus.QUEUED
    retry_count: int = 0
    max_retries: int = 3
    session_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    error_message: str | None = None


@dataclass
class TaskResult:
    task_id: str
    provider_type: BrowserProviderType
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    completed_at: datetime | None = None


@dataclass
class BrowserSession:
    session_id: str
    provider: BrowserProviderType
    created_at: datetime
    last_used: datetime
    profile_path: str
    is_active: bool = True


@dataclass
class ProviderHealth:
    provider_type: BrowserProviderType
    healthy: bool
    message: str | None = None
    checked_at: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeHealth:
    browser_running: bool
    context_loaded: bool
    pages_open: int
    profile_exists: bool
