"""Gemini smart trim — cut excess words with minimal damage to grade quality."""

from __future__ import annotations

import json
from typing import Any

from services.assignment_spec.models import AssignmentSpec
from services.assignment_spec.validate import (
    count_body_words,
    count_words,
    is_references_section_title,
    parse_markdown_sections,
    render_structured_markdown,
)
from services.humanizer_engine.heading_utils import join_body_and_references, split_off_references

_SYSTEM = """You trim an academic assignment BODY so its word count fits a hard budget.
Return ONLY JSON:
{
  "sections": [
    {"title": "Exact existing section title", "body": "Full trimmed body WITHOUT ## heading"}
  ],
  "words_removed_estimate": 0,
  "notes": ["what was cut"]
}

PRIORITY (highest first):
1. Preserve predicted grade / rubric coverage — prefer cuts that do NOT lower the mark at all.
2. If any cut is required, remove text that has the SMALLEST impact on assessment criteria.
3. Fit TOTAL body words inside [min_total, max_total] (References are excluded from this budget).

Rules:
- Keep the SAME section titles and order. Do not invent sections or new claims.
- Delete or lightly condense ONLY what is needed.
- Cut first: redundancy, repeated examples, filler hedges, ornate phrasing, duplicated transitions.
- NEVER remove or weaken:
  - required lecture/seminar references
  - mandatory comparisons / reflections / personal-major links
  - citations and evidence anchors
  - learning-outcome / rubric-critical claims
  - section structure and logical flow
- Do NOT trim or alter References / Bibliography / Works Cited (they are not in the payload).
- Do not add new text. Academic tone only. No meta notes.
"""


def gemini_trim_markdown_to_budget(
    content: str,
    *,
    spec: AssignmentSpec,
    current_words: int | None = None,
) -> str | None:
    """Ask Gemini to remove the minimum safe excess body words. Returns trimmed markdown or None."""
    from services.assignment_llm import (
        STAGE_REVISION,
        assignment_generate_json,
        assignment_llm_configured,
    )

    if not assignment_llm_configured(STAGE_REVISION):
        return None

    body, refs = split_off_references(content or "")
    total = int(current_words if current_words is not None else count_body_words(body))
    if total <= spec.max_total_words:
        return content

    excess = total - spec.max_total_words
    prefer_remove = max(excess, total - spec.total_word_target)
    sections = [
        s
        for s in parse_markdown_sections(body)
        if not is_references_section_title(s.get("title") or "")
    ]
    payload = {
        "task": "trim_to_word_budget_preserve_grade",
        "current_body_words": total,
        "min_total": spec.min_total_words,
        "max_total": spec.max_total_words,
        "target_words": spec.total_word_target,
        "minimum_words_to_remove": excess,
        "preferred_words_to_remove": prefer_remove,
        "priority": (
            "Minimize grade impact first; ideally keep predicted grade unchanged. "
            "Only then minimize words removed."
        ),
        "constraints": {
            "mandatory_content_rules": spec.mandatory_content_rules,
            "required_lecture_seminar_refs": spec.required_lecture_seminar_refs,
            "mandatory_reflections": spec.mandatory_reflections,
            "mandatory_comparisons": spec.mandatory_comparisons,
            "learning_outcomes": spec.learning_outcomes,
            "forbidden_content": spec.forbidden_content,
            "section_word_targets": spec.section_word_targets,
            "rubric_criteria": [c.to_dict() for c in (spec.rubric_criteria or [])][:12],
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
        body_text = str(item.get("body") or "").strip()
        if not title or not body_text:
            continue
        if is_references_section_title(title):
            continue
        section = by_title.get(title.lower())
        if section is None:
            continue
        # Never accept a Gemini cut that empties a previously substantive section.
        if count_words(body_text) < max(20, int(count_words(section.get("body") or "") * 0.45)):
            continue
        section["body"] = body_text
        updated = True

    if not updated:
        return None

    trimmed_body = render_structured_markdown(sections)
    trimmed_words = count_body_words(trimmed_body)
    if trimmed_words >= total:
        return None
    if trimmed_words < spec.min_total_words:
        return None
    return join_body_and_references(trimmed_body, refs)


def clamp_markdown_body_to_budget(content: str, *, max_body_words: int) -> str:
    """Deterministic proportional trim of non-reference sections (never raises)."""
    if max_body_words <= 0:
        return content or ""
    body, refs = split_off_references(content or "")
    sections = parse_markdown_sections(body)
    writable = [
        s
        for s in sections
        if (s.get("body") or "").strip()
        and (s.get("title") or "") not in {"Preamble", "Document"}
        and not is_references_section_title(s.get("title") or "")
    ]
    current = count_body_words(render_structured_markdown(sections) if sections else body)
    if current <= max_body_words:
        return content or ""

    # Reserve heading tokens counted by count_body_words so the final total lands in-band.
    heading_overhead = sum(count_words(s.get("title") or "") for s in writable)
    body_budget = max(1, max_body_words - heading_overhead)
    body_current = sum(count_words(s.get("body") or "") for s in writable) or 1
    remaining = body_budget
    for index, section in enumerate(writable):
        words = (section.get("body") or "").split()
        share = int(round(body_budget * (len(words) / body_current))) if body_current else 1
        if index == len(writable) - 1:
            share = remaining
        share = max(1, share)
        remaining = max(0, remaining - share)
        if len(words) <= share:
            continue
        trimmed = " ".join(words[:share]).rstrip(" ,;:")
        if trimmed and trimmed[-1] not in ".!?":
            trimmed += "."
        section["body"] = trimmed

    fitted = join_body_and_references(render_structured_markdown(sections), refs)
    # Final safety: if still slightly over (punctuation/rounding), peel from last writable.
    while count_body_words(fitted) > max_body_words and writable:
        last = writable[-1]
        words = (last.get("body") or "").split()
        if len(words) <= 1:
            break
        last["body"] = " ".join(words[:-1]).rstrip(" ,;:")
        if last["body"] and last["body"][-1] not in ".!?":
            last["body"] += "."
        fitted = join_body_and_references(render_structured_markdown(sections), refs)
    return fitted


def fit_content_to_word_budget(
    content: str,
    *,
    spec: AssignmentSpec,
) -> tuple[str, dict[str, Any]]:
    """Ensure body words fit ±10% band. Soft: never raises; prefers grade-safe Gemini trim."""
    meta: dict[str, Any] = {"trimmed": False, "method": None}
    body_words = count_body_words(content or "")
    if not spec.total_word_target or body_words <= spec.max_total_words:
        meta["body_words"] = body_words
        return content or "", meta

    trimmed = gemini_trim_markdown_to_budget(content, spec=spec, current_words=body_words)
    if trimmed:
        after = count_body_words(trimmed)
        if after <= spec.max_total_words and after >= spec.min_total_words:
            meta.update({"trimmed": True, "method": "gemini_grade_safe", "body_words": after})
            return trimmed, meta
        if after < body_words:
            content = trimmed
            body_words = after

    if body_words > spec.max_total_words:
        clamped = clamp_markdown_body_to_budget(content, max_body_words=spec.max_total_words)
        meta.update(
            {
                "trimmed": True,
                "method": "proportional_clamp",
                "body_words": count_body_words(clamped),
            }
        )
        return clamped, meta

    meta["body_words"] = body_words
    return content or "", meta


def apply_trimmed_markdown_to_session(session: Any, trimmed_markdown: str) -> bool:
    """Write trimmed section bodies back onto a writer session. Returns True if any section changed."""
    body, _refs = split_off_references(trimmed_markdown)
    by_title = {
        s["title"].strip().lower(): s["body"]
        for s in parse_markdown_sections(body)
    }
    changed = False
    for section in session.sections:
        if is_references_section_title(section.title or ""):
            continue
        body_text = by_title.get((section.title or "").strip().lower())
        if body_text is None:
            continue
        if body_text.strip() == (section.generated_text or "").strip():
            continue
        section.generated_text = body_text.strip()
        section.warnings = list(section.warnings) + [
            "Gemini smart-trim applied to fit total word budget"
        ]
        changed = True
    return changed
