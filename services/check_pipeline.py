"""Orchestrate requirements → metrics → validation → scoring → explanation."""

from __future__ import annotations

from typing import Any

from docx import Document

from services.check_explanation import explain_check_results
from services.check_metrics import extract_document_metrics
from services.check_requirements import StructuredRequirements, normalize_requirements
from services.check_scoring import (
    build_action_plan,
    build_priorities,
    compute_readiness_score,
    score_to_verdict,
    validations_to_categories,
    validations_to_issues,
)
from services.check_validator import validate_all_requirements


def run_check_pipeline(
    *,
    text: str,
    requirements: str,
    paragraphs: list[str],
    doc: Document | None,
    document_type: str,
    structure_tree: list[dict[str, Any]] | None = None,
    parsed_requirements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full validation-based check; returns score, validations, action plan, explanation."""
    structured = normalize_requirements(
        requirements,
        parsed_payload=parsed_requirements,
        doc_type=document_type,
    )
    expected_format = {
        "font_family": structured.font_family,
        "font_size": structured.font_size,
        "line_spacing": structured.line_spacing,
        "alignment": structured.alignment,
        "require_page_numbers": structured.page_numbers_required is True,
        "expect_references_section": structured.references_required is not False,
    }
    metrics = extract_document_metrics(
        text=text,
        paragraphs=paragraphs,
        doc=doc,
        structure_tree=structure_tree,
        expected_format=expected_format,
    )
    validations = validate_all_requirements(structured, metrics)
    score = compute_readiness_score(validations)
    verdict = score_to_verdict(score)
    categories = validations_to_categories(validations)
    priorities = build_priorities(validations)
    action_plan = build_action_plan(validations)
    issues = validations_to_issues(validations)
    explanation = explain_check_results(
        requirements=requirements,
        validations=validations,
        readiness_score=score,
        metrics=metrics,
        document_type=document_type,
    )
    return {
        "structured_requirements": structured.to_dict(),
        "metrics": metrics,
        "validations": validations,
        "score": score,
        "verdict": verdict,
        "categories": categories,
        "priorities": priorities,
        "action_plan": action_plan,
        "issues": issues,
        "explanation": explanation,
    }
