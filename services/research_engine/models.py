"""Research Engine data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ParsedDocument:
    """Parsed text from an uploaded project file — never raw binary."""

    id: str
    file_id: str
    file_type: str
    filename: str
    text: str
    word_count: int = 0
    parsed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_id": self.file_id,
            "file_type": self.file_type,
            "filename": self.filename,
            "text": self.text,
            "word_count": self.word_count,
            "parsed_at": self.parsed_at.isoformat() if self.parsed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParsedDocument:
        parsed_at = None
        if data.get("parsed_at"):
            parsed_at = datetime.fromisoformat(str(data["parsed_at"]).replace("Z", "+00:00"))
        text = str(data.get("text") or "")
        return cls(
            id=str(data["id"]),
            file_id=str(data.get("file_id") or data["id"]),
            file_type=str(data.get("file_type") or "additional_file"),
            filename=str(data.get("filename") or "document"),
            text=text,
            word_count=int(data.get("word_count") or len(text.split())),
            parsed_at=parsed_at,
        )


@dataclass
class ResearchSection:
    title: str
    description: str
    purpose: str
    estimated_words: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "purpose": self.purpose,
            "estimated_words": self.estimated_words,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchSection:
        return cls(
            title=str(data.get("title") or ""),
            description=str(data.get("description") or ""),
            purpose=str(data.get("purpose") or ""),
            estimated_words=int(data.get("estimated_words") or 0),
        )


@dataclass
class ResearchPlan:
    """Blueprint for the Writer Engine — no generated assignment text."""

    id: str
    project_id: str | None
    assignment_topic: str
    writing_objective: str
    main_research_question: str
    research_question: str = ""
    key_arguments: list[str] = field(default_factory=list)
    counter_arguments: list[str] = field(default_factory=list)
    academic_theories: list[str] = field(default_factory=list)
    important_keywords: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    recommended_journals: list[str] = field(default_factory=list)
    recommended_statistics: list[str] = field(default_factory=list)
    suggested_sections: list[str] = field(default_factory=list)
    terminology: list[str] = field(default_factory=list)
    writing_risks: list[str] = field(default_factory=list)
    research_depth: str = ""
    secondary_questions: list[str] = field(default_factory=list)
    target_audience: str = ""
    writing_tone: str = ""
    recommended_structure: str = ""
    section_list: list[ResearchSection] = field(default_factory=list)
    required_theories: list[str] = field(default_factory=list)
    required_concepts: list[str] = field(default_factory=list)
    required_case_studies: list[str] = field(default_factory=list)
    required_arguments: list[str] = field(default_factory=list)
    possible_counterarguments: list[str] = field(default_factory=list)
    suggested_evidence: list[str] = field(default_factory=list)
    estimated_academic_sources: int = 0
    recommended_source_types: list[str] = field(default_factory=list)
    potential_risks: list[str] = field(default_factory=list)
    notes_for_writer: list[str] = field(default_factory=list)
    estimated_difficulty: str = ""
    estimated_completion_time: str = ""
    engine_version: str = "mock-1.0"
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "assignment_topic": self.assignment_topic,
            "writing_objective": self.writing_objective,
            "main_research_question": self.main_research_question,
            "research_question": self.research_question or self.main_research_question,
            "key_arguments": list(self.key_arguments),
            "counter_arguments": list(self.counter_arguments),
            "academic_theories": list(self.academic_theories),
            "important_keywords": list(self.important_keywords),
            "search_queries": list(self.search_queries),
            "recommended_journals": list(self.recommended_journals),
            "recommended_statistics": list(self.recommended_statistics),
            "suggested_sections": list(self.suggested_sections),
            "terminology": list(self.terminology),
            "writing_risks": list(self.writing_risks),
            "research_depth": self.research_depth,
            "secondary_questions": list(self.secondary_questions),
            "target_audience": self.target_audience,
            "writing_tone": self.writing_tone,
            "recommended_structure": self.recommended_structure,
            "section_list": [section.to_dict() for section in self.section_list],
            "required_theories": list(self.required_theories),
            "required_concepts": list(self.required_concepts),
            "required_case_studies": list(self.required_case_studies),
            "required_arguments": list(self.required_arguments),
            "possible_counterarguments": list(self.possible_counterarguments),
            "suggested_evidence": list(self.suggested_evidence),
            "estimated_academic_sources": self.estimated_academic_sources,
            "recommended_source_types": list(self.recommended_source_types),
            "potential_risks": list(self.potential_risks),
            "notes_for_writer": list(self.notes_for_writer),
            "estimated_difficulty": self.estimated_difficulty,
            "estimated_completion_time": self.estimated_completion_time,
            "engine_version": self.engine_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchPlan:
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
        return cls(
            id=str(data["id"]),
            project_id=data.get("project_id"),
            assignment_topic=str(data.get("assignment_topic") or ""),
            writing_objective=str(data.get("writing_objective") or ""),
            main_research_question=str(data.get("main_research_question") or ""),
            research_question=str(data.get("research_question") or data.get("main_research_question") or ""),
            key_arguments=list(data.get("key_arguments") or []),
            counter_arguments=list(data.get("counter_arguments") or []),
            academic_theories=list(data.get("academic_theories") or []),
            important_keywords=list(data.get("important_keywords") or []),
            search_queries=list(data.get("search_queries") or []),
            recommended_journals=list(data.get("recommended_journals") or []),
            recommended_statistics=list(data.get("recommended_statistics") or []),
            suggested_sections=list(data.get("suggested_sections") or []),
            terminology=list(data.get("terminology") or []),
            writing_risks=list(data.get("writing_risks") or []),
            research_depth=str(data.get("research_depth") or ""),
            secondary_questions=list(data.get("secondary_questions") or []),
            target_audience=str(data.get("target_audience") or ""),
            writing_tone=str(data.get("writing_tone") or ""),
            recommended_structure=str(data.get("recommended_structure") or ""),
            section_list=[ResearchSection.from_dict(item) for item in (data.get("section_list") or [])],
            required_theories=list(data.get("required_theories") or []),
            required_concepts=list(data.get("required_concepts") or []),
            required_case_studies=list(data.get("required_case_studies") or []),
            required_arguments=list(data.get("required_arguments") or []),
            possible_counterarguments=list(data.get("possible_counterarguments") or []),
            suggested_evidence=list(data.get("suggested_evidence") or []),
            estimated_academic_sources=int(data.get("estimated_academic_sources") or 0),
            recommended_source_types=list(data.get("recommended_source_types") or []),
            potential_risks=list(data.get("potential_risks") or []),
            notes_for_writer=list(data.get("notes_for_writer") or []),
            estimated_difficulty=str(data.get("estimated_difficulty") or ""),
            estimated_completion_time=str(data.get("estimated_completion_time") or ""),
            engine_version=str(data.get("engine_version") or "mock-1.0"),
            created_at=created_at,
        )


@dataclass
class ResearchEngineInput:
    """Only valid inputs for the Research Engine."""

    requirement_json: dict[str, Any]
    parsed_documents: list[ParsedDocument]
    project_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "requirement_json": dict(self.requirement_json),
            "parsed_documents": [doc.to_dict() for doc in self.parsed_documents],
        }
