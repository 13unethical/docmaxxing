"""Merge humanized paragraphs into a new draft version."""

from __future__ import annotations

import re
import uuid

from services.assignment_pipeline.models import utc_now
from services.humanizer_engine.heading_utils import normalize_markdown_headings
from services.humanizer_engine.models import HumanizedDraft, HumanizerSession, count_words


def merge_session_to_humanized_draft(session: HumanizerSession, *, title: str | None = None) -> HumanizedDraft:
    parts: list[str] = []
    current_section: str | None = None

    for paragraph in session.paragraphs:
        text = normalize_markdown_headings(paragraph.humanized_text or paragraph.original_text)
        if not text:
            continue
        if text.startswith("## ") and "\n" not in text:
            parts.append(text)
            current_section = text[3:].strip()
            continue
        if text.lstrip().startswith("## "):
            parts.append(text)
            # Track last explicit heading in the batch.
            matches = re.findall(r"(?m)^##\s+(.+)$", text)
            if matches:
                current_section = matches[-1].strip()
            elif paragraph.section:
                current_section = paragraph.section
            continue
        if paragraph.section and paragraph.section != current_section:
            # Never invent placeholder structure labels.
            if paragraph.section.strip().lower() not in {"document", "preamble"}:
                parts.append(f"## {paragraph.section}")
                current_section = paragraph.section
            elif current_section is None:
                current_section = paragraph.section
        parts.append(text)

    content = normalize_markdown_headings("\n\n".join(parts))
    draft_title = title or "Humanized Assignment Draft"
    source_version = session.source_draft_version
    try:
        from services.assignment_spec.validate import count_body_words

        words = count_body_words(content)
    except Exception:  # noqa: BLE001
        words = count_words(content)
    return HumanizedDraft(
        id=str(uuid.uuid4()),
        project_id=session.project_id,
        session_id=session.id,
        source_draft_id=session.source_draft_id,
        source_version=source_version,
        title=draft_title,
        content=content,
        total_words=words,
        version=source_version + 1,
        paragraphs_processed=session.paragraphs_processed,
        average_ai_reduction=session.average_ai_reduction,
        created_at=utc_now(),
    )
