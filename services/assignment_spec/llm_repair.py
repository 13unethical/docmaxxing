"""Optional LLM repair pass to raise rubric coverage while preserving structure."""

from __future__ import annotations

import json
from typing import Any

from services.assignment_spec.models import AssignmentSpec
from services.assignment_spec.validate import count_words, parse_markdown_sections, render_structured_markdown

_SYSTEM = """You repair an academic assignment draft to maximize grading-rubric coverage.
Return ONLY JSON:
{
  "sections": [
    {"title": "Exact existing section title", "body": "Full revised body without ## heading"}
  ],
  "changes": ["..."]
}
Rules:
- Keep the SAME section titles and order. Do not invent new sections.
- Preserve hard word budgets: each body must stay within ±10% of target_words when provided.
- Maximize coverage of weak rubric criteria and learning outcomes.
- Add explicit lecture/seminar references where required.
- Strengthen reflection / comparison / entrepreneurial perspective when listed in repairs.
- Academic tone only. No meta notes like [Revision: ...].
"""


def llm_rubric_repair(content: str, spec: AssignmentSpec, repairs: list[str]) -> str:
    """Best-effort LLM repair. Falls back by raising if LLM unavailable/unusable."""
    from services.assignment_llm import (
        STAGE_REVISION,
        assignment_generate_json,
        assignment_llm_configured,
    )

    if not assignment_llm_configured(STAGE_REVISION):
        raise RuntimeError("LLM repair unavailable")

    sections = parse_markdown_sections(content)
    payload = {
        "repairs": repairs,
        "assignment_spec": {
            "title": spec.title,
            "total_word_target": spec.total_word_target,
            "section_word_targets": spec.section_word_targets,
            "learning_outcomes": spec.learning_outcomes,
            "rubric_criteria": [c.to_dict() for c in spec.rubric_criteria],
            "mandatory_content_rules": spec.mandatory_content_rules,
            "required_lecture_seminar_refs": spec.required_lecture_seminar_refs,
            "mandatory_reflections": spec.mandatory_reflections,
            "mandatory_comparisons": spec.mandatory_comparisons,
            "forbidden_content": spec.forbidden_content,
            "min_rubric_coverage": spec.min_rubric_coverage,
        },
        "sections": [
            {
                "title": s["title"],
                "body": s["body"],
                "target_words": (spec.section_by_title(s["title"]).target_words if spec.section_by_title(s["title"]) else 0),
            }
            for s in sections
            if s["title"] not in {"Preamble", "Document"}
        ],
    }
    data, _meta = assignment_generate_json(
        system_prompt=_SYSTEM,
        user_prompt=json.dumps(payload, ensure_ascii=False, indent=2),
        temperature=0.2,
        max_retries=1,
        stage=STAGE_REVISION,
    )
    if not isinstance(data, dict):
        raise RuntimeError("LLM repair returned non-object")

    by_title = {s["title"].strip().lower(): s for s in sections}
    updated = False
    for item in data.get("sections") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        if not title or not body:
            continue
        key = title.lower()
        if key not in by_title:
            continue
        target = spec.section_by_title(title)
        target_words = target.target_words if target else 0
        if target_words > 0 and count_words(body) < int(target_words * 0.9):
            # Reject under-length LLM repair for this section.
            continue
        by_title[key]["body"] = body
        updated = True
    if not updated:
        raise RuntimeError("LLM repair made no valid section updates")
    return render_structured_markdown(sections)
