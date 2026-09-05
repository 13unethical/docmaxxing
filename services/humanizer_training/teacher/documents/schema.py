"""Schemas for document-level offline teacher collection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TeacherChunkRecord:
    chunk_id: str
    index: int
    source_text: str
    teacher_text: str = ""
    source_word_count: int = 0
    teacher_word_count: int = 0
    status: str = "pending"
    quality_flags: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HumanizerTeacherDocument:
    document_id: str
    source_text: str
    teacher_text: str
    domain: str
    document_type: str
    language: str
    seed: int
    teacher_provider: str
    teacher_model: str
    teacher_level: int
    teacher_timeout: float
    source_word_count: int
    teacher_word_count: int
    source_body_word_count: int
    teacher_body_word_count: int
    references_present: bool
    references_word_count: int
    quality_flags: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    created_at: str = ""
    section_count: int = 0
    section_titles: list[str] = field(default_factory=list)
    chunks: list[TeacherChunkRecord] = field(default_factory=list)
    status: str = "accepted"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["chunks"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.chunks]
        return payload


@dataclass(slots=True)
class SyntheticDocument:
    document_id: str
    source_text: str
    domain: str
    document_type: str
    language: str
    seed: int
    word_count: int
    body_word_count: int
    references_present: bool
    references_word_count: int
    section_count: int
    section_titles: list[str]
    length_bucket: str
    topic: str = ""
    angle: str = ""
    generation_prompt: str = ""
    combination_key: str = ""


@dataclass(slots=True)
class DocumentCollectorConfig:
    count: int = 10
    seed: int = 300
    output_dir: str = "data/humanizer_training/teacher_raw_documents"
    dry_run: bool = False
    resume: bool = False
    delay_s: float = 0.0
    max_provider_words: int = 5000
    provider_name: str = "stealthwriter"
    model: str = "Legacy 5.1"
    level: int = 8
    timeout_s: float = 150.0
    # Collector-owned attempt budget (outer). Provider internal retries are forced to 1
    # to avoid nested multiplication (collector × provider).
    max_attempts_per_document: int = 2
    # Legacy alias kept for older callers; ignored when max_attempts_per_document is set
    # via the new CLI. Document collector always builds the browser provider with
    # max_retries=1.
    max_retries: int = 2
    allow_mock_provider: bool = False
