"""Tests for Gemini client retries, fallback models, and failure classification."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from services.gemini_client import generate_json


def _mock_response(status: int, json_body: dict | None = None, text: str = "") -> MagicMock:
    res = MagicMock()
    res.status_code = status
    res.ok = 200 <= status < 300
    res.text = text
    if json_body is not None:
        res.json.return_value = json_body
    else:
        res.json.side_effect = ValueError("not json")
    return res


@patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}, clear=False)
@patch("services.gemini_client.time.sleep")
@patch("services.gemini_client.requests.post")
def test_retries_503_then_succeeds(mock_post, mock_sleep):
    success_payload = {
        "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
        "usageMetadata": {"totalTokenCount": 12},
    }
    mock_post.side_effect = [
        _mock_response(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}}),
        _mock_response(200, success_payload),
    ]

    data, diag = generate_json(system_prompt="sys", user_prompt="user", max_retries=2)

    assert data == {"ok": True}
    assert diag["api_call_success"] is True
    assert diag["retry_count"] == 1
    assert diag["http_status"] == 200
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once()


@patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}, clear=False)
@patch("services.gemini_client.time.sleep")
@patch("services.gemini_client.requests.post")
def test_503_exhausted_returns_unavailable(mock_post, mock_sleep):
    mock_post.return_value = _mock_response(
        503,
        {"error": {"message": "This model is currently experiencing high demand.", "status": "UNAVAILABLE"}},
    )

    data, diag = generate_json(
        system_prompt="sys",
        user_prompt="user",
        models=["gemini-2.5-flash"],
        max_retries=1,
    )

    assert data is None
    assert diag["failure_reason"] == "unavailable"
    assert diag["http_status"] == 503
    assert diag["retry_count"] == 1


@patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}, clear=False)
@patch("services.gemini_client.time.sleep")
@patch("services.gemini_client.requests.post")
def test_fallback_model_on_404(mock_post, mock_sleep):
    success_payload = {
        "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
    }
    mock_post.side_effect = [
        _mock_response(404, {"error": {"message": "model not found"}}),
        _mock_response(200, success_payload),
    ]

    data, diag = generate_json(
        system_prompt="sys",
        user_prompt="user",
        models=["gemini-2.5-flash", "gemini-2.5-flash-lite"],
        max_retries=0,
    )

    assert data == {"ok": True}
    assert diag["fallback_activated"] is True
    assert diag["models_attempted"] == ["gemini-2.5-flash", "gemini-2.5-flash-lite"]


@patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}, clear=False)
@patch("services.gemini_client.time.sleep")
@patch("services.gemini_client.requests.post")
def test_quota_failure_classification(mock_post, mock_sleep):
    mock_post.return_value = _mock_response(
        429,
        {
            "error": {
                "message": "Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20",
                "status": "RESOURCE_EXHAUSTED",
            }
        },
    )

    data, diag = generate_json(system_prompt="sys", user_prompt="user", models=["gemini-2.5-flash"], max_retries=0)

    assert data is None
    assert diag["failure_reason"] == "quota"
    assert diag["http_status"] == 429


@patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}, clear=False)
@patch("services.gemini_client.requests.post")
def test_timeout_failure_classification(mock_post):
    mock_post.side_effect = requests.exceptions.Timeout("timed out")

    data, diag = generate_json(
        system_prompt="sys",
        user_prompt="user",
        models=["gemini-2.5-flash"],
        max_retries=0,
    )

    assert data is None
    assert diag["failure_reason"] == "timeout"


@patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}, clear=False)
@patch("services.gemini_client.requests.post")
def test_parse_error_on_invalid_json(mock_post):
    mock_post.return_value = _mock_response(
        200,
        {"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]},
    )

    data, diag = generate_json(
        system_prompt="sys",
        user_prompt="user",
        models=["gemini-2.5-flash"],
        max_retries=0,
    )

    assert data is None
    assert diag["failure_reason"] == "parse_error"
