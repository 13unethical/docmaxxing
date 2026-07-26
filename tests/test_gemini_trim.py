"""Tests for Gemini smart-trim on merge word-budget overage."""

from __future__ import annotations

from services.assignment_spec import build_assignment_spec
from services.assignment_spec.validate import count_words, render_structured_markdown
from services.writer_engine.gemini_trim import gemini_trim_markdown_to_budget


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
                    {"title": "Introduction", "body": " ".join(["intro"] * 200)},
                    {
                        "title": "Journal Entry 1",
                        "body": " ".join(["entryone"] * 280) + " lecture seminar evidence.",
                    },
                    {"title": "Journal Entry 2", "body": " ".join(["entrytwo"] * 280)},
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
    words = count_words(trimmed)
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
