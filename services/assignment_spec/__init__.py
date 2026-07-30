"""AssignmentSpec package — grade-driven generation contract."""

from services.assignment_spec.builder import build_assignment_spec
from services.assignment_spec.grade_gate import (
    MAX_REPAIR_ITERATIONS,
    GradeGateResult,
    apply_repairs,
    run_grade_gate,
)
from services.assignment_spec.models import (
    AssignmentSpec,
    FormatSpec,
    MIN_OVERALL_PREDICTED,
    MIN_RUBRIC_COVERAGE,
    RubricCriterionSpec,
    SectionSpec,
    WORD_TOLERANCE,
)
from services.assignment_spec.rubric_coverage import (
    CriterionCoverage,
    RubricCoverageReport,
    analyze_rubric_coverage,
)
from services.assignment_spec.validate import (
    SpecValidationResult,
    count_body_words,
    count_words,
    needs_expansion,
    render_structured_markdown,
    section_bounds,
    validate_draft_against_spec,
    words_within_tolerance,
)

__all__ = [
    "AssignmentSpec",
    "CriterionCoverage",
    "FormatSpec",
    "GradeGateResult",
    "MAX_REPAIR_ITERATIONS",
    "MIN_OVERALL_PREDICTED",
    "MIN_RUBRIC_COVERAGE",
    "RubricCoverageReport",
    "RubricCriterionSpec",
    "SectionSpec",
    "SpecValidationResult",
    "WORD_TOLERANCE",
    "analyze_rubric_coverage",
    "apply_repairs",
    "build_assignment_spec",
    "count_body_words",
    "count_words",
    "needs_expansion",
    "render_structured_markdown",
    "run_grade_gate",
    "section_bounds",
    "validate_draft_against_spec",
    "words_within_tolerance",
]
