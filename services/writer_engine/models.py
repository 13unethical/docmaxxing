"""Writer Engine data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class WriterSectionStatus(StrEnum):
    PENDING = "pending"
    WRITING = "writing"
    SECTION_REVIEW = "section_review"
    REVISION = "revision"
    COMPLETED = "completed"


class WriterSessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    MERGED = "merged"


@dataclass
class SectionReview:
    passed: bool
    score: int
    requirement_coverage: int = 0
    argument_quality: int = 0
    academic_style: int = 0
    citation_quality: int = 0
    critical_thinking: int = 0
    missing_points: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    needs_revision: bool = False
    needs_manual_review: bool = False
    review_message: str = ""
    reviewed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "requirement_coverage": self.requirement_coverage,
            "argument_quality": self.argument_quality,
            "academic_style": self.academic_style,
            "citation_quality": self.citation_quality,
            "critical_thinking": self.critical_thinking,
            "missing_points": list(self.missing_points),
            "warnings": list(self.warnings),
            "needs_revision": self.needs_revision,
            "needs_manual_review": self.needs_manual_review,
            "review_message": self.review_message,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SectionReview:
        reviewed_at = None
        if data.get("reviewed_at"):
            reviewed_at = datetime.fromisoformat(str(data["reviewed_at"]).replace("Z", "+00:00"))
        return cls(
            passed=bool(data.get("passed")),
            score=int(data.get("score") or 0),
            requirement_coverage=int(data.get("requirement_coverage") or 0),
            argument_quality=int(data.get("argument_quality") or 0),
            academic_style=int(data.get("academic_style") or 0),
            citation_quality=int(data.get("citation_quality") or 0),
            critical_thinking=int(data.get("critical_thinking") or 0),
            missing_points=list(data.get("missing_points") or []),
            warnings=list(data.get("warnings") or []),
            needs_revision=bool(data.get("needs_revision")),
            needs_manual_review=bool(data.get("needs_manual_review")),
            review_message=str(data.get("review_message") or ""),
            reviewed_at=reviewed_at,
        )


@dataclass
class WriterSection:
    id: str
    title: str
    objective: str
    estimated_words: int
    generated_text: str = ""
    citations_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generation_time: float = 0.0
    model_used: str = ""
    status: WriterSectionStatus = WriterSectionStatus.PENDING
    review_score: int | None = None
    revision_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_review: SectionReview | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "objective": self.objective,
            "estimated_words": self.estimated_words,
            "generated_text": self.generated_text,
            "citations_used": list(self.citations_used),
            "warnings": list(self.warnings),
            "generation_time": self.generation_time,
            "model_used": self.model_used,
            "status": self.status.value,
            "review_score": self.review_score,
            "revision_count": self.revision_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_review": self.last_review.to_dict() if self.last_review else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WriterSection:
        status_raw = str(data.get("status") or WriterSectionStatus.PENDING.value)
        try:
            status = WriterSectionStatus(status_raw)
        except ValueError:
            status = WriterSectionStatus.PENDING
        started_at = None
        completed_at = None
        if data.get("started_at"):
            started_at = datetime.fromisoformat(str(data["started_at"]).replace("Z", "+00:00"))
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(str(data["completed_at"]).replace("Z", "+00:00"))
        review = data.get("last_review")
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            objective=str(data.get("objective") or ""),
            estimated_words=int(data.get("estimated_words") or 0),
            generated_text=str(data.get("generated_text") or ""),
            citations_used=list(data.get("citations_used") or []),
            warnings=list(data.get("warnings") or []),
            generation_time=float(data.get("generation_time") or 0.0),
            model_used=str(data.get("model_used") or ""),
            status=status,
            review_score=data.get("review_score"),
            revision_count=int(data.get("revision_count") or 0),
            started_at=started_at,
            completed_at=completed_at,
            last_review=SectionReview.from_dict(review) if isinstance(review, dict) else None,
        )


@dataclass
class WriterSession:
    id: str
    project_id: str | None
    sections: list[WriterSection]
    current_section_id: str | None
    completed_section_ids: list[str]
    remaining_section_ids: list[str]
    progress: int
    total_words_written: int
    estimated_remaining_time: str
    status: WriterSessionStatus = WriterSessionStatus.ACTIVE
    draft_id: str | None = None
    engine_version: str = "mock-1.0"
    requirement_json: dict[str, Any] = field(default_factory=dict)
    research_plan: dict[str, Any] = field(default_factory=dict)
    blueprint: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        current = self.current_section()
        return {
            "id": self.id,
            "project_id": self.project_id,
            "current_section_id": self.current_section_id,
            "current_section": current.to_dict() if current else None,
            "completed_section_ids": list(self.completed_section_ids),
            "remaining_section_ids": list(self.remaining_section_ids),
            "progress": self.progress,
            "total_words_written": self.total_words_written,
            "estimated_remaining_time": self.estimated_remaining_time,
            "status": self.status.value,
            "draft_id": self.draft_id,
            "engine_version": self.engine_version,
            "requirement_json": dict(self.requirement_json),
            "research_plan": dict(self.research_plan),
            "blueprint": dict(self.blueprint),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sections": [section.to_dict() for section in self.sections],
            "writing_queue": [section.title for section in self.sections],
        }

    def current_section(self) -> WriterSection | None:
        if not self.current_section_id:
            return None
        for section in self.sections:
            if section.id == self.current_section_id:
                return section
        return None

    def section_by_id(self, section_id: str) -> WriterSection:
        for section in self.sections:
            if section.id == section_id:
                return section
        raise KeyError(f"Section not found: {section_id}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WriterSession:
        status_raw = str(data.get("status") or WriterSessionStatus.ACTIVE.value)
        try:
            status = WriterSessionStatus(status_raw)
        except ValueError:
            status = WriterSessionStatus.ACTIVE
        created_at = None
        updated_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(str(data["updated_at"]).replace("Z", "+00:00"))
        sections = [WriterSection.from_dict(section) for section in (data.get("sections") or [])]
        return cls(
            id=str(data.get("id") or ""),
            project_id=data.get("project_id"),
            sections=sections,
            current_section_id=data.get("current_section_id"),
            completed_section_ids=list(data.get("completed_section_ids") or []),
            remaining_section_ids=list(data.get("remaining_section_ids") or []),
            progress=int(data.get("progress") or 0),
            total_words_written=int(data.get("total_words_written") or 0),
            estimated_remaining_time=str(data.get("estimated_remaining_time") or "0 minutes"),
            status=status,
            draft_id=data.get("draft_id"),
            engine_version=str(data.get("engine_version") or "mock-1.0"),
            requirement_json=dict(data.get("requirement_json") or {}),
            research_plan=dict(data.get("research_plan") or {}),
            blueprint=dict(data.get("blueprint") or {}),
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass
class Draft:
    id: str
    project_id: str | None
    session_id: str
    title: str
    content: str
    sections: list[dict[str, Any]] = field(default_factory=list)
    total_words: int = 0
    generation_time: float = 0.0
    model: str = ""
    version: int = 1
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "title": self.title,
            "content": self.content,
            "sections": list(self.sections),
            "total_words": self.total_words,
            "generation_time": self.generation_time,
            "model": self.model,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Draft:
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
        return cls(
            id=str(data["id"]),
            project_id=data.get("project_id"),
            session_id=str(data.get("session_id") or ""),
            title=str(data.get("title") or ""),
            content=str(data.get("content") or ""),
            sections=list(data.get("sections") or []),
            total_words=int(data.get("total_words") or 0),
            generation_time=float(data.get("generation_time") or 0.0),
            model=str(data.get("model") or ""),
            version=int(data.get("version") or 1),
            created_at=created_at,
        )


@dataclass
class WriterEngineInput:
    requirement_json: dict[str, Any]
    research_plan: dict[str, Any]
    blueprint: dict[str, Any]
    project_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "requirement_json": dict(self.requirement_json),
            "research_plan": dict(self.research_plan),
            "blueprint": dict(self.blueprint),
        }


def count_words(text: str) -> int:
    return len([word for word in text.split() if word.strip()])
