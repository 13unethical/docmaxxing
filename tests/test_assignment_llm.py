"""Tests for assignment LLM provider routing."""

from __future__ import annotations

from unittest.mock import patch

from services.assignment_llm import (
    assignment_generate_json,
    assignment_llm_provider,
    assignment_uses_claude,
    assignment_uses_gemini,
)


@patch.dict(
    "os.environ",
    {"GOOGLE_API_KEY": "g-test", "ANTHROPIC_API_KEY": "sk-test"},
    clear=False,
)
def test_assignment_defaults_to_gemini_when_both_keys_present():
    assert assignment_llm_provider() == "gemini"
    assert assignment_uses_gemini() is True
    assert assignment_uses_claude() is False


@patch.dict("os.environ", {"ASSIGNMENT_LLM": "claude", "ANTHROPIC_API_KEY": "sk-test"}, clear=False)
def test_assignment_can_force_claude():
    assert assignment_llm_provider() == "claude"
    assert assignment_uses_claude() is True


@patch.dict("os.environ", {"ASSIGNMENT_LLM": "gemini", "GOOGLE_API_KEY": "g-test"}, clear=False)
def test_assignment_can_force_gemini():
    assert assignment_llm_provider() == "gemini"
    assert assignment_uses_claude() is False


@patch.dict(
    "os.environ",
    {
        "ANTHROPIC_API_KEY": "sk-test",
        "GOOGLE_API_KEY": "",
        "GEMINI_API_KEY": "",
        "ASSIGNMENT_LLM": "",
    },
    clear=False,
)
def test_assignment_falls_back_to_claude_without_google_key():
    assert assignment_llm_provider() == "claude"


@patch("services.assignment_llm.gemini_generate_json", return_value=({"ok": True}, {"api_call_success": True}))
@patch.dict("os.environ", {"GOOGLE_API_KEY": "g-test"}, clear=False)
def test_assignment_generate_json_uses_gemini_by_default(mock_gemini):
    data, diag = assignment_generate_json(system_prompt="sys", user_prompt="user")
    assert data == {"ok": True}
    assert diag["api_call_success"] is True
    mock_gemini.assert_called_once()


@patch("services.assignment_llm.claude_generate_json", return_value=({"ok": True}, {"api_call_success": True}))
@patch.dict("os.environ", {"ASSIGNMENT_LLM": "claude", "ANTHROPIC_API_KEY": "sk-test"}, clear=False)
def test_assignment_generate_json_uses_claude_when_forced(mock_claude):
    data, diag = assignment_generate_json(system_prompt="sys", user_prompt="user")
    assert data == {"ok": True}
    assert diag["api_call_success"] is True
    mock_claude.assert_called_once()
