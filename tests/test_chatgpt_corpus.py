"""ChatGPT corpus generation and the OpenAI client request shape (no network)."""

from __future__ import annotations

from services.humanizer_training.chatgpt_corpus import (
    SOURCE,
    detector_rows,
    flatten_markdown,
    generate_one,
    make_briefs,
    parse_model_mix,
    split_of,
    windows,
)
from services.openai_client import build_body, estimate_cost_usd, generate_text


def test_briefs_are_deterministic_varied_and_split_by_id():
    mix = parse_model_mix("gpt-4o:3,gpt-5:1")
    a = make_briefs(200, seed=1, model_mix=mix)
    b = make_briefs(200, seed=1, model_mix=mix)
    assert [x.brief_id for x in a] == [x.brief_id for x in b]
    assert len({x.brief_id for x in a}) == 200
    assert len({x.prompt for x in a}) > 190
    assert {x.model for x in a} == {"gpt-4o", "gpt-5"}
    assert len({x.target_words for x in a}) >= 6
    test_share = sum(x.split == "test" for x in a) / len(a)
    assert 0.05 < test_share < 0.3
    assert all(x.split == split_of(x.brief_id) for x in a)


def test_flatten_markdown_matches_copied_chatgpt_text():
    raw = "# Title\n\n## Intro\n\n**Climate** change is *real*.\n\n- First point\n- Second point\n\n1. One\n\n---\n\nEnd."
    flat = flatten_markdown(raw)
    assert flat.startswith("Title\n\nIntro\n\nClimate change is real.")
    assert "First point\nSecond point" in flat
    assert "#" not in flat and "*" not in flat and "---" not in flat and "1." not in flat


def test_windows_and_detector_rows():
    sentence = "This sentence adds another twelve words to the running window of text. "
    text = sentence * 40
    ws = list(windows(text))
    assert ws and all(len(w.split()) >= 40 for w in ws)
    assert all(len(w.split()) < 140 for w in ws)
    rows = detector_rows([{"id": "gpt-1", "split": "test", "text": text}])
    assert len(rows) == len(ws)
    assert rows[0] == {"text": ws[0], "ai": 1, "ai_frac": 1.0, "source": SOURCE, "doc": "gpt-1", "split": "test"}
    assert list(windows("Smith (2020). Retrieved from https://x.org " * 20)) == []


def test_generate_one_rejects_truncated_and_short_answers():
    brief = make_briefs(1, seed=3, model_mix=[("gpt-4o", 1.0)])[0]
    long_text = "## Heading\n\n" + "A real paragraph about the topic with enough words. " * 40

    def ok(**kw):
        assert kw["model"] == "gpt-4o" and kw["system_prompt"] == ""
        return long_text, {"model": "gpt-4o-2024-11-20", "cost_usd": 0.01, "finish_reason": "stop"}

    doc, _ = generate_one(brief, ok)
    assert doc["id"] == brief.brief_id and doc["model"] == "gpt-4o-2024-11-20"
    assert not doc["text"].startswith("#") and doc["words"] > 300

    doc, _ = generate_one(brief, lambda **kw: (long_text, {"finish_reason": "MAX_TOKENS"}))
    assert doc is None
    doc, diag = generate_one(brief, lambda **kw: ("Too short.", {"finish_reason": "stop"}))
    assert doc is None and diag["error_message"] == "too short"


def test_openai_body_omits_temperature_for_reasoning_models():
    body = build_body(system_prompt="S", content="C", temperature=0.9, model="gpt-4o", max_tokens=100)
    assert body["temperature"] == 0.9 and body["max_completion_tokens"] == 100
    assert body["messages"] == [{"role": "system", "content": "S"}, {"role": "user", "content": "C"}]
    body = build_body(system_prompt="", content="C", temperature=0.9, model="gpt-5-mini", max_tokens=100)
    assert "temperature" not in body
    assert body["messages"] == [{"role": "user", "content": "C"}]


def test_openai_cost_estimate_and_missing_key(monkeypatch):
    assert estimate_cost_usd("gpt-4o", 1_000_000, 1_000_000) == 12.5
    assert estimate_cost_usd("gpt-4o-2024-11-20", 1_000_000, 0) == 2.5
    assert estimate_cost_usd("unknown-model", 10, 10) is None
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    text, diag = generate_text(system_prompt="", content="hi")
    assert text is None and "OPENAI_API_KEY" in diag["error_message"]
