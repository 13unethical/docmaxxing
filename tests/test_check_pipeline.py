"""Tests for validation-based check pipeline and weighted scoring."""

from __future__ import annotations

from services.check_pipeline import run_check_pipeline
from services.check_requirements import normalize_requirements, parse_word_count_spec
from services.check_scoring import compute_readiness_score
from services.check_validator import validate_all_requirements
from services.document_checker import check_document


def test_parse_word_count_range():
    wmin, wmax, conf = parse_word_count_spec("1800-2200 words")
    assert wmin == 1800
    assert wmax == 2200
    assert conf >= 0.9


def test_short_document_gets_low_readiness_score():
    requirements = (
        "Write between 1800 and 2200 words. Use APA 7. "
        "Include 10 peer-reviewed articles. "
        "Required sections: Introduction, Body 1, Body 2, Body 3, Counterargument, Conclusion."
    )
    text = "Hello.\n\nAI is good.\n\nThanks."
    parsed = {
        "word_count": "1800-2200 words",
        "citation_style": "APA",
        "references_required": True,
        "required_sections": [
            "Introduction",
            "Body 1",
            "Body 2",
            "Body 3",
            "Counterargument",
            "Conclusion",
        ],
        "confidence_score": 0.9,
    }
    result = check_document(
        text=text,
        requirements=requirements,
        document_type="essay",
        parsed_requirements=parsed,
    )
    assert result["score"] < 45
    validations = {v["id"]: v for v in result["validations"]}
    assert validations["word_count"]["completion_pct"] < 15
    assert validations["word_count"]["status"] == "FAIL"
    assert validations["references"]["detected"] == "0"
    assert validations["references"]["status"] in ("FAIL", "PARTIAL")


def test_word_count_completion_math():
    req = normalize_requirements(
        "1800-2200 words",
        parsed_payload={"word_count": "1800-2200 words"},
    )
    metrics = {"word_count": 134}
    validations = validate_all_requirements(req, metrics)
    wc = next(v for v in validations if v["id"] == "word_count")
    assert wc["completion_pct"] == 7
    assert round(wc["points_earned"], 1) == 1.9


def test_weighted_score_sums_completion():
    validations = [
        {"weight": 25, "completion": 0.07, "status": "FAIL"},
        {"weight": 20, "completion": 0.0, "status": "FAIL"},
        {"weight": 15, "completion": 0.0, "status": "FAIL"},
        {"weight": 10, "completion": 0.9, "status": "PASS"},
    ]
    score = compute_readiness_score(validations)
    assert score == int(round(25 * 0.07 + 20 * 0 + 15 * 0 + 10 * 0.9))


def test_sections_checklist():
    req = normalize_requirements(
        "Include Introduction and Conclusion",
        parsed_payload={"required_sections": ["Introduction", "Conclusion", "Body 1"]},
    )
    metrics = {
        "detected_sections": [
            {"title": "Introduction", "canonical": "introduction"},
            {"title": "Conclusion", "canonical": "conclusion"},
        ],
        "word_count": 500,
    }
    validations = validate_all_requirements(req, metrics)
    sections = next(v for v in validations if v["id"] == "sections")
    assert sections["detected"] == "2/3"
    assert sections["details"]["missing"] == ["Body 1"]


def test_pipeline_action_plan_orders_by_gain():
    text = "Intro\n\nBody text here with some words.\n\nConclusion"
    requirements = "1800-2200 words. 10 peer reviewed articles. APA."
    pipeline = run_check_pipeline(
        text=text,
        requirements=requirements,
        paragraphs=[p for p in text.split("\n\n") if p.strip()],
        doc=None,
        document_type="essay",
        parsed_requirements={"word_count": "1800-2200 words", "citation_style": "APA"},
    )
    plan = pipeline["action_plan"]
    assert plan
    assert plan[0]["estimated_improvement"] >= (plan[-1]["estimated_improvement"] if len(plan) > 1 else 0)
