"""Blueprint Engine data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SectionCompletionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WordDistributionEntry:
    title: str
    estimated_words: int

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "estimated_words": self.estimated_words}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WordDistributionEntry:
        return cls(
            title=str(data.get("title") or ""),
            estimated_words=int(data.get("estimated_words") or 0),
        )


@dataclass
class BlueprintSection:
    id: str
    title: str
    objective: str
    estimated_words: int
    key_points: list[str] = field(default_factory=list)
    required_arguments: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    required_theories: list[str] = field(default_factory=list)
    transition_from_previous: str = ""
    transition_to_next: str = ""
    citation_target: int = 0
    completion_status: SectionCompletionStatus = SectionCompletionStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "objective": self.objective,
            "estimated_words": self.estimated_words,
            "key_points": list(self.key_points),
            "required_arguments": list(self.required_arguments),
            "required_evidence": list(self.required_evidence),
            "required_theories": list(self.required_theories),
            "transition_from_previous": self.transition_from_previous,
            "transition_to_next": self.transition_to_next,
            "citation_target": self.citation_target,
            "completion_status": self.completion_status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BlueprintSection:
        status_raw = str(data.get("completion_status") or SectionCompletionStatus.PENDING.value)
        try:
            status = SectionCompletionStatus(status_raw)
        except ValueError:
            status = SectionCompletionStatus.PENDING
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            objective=str(data.get("objective") or ""),
            estimated_words=int(data.get("estimated_words") or 0),
            key_points=list(data.get("key_points") or []),
            required_arguments=list(data.get("required_arguments") or []),
            required_evidence=list(data.get("required_evidence") or []),
            required_theories=list(data.get("required_theories") or []),
            transition_from_previous=str(data.get("transition_from_previous") or ""),
            transition_to_next=str(data.get("transition_to_next") or ""),
            citation_target=int(data.get("citation_target") or 0),
            completion_status=status,
        )


@dataclass
class Blueprint:
    """Exact writing blueprint for the Writer Engine — no generated text."""

    id: str
    project_id: str | None
    total_target_words: int
    total_target_sections: int
    writing_order: list[str]
    transition_rules: list[str]
    citation_strategy: str
    academic_tone: str
    critical_analysis_locations: list[str]
    comparison_locations: list[str]
    counterargument_locations: list[str]
    conclusion_goals: list[str]
    sections: list[BlueprintSection]
    word_distribution: list[WordDistributionEntry]
    writing_queue: list[str]
    estimated_completion_time: str
    document_structure: list[str] = field(default_factory=list)
    section_purposes: dict[str, str] = field(default_factory=dict)
    target_word_distribution: list[WordDistributionEntry] = field(default_factory=list)
    argument_flow: list[str] = field(default_factory=list)
    evidence_plan: list[str] = field(default_factory=list)
    citation_plan: list[str] = field(default_factory=list)
    transition_plan: list[str] = field(default_factory=list)
    writing_style: str = ""
    critical_discussion_points: list[str] = field(default_factory=list)
    forbidden_topics: list[str] = field(default_factory=list)
    risk_points: list[str] = field(default_factory=list)
    engine_version: str = "mock-1.0"
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "total_target_words": self.total_target_words,
            "total_target_sections": self.total_target_sections,
            "writing_order": list(self.writing_order),
            "transition_rules": list(self.transition_rules),
            "citation_strategy": self.citation_strategy,
            "academic_tone": self.academic_tone,
            "document_structure": list(self.document_structure),
            "section_purposes": dict(self.section_purposes),
            "target_word_distribution": [entry.to_dict() for entry in self.target_word_distribution],
            "argument_flow": list(self.argument_flow),
            "evidence_plan": list(self.evidence_plan),
            "citation_plan": list(self.citation_plan),
            "transition_plan": list(self.transition_plan),
            "writing_style": self.writing_style,
            "critical_discussion_points": list(self.critical_discussion_points),
            "forbidden_topics": list(self.forbidden_topics),
            "risk_points": list(self.risk_points),
            "critical_analysis_locations": list(self.critical_analysis_locations),
            "comparison_locations": list(self.comparison_locations),
            "counterargument_locations": list(self.counterargument_locations),
            "conclusion_goals": list(self.conclusion_goals),
            "sections": [section.to_dict() for section in self.sections],
            "word_distribution": [entry.to_dict() for entry in self.word_distribution],
            "writing_queue": list(self.writing_queue),
            "estimated_completion_time": self.estimated_completion_time,
            "engine_version": self.engine_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Blueprint:
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
        return cls(
            id=str(data["id"]),
            project_id=data.get("project_id"),
            total_target_words=int(data.get("total_target_words") or 0),
            total_target_sections=int(data.get("total_target_sections") or 0),
            writing_order=list(data.get("writing_order") or []),
            transition_rules=list(data.get("transition_rules") or []),
            citation_strategy=str(data.get("citation_strategy") or ""),
            academic_tone=str(data.get("academic_tone") or ""),
            document_structure=list(data.get("document_structure") or []),
            section_purposes=dict(data.get("section_purposes") or {}),
            target_word_distribution=[
                WordDistributionEntry.from_dict(item)
                for item in (data.get("target_word_distribution") or [])
            ],
            argument_flow=list(data.get("argument_flow") or []),
            evidence_plan=list(data.get("evidence_plan") or []),
            citation_plan=list(data.get("citation_plan") or []),
            transition_plan=list(data.get("transition_plan") or []),
            writing_style=str(data.get("writing_style") or ""),
            critical_discussion_points=list(data.get("critical_discussion_points") or []),
            forbidden_topics=list(data.get("forbidden_topics") or []),
            risk_points=list(data.get("risk_points") or []),
            critical_analysis_locations=list(data.get("critical_analysis_locations") or []),
            comparison_locations=list(data.get("comparison_locations") or []),
            counterargument_locations=list(data.get("counterargument_locations") or []),
            conclusion_goals=list(data.get("conclusion_goals") or []),
            sections=[BlueprintSection.from_dict(item) for item in (data.get("sections") or [])],
            word_distribution=[
                WordDistributionEntry.from_dict(item) for item in (data.get("word_distribution") or [])
            ],
            writing_queue=list(data.get("writing_queue") or []),
            estimated_completion_time=str(data.get("estimated_completion_time") or ""),
            engine_version=str(data.get("engine_version") or "mock-1.0"),
            created_at=created_at,
        )


@dataclass
class BlueprintEngineInput:
    """Only valid inputs for the Blueprint Engine."""

    requirement_json: dict[str, Any]
    research_plan: dict[str, Any]
    project_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "requirement_json": dict(self.requirement_json),
            "research_plan": dict(self.research_plan),
        }
