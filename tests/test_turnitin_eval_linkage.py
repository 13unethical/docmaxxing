"""Unit tests for isolated Turnitin eval linkage (no Chrome / Turnitin / production)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.humanizer_training.turnitin_eval import (
    TurnitinEvalError,
    attach_from_submission_row,
    attach_turnitin_result,
    create_eval_case,
    load_eval_case,
    strip_pii,
    text_sha256,
)


def test_create_eval_case_and_deterministic_hashes(tmp_path: Path):
    original = "Original academic paragraph one."
    humanized = "Humanized academic paragraph one."
    rec = create_eval_case(
        original_text=original,
        humanized_text=humanized,
        root=tmp_path,
    )
    assert rec["eval_id"]
    assert rec["original_text_hash"] == text_sha256(original)
    assert rec["humanized_text_hash"] == text_sha256(humanized)
    assert text_sha256(original) == text_sha256(original)
    assert rec["status"] == "pending_turnitin"
    assert rec["marked_ai_spans"] == []
    assert rec["span_extraction_status"] == "unavailable_with_current_parsers"
    case_path = tmp_path / "cases" / f"{rec['eval_id']}.json"
    assert case_path.is_file()
    loaded = load_eval_case(rec["eval_id"], root=tmp_path)
    assert loaded["original_text"] == original
    assert loaded["humanized_text"] == humanized


def test_attach_report_success(tmp_path: Path):
    rec = create_eval_case(
        original_text="Source text A.",
        humanized_text="Rewritten text A.",
        root=tmp_path,
    )
    report = tmp_path / "fake_ai_report.pdf"
    report.write_bytes(b"%PDF-1.4 fake")
    updated = attach_turnitin_result(
        rec["eval_id"],
        original_text_hash=rec["original_text_hash"],
        humanized_text_hash=rec["humanized_text_hash"],
        turnitin_submission_id="abc123def456",
        ai_score=12.5,
        similarity=3.0,
        report_path=str(report),
        provider="plagdetect",
        root=tmp_path,
    )
    assert updated["status"] == "report_attached"
    assert updated["ai_score"] == 12.5
    assert updated["similarity"] == 3.0
    assert updated["report_path"] == str(report)
    assert updated["ai_report_path"] == str(report)
    assert updated["turnitin_submission_id"] == "abc123def456"
    assert updated["marked_ai_spans"] == []


def test_hash_mismatch_rejected(tmp_path: Path):
    rec = create_eval_case(
        original_text="Source text B.",
        humanized_text="Rewritten text B.",
        root=tmp_path,
    )
    with pytest.raises(TurnitinEvalError, match="hash mismatch"):
        attach_turnitin_result(
            rec["eval_id"],
            original_text_hash=text_sha256("different original"),
            humanized_text_hash=rec["humanized_text_hash"],
            turnitin_submission_id="x",
            ai_score=1.0,
            root=tmp_path,
        )
    # Unchanged case remains pending
    loaded = load_eval_case(rec["eval_id"], root=tmp_path)
    assert loaded["status"] == "pending_turnitin"
    assert loaded.get("ai_score") is None


def test_missing_eval_rejected(tmp_path: Path):
    with pytest.raises(TurnitinEvalError, match="not found"):
        attach_turnitin_result(
            "deadbeefcafebabe",
            original_text_hash="a" * 64,
            humanized_text_hash="b" * 64,
            root=tmp_path,
        )


def test_pii_excluded(tmp_path: Path):
    rec = create_eval_case(
        original_text="Source with enough content.",
        humanized_text="Target with enough content.",
        root=tmp_path,
        metadata={
            "user_id": 42,
            "email": "secret@example.com",
            "note": "ok",
        },
    )
    assert "user_id" not in rec
    assert "email" not in rec.get("metadata", {})
    assert rec["metadata"].get("note") == "ok"
    raw = (tmp_path / "cases" / f"{rec['eval_id']}.json").read_text()
    assert "secret@example.com" not in raw
    assert '"user_id"' not in raw
    cleaned = strip_pii({"user_id": 1, "session_id": "s", "ip": "1.1.1.1", "keep": True})
    assert cleaned == {"keep": True}


def test_attach_from_submission_row_stores_scores_and_paths(tmp_path: Path):
    rec = create_eval_case(
        original_text="Orig C.",
        humanized_text="Hum C.",
        root=tmp_path,
    )
    report = str(tmp_path / "ai.pdf")
    updated = attach_from_submission_row(
        rec["eval_id"],
        original_text_hash=rec["original_text_hash"],
        humanized_text_hash=rec["humanized_text_hash"],
        submission_row={
            "id": "sub123456789",
            "user_id": 99,
            "email": "nope@x.com",
            "ai_score": 40,
            "similarity": 5,
            "ai_highlights": 38,
            "ai_report_path": report,
            "ai_highlights_report_path": report,
            "similarity_report_path": str(tmp_path / "sim.pdf"),
            "status": "completed",
            "external_id": "ext-1",
            "meta_json": json.dumps(
                {
                    "provider": "plagdetect",
                    "ai_score_display": "40%",
                    "user_id": 99,
                }
            ),
        },
        root=tmp_path,
    )
    assert updated["ai_score"] == 40.0
    assert updated["similarity"] == 5.0
    assert updated["ai_highlights"] == 38.0
    assert updated["report_path"] == report
    assert updated["turnitin_submission_id"] == "sub123456789"
    assert updated["provider"] == "plagdetect"
    assert "user_id" not in updated
    assert "email" not in json.dumps(updated)


def test_empty_texts_rejected(tmp_path: Path):
    with pytest.raises(TurnitinEvalError):
        create_eval_case(original_text="  ", humanized_text="ok", root=tmp_path)
    with pytest.raises(TurnitinEvalError):
        create_eval_case(original_text="ok", humanized_text="", root=tmp_path)
