"""Tests for multi-phase AI structure recovery orchestration."""

from __future__ import annotations

from unittest.mock import patch

from services.ai_structure_recovery import (
    MULTI_PHASE_CHAR_THRESHOLD,
    _merge_hierarchy_sections,
    _recover_multiphase,
    recover_structure_with_ai,
)


def _ok_diag(phase: str) -> dict:
    return {
        "phase": phase,
        "api_call_success": True,
        "enabled": True,
        "model": "gemini-2.5-flash",
        "models_attempted": ["gemini-2.5-flash"],
        "fallback_activated": False,
        "retry_count": 0,
        "latency_ms": 1,
        "request_chars": 10,
        "token_usage_estimate": 5,
    }


def _classify_ok(*_args, **_kwargs):
    return {"document_type": "learning_journal", "document_type_confidence": 0.9}, _ok_diag("classify")


def _headings_ok(*_args, **_kwargs):
    return [], [_ok_diag("headings")]


def _hierarchy_from(mapping: dict[int, list[dict]]):
    def _side(_paragraphs, *, start, end, document_type, candidates):
        return {"sections": mapping.get(start, [])}, _ok_diag(f"hierarchy_{start}_{end}")

    return _side


def test_merge_hierarchy_sections_concatenates_batches():
    groups = [
        [{"title": "Intro", "heading_text": "Introduction", "paragraph_indices": [1, 2], "confidence": 0.8}],
        [{"title": "Body", "heading_text": "Journal Entry 1", "paragraph_indices": [3], "confidence": 0.9}],
    ]
    merged = _merge_hierarchy_sections(groups)
    assert len(merged) == 2
    assert merged[0]["paragraph_indices"] == [1, 2]


@patch("services.ai_structure_recovery.gemini_enabled", return_value=True)
@patch("services.ai_structure_recovery._recover_multiphase")
def test_large_document_uses_multiphase(mock_multiphase, _mock_enabled):
    long_paragraphs = ["x" * (MULTI_PHASE_CHAR_THRESHOLD + 100)] * 2
    mock_multiphase.return_value = {
        "recovery_mode": "ai_reconstructed",
        "ai_powered": True,
        "gemini_diagnostics": {"strategy": "multi_phase", "api_call_success": True},
    }

    result = recover_structure_with_ai(paragraphs=long_paragraphs, document_type="essay")

    mock_multiphase.assert_called_once()
    assert result["recovery_mode"] == "ai_reconstructed"


@patch("services.ai_structure_recovery.gemini_enabled", return_value=True)
@patch("services.ai_structure_recovery._recover_monolithic")
def test_small_document_uses_monolithic(mock_monolithic, _mock_enabled):
    mock_monolithic.return_value = {
        "recovery_mode": "ai_reconstructed",
        "ai_powered": True,
        "gemini_diagnostics": {"strategy": "monolithic", "api_call_success": True},
    }

    result = recover_structure_with_ai(paragraphs=["Short title", "Short body."], document_type="essay")

    mock_monolithic.assert_called_once()
    assert result["recovery_mode"] == "ai_reconstructed"


@patch("services.ai_structure_recovery.gemini_enabled", return_value=True)
@patch("services.ai_structure_recovery._recover_monolithic")
def test_ai_failure_returns_explicit_payload(mock_monolithic, _mock_enabled):
    mock_monolithic.return_value = {
        "ai_failure": True,
        "failure_reason": "unavailable",
        "error": "AI structure recovery failed: unavailable",
        "recovery_mode": "ai_failed",
        "gemini_diagnostics": {
            "failure_reason": "unavailable",
            "http_status": 503,
            "api_call_success": False,
        },
    }

    result = recover_structure_with_ai(paragraphs=["A", "B"], document_type="essay")

    assert result["ai_failure"] is True
    assert result["failure_reason"] == "unavailable"


@patch("services.ai_structure_recovery._classify_document", side_effect=_classify_ok)
@patch("services.ai_structure_recovery._identify_heading_candidates", side_effect=_headings_ok)
@patch("services.ai_structure_recovery._recover_hierarchy_batch")
def test_empty_chunk_returns_ai_failed(mock_hier, _headings, _classify):
    paragraphs = [f"P{i}" for i in range(1, 8)]  # 7 paragraphs -> batches (1,4),(5,7)
    mock_hier.side_effect = _hierarchy_from(
        {
            1: [
                {"title": "Intro", "heading_text": "Introduction", "paragraph_indices": [1, 2, 3, 4], "confidence": 0.9},
            ],
            5: [],
        }
    )

    result = _recover_multiphase(paragraphs, "learning_journal")

    assert result["ai_failure"] is True
    assert result["failure_reason"] == "incomplete_chunk"
    assert result["recovery_mode"] == "ai_failed"
    diag = result["gemini_diagnostics"]
    assert diag["coverage_ok"] is False
    assert diag["chunk_section_counts"]
    # empty chunk 2 is retried exactly once (initial + 1 retry) on top of chunk 1.
    assert mock_hier.call_count == 3


@patch("services.ai_structure_recovery._classify_document", side_effect=_classify_ok)
@patch("services.ai_structure_recovery._identify_heading_candidates", side_effect=_headings_ok)
@patch("services.ai_structure_recovery._recover_hierarchy_batch")
def test_missing_coverage_returns_ai_failed(mock_hier, _headings, _classify):
    paragraphs = [f"P{i}" for i in range(1, 7)]  # 6 paragraphs -> batches (1,4),(5,6)
    mock_hier.side_effect = _hierarchy_from(
        {
            # chunk passes (has an in-range section) but paragraph 4 is left unowned
            1: [{"title": "Intro", "heading_text": "Introduction", "paragraph_indices": [1, 2, 3], "confidence": 0.9}],
            5: [{"title": "Body", "heading_text": "Body", "paragraph_indices": [5, 6], "confidence": 0.9}],
        }
    )

    result = _recover_multiphase(paragraphs, "essay")

    assert result["ai_failure"] is True
    assert result["failure_reason"] == "incomplete_coverage"
    assert result["recovery_mode"] == "ai_failed"
    diag = result["gemini_diagnostics"]
    assert diag["coverage_ok"] is False
    assert diag["unowned_paragraphs"] == [4]


@patch("services.ai_structure_recovery._classify_document", side_effect=_classify_ok)
@patch("services.ai_structure_recovery._identify_heading_candidates", side_effect=_headings_ok)
@patch("services.ai_structure_recovery._recover_hierarchy_batch")
def test_complete_coverage_returns_ai_reconstructed(mock_hier, _headings, _classify):
    paragraphs = ["Title", "Intro body", "Body two", "Body three", "Conclusion", "References list"]
    mock_hier.side_effect = _hierarchy_from(
        {
            1: [
                {"title": "Title", "heading_text": "Title", "paragraph_indices": [1], "confidence": 0.9, "insert_heading": False},
                {"title": "Introduction", "heading_text": "Introduction", "paragraph_indices": [2, 3, 4], "confidence": 0.85},
            ],
            5: [
                {"title": "Conclusion", "heading_text": "Conclusion", "paragraph_indices": [5], "confidence": 0.8},
                {"title": "References", "heading_text": "References", "paragraph_indices": [6], "confidence": 0.9},
            ],
        }
    )

    result = _recover_multiphase(paragraphs, "essay")

    assert result.get("ai_failure") is None
    assert result["recovery_mode"] == "ai_reconstructed"
    diag = result["gemini_diagnostics"]
    assert diag["coverage_ok"] is True
    assert diag["unowned_paragraphs"] == []


@patch("services.ai_structure_recovery._classify_document", side_effect=_classify_ok)
@patch("services.ai_structure_recovery._identify_heading_candidates", side_effect=_headings_ok)
@patch("services.ai_structure_recovery._recover_hierarchy_batch")
def test_bes_chunk2_empty_returns_ai_failed(mock_hier, _headings, _classify):
    # BES simulation: chunk 1 returns sections, chunk 2 (JE3/JE4/Reflection/References) is empty.
    paragraphs = [
        "Learning Journal",
        "Introduction",
        "Journal Entry 1",
        "Journal Entry 2",
        "Journal Entry 3",
        "Journal Entry 4",
        "References",
    ]
    mock_hier.side_effect = _hierarchy_from(
        {
            1: [
                {"title": "Learning Journal", "heading_text": "Learning Journal", "paragraph_indices": [1], "confidence": 1.0},
                {"title": "Introduction", "heading_text": "Introduction", "paragraph_indices": [2], "confidence": 1.0},
                {"title": "Journal Entry 1", "heading_text": "Journal Entry 1", "paragraph_indices": [3], "confidence": 1.0},
                {"title": "Journal Entry 2", "heading_text": "Journal Entry 2", "paragraph_indices": [4], "confidence": 1.0},
            ],
            5: [],
        }
    )

    result = _recover_multiphase(paragraphs, "learning_journal")

    assert result["ai_failure"] is True
    assert result["failure_reason"] == "incomplete_chunk"
    assert result["recovery_mode"] == "ai_failed"
