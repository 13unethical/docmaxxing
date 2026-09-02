"""PlagDetect row status: similarity success must not become a full Failed check."""

from services.browser.providers.plagdetect import (
    AI_WORD_LIMIT_DISPLAY,
    _ai_unavailable_reason,
    _is_ai_word_limit_text,
    _row_status,
)


def test_similarity_with_ai_word_limit_is_completed():
    row = {
        "ai_text": "AI reports require 300-30,000 words",
        "similarity_text": "12%",
        "status_text": "Failed",
        "row_text": "12% | AI reports require 300-30,000 words | Failed",
    }
    assert _row_status(row) == "completed"
    assert _ai_unavailable_reason(row) == AI_WORD_LIMIT_DISPLAY
    assert _is_ai_word_limit_text(row["ai_text"])


def test_true_failure_without_similarity_is_failed():
    row = {
        "ai_text": "-",
        "similarity_text": "-",
        "status_text": "Failed",
        "row_text": "upload error Failed",
    }
    assert _row_status(row) == "failed"


def test_processing_row_stays_running():
    row = {
        "ai_text": "-",
        "similarity_text": "-",
        "status_text": "Processing",
        "row_text": "Processing",
    }
    assert _row_status(row) == "running"


def test_numeric_ai_or_sim_counts_as_completed():
    assert _row_status({"ai_text": "8%", "similarity_text": "-", "status_text": ""}) == "completed"
    assert _row_status({"ai_text": "-", "similarity_text": "4%", "status_text": ""}) == "completed"
