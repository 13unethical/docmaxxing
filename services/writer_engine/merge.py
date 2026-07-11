"""Merge completed sections into a draft document."""

from __future__ import annotations

import uuid

from services.assignment_pipeline.models import utc_now
from services.writer_engine.models import Draft, WriterSession, count_words


def merge_session_to_draft(session: WriterSession, *, title: str | None = None) -> Draft:
    parts: list[str] = []
    sections_payload: list[dict] = []
    total_generation_time = 0.0
    models_used: list[str] = []
    for section in session.sections:
        if section.status.value != "completed" or not section.generated_text.strip():
            continue
        parts.append(section.generated_text.strip())
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
