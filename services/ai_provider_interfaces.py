"""Provider-agnostic AI interfaces for backend integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class DetectionResult:
    provider: str
    ai_score: float
    passed: bool
    paragraphs: list[dict[str, Any]]
    raw: dict[str, Any]


@dataclass(slots=True)
class HumanizedResult:
    provider: str
    text: str
    original_words: int
    humanized_words: int
    processing_time: float
    raw: dict[str, Any]


class DetectionProvider(Protocol):
    def detect(self, text: str) -> DetectionResult: ...


class HumanizerProvider(Protocol):
    def humanize(self, text: str) -> HumanizedResult: ...
