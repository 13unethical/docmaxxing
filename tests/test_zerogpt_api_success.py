"""Tests for ZeroGPT business JSON success flag handling."""

from __future__ import annotations

import pytest

from services.zerogpt_business.client import ZeroGPTError, _ensure_api_success
from services.zerogpt_business.providers import _extract_humanized_text


def test_extract_humanized_text_reads_paraphrase_message():
    payload = {
        "success": True,
        "code": 200,
        "message": "Text Transformed",
        "data": {
            "message": "Paraphrased paragraph text.",
            "message_html": "<span>Paraphrased paragraph text.</span>",
            "code": 200,
        },
    }
    assert _extract_humanized_text(payload) == "Paraphrased paragraph text."


def test_extract_humanized_text_reads_data_output():
    payload = {
        "success": True,
        "code": 200,
        "message": "Text humanized successfully.",
        "data": {
            "documentId": "abc",
            "output": "Humanized paragraph text.",
            "status": "done",
        },
    }
    assert _extract_humanized_text(payload) == "Humanized paragraph text."


def test_extract_humanized_text_reads_nested_raw_output():
    payload = {
        "success": True,
        "data": {
            "raw": {"output": "Nested humanized text."},
        },
    }
    assert _extract_humanized_text(payload) == "Nested humanized text."


def test_ensure_api_success_raises_on_false_success():
    with pytest.raises(ZeroGPTError, match="whitelisted"):
        _ensure_api_success(
            {"success": False, "code": 500, "message": "Illegal Request", "data": None},
            path="/api/transform/humanize",
        )


def test_ensure_api_success_passes_true_success():
    body = {"success": True, "data": {"output_text": "hello"}}
    assert _ensure_api_success(body, path="/api/transform/humanize") == body
