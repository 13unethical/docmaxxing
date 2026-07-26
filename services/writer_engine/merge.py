"""Merge completed sections into a draft document."""

from __future__ import annotations

import re
import uuid

from services.assignment_pipeline.models import utc_now
from services.writer_engine.models import Draft, WriterSession, count_words

_HEADING_LINE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _section_block(title: str, body: str) -> str:
    """Ensure each section contributes a structural ``## Title`` heading + body.

    The LLM writer returns body prose only. Mock writer may already include the
    heading. Either way, mandatory section titles from the blueprint/requirements
    must survive into the merged draft as explicit headings.
    """
    text = (body or "").strip()
    title = (title or "").strip() or "Section"
    if not text:
        return f"## {title}"

    match = _HEADING_LINE.match(text.split("\n", 1)[0].strip())
    if match:
        existing = match.group(1).strip()
        # Keep an existing heading when it already matches this section.
        if existing.lower() == title.lower():
            return text
        # Wrong/invented heading on this section — replace with the required title.
        rest = text.split("\n", 1)[1].lstrip() if "\n" in text else ""
        return f"## {title}\n\n{rest}".strip()

    return f"## {title}\n\n{text}"


def merge_session_to_draft(session: WriterSession, *, title: str | None = None) -> Draft:
    parts: list[str] = []
    sections_payload: list[dict] = []
    total_generation_time = 0.0
    models_used: list[str] = []
    for section in session.sections:
        if section.status.value != "completed" or not section.generated_text.strip():
            continue
        block = _section_block(section.title, section.generated_text)
        parts.append(block)
        sections_payload.append(
            {
                "title": section.title,
                "purpose": section.objective,
                "target_words": section.estimated_words,
                "draft": section.generated_text,
                "citations_used": list(section.citations_used),
                "warnings": list(section.warnings),
                "generation_time": section.generation_time,
                "model_used": section.model_used,
                "review_result": section.last_review.to_dict() if section.last_review else None,
            }
        )
        total_generation_time += float(section.generation_time or 0.0)
        if section.model_used and section.model_used not in models_used:
            models_used.append(section.model_used)
    content = "\n\n".join(parts)
    draft_title = title or "Assignment Draft"
    return Draft(
        id=str(uuid.uuid4()),
        project_id=session.project_id,
        session_id=session.id,
        title=draft_title,
        content=content,
        sections=sections_payload,
        total_words=count_words(content),
        generation_time=round(total_generation_time, 3),
        model=", ".join(models_used),
        version=1,
        created_at=utc_now(),
    )
