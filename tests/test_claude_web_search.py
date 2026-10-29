"""Claude web search helper: pause_turn continuation, search count, and source extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

from services import claude_client


def _response(payload, status=200):
    res = MagicMock()
    res.status_code = status
    res.ok = status < 400
    res.json.return_value = payload
    res.text = str(payload)
    return res


def test_generate_with_web_search_continues_paused_turn_and_collects_sources(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    first = {
        "stop_reason": "pause_turn",
        "usage": {"server_tool_use": {"web_search_requests": 2}},
        "content": [
            {"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "q"}},
            {
                "type": "web_search_tool_result",
                "tool_use_id": "s1",
                "content": [
                    {"type": "web_search_result", "url": "https://b.org/x", "title": "B"},
                    {"type": "web_search_result", "url": "https://a.org/y", "title": "A"},
                ],
            },
        ],
    }
    second = {
        "stop_reason": "end_turn",
        "usage": {"server_tool_use": {"web_search_requests": 1}},
        "content": [
            {"type": "text", "text": "Fact one. "},
            {
                "type": "text",
                "text": "Fact two.",
                "citations": [{"type": "web_search_result_location", "url": "https://a.org/y", "title": "A"}],
            },
        ],
    }
    post = MagicMock(side_effect=[_response(first), _response(second)])
    monkeypatch.setattr(claude_client.requests, "post", post)

    text, sources, diag = claude_client.generate_with_web_search(
        system_prompt="sys", user_prompt="topic", max_searches=4
    )

    assert text == "Fact one. Fact two."
    assert sources == [{"url": "https://a.org/y", "title": "A"}, {"url": "https://b.org/x", "title": "B"}]
    assert diag["web_searches"] == 3 and diag["api_call_success"] is True
    first_body = post.call_args_list[0].kwargs["json"]
    assert first_body["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}]
    second_messages = post.call_args_list[1].kwargs["json"]["messages"]
    assert second_messages[-1] == {"role": "assistant", "content": first["content"]}


def test_generate_with_web_search_reports_api_errors(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(claude_client.requests, "post", MagicMock(return_value=_response({"error": "bad"}, 400)))
    text, sources, diag = claude_client.generate_with_web_search(system_prompt="s", user_prompt="u")
    assert text is None and sources == []
    assert diag["failure_reason"] == "unavailable"


def test_generate_with_web_search_needs_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("Claude_API_Key", raising=False)
    text, _sources, diag = claude_client.generate_with_web_search(system_prompt="s", user_prompt="u")
    assert text is None and diag["failure_reason"] == "validation_error"


def test_temperature_is_sent_only_to_models_that_accept_it(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    post = MagicMock(return_value=_response({"content": [{"type": "text", "text": '{"ok": true}'}]}))
    monkeypatch.setattr(claude_client.requests, "post", post)
    claude_client.generate_json(system_prompt="s", user_prompt="u", model="claude-sonnet-4-6", temperature=0.5)
    assert post.call_args.kwargs["json"]["temperature"] == 0.5
    claude_client.generate_json(system_prompt="s", user_prompt="u", model="claude-sonnet-5-5", temperature=0.5)
    assert "temperature" not in post.call_args.kwargs["json"]
    assert claude_client.accepts_temperature("claude-haiku-4-5")
    assert not claude_client.accepts_temperature("claude-haiku-5-5")
    assert not claude_client.accepts_temperature("claude-opus-5-5")
