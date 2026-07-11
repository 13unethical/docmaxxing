"""Humanizer Engine data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

MAX_PARAGRAPH_ATTEMPTS = 3


class HumanizerParagraphStatus(StrEnum):
    PENDING = "pending"
    HUMANIZING = "humanizing"
    VALIDATING = "validating"
    REVISION = "revision"
    COMPLETED = "completed"
    FAILED = "failed"


class HumanizerSessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    MERGED = "merged"


@dataclass
class ParagraphValidation:
    passed: bool
    issues: list[str] = field(default_factory=list)
    preserved_meaning: bool = True
    preserved_tone: bool = True
    preserved_formatting: bool = True
    preserved_citations: bool = True
    preserved_flow: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": list(self.issues),
            "preserved_meaning": self.preserved_meaning,
            "preserved_tone": self.preserved_tone,
            "preserved_formatting": self.preserved_formatting,
            "preserved_citations": self.preserved_citations,
            "preserved_flow": self.preserved_flow,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParagraphValidation:
        return cls(
            passed=bool(data.get("passed")),
            issues=list(data.get("issues") or []),
            preserved_meaning=bool(data.get("preserved_meaning", True)),
            preserved_tone=bool(data.get("preserved_tone", True)),
            preserved_formatting=bool(data.get("preserved_formatting", True)),
            preserved_citations=bool(data.get("preserved_citations", True)),
            preserved_flow=bool(data.get("preserved_flow", True)),
        )


@dataclass
class HumanizerParagraph:
    paragraph_id: str
    section: str
    original_text: str
    humanized_text: str = ""
    status: HumanizerParagraphStatus = HumanizerParagraphStatus.PENDING
    ai_score_before: int | None = None
    ai_score_after: int | None = None
    attempts: int = 0
    last_validation: ParagraphValidation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "paragraph_id": self.paragraph_id,
            "section": self.section,
            "original_text": self.original_text,
            "humanized_text": self.humanized_text,
            "status": self.status.value,
            "ai_score_before": self.ai_score_before,
            "ai_score_after": self.ai_score_after,
            "attempts": self.attempts,
            "last_validation": self.last_validation.to_dict() if self.last_validation else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HumanizerParagraph:
        status_raw = str(data.get("status") or HumanizerParagraphStatus.PENDING.value)
        try:
            status = HumanizerParagraphStatus(status_raw)
        except ValueError:
            status = HumanizerParagraphStatus.PENDING
        validation = data.get("last_validation")
        return cls(
            paragraph_id=str(data.get("paragraph_id") or ""),
            section=str(data.get("section") or ""),
            original_text=str(data.get("original_text") or ""),
            humanized_text=str(data.get("humanized_text") or ""),
            status=status,
            ai_score_before=data.get("ai_score_before"),
            ai_score_after=data.get("ai_score_after"),
            attempts=int(data.get("attempts") or 0),
            last_validation=ParagraphValidation.from_dict(validation) if isinstance(validation, dict) else None,
        )


@dataclass
class HumanizerSession:
    id: str
    project_id: str | None
    source_draft_id: str
    source_draft_version: int
    paragraphs: list[HumanizerParagraph]
    current_paragraph_id: str | None
    completed_paragraph_ids: list[str]
    remaining_paragraph_ids: list[str]
    progress: int
    paragraphs_processed: int
    average_ai_reduction: float
    estimated_remaining_time: str
    status: HumanizerSessionStatus = HumanizerSessionStatus.ACTIVE
    humanized_draft_id: str | None = None
    engine_version: str = "mock-1.0"
    requirement_json: dict[str, Any] = field(default_factory=dict)
    blueprint: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        current = self.current_paragraph()
        return {
            "id": self.id,
            "project_id": self.project_id,
            "source_draft_id": self.source_draft_id,
            "source_draft_version": self.source_draft_version,
            "current_paragraph_id": self.current_paragraph_id,
            "current_paragraph": current.to_dict() if current else None,
            "completed_paragraph_ids": list(self.completed_paragraph_ids),
            "remaining_paragraph_ids": list(self.remaining_paragraph_ids),
            "progress": self.progress,
            "paragraphs_processed": self.paragraphs_processed,
            "total_paragraphs": len(self.paragraphs),
            "average_ai_reduction": round(self.average_ai_reduction, 1),
            "estimated_remaining_time": self.estimated_remaining_time,
            "status": self.status.value,
            "humanized_draft_id": self.humanized_draft_id,
            "engine_version": self.engine_version,
            "requirement_json": dict(self.requirement_json),
            "blueprint": dict(self.blueprint),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "paragraphs": [paragraph.to_dict() for paragraph in self.paragraphs],
        }

    def current_paragraph(self) -> HumanizerParagraph | None:
        if not self.current_paragraph_id:
            return None
        for paragraph in self.paragraphs:
            if paragraph.paragraph_id == self.current_paragraph_id:
                return paragraph
        return None

    def paragraph_by_id(self, paragraph_id: str) -> HumanizerParagraph:
        for paragraph in self.paragraphs:
            if paragraph.paragraph_id == paragraph_id:
                return paragraph
        raise KeyError(f"Paragraph not found: {paragraph_id}")


@dataclass
class HumanizedDraft:
    id: str
    project_id: str | None
    session_id: str
    source_draft_id: str
    source_version: int
    title: str
    content: str
    total_words: int
    version: int
    paragraphs_processed: int
    average_ai_reduction: float
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "source_draft_id": self.source_draft_id,
            "source_version": self.source_version,
            "title": self.title,
            "content": self.content,
            "total_words": self.total_words,
            "version": self.version,
            "paragraphs_processed": self.paragraphs_processed,
            "average_ai_reduction": round(self.average_ai_reduction, 1),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HumanizedDraft:
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
        return cls(
            id=str(data["id"]),
            project_id=data.get("project_id"),
            session_id=str(data.get("session_id") or ""),
            source_draft_id=str(data.get("source_draft_id") or ""),
            source_version=int(data.get("source_version") or 0),
            title=str(data.get("title") or ""),
            content=str(data.get("content") or ""),
            total_words=int(data.get("total_words") or 0),
            version=int(data.get("version") or 1),
            paragraphs_processed=int(data.get("paragraphs_processed") or 0),
            average_ai_reduction=float(data.get("average_ai_reduction") or 0),
            created_at=created_at,
        )


@dataclass
class HumanizerEngineInput:
    draft: dict[str, Any]
    requirement_json: dict[str, Any]
    blueprint: dict[str, Any]
    project_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "draft": dict(self.draft),
            "requirement_json": dict(self.requirement_json),
            "blueprint": dict(self.blueprint),
        }


def count_words(text: str) -> int:
    return len([word for word in text.split() if word.strip()])
