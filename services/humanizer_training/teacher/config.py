"""Configuration and models for isolated teacher-data collection.

Canonical live path is document-level collection under ``teacher/documents/``.
Defaults target the isolated StealthWriter training provider (Legacy 5.1 / level 8).
``mock_teacher`` is available only when explicitly requested (tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SOURCE_TYPE = "synthetic"
LANGUAGE = "en"

# Canonical training teacher selection.
DEFAULT_PROVIDER_NAME = "stealthwriter"
DEFAULT_MODEL = "Legacy 5.1"
DEFAULT_LEVEL = 8
DEFAULT_TIMEOUT_S = 150.0


@dataclass(slots=True)
class TeacherProviderConfig:
    provider_name: str = DEFAULT_PROVIDER_NAME
    model: str | None = DEFAULT_MODEL
    level: int | str | None = DEFAULT_LEVEL
    timeout_s: float | None = DEFAULT_TIMEOUT_S
    max_retries: int = 3
    retry_delay_s: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_s: float = 15.0
    endpoint: str | None = None
    api_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def safe_dict(self) -> dict[str, Any]:
        """Serializable provider config without secrets."""
        return {
            "provider_name": self.provider_name,
            "model": self.model,
            "level": self.level,
            "timeout_s": (float(self.timeout_s) if self.timeout_s is not None else None),
            "max_retries": int(self.max_retries),
            "retry_delay_s": float(self.retry_delay_s),
            "backoff_multiplier": float(self.backoff_multiplier),
            "max_delay_s": float(self.max_delay_s),
            "endpoint": self.endpoint,
            "extra": dict(self.extra),
        }


@dataclass(slots=True)
class TeacherResult:
    text: str
    provider: str
    version: str
    meta: dict = field(default_factory=dict)  # actual runtime config, safe to store
