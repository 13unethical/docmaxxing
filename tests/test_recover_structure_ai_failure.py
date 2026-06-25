"""Tests for explicit AI failure handling in recover_structure."""

from __future__ import annotations

from unittest.mock import patch

from services.document_structure_engine import recover_structure


@patch("services.document_structure_engine.gemini_enabled", return_value=True)
@patch("services.ai_structure_recovery.recover_structure_with_ai")
def test_gemini_failure_returns_ai_failed_not_reconstructed(mock_ai, _mock_enabled):
    mock_ai.return_value = {
        "ai_failure": True,
        "failure_reason": "unavailable",
        "error": "AI structure recovery failed: unavailable",
        "recovery_mode": "ai_failed",
        "gemini_diagnostics": {"api_call_success": False, "failure_reason": "unavailable"},
    }

    result = recover_structure(
        paragraphs=["Journal Entry 1: Topic", "Body text here."],
        document_type="learning_journal",
    )

    assert result.get("recovery_mode") == "ai_failed"
    assert result.get("ai_failure") is True
    assert result.get("failure_reason") == "unavailable"
    assert "error" in result
    assert result.get("ai_powered") is False


@patch("services.document_structure_engine.gemini_enabled", return_value=False)
def test_heuristic_fallback_when_gemini_disabled(_mock_enabled):
    result = recover_structure(
        paragraphs=["Journal Entry 1: Topic", "Body text here."],
        document_type="learning_journal",
    )

    assert result.get("recovery_mode") == "reconstructed"
    assert result.get("ai_powered") is False
    assert not result.get("ai_failure")
