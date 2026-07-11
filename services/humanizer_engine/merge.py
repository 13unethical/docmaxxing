"""Merge humanized paragraphs into a new draft version."""

from __future__ import annotations

import uuid

from services.assignment_pipeline.models import utc_now
from services.humanizer_engine.models import HumanizedDraft, HumanizerSession, count_words


def merge_session_to_humanized_draft(session: HumanizerSession, *, title: str | None = None) -> HumanizedDraft:
    parts: list[str] = []
    current_section: str | None = None

    for paragraph in session.paragraphs:
        text = (paragraph.humanized_text or paragraph.original_text).strip()
        if not text:
            continue
        if text.startswith("## "):
            parts.append(text)
            current_section = text[3:].strip()
            continue
        if "## " in text:
            parts.append(text)
            if paragraph.section:
                current_section = paragraph.section
            continue
        if paragraph.section and paragraph.section != current_section:
            parts.append(f"## {paragraph.section}")
            current_section = paragraph.section
        parts.append(text)

    content = "\n\n".join(parts)
    draft_title = title or "Humanized Assignment Draft"
    source_version = session.source_draft_version
    return HumanizedDraft(
        id=str(uuid.uuid4()),
        project_id=session.project_id,
        session_id=session.id,
        source_draft_id=session.source_draft_id,
        source_version=source_version,
        title=draft_title,
        content=content,
        total_words=count_words(content),
        version=source_version + 1,
        paragraphs_processed=session.paragraphs_processed,
        average_ai_reduction=session.average_ai_reduction,
        created_at=utc_now(),
    )
