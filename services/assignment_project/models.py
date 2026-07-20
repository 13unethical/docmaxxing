"""Project, file, and requirement data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from services.assignment_pipeline.models import PipelineStage, utc_now


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


class ProjectFileType(StrEnum):
    ASSIGNMENT_BRIEF = "assignment_brief"
    RUBRIC = "rubric"
    LECTURE_SLIDES = "lecture_slides"
    READING_MATERIAL = "reading_material"
    SAMPLE_ASSIGNMENT = "sample_assignment"
    PROFESSOR_NOTES = "professor_notes"
    ADDITIONAL_FILE = "additional_file"


@dataclass
class RubricCriterion:
    criterion: str
    weight: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "criterion": self.criterion,
            "weight": self.weight,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RubricCriterion:
        return cls(
            criterion=str(data.get("criterion") or ""),
            weight=str(data.get("weight") or ""),
            description=str(data.get("description") or ""),
        )


@dataclass
class RequirementFormatting:
    font_family: str | None = None
    font_size: int | None = None
    line_spacing: float | None = None
    margins: str | None = None
    alignment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "font_family": self.font_family,
            "font_size": self.font_size,
            "line_spacing": self.line_spacing,
            "margins": self.margins,
            "alignment": self.alignment,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RequirementFormatting:
        if not data:
            return cls()
        return cls(
            font_family=data.get("font_family"),
            font_size=data.get("font_size"),
            line_spacing=data.get("line_spacing"),
            margins=data.get("margins"),
            alignment=data.get("alignment"),
        )


@dataclass
class RequirementJSON:
    """Structured requirements — one per project. Populated by analyzer (mock → Gemini)."""

    id: str
    project_id: str
    assignment_type: str | None = None
    title: str | None = None
    word_count: int | None = None
    citation_style: str | None = None
    required_sections: list[str] = field(default_factory=list)
    # Explicit per-section limits from the brief, e.g. {"Introduction": 100, "Reflection": 300}.
    section_word_budgets: dict[str, int] = field(default_factory=dict)
    rubric: list[RubricCriterion] = field(default_factory=list)
    learning_outcomes: list[str] = field(default_factory=list)
    minimum_sources: int | None = None
    formatting: RequirementFormatting = field(default_factory=RequirementFormatting)
    deadline: str | None = None
    difficulty: str | None = None
    academic_level: str | None = None
    missing_information: list[str] = field(default_factory=list)
    analyzer_version: str = "mock-1.0"
    analyzed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "assignment_type": self.assignment_type,
            "title": self.title,
            "word_count": self.word_count,
            "citation_style": self.citation_style,
            "required_sections": list(self.required_sections),
            "section_word_budgets": dict(self.section_word_budgets),
            "rubric": [item.to_dict() for item in self.rubric],
            "learning_outcomes": list(self.learning_outcomes),
            "minimum_sources": self.minimum_sources,
            "formatting": self.formatting.to_dict(),
            "deadline": self.deadline,
            "difficulty": self.difficulty,
            "academic_level": self.academic_level,
            "missing_information": list(self.missing_information),
            "analyzer_version": self.analyzer_version,
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequirementJSON:
        analyzed_raw = data.get("analyzed_at")
        analyzed_at = None
        if analyzed_raw:
            analyzed_at = datetime.fromisoformat(str(analyzed_raw).replace("Z", "+00:00"))
        return cls(
            id=str(data["id"]),
            project_id=str(data["project_id"]),
            assignment_type=data.get("assignment_type"),
            title=data.get("title"),
            word_count=data.get("word_count"),
            citation_style=data.get("citation_style"),
            required_sections=list(data.get("required_sections") or []),
            section_word_budgets={
                str(k): int(v)
                for k, v in dict(data.get("section_word_budgets") or {}).items()
                if str(k).strip() and int(v) >= 0
            },
            rubric=[RubricCriterion.from_dict(item) for item in (data.get("rubric") or [])],
            learning_outcomes=list(data.get("learning_outcomes") or []),
            minimum_sources=data.get("minimum_sources"),
            formatting=RequirementFormatting.from_dict(data.get("formatting")),
            deadline=data.get("deadline"),
            difficulty=data.get("difficulty"),
            academic_level=data.get("academic_level"),
            missing_information=list(data.get("missing_information") or []),
            analyzer_version=str(data.get("analyzer_version") or "mock-1.0"),
            analyzed_at=analyzed_at,
        )


@dataclass
class ProjectFile:
    id: str
    project_id: str
    file_type: ProjectFileType
    filename: str
    original_filename: str
    storage_path: str
    parsed: bool = False
    uploaded_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "file_type": self.file_type.value,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "storage_path": self.storage_path,
            "parsed": self.parsed,
            "uploaded_at": self.uploaded_at.isoformat(),
        }


    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectFile:
        uploaded_raw = data.get("uploaded_at")
        uploaded_at = utc_now()
        if uploaded_raw:
            uploaded_at = datetime.fromisoformat(str(uploaded_raw).replace("Z", "+00:00"))
        return cls(
            id=str(data["id"]),
            project_id=str(data["project_id"]),
            file_type=ProjectFileType(str(data.get("file_type") or ProjectFileType.ADDITIONAL_FILE.value)),
            filename=str(data.get("filename") or data.get("original_filename") or ""),
            original_filename=str(data.get("original_filename") or ""),
            storage_path=str(data.get("storage_path") or ""),
            parsed=bool(data.get("parsed")),
            uploaded_at=uploaded_at,
        )


@dataclass
class Project:
    id: str
    user_id: str | None
    title: str
    assignment_type: str | None
    university: str | None
    status: ProjectStatus
    current_stage: PipelineStage
    progress: int
    price: float | None
    credits: int | None
    estimated_word_count: int | None
    citation_style: str | None
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime
    note: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "assignment_type": self.assignment_type,
            "university": self.university,
            "status": self.status.value,
            "current_stage": self.current_stage.value,
            "progress": self.progress,
            "price": self.price,
            "credits": self.credits,
            "estimated_word_count": self.estimated_word_count,
            "citation_style": self.citation_style,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "note": self.note,
            "artifacts": dict(self.artifacts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        def _parse_dt(value: str | None) -> datetime | None:
            if not value:
                return None
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        created = _parse_dt(data.get("created_at")) or utc_now()
        updated = _parse_dt(data.get("updated_at")) or created
        return cls(
            id=str(data["id"]),
            user_id=data.get("user_id"),
            title=str(data.get("title") or "Untitled Assignment"),
            assignment_type=data.get("assignment_type"),
            university=data.get("university"),
            status=ProjectStatus(str(data.get("status") or ProjectStatus.DRAFT.value)),
            current_stage=PipelineStage(str(data.get("current_stage") or PipelineStage.UPLOAD.value)),
            progress=int(data.get("progress") or 0),
            price=data.get("price"),
            credits=data.get("credits"),
            estimated_word_count=data.get("estimated_word_count"),
            citation_style=data.get("citation_style"),
            deadline=_parse_dt(data.get("deadline")),
            created_at=created,
            updated_at=updated,
            note=data.get("note"),
            artifacts=dict(data.get("artifacts") or {}),
        )


@dataclass
class ProjectBundle:
    """Project with related files and requirement JSON."""

    project: Project
    files: list[ProjectFile]
    requirement: RequirementJSON

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project.to_dict(),
            "files": [item.to_dict() for item in self.files],
            "requirement": self.requirement.to_dict(),
        }
