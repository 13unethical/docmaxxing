"""Revision Engine data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

MAX_REVISION_ATTEMPTS = 3


@dataclass
class SectionRevision:
    issue_id: str
    section: str
    category: str
    change_description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "section": self.section,
            "category": self.category,
            "change_description": self.change_description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SectionRevision:
        return cls(
            issue_id=str(data.get("issue_id") or ""),
            section=str(data.get("section") or ""),
            category=str(data.get("category") or ""),
            change_description=str(data.get("change_description") or ""),
        )


@dataclass
class DraftVersionRecord:
    version: int
    draft_id: str
    title: str
    content: str
    total_words: int
    created_at: datetime | None
    changes: list[str] = field(default_factory=list)
    review_score: int | None = None
    source: str = "merge"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "draft_id": self.draft_id,
            "title": self.title,
            "content": self.content,
            "total_words": self.total_words,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "changes": list(self.changes),
            "review_score": self.review_score,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DraftVersionRecord:
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
        return cls(
            version=int(data.get("version") or 1),
            draft_id=str(data.get("draft_id") or ""),
            title=str(data.get("title") or ""),
            content=str(data.get("content") or ""),
            total_words=int(data.get("total_words") or 0),
            created_at=created_at,
            changes=list(data.get("changes") or []),
            review_score=data.get("review_score"),
            source=str(data.get("source") or "merge"),
        )


@dataclass
class RevisionHistory:
    project_id: str
    versions: list[DraftVersionRecord] = field(default_factory=list)
    revision_attempts: int = 0
    max_attempts: int = MAX_REVISION_ATTEMPTS
    needs_manual_review: bool = False

    @property
    def current_version(self) -> int:
        if not self.versions:
            return 0
        return self.versions[-1].version

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "current_version": self.current_version,
            "revision_attempts": self.revision_attempts,
            "max_attempts": self.max_attempts,
            "needs_manual_review": self.needs_manual_review,
            "versions": [version.to_dict() for version in self.versions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RevisionHistory:
        return cls(
            project_id=str(data.get("project_id") or ""),
            versions=[DraftVersionRecord.from_dict(item) for item in (data.get("versions") or [])],
            revision_attempts=int(data.get("revision_attempts") or 0),
            max_attempts=int(data.get("max_attempts") or MAX_REVISION_ATTEMPTS),
            needs_manual_review=bool(data.get("needs_manual_review")),
        )


@dataclass
class RevisionResult:
    id: str
    project_id: str | None
    draft: dict[str, Any]
    previous_version: int
    new_version: int
    changes: list[str]
    sections_revised: list[SectionRevision]
    issues_addressed: list[str]
    attempt_number: int
    engine_version: str = "mock-1.0"
    revised_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "draft": dict(self.draft),
            "previous_version": self.previous_version,
            "new_version": self.new_version,
            "changes": list(self.changes),
            "sections_revised": [item.to_dict() for item in self.sections_revised],
            "issues_addressed": list(self.issues_addressed),
            "attempt_number": self.attempt_number,
            "engine_version": self.engine_version,
            "revised_at": self.revised_at.isoformat() if self.revised_at else None,
        }


@dataclass
class RevisionEngineInput:
    requirement_json: dict[str, Any]
    research_plan: dict[str, Any]
    blueprint: dict[str, Any]
    draft: dict[str, Any]
    review_report: dict[str, Any]
    project_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "requirement_json": dict(self.requirement_json),
            "research_plan": dict(self.research_plan),
            "blueprint": dict(self.blueprint),
            "draft": dict(self.draft),
            "review_report": dict(self.review_report),
        }
