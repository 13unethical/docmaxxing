"""Tests for Gemini smart-trim and post-humanize sentence-drop."""

from __future__ import annotations

from services.assignment_spec import build_assignment_spec
from services.assignment_spec.validate import count_body_words, count_words, render_structured_markdown
from services.writer_engine.gemini_trim import (
    fit_humanized_content_to_budget,
    gemini_trim_markdown_to_budget,
)


def test_gemini_trim_reduces_over_budget_draft(monkeypatch):
    requirement = {
        "title": "Learning Journal",
        "assignment_type": "Learning Journal",
        "word_count": 1200,
        "required_sections": [
            "Introduction",
            "Journal Entry 1",
            "Journal Entry 2",
            "Reflection",
        ],
        "section_word_budgets": {
            "Introduction": 200,
            "Journal Entry 1": 300,
            "Journal Entry 2": 300,
            "Reflection": 400,
        },
        "learning_outcomes": ["LO1. Define historical concepts"],
        "rubric": [{"criterion": "LO1", "weight": "100%", "description": "Define concepts"}],
    }
    spec = build_assignment_spec(requirement, project_id="p1")

    # Intentionally over max (1320 for ±10% of 1200).
    bloated = {
        "Introduction": " ".join(["intro"] * 250),
        "Journal Entry 1": " ".join(["entryone"] * 350) + " lecture seminar evidence.",
        "Journal Entry 2": " ".join(["entrytwo"] * 350),
        "Reflection": " ".join(["reflect"] * 450) + " personal major choice.",
    }
    content = render_structured_markdown(
        [{"title": title, "body": body} for title, body in bloated.items()]
    )
    assert count_words(content) > spec.max_total_words

    def fake_generate_json(**kwargs):
        # Land inside ±10% band (1080–1320 for target 1200).
        return (
            {
                "sections": [
                    {"title": "Introduction", "body": " ".join(["intro"] * 200) + "."},
                    {
                        "title": "Journal Entry 1",
                        "body": " ".join(["entryone"] * 280) + " lecture seminar evidence.",
                    },
                    {"title": "Journal Entry 2", "body": " ".join(["entrytwo"] * 280) + "."},
                    {
                        "title": "Reflection",
                        "body": " ".join(["reflect"] * 360) + " personal major choice.",
                    },
                ],
                "words_removed_estimate": 200,
                "notes": ["cut filler"],
            },
            {"ok": True},
        )

    monkeypatch.setattr(
        "services.assignment_llm.assignment_generate_json",
        fake_generate_json,
    )
    monkeypatch.setattr(
        "services.assignment_llm.assignment_llm_configured",
        lambda stage=None: True,
    )

    trimmed = gemini_trim_markdown_to_budget(content, spec=spec)
    assert trimmed is not None
    words = count_body_words(trimmed)
    assert words <= spec.max_total_words
    assert words >= spec.min_total_words
    assert "lecture" in trimmed.lower()
    assert "personal" in trimmed.lower()


def test_gemini_trim_rejects_destructive_cuts(monkeypatch):
    requirement = {
        "title": "Essay",
        "word_count": 500,
        "required_sections": ["Introduction", "Body"],
        "section_word_budgets": {"Introduction": 150, "Body": 350},
    }
    spec = build_assignment_spec(requirement, project_id="p2")
    content = render_structured_markdown(
        [
            {"title": "Introduction", "body": " ".join(["word"] * 200)},
            {"title": "Body", "body": " ".join(["body"] * 400)},
        ]
    )

    def fake_generate_json(**kwargs):
        return (
            {
                "sections": [
                    {"title": "Introduction", "body": "too short"},
                    {"title": "Body", "body": "also ruined"},
                ]
            },
            {},
        )

    monkeypatch.setattr("services.assignment_llm.assignment_generate_json", fake_generate_json)
    monkeypatch.setattr("services.assignment_llm.assignment_llm_configured", lambda stage=None: True)

    assert gemini_trim_markdown_to_budget(content, spec=spec) is None


def _many_sentences(prefix: str, n: int) -> str:
    return " ".join(f"{prefix} point number {i} elaborates the discussion further." for i in range(n))


def test_fit_humanized_drops_qa_unit_together(monkeypatch):
    """Question + answer must drop as one unit; no rewritten wording."""
    spec = build_assignment_spec(
        {
            "title": "Essay",
            "word_count": 80,
            "required_sections": ["Introduction", "Body", "References"],
            "section_word_budgets": {"Introduction": 30, "Body": 50},
        },
        project_id="qa1",
    )
    monkeypatch.setattr(
        "services.assignment_llm.assignment_llm_configured",
        lambda stage=None: False,
    )

    unique_marker = "UNIQUE_SW_MARKER_XYZ"
    content = (
        "## Introduction\n\n"
        f"This assignment aims to examine practice. {unique_marker} opening stays. "
        "Filler sentence one pads the introduction length. "
        "Filler sentence two pads the introduction length. "
        "Filler sentence three pads the introduction length.\n\n"
        "## Body\n\n"
        "What drives the outcome in this case? The outcome is driven by local context. "
        + _many_sentences("Body", 25)
        + " Closing synthesis remains for the section.\n\n"
        "## References\n\n"
        "Smith, J. (2020). Title. Journal.\n"
        "Jones, A. (2021). Other. Press.\n"
    )
    before = count_body_words(content)
    assert before > spec.max_total_words

    fitted, meta = fit_humanized_content_to_budget(content, spec=spec)
    assert unique_marker in fitted  # original SW wording preserved when kept
    assert "## References" in fitted
    assert "Smith, J. (2020)" in fitted
    assert meta.get("method") == "heuristic_sentence_drop"
    # Either keep both Q+A or drop both — never leave orphan answer alone after orphaned Q removal
    has_q = "What drives the outcome in this case?" in fitted
    has_a = "The outcome is driven by local context." in fitted
    assert has_q == has_a
    assert count_body_words(fitted) < before


def test_fit_humanized_gemini_ranks_drop_ids_only(monkeypatch):
    """Gemini may only return drop_ids; Python deletes original sentences."""
    spec = build_assignment_spec(
        {
            "title": "Essay",
            "word_count": 60,
            "required_sections": ["Body", "References"],
            "section_word_budgets": {"Body": 60},
        },
        project_id="drop1",
    )
    keep_a = "Alpha sentence must remain intact after trim."
    keep_b = "Beta sentence must remain intact after trim."
    drop_me = "Gamma filler sentence is disposable background fluff."
    drop_me2 = "Delta filler sentence repeats the same background fluff."
    content = (
        "## Body\n\n"
        f"{keep_a} {drop_me} {drop_me2} "
        + _many_sentences("Extra", 20)
        + f" {keep_b}\n\n"
        "## References\n\nDoe, A. (2019). Book.\n"
    )

    def fake_generate_json(**kwargs):
        user = kwargs.get("user_prompt") or ""
        assert "rank_sentences_to_delete" in user or '"sentences"' in user
        return (
            {
                "drop_ids": ["body-s2", "body-s3"],
                "words_removed_estimate": 20,
                "notes": ["drop filler"],
            },
            {"ok": True},
        )

    monkeypatch.setattr("services.assignment_llm.assignment_generate_json", fake_generate_json)
    monkeypatch.setattr("services.assignment_llm.assignment_llm_configured", lambda stage=None: True)

    fitted, meta = fit_humanized_content_to_budget(content, spec=spec)
    assert keep_a in fitted
    assert keep_b in fitted
    assert drop_me not in fitted
    assert drop_me2 not in fitted
    assert "Doe, A. (2019)" in fitted
    assert meta.get("method") == "gemini_ranked_sentence_drop"
    assert "body-s2" in (meta.get("dropped_ids") or [])


def test_fit_humanized_rejects_gemini_rewrite_payload(monkeypatch):
    """If Gemini returns rewritten sections, ignore and fall back to heuristic."""
    spec = build_assignment_spec(
        {
            "title": "Essay",
            "word_count": 50,
            "required_sections": ["Body"],
            "section_word_budgets": {"Body": 50},
        },
        project_id="rej1",
    )
    original = "Original stealth sentence one stays. Original stealth sentence two stays. "
    content = (
        "## Body\n\n"
        + original
        + _many_sentences("Pad", 30)
        + " Final protected closing sentence here.\n"
    )

    def fake_generate_json(**kwargs):
        return (
            {
                "sections": [{"title": "Body", "body": "Totally rewritten Gemini prose that must not appear."}],
                "drop_ids": [],
            },
            {},
        )

    monkeypatch.setattr("services.assignment_llm.assignment_generate_json", fake_generate_json)
    monkeypatch.setattr("services.assignment_llm.assignment_llm_configured", lambda stage=None: True)

    fitted, meta = fit_humanized_content_to_budget(content, spec=spec)
    assert "Totally rewritten Gemini prose" not in fitted
    assert "Original stealth sentence one stays." in fitted
    assert meta.get("method") == "heuristic_sentence_drop"
