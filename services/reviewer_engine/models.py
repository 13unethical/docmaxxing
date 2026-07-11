"""Academic Reviewer data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class IssueSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ReviewIssue:
    issue_id: str
    category: str
    severity: IssueSeverity
    section: str
    description: str
    suggested_fix: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "category": self.category,
            "severity": self.severity.value,
            "section": self.section,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewIssue:
        try:
            severity = IssueSeverity(str(data.get("severity") or IssueSeverity.MEDIUM.value))
        except ValueError:
            severity = IssueSeverity.MEDIUM
        return cls(
            issue_id=str(data.get("issue_id") or ""),
            category=str(data.get("category") or ""),
            severity=severity,
            section=str(data.get("section") or ""),
            description=str(data.get("description") or ""),
            suggested_fix=str(data.get("suggested_fix") or ""),
        )


@dataclass
class ChecklistItem:
    id: str
    label: str
    passed: bool
    score: int
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "passed": self.passed,
            "score": self.score,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChecklistItem:
        return cls(
            id=str(data.get("id") or ""),
            label=str(data.get("label") or ""),
            passed=bool(data.get("passed")),
            score=int(data.get("score") or 0),
            notes=str(data.get("notes") or ""),
        )


@dataclass
class QualityScores:
    structure: int
    research: int
    critical_thinking: int
    evidence: int
    formatting: int
    language: int
    academic_tone: int
    overall: int

    def to_dict(self) -> dict[str, int]:
        return {
            "structure": self.structure,
            "research": self.research,
            "critical_thinking": self.critical_thinking,
            "evidence": self.evidence,
            "formatting": self.formatting,
            "language": self.language,
            "academic_tone": self.academic_tone,
            "overall": self.overall,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QualityScores:
        return cls(
            structure=int(data.get("structure") or 0),
            research=int(data.get("research") or 0),
            critical_thinking=int(data.get("critical_thinking") or 0),
            evidence=int(data.get("evidence") or 0),
            formatting=int(data.get("formatting") or 0),
            language=int(data.get("language") or 0),
            academic_tone=int(data.get("academic_tone") or 0),
            overall=int(data.get("overall") or 0),
        )


@dataclass
class ReviewReport:
    id: str
    project_id: str | None
    overall_score: int
    passed: bool
    requirement_checklist: list[ChecklistItem]
    rubric_checklist: list[ChecklistItem]
    issues: list[ReviewIssue]
    recommendations: list[str]
    quality_scores: QualityScores
    engine_version: str = "mock-1.0"
    reviewed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "overall_score": self.overall_score,
            "passed": self.passed,
            "requirement_checklist": [item.to_dict() for item in self.requirement_checklist],
            "rubric_checklist": [item.to_dict() for item in self.rubric_checklist],
            "issues": [issue.to_dict() for issue in self.issues],
            "recommendations": list(self.recommendations),
            "quality_scores": self.quality_scores.to_dict(),
            "engine_version": self.engine_version,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewReport:
        reviewed_at = None
        if data.get("reviewed_at"):
            reviewed_at = datetime.fromisoformat(str(data["reviewed_at"]).replace("Z", "+00:00"))
        return cls(
            id=str(data["id"]),
            project_id=data.get("project_id"),
            overall_score=int(data.get("overall_score") or 0),
            passed=bool(data.get("passed")),
            requirement_checklist=[
                ChecklistItem.from_dict(item) for item in (data.get("requirement_checklist") or [])
            ],
            rubric_checklist=[ChecklistItem.from_dict(item) for item in (data.get("rubric_checklist") or [])],
            issues=[ReviewIssue.from_dict(item) for item in (data.get("issues") or [])],
            recommendations=list(data.get("recommendations") or []),
            quality_scores=QualityScores.from_dict(data.get("quality_scores") or {}),
            engine_version=str(data.get("engine_version") or "mock-1.0"),
            reviewed_at=reviewed_at,
        )


@dataclass
class ReviewEngineInput:
    requirement_json: dict[str, Any]
    research_plan: dict[str, Any]
    blueprint: dict[str, Any]
    draft: dict[str, Any]
    project_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "requirement_json": dict(self.requirement_json),
            "research_plan": dict(self.research_plan),
            "blueprint": dict(self.blueprint),
            "draft": dict(self.draft),
        }
