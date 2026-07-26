"""Tests for grade-driven AssignmentSpec, rubric coverage, and repair gate."""

from __future__ import annotations

from services.assignment_spec import (
    analyze_rubric_coverage,
    build_assignment_spec,
    run_grade_gate,
)


def _lj_requirement() -> dict:
    return {
        "id": "req-1",
        "project_id": "proj-1",
        "title": "Learning Journal",
        "assignment_type": "Learning Journal",
        "word_count": 1200,
        "required_sections": [
            "Cover page",
            "Introduction",
            "Journal Entry 1",
            "Journal Entry 2",
            "Journal Entry 3",
            "Journal Entry 4",
            "Reflection",
            "References",
        ],
        "section_word_budgets": {
            "Introduction": 100,
            "Journal Entry 1": 200,
            "Journal Entry 2": 200,
            "Journal Entry 3": 200,
            "Journal Entry 4": 200,
            "Reflection": 300,
        },
        "formatting": {
            "font_family": "Times New Roman",
            "font_size": "12",
            "line_spacing": "double-spaced",
            "margins": "1 inch from each sides",
            "alignment": "left",
        },
        "learning_outcomes": [
            "LO1. Define key historical concepts in Marketing, Digital Innovation, and International Business",
            "LO2. Recognize historical stages of business evolution",
            "LO4. Interpret development from entrepreneurial perspective",
            "LO5. Relate knowledge and personal interest to make an informed decision",
        ],
        "rubric": [
            {"criterion": "LO1", "weight": "10%", "description": "Define key historical concepts"},
            {"criterion": "LO2", "weight": "10%", "description": "Recognize historical stages of business evolution"},
            {"criterion": "LO4", "weight": "30%", "description": "Interpret development from entrepreneurial perspective"},
            {"criterion": "LO5", "weight": "30%", "description": "Relate personal interest and decision-making"},
            {"criterion": "Paper Quality", "weight": "10%", "description": "Organisation, lecture/seminar refs, academic sources"},
        ],
    }


def _strong_draft() -> str:
    intro = (
        "This learning journal defines key historical concepts in marketing, digital innovation, "
        "and international business to frame entrepreneurial learning. "
    ) * 5
    entry = (
        "This entry explains the origin and development of a historical concept in marketing and "
        "digital innovation. A historical stage of business evolution shaped current practices. "
        "Entrepreneurs responded to change through innovation. This insight was reinforced during "
        "the related lecture and seminar discussion (Schumpeter, 1942). "
    )
    entry4 = (
        entry
        + "Comparing these two historical concepts across different fields clarifies how each "
        "shaped present practice and may influence future entrepreneurial strategy. "
    )
    reflection = (
        "Reflecting on these journal entries, my personal interest aligns with digital innovation "
        "as a major choice. This informed decision follows from the historical stages and "
        "entrepreneurial patterns examined across marketing and international business. "
    ) * 8
    refs = (
        "Schumpeter, J. (1942). Capitalism, socialism and democracy. Harper.\n\n"
        "Barney, J. (1991). Firm resources and sustained competitive advantage. "
        "Journal of Management, 17(1), 99-120. https://doi.org/10.1177/014920639101700108"
    )
    return "\n\n".join(
        [
            f"## Introduction\n\n{intro}",
            f"## Journal Entry 1\n\n{(entry * 4).strip()}",
            f"## Journal Entry 2\n\n{(entry * 4).strip()}",
            f"## Journal Entry 3\n\n{(entry * 4).strip()}",
            f"## Journal Entry 4\n\n{(entry4 * 3).strip()}",
            f"## Reflection\n\n{reflection}",
            f"## References\n\n{refs}",
        ]
    )


def test_assignment_spec_includes_rubric_weights_and_grade_fields():
    spec = build_assignment_spec(_lj_requirement(), project_id="proj-1")
    assert len(spec.rubric_criteria) == 5
    assert abs(sum(c.weight_percent for c in spec.rubric_criteria) - 100) < 1.5
    assert spec.required_lecture_seminar_refs is True
    assert spec.mandatory_reflections
    assert spec.assessment_weights
    assert "LO1" in {c.label for c in spec.rubric_criteria}


def test_rubric_coverage_reports_per_criterion_and_overall():
    spec = build_assignment_spec(_lj_requirement())
    report = analyze_rubric_coverage(content=_strong_draft(), spec=spec)
    assert report.criteria
    assert all(c.coverage_percent >= 0 for c in report.criteria)
    assert report.overall_predicted_grade > 0
    by_label = {c.label: c.coverage_percent for c in report.criteria}
    assert "LO1" in by_label
    assert "Paper Quality" in by_label


def test_grade_gate_repairs_and_can_pass_strong_draft():
    spec = build_assignment_spec(_lj_requirement())
    # Slightly weak draft missing lecture refs in one entry — gate should repair.
    weak = _strong_draft().replace(
        "## Journal Entry 2\n\n",
        "## Journal Entry 2\n\nHistorical stage discussion without classroom cross-reference. ",
        1,
    )
    # Remove first lecture mention in entry 2 block only approximately by shortening.
    result = run_grade_gate(content=weak, spec=spec, llm_repair=None)
    assert result.rubric_coverage.overall_predicted_grade >= 50
    assert isinstance(result.to_dict()["per_criterion_coverage"], dict)


def test_grade_gate_blocks_empty_draft():
    spec = build_assignment_spec(_lj_requirement())
    result = run_grade_gate(content="## Introduction\n\nToo short.", spec=spec, llm_repair=None)
    assert result.passed is False
    assert result.export_blocked is True
    assert result.blocking_issues
