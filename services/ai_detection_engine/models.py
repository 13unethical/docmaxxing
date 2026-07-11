"""AI Detection Engine data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

MAX_DETECTION_ATTEMPTS = 3


class ParagraphDetectionStatus(StrEnum):
    PENDING = "pending"
    DETECTING = "detecting"
    PASSED = "passed"
    FAILED = "failed"
    REPROCESSING = "reprocessing"
    COMPLETED = "completed"
    MANUAL_REVIEW = "manual_review"


class DetectionSessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


class FinalDetectionStatus(StrEnum):
    PASSED = "passed"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


@dataclass
class DetectionThresholds:
    excellent_max: float = 5.0
    good_max: float = 10.0
    acceptable_max: float = 15.0
    needs_revision_max: float = 25.0

    def to_dict(self) -> dict[str, float]:
        return {
            "excellent_max": self.excellent_max,
            "good_max": self.good_max,
            "acceptable_max": self.acceptable_max,
            "needs_revision_max": self.needs_revision_max,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DetectionThresholds:
        if not data:
            return cls()
        return cls(
            excellent_max=float(data.get("excellent_max", 5.0)),
            good_max=float(data.get("good_max", 10.0)),
            acceptable_max=float(data.get("acceptable_max", 15.0)),
            needs_revision_max=float(data.get("needs_revision_max", 25.0)),
        )


@dataclass
class ParagraphDetection:
    paragraph_id: str
    section: str
    text: str
    ai_score: float | None = None
    status: ParagraphDetectionStatus = ParagraphDetectionStatus.PENDING
    attempts: int = 0
    last_checked: datetime | None = None
    humanizer_paragraph_id: str | None = None
    classification: str | None = None
    reprocessed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "paragraph_id": self.paragraph_id,
            "section": self.section,
            "text": self.text,
            "ai_score": self.ai_score,
            "status": self.status.value,
            "attempts": self.attempts,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "humanizer_paragraph_id": self.humanizer_paragraph_id,
            "classification": self.classification,
            "reprocessed": self.reprocessed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParagraphDetection:
        status_raw = str(data.get("status") or ParagraphDetectionStatus.PENDING.value)
        try:
            status = ParagraphDetectionStatus(status_raw)
        except ValueError:
            status = ParagraphDetectionStatus.PENDING
        last_checked = None
        if data.get("last_checked"):
            last_checked = datetime.fromisoformat(str(data["last_checked"]).replace("Z", "+00:00"))
        return cls(
            paragraph_id=str(data.get("paragraph_id") or ""),
            section=str(data.get("section") or ""),
            text=str(data.get("text") or ""),
            ai_score=float(data["ai_score"]) if data.get("ai_score") is not None else None,
            status=status,
            attempts=int(data.get("attempts") or 0),
            last_checked=last_checked,
            humanizer_paragraph_id=data.get("humanizer_paragraph_id"),
            classification=data.get("classification"),
            reprocessed=bool(data.get("reprocessed")),
        )


@dataclass
class DetectionSession:
    id: str
    project_id: str | None
    humanized_draft_id: str
    paragraphs: list[ParagraphDetection]
    current_paragraph_id: str | None
    completed_paragraph_ids: list[str]
    remaining_paragraph_ids: list[str]
    progress: int
    paragraphs_completed: int
    average_ai_score: float
    thresholds: DetectionThresholds
    status: DetectionSessionStatus = DetectionSessionStatus.ACTIVE
    report_id: str | None = None
    engine_version: str = "mock-1.0"
    requirement_json: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        current = self.current_paragraph()
        return {
            "id": self.id,
            "project_id": self.project_id,
            "humanized_draft_id": self.humanized_draft_id,
            "current_paragraph_id": self.current_paragraph_id,
            "current_paragraph": current.to_dict() if current else None,
            "completed_paragraph_ids": list(self.completed_paragraph_ids),
            "remaining_paragraph_ids": list(self.remaining_paragraph_ids),
            "progress": self.progress,
            "paragraphs_completed": self.paragraphs_completed,
            "total_paragraphs": len(self.paragraphs),
            "average_ai_score": round(self.average_ai_score, 1),
            "thresholds": self.thresholds.to_dict(),
            "status": self.status.value,
            "report_id": self.report_id,
            "engine_version": self.engine_version,
            "requirement_json": dict(self.requirement_json),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "paragraphs": [paragraph.to_dict() for paragraph in self.paragraphs],
        }

    def current_paragraph(self) -> ParagraphDetection | None:
        if not self.current_paragraph_id:
            return None
        for paragraph in self.paragraphs:
            if paragraph.paragraph_id == self.current_paragraph_id:
                return paragraph
        return None

    def paragraph_by_id(self, paragraph_id: str) -> ParagraphDetection:
        for paragraph in self.paragraphs:
            if paragraph.paragraph_id == paragraph_id:
                return paragraph
        raise KeyError(f"Paragraph not found: {paragraph_id}")


@dataclass
class DetectionReport:
    id: str
    project_id: str | None
    session_id: str
    overall_ai_score: float
    paragraph_scores: list[dict[str, Any]]
    average_score: float
    highest_score: float
    lowest_score: float
    paragraphs_reprocessed: int
    final_status: FinalDetectionStatus
    thresholds: DetectionThresholds
    engine_version: str = "mock-1.0"
    generated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "overall_ai_score": round(self.overall_ai_score, 1),
            "paragraph_scores": list(self.paragraph_scores),
            "average_score": round(self.average_score, 1),
            "highest_score": round(self.highest_score, 1),
            "lowest_score": round(self.lowest_score, 1),
            "paragraphs_reprocessed": self.paragraphs_reprocessed,
            "final_status": self.final_status.value,
            "thresholds": self.thresholds.to_dict(),
            "engine_version": self.engine_version,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
        }


@dataclass
class AIDetectionEngineInput:
    humanized_draft: dict[str, Any]
    requirement_json: dict[str, Any]
    project_id: str | None = None
    thresholds: DetectionThresholds | None = None
    humanizer_paragraph_ids: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "humanized_draft": dict(self.humanized_draft),
            "requirement_json": dict(self.requirement_json),
            "thresholds": (self.thresholds or DetectionThresholds()).to_dict(),
            "humanizer_paragraph_ids": list(self.humanizer_paragraph_ids or []),
        }
