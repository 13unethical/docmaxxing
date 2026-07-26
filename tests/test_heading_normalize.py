"""Tests for markdown heading normalization after humanizer providers."""

from __future__ import annotations

from services.humanizer_engine.heading_utils import (
    normalize_markdown_headings,
    protect_markdown_headings,
    restore_markdown_headings,
)
from services.humanizer_engine.merge import merge_session_to_humanized_draft
from services.humanizer_engine.models import HumanizerParagraph, HumanizerSession, HumanizerSessionStatus
from services.assignment_pipeline.models import utc_now


def test_normalize_splits_inline_heading_and_body():
    raw = (
        "## Introduction The development of marketing has historically transformed "
        "how organisations compete. ## Journal Entry 1 Continuing the introduction..."
    )
    out = normalize_markdown_headings(raw)
    assert "## Introduction\n\nThe development" in out
    assert "## Journal Entry 1\n\nContinuing" in out


def test_protect_restore_keeps_heading_on_own_line():
    original = "## Introduction\n\nBody paragraph about markets.\n\n## Journal Entry 1\n\nMore body."
    protected, headings = protect_markdown_headings(original)
    assert "[[[HEADING_0]]]" in protected
    # Simulate provider collapsing whitespace around placeholders.
    collapsed = protected.replace("\n\n", " ").replace("\n", " ")
    restored = restore_markdown_headings(collapsed, headings)
    assert "## Introduction\n\n" in restored
    assert "## Journal Entry 1\n\n" in restored


def test_merge_normalizes_collapsed_stealthwriter_output():
    now = utc_now()
    session = HumanizerSession(
        id="hz-1",
        project_id="p1",
        source_draft_id="d1",
        source_draft_version=1,
        paragraphs=[
            HumanizerParagraph(
                paragraph_id="p1",
                section="Introduction",
                original_text="## Introduction\n\nOriginal.",
                humanized_text=(
                    "## Introduction The development of marketing has historically "
                    "transformed organisations. ## Journal Entry 1 Continuing on..."
                ),
            )
        ],
        current_paragraph_id=None,
        completed_paragraph_ids=["p1"],
        remaining_paragraph_ids=[],
        progress=100,
        paragraphs_processed=1,
        average_ai_reduction=50.0,
        estimated_remaining_time="0 minutes",
        status=HumanizerSessionStatus.COMPLETED,
        engine_version="test",
        requirement_json={},
        blueprint={},
        created_at=now,
        updated_at=now,
    )
    draft = merge_session_to_humanized_draft(session)
    assert "## Introduction\n\nThe development" in draft.content
    assert "## Journal Entry 1\n\nContinuing" in draft.content
