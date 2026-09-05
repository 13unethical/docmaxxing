"""Unit tests for Legacy 5.1 teacher eligibility / quarantine rules."""

from __future__ import annotations

from services.humanizer_training.teacher_eligibility import (
    REASON_AMBIGUOUS_METADATA,
    REASON_FAILED_NO_OUTPUT,
    REASON_MOCK_DEFAULT,
    REASON_WRONG_LEVEL,
    REASON_WRONG_MODEL,
    evaluate_teacher_sample,
    primary_quarantine_bucket,
)


def _eligible_doc(**overrides):
    base = {
        "document_id": "doc-ok",
        "source_text": "Source paragraph about markets.",
        "teacher_text": "Rewritten paragraph about markets with hedges.",
        "teacher_provider": "stealthwriter_training",
        "teacher_model": "Legacy 5.1",
        "teacher_level": 8,
        "teacher_meta": {
            "requested_model": "Legacy 5.1",
            "verified_model": "Legacy 5.1",
            "ui_model_label": "Ghost 5.1 Legacy",
            "requested_level": 8,
            "verified_level": 8,
            "selection_verified": True,
            "last_successful_stage": "RESULT_EXTRACTED",
        },
    }
    base.update(overrides)
    return base


def test_eligible_legacy51_level8_document():
    v = evaluate_teacher_sample(_eligible_doc())
    assert v.eligible is True
    assert v.reasons == []
    assert v.ui_model_label == "Ghost 5.1 Legacy"
    assert v.verified_model == "Legacy 5.1"
    assert v.verified_level == 8


def test_mock_provider_quarantined():
    v = evaluate_teacher_sample(
        {
            "source_id": "s1",
            "source_text": "abc",
            "target_text": "def",
            "teacher_provider": "mock_teacher",
            "teacher_version": "mock-v1",
            "teacher_config": {"provider_name": "mock_teacher", "model": "mock-v1", "level": "default"},
        }
    )
    assert v.eligible is False
    assert REASON_MOCK_DEFAULT in v.reasons
    assert primary_quarantine_bucket(v.reasons) == REASON_MOCK_DEFAULT


def test_mock_v1_model_quarantined_even_if_provider_name_looks_real():
    v = evaluate_teacher_sample(
        {
            "source_id": "s2",
            "source_text": "abc",
            "target_text": "def",
            "teacher_provider": "stealthwriter_training",
            "teacher_version": "mock-v1",
            "teacher_config": {
                "provider_name": "stealthwriter_training",
                "model": "mock-v1",
                "level": 8,
            },
        }
    )
    assert v.eligible is False
    assert REASON_MOCK_DEFAULT in v.reasons


def test_missing_selection_telemetry_is_ambiguous():
    v = evaluate_teacher_sample(
        {
            "document_id": "doc-old",
            "source_text": "Source text here.",
            "teacher_text": "Teacher text here.",
            "teacher_provider": "stealthwriter_training",
            "teacher_model": "Legacy 5.1",
            "teacher_level": 8,
            # no teacher_meta
        }
    )
    assert v.eligible is False
    assert REASON_AMBIGUOUS_METADATA in v.reasons
    assert primary_quarantine_bucket(v.reasons) == REASON_AMBIGUOUS_METADATA


def test_short_pair_legacy_claim_without_ui_proof_quarantined():
    v = evaluate_teacher_sample(
        {
            "source_id": "s3",
            "source_text": "Source text here.",
            "target_text": "Teacher text here.",
            "teacher_provider": "stealthwriter_training",
            "teacher_version": "Legacy 5.1",
            "teacher_config": {
                "provider_name": "stealthwriter_training",
                "model": "Legacy 5.1",
                "level": 8,
            },
        }
    )
    assert v.eligible is False
    assert REASON_AMBIGUOUS_METADATA in v.reasons


def test_wrong_ui_model_quarantined():
    doc = _eligible_doc()
    doc["teacher_meta"]["ui_model_label"] = "Ghost 5.2 Mini"
    doc["teacher_meta"]["verified_model"] = "Ghost 5.2 Mini"
    v = evaluate_teacher_sample(doc)
    assert v.eligible is False
    assert REASON_WRONG_MODEL in v.reasons


def test_wrong_level_quarantined():
    doc = _eligible_doc()
    doc["teacher_meta"]["verified_level"] = 5
    v = evaluate_teacher_sample(doc)
    assert v.eligible is False
    assert REASON_WRONG_LEVEL in v.reasons


def test_failed_no_output_quarantined():
    v = evaluate_teacher_sample(
        {
            "document_id": "doc-fail",
            "error_code": "TIMEOUT",
            "provider": "stealthwriter_training",
            "model": "Legacy 5.1",
            "level": 8,
            "selection_verified": False,
            "last_successful_stage": "HUMANIZE_CLICKED",
            "failed_stage": "RESULT_FOUND",
        }
    )
    assert v.eligible is False
    assert REASON_FAILED_NO_OUTPUT in v.reasons
    assert primary_quarantine_bucket(v.reasons) == REASON_FAILED_NO_OUTPUT


def test_identical_output_quarantined():
    text = "Same text on both sides."
    doc = _eligible_doc(source_text=text, teacher_text=text)
    v = evaluate_teacher_sample(doc)
    assert v.eligible is False
    assert "identical_output" in v.reasons


def test_selection_verified_false_quarantined():
    doc = _eligible_doc()
    doc["teacher_meta"]["selection_verified"] = False
    v = evaluate_teacher_sample(doc)
    assert v.eligible is False
    assert "selection_not_verified" in v.reasons
