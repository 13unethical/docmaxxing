"""Gemini smart trim — cut excess words with minimal damage to grade quality."""

from __future__ import annotations

import json
from typing import Any

from services.assignment_spec.models import AssignmentSpec
from services.assignment_spec.validate import count_words, parse_markdown_sections, render_structured_markdown

_SYSTEM = """You trim an academic assignment so its TOTAL word count fits a hard budget.
Return ONLY JSON:
{
  "sections": [
    {"title": "Exact existing section title", "body": "Full trimmed body WITHOUT ## heading"}
  ],
  "words_removed_estimate": 0,
  "notes": ["what was cut"]
}

Rules:
- Keep the SAME section titles and order. Do not invent sections or new claims.
- Delete or lightly condense ONLY what is needed so TOTAL body words land inside [min_total, max_total].
- Prefer landing near target_words when possible without harming quality.
- Cut first: redundancy, repeated examples, filler hedges, ornate phrasing, duplicated transitions.
- NEVER remove or weaken:
  - required lecture/seminar references
  - mandatory comparisons / reflections / personal-major links
  - citations and evidence anchors
  - learning-outcome / rubric-critical claims
  - section structure and logical flow
- Do not add new text. Academic tone only. No meta notes.
"""


def gemini_trim_markdown_to_budget(
    content: str,
    *,
    spec: AssignmentSpec,
    current_words: int | None = None,
) -> str | None:
    """Ask Gemini to remove the minimum safe excess words. Returns trimmed markdown or None."""
    from services.assignment_llm import (
        STAGE_REVISION,
        assignment_generate_json,
        assignment_llm_configured,
    )

    if not assignment_llm_configured(STAGE_REVISION):
        return None

    total = int(current_words if current_words is not None else count_words(content))
    if total <= spec.max_total_words:
        return content

    excess = total - spec.max_total_words
    # Prefer cutting toward target when that still lands in-band.
    prefer_remove = max(excess, total - spec.total_word_target)
    sections = parse_markdown_sections(content)
    payload = {
        "task": "trim_to_word_budget",
        "current_total_words": total,
        "min_total": spec.min_total_words,
        "max_total": spec.max_total_words,
        "target_words": spec.total_word_target,
        "minimum_words_to_remove": excess,
        "preferred_words_to_remove": prefer_remove,
        "constraints": {
            "mandatory_content_rules": spec.mandatory_content_rules,
            "required_lecture_seminar_refs": spec.required_lecture_seminar_refs,
            "mandatory_reflections": spec.mandatory_reflections,
            "mandatory_comparisons": spec.mandatory_comparisons,
            "learning_outcomes": spec.learning_outcomes,
            "forbidden_content": spec.forbidden_content,
            "section_word_targets": spec.section_word_targets,
        },
        "sections": [
            {
                "title": s["title"],
                "body": s["body"],
                "target_words": (
                    spec.section_by_title(s["title"]).target_words
                    if spec.section_by_title(s["title"])
                    else 0
                ),
                "current_words": count_words(s["body"]),
            }
            for s in sections
            if s["title"] not in {"Preamble", "Document"}
        ],
    }

    data, _meta = assignment_generate_json(
        system_prompt=_SYSTEM,
        user_prompt=json.dumps(payload, ensure_ascii=False, indent=2),
        temperature=0.1,
        max_retries=1,
        stage=STAGE_REVISION,
    )
    if not isinstance(data, dict):
        return None

    by_title = {s["title"].strip().lower(): s for s in sections}
    updated = False
    for item in data.get("sections") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        if not title or not body:
            continue
        section = by_title.get(title.lower())
        if section is None:
            continue
        # Never accept a Gemini cut that empties a previously substantive section.
        if count_words(body) < max(20, int(count_words(section.get("body") or "") * 0.45)):
            continue
        section["body"] = body
        updated = True

    if not updated:
        return None

    trimmed = render_structured_markdown(sections)
    trimmed_words = count_words(trimmed)
    # Must reduce length and not crash below the hard minimum.
    if trimmed_words >= total:
        return None
    if trimmed_words < spec.min_total_words:
        # Too aggressive — reject so caller can fall back to proportional clamp.
        return None
    return trimmed


def apply_trimmed_markdown_to_session(session: Any, trimmed_markdown: str) -> bool:
    """Write trimmed section bodies back onto a writer session. Returns True if any section changed."""
    by_title = {
        s["title"].strip().lower(): s["body"]
        for s in parse_markdown_sections(trimmed_markdown)
    }
    changed = False
    for section in session.sections:
        body = by_title.get((section.title or "").strip().lower())
        if body is None:
            continue
        if body.strip() == (section.generated_text or "").strip():
            continue
        section.generated_text = body.strip()
        section.warnings = list(section.warnings) + [
            "Gemini smart-trim applied to fit total word budget"
        ]
        changed = True
    return changed
