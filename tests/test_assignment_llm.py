"""Tests for assignment LLM provider routing."""

from __future__ import annotations

from unittest.mock import patch

from services.assignment_llm import (
    STAGE_BLUEPRINT,
    STAGE_REQUIREMENT_ANALYSIS,
    STAGE_RESEARCH,
    STAGE_SECTION_REVIEW,
    STAGE_WRITER,
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
def test_planning_stages_use_gemini_when_both_keys_present():
    for stage in (STAGE_REQUIREMENT_ANALYSIS, STAGE_RESEARCH, STAGE_BLUEPRINT, STAGE_SECTION_REVIEW):
        assert assignment_llm_provider(stage) == "gemini"
        assert assignment_uses_gemini(stage) is True


@patch.dict(
    "os.environ",
    {"GOOGLE_API_KEY": "g-test", "ANTHROPIC_API_KEY": "sk-test"},
    clear=False,
)
def test_writer_stage_stays_on_claude_when_both_keys_present():
    assert assignment_llm_provider(STAGE_WRITER) == "claude"
    assert assignment_uses_claude(STAGE_WRITER) is True


@patch.dict("os.environ", {"ASSIGNMENT_LLM": "claude", "ANTHROPIC_API_KEY": "sk-test"}, clear=False)
def test_writer_can_force_claude_via_env():
    assert assignment_llm_provider(STAGE_WRITER) == "claude"


@patch.dict("os.environ", {"ASSIGNMENT_LLM": "gemini", "GOOGLE_API_KEY": "g-test"}, clear=False)
def test_writer_can_force_gemini_via_env():
    assert assignment_llm_provider(STAGE_WRITER) == "gemini"


@patch("services.assignment_llm.gemini_generate_json", return_value=({"ok": True}, {"api_call_success": True}))
@patch.dict("os.environ", {"GOOGLE_API_KEY": "g-test", "ANTHROPIC_API_KEY": "sk-test"}, clear=False)
def test_research_generate_json_uses_gemini(mock_gemini):
    data, diag = assignment_generate_json(
        system_prompt="sys",
        user_prompt="user",
        stage=STAGE_RESEARCH,
    )
    assert data == {"ok": True}
    assert diag["api_call_success"] is True
    mock_gemini.assert_called_once()


@patch("services.assignment_llm.claude_generate_json", return_value=({"ok": True}, {"api_call_success": True}))
@patch.dict("os.environ", {"GOOGLE_API_KEY": "g-test", "ANTHROPIC_API_KEY": "sk-test"}, clear=False)
def test_writer_generate_json_uses_claude(mock_claude):
    data, diag = assignment_generate_json(
        system_prompt="sys",
        user_prompt="user",
        stage=STAGE_WRITER,
    )
    assert data == {"ok": True}
    assert diag["api_call_success"] is True
    mock_claude.assert_called_once()
