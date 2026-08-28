"""Orchestrate requirements → metrics → validation → scoring → explanation."""

from __future__ import annotations

from typing import Any

from docx import Document

from services.check_explanation import explain_check_results
from services.check_metrics import extract_document_metrics
from services.check_requirements import normalize_requirements
from services.check_scoring import (
    build_action_plan,
    build_not_checked,
    compute_readiness_score,
    score_to_verdict,
    validations_to_categories,
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
    del structure_tree
    structured = normalize_requirements(
        requirements,
        parsed_payload=parsed_requirements,
        doc_type=document_type,
    )
    structured_dict = structured.to_dict()
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
        expected_format=expected_format,
        expected_sections=structured.required_sections or None,
    )
    validations = validate_all_requirements(structured, metrics)
    score_meta = compute_readiness_score(validations)
    score = int(score_meta["score"])
    verdict = score_to_verdict(score)
    categories = validations_to_categories(validations)
    not_checked = build_not_checked(
        structured=structured_dict,
        validations=validations,
        has_docx=doc is not None,
    )
    action_plan = build_action_plan(validations)
    explanation = explain_check_results(
        requirements=requirements,
        validations=validations,
        readiness_score=score,
        metrics=metrics,
        document_type=document_type,
        structured_requirements=structured_dict,
        has_assignment_brief=bool((requirements or "").strip()),
    )
    return {
        "structured_requirements": structured_dict,
        "metrics": metrics,
        "validations": validations,
        "score": score,
        "applicable_weight": score_meta["applicable_weight"],
        "checks_applied": score_meta["checks_applied"],
        "verdict": verdict,
        "categories": categories,
        "not_checked": not_checked,
        "action_plan": action_plan,
        "explanation": explanation,
    }
