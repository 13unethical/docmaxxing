"""AssignmentSpec — unified grade-driven generation contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


WORD_TOLERANCE = 0.10  # ±10%
MIN_RUBRIC_COVERAGE = 85.0  # minimum per-criterion coverage before export
MIN_OVERALL_PREDICTED = 70.0  # minimum weighted predicted grade


@dataclass
class FormatSpec:
    font_family: str = "Times New Roman"
    font_size_pt: int = 12
    line_spacing: float = 2.0
    alignment: str = "left"  # left | justify
    margins_inches: float = 1.0
    first_line_indent: bool = False
    heading_size_pt: int = 14
    references_on_new_page: bool = True
    cover_page_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "font_family": self.font_family,
            "font_size_pt": self.font_size_pt,
            "line_spacing": self.line_spacing,
            "alignment": self.alignment,
            "margins_inches": self.margins_inches,
            "first_line_indent": self.first_line_indent,
            "heading_size_pt": self.heading_size_pt,
            "references_on_new_page": self.references_on_new_page,
            "cover_page_required": self.cover_page_required,
            "font_size": self.font_size_pt,
            "margins": f"{self.margins_inches} inch",
            "margin_preset": _margin_preset(self.margins_inches),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FormatSpec:
        data = data or {}
        return cls(
            font_family=str(data.get("font_family") or "Times New Roman"),
            font_size_pt=int(data.get("font_size_pt") or data.get("font_size") or 12),
            line_spacing=float(data.get("line_spacing") or 2.0),
            alignment=str(data.get("alignment") or "left").lower(),
            margins_inches=float(data.get("margins_inches") or 1.0),
            first_line_indent=bool(data.get("first_line_indent", False)),
            heading_size_pt=int(data.get("heading_size_pt") or 14),
            references_on_new_page=bool(data.get("references_on_new_page", True)),
            cover_page_required=bool(data.get("cover_page_required", False)),
        )


@dataclass
class SectionSpec:
    id: str
    title: str
    target_words: int = 0
    writable: bool = True
    mandatory: bool = True
    order: int = 0
    notes: str = ""
    linked_criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "target_words": self.target_words,
            "writable": self.writable,
            "mandatory": self.mandatory,
            "order": self.order,
            "notes": self.notes,
            "linked_criteria": list(self.linked_criteria),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SectionSpec:
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            target_words=int(data.get("target_words") or 0),
            writable=bool(data.get("writable", True)),
            mandatory=bool(data.get("mandatory", True)),
            order=int(data.get("order") or 0),
            notes=str(data.get("notes") or ""),
            linked_criteria=[str(x) for x in (data.get("linked_criteria") or []) if str(x).strip()],
        )


@dataclass
class RubricCriterionSpec:
    """One graded criterion from the uploaded rubric."""

    id: str
    label: str
    weight_percent: float
    description: str = ""
    top_band_guidance: str = ""
    signals: list[str] = field(default_factory=list)
    linked_learning_outcomes: list[str] = field(default_factory=list)
    linked_sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "weight_percent": self.weight_percent,
            "weight": f"{self.weight_percent:g}%",
            "criterion": self.label,
            "description": self.description,
            "top_band_guidance": self.top_band_guidance,
            "signals": list(self.signals),
            "linked_learning_outcomes": list(self.linked_learning_outcomes),
            "linked_sections": list(self.linked_sections),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RubricCriterionSpec:
        weight = _parse_weight(data.get("weight_percent", data.get("weight")))
        label = str(data.get("label") or data.get("criterion") or data.get("id") or "Criterion")
        cid = str(data.get("id") or _slug(label))
        return cls(
            id=cid,
            label=label,
            weight_percent=weight,
            description=str(data.get("description") or ""),
            top_band_guidance=str(data.get("top_band_guidance") or ""),
            signals=[str(x) for x in (data.get("signals") or []) if str(x).strip()],
            linked_learning_outcomes=[
                str(x) for x in (data.get("linked_learning_outcomes") or []) if str(x).strip()
            ],
            linked_sections=[str(x) for x in (data.get("linked_sections") or []) if str(x).strip()],
        )


@dataclass
class AssignmentSpec:
    """Canonical grade-driven contract. Every pipeline stage must consume this."""

    project_id: str
    title: str
    assignment_type: str
    total_word_target: int
    word_tolerance: float = WORD_TOLERANCE
    citation_style: str | None = None
    sections: list[SectionSpec] = field(default_factory=list)
    formatting: FormatSpec = field(default_factory=FormatSpec)
    learning_outcomes: list[str] = field(default_factory=list)
    rubric_criteria: list[RubricCriterionSpec] = field(default_factory=list)
    # Legacy alias list kept for older consumers.
    rubric: list[dict[str, Any]] = field(default_factory=list)
    minimum_sources: int | None = None
    mandatory_content_rules: list[str] = field(default_factory=list)
    required_lecture_seminar_refs: bool = False
    required_evidence: list[str] = field(default_factory=list)
    citation_requirements: list[str] = field(default_factory=list)
    mandatory_comparisons: list[str] = field(default_factory=list)
    mandatory_reflections: list[str] = field(default_factory=list)
    forbidden_content: list[str] = field(default_factory=list)
    min_rubric_coverage: float = MIN_RUBRIC_COVERAGE
    min_overall_predicted_grade: float = MIN_OVERALL_PREDICTED
    source_requirement_id: str | None = None

    @property
    def required_section_titles(self) -> list[str]:
        return [s.title for s in self.sections if s.mandatory]

    @property
    def writable_sections(self) -> list[SectionSpec]:
        return [s for s in self.sections if s.writable and s.target_words > 0]

    @property
    def section_word_targets(self) -> dict[str, int]:
        return {s.title: s.target_words for s in self.sections if s.target_words > 0}

    @property
    def assessment_weights(self) -> dict[str, float]:
        return {c.id: c.weight_percent for c in self.rubric_criteria}

    @property
    def min_total_words(self) -> int:
        return max(1, int(round(self.total_word_target * (1.0 - self.word_tolerance))))

    @property
    def max_total_words(self) -> int:
        return max(self.min_total_words, int(round(self.total_word_target * (1.0 + self.word_tolerance))))

    def section_by_title(self, title: str) -> SectionSpec | None:
        key = (title or "").strip().lower()
        for section in self.sections:
            if section.title.strip().lower() == key:
                return section
        return None

    def to_dict(self) -> dict[str, Any]:
        criteria = [c.to_dict() for c in self.rubric_criteria]
        return {
            "project_id": self.project_id,
            "title": self.title,
            "assignment_type": self.assignment_type,
            "total_word_target": self.total_word_target,
            "word_tolerance": self.word_tolerance,
            "citation_style": self.citation_style,
            "sections": [s.to_dict() for s in self.sections],
            "required_sections": self.required_section_titles,
            "section_word_targets": self.section_word_targets,
            "formatting": self.formatting.to_dict(),
            "learning_outcomes": list(self.learning_outcomes),
            "rubric_criteria": criteria,
            "rubric": criteria or list(self.rubric),
            "assessment_weights": self.assessment_weights,
            "minimum_sources": self.minimum_sources,
            "mandatory_content_rules": list(self.mandatory_content_rules),
            "required_lecture_seminar_refs": self.required_lecture_seminar_refs,
            "required_evidence": list(self.required_evidence),
            "citation_requirements": list(self.citation_requirements),
            "mandatory_comparisons": list(self.mandatory_comparisons),
            "mandatory_reflections": list(self.mandatory_reflections),
            "forbidden_content": list(self.forbidden_content),
            "min_rubric_coverage": self.min_rubric_coverage,
            "min_overall_predicted_grade": self.min_overall_predicted_grade,
            "source_requirement_id": self.source_requirement_id,
            "min_total_words": self.min_total_words,
            "max_total_words": self.max_total_words,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssignmentSpec:
        raw_criteria = data.get("rubric_criteria") or data.get("rubric") or []
        criteria = [RubricCriterionSpec.from_dict(c) for c in raw_criteria if isinstance(c, dict)]
        return cls(
            project_id=str(data.get("project_id") or ""),
            title=str(data.get("title") or "Assignment"),
            assignment_type=str(data.get("assignment_type") or "Assignment"),
            total_word_target=int(data.get("total_word_target") or data.get("word_count") or 0),
            word_tolerance=float(data.get("word_tolerance") or WORD_TOLERANCE),
            citation_style=data.get("citation_style"),
            sections=[SectionSpec.from_dict(s) for s in (data.get("sections") or [])],
            formatting=FormatSpec.from_dict(data.get("formatting")),
            learning_outcomes=list(data.get("learning_outcomes") or []),
            rubric_criteria=criteria,
            rubric=[c.to_dict() for c in criteria],
            minimum_sources=data.get("minimum_sources"),
            mandatory_content_rules=list(data.get("mandatory_content_rules") or []),
            required_lecture_seminar_refs=bool(data.get("required_lecture_seminar_refs", False)),
            required_evidence=list(data.get("required_evidence") or []),
            citation_requirements=list(data.get("citation_requirements") or []),
            mandatory_comparisons=list(data.get("mandatory_comparisons") or []),
            mandatory_reflections=list(data.get("mandatory_reflections") or []),
            forbidden_content=list(data.get("forbidden_content") or []),
            min_rubric_coverage=float(data.get("min_rubric_coverage") or MIN_RUBRIC_COVERAGE),
            min_overall_predicted_grade=float(
                data.get("min_overall_predicted_grade") or MIN_OVERALL_PREDICTED
            ),
            source_requirement_id=data.get("source_requirement_id"),
        )


def _margin_preset(inches: float) -> str:
    if inches <= 0.6:
        return "narrow"
    if inches >= 1.4:
        return "wide"
    return "normal"


def _slug(title: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "criterion"


def _parse_weight(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    import re

    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else 0.0
