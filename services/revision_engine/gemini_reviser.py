"""Gemini-backed section reviser driven by academic review issues."""

from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any

from services.assignment_llm import (
    STAGE_REVISION,
    assignment_generate_json,
    assignment_llm_configured,
    assignment_llm_model,
)
from services.assignment_pipeline.models import utc_now
from services.revision_engine.mock_reviser import MockSectionReviser
from services.revision_engine.models import RevisionEngineInput, RevisionResult, SectionRevision
from services.assignment_spec.builder import build_assignment_spec
from services.assignment_spec.validate import needs_expansion, section_bounds
from services.revision_engine.section_parser import ensure_actionable_sections, render_sections
from services.writer_engine.models import count_words

_SYSTEM = """You revise academic draft sections to address review issues.
Return ONLY valid JSON:
{
  "sections": [
    {"title": "Exact section title", "body": "Full revised section body without the ## heading", "change_description": "...", "issue_ids": ["..."]}
  ],
  "issues_addressed": ["issue_id", ...]
}
Rules:
- Only revise sections that have issues.
- Preserve academic tone; do not rewrite the entire document.
- Keep markdown paragraphs; do not include the ## heading line in body.
- Every returned title must match an existing section title exactly.
- Never insert meta notes like [Revision: ...] into the body — apply the fix in the prose itself.
- HARD WORD BUDGET: each revised body MUST stay within ±10% of that section's target_words from requirement_json.section_word_budgets / blueprint estimated_words. Do NOT shorten a section below its minimum. If removing redundancy, REPLACE cut text with additional analysis/evidence so length is preserved.
- Prefer clarity over deletion. Condensing is allowed only when the section remains at or above its minimum word target.
- If issues mention citation style: convert square-bracket citations like [Author, Year] to (Author, Year).
"""


def _strip_revision_meta(text: str) -> str:
    """Remove instructional revision markers that must never ship in student drafts."""
    cleaned = re.sub(r"\n*\s*\[Revision:[^\]]*\]\s*", "\n\n", text or "", flags=re.I)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _resolve_section_index(by_title: dict[str, int], title: str, sections: list[dict[str, str]]) -> int | None:
    key = (title or "").strip().lower()
    if not key:
        return None
    if key in by_title:
        return by_title[key]
    # Fuzzy: "Body paragraph 1" vs "Body Paragraphs" / partial contains
    for candidate, index in by_title.items():
        if key in candidate or candidate in key:
            return index
    # Global labels from reviewers → first substantial body-like section
    if key in {"overall", "throughout", "document", "essay", "whole document", "all sections"}:
        for index, section in enumerate(sections):
            t = section["title"].strip().lower()
            if t not in {"preamble", "references", "reference list", "bibliography"}:
                return index
    if "body" in key:
        for index, section in enumerate(sections):
            if "body" in section["title"].strip().lower():
                return index
    return None


class GeminiSectionReviser:
    VERSION = f"gemini-{assignment_llm_model(STAGE_REVISION)}"

    def __init__(self, *, fallback: MockSectionReviser | None = None) -> None:
        self._fallback = fallback or MockSectionReviser()

    def revise(self, payload: RevisionEngineInput) -> RevisionResult:
        issues = list((payload.review_report or {}).get("issues") or [])
        if not issues:
            raise ValueError("Review report has no issues to fix")
        if not assignment_llm_configured(STAGE_REVISION):
            return self._fallback.revise(payload)

        sections = ensure_actionable_sections(str(payload.draft.get("content") or ""), payload.blueprint)
        exact_titles = [s["title"] for s in sections]
        targets = _section_targets(payload)
        user_prompt = json.dumps(
            {
                "issues": issues,
                "requirement_json": payload.requirement_json,
                "section_word_targets": targets,
                "exact_section_titles": exact_titles,
                "sections": [
                    {
                        "title": s["title"],
                        "body": s["body"],
                        "target_words": targets.get(s["title"].strip().lower(), 0),
                        "min_words": section_bounds(targets.get(s["title"].strip().lower(), 0))[0],
                    }
                    for s in sections
                ],
                "instructions": (
                    "Return revised sections using ONLY titles from exact_section_titles. "
                    "When an issue says Overall/Throughout, revise every body section that needs the fix. "
                    "Each revised body must remain at or above min_words."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        data, _meta = assignment_generate_json(
            system_prompt=_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.2,
            max_retries=2,
            stage=STAGE_REVISION,
        )
        if not isinstance(data, dict):
            return self._fallback.revise(payload)

        by_title = {s["title"].strip().lower(): i for i, s in enumerate(sections)}
        sections_revised: list[SectionRevision] = []
        changes: list[str] = []
        issues_addressed: list[str] = []

        for item in data.get("sections") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            body = str(item.get("body") or "").strip()
            if not title or not body:
                continue
            index = _resolve_section_index(by_title, title, sections)
            if index is None:
                continue
            matched_title = sections[index]["title"]
            original_body = sections[index]["body"].strip()
            if body == original_body:
                continue
            cleaned = _strip_revision_meta(body)
            target = targets.get(matched_title.strip().lower(), 0)
            if target and needs_expansion(count_words(cleaned), target):
                # Reject under-length revisions — keep original body to protect word budget.
                changes.append(
                    f"Rejected under-length revision for {matched_title} "
                    f"({count_words(cleaned)}/{target}); kept original length"
                )
                continue
            sections[index]["body"] = cleaned
            issue_ids = [str(x) for x in (item.get("issue_ids") or []) if str(x).strip()]
            change = str(item.get("change_description") or f"Revised {matched_title}")
            for issue_id in issue_ids or [""]:
                sections_revised.append(
                    SectionRevision(
                        issue_id=issue_id,
                        section=matched_title,
                        category="gemini_revision",
                        change_description=change,
                    )
                )
            changes.append(change)
            issues_addressed.extend(issue_ids)

        if not sections_revised:
            # Do not fall back to mock marker injection — leave draft unchanged.
            draft = copy.deepcopy(payload.draft)
            previous_version = int(draft.get("version") or 1)
            return RevisionResult(
                id=str(uuid.uuid4()),
                project_id=payload.project_id,
                draft=draft,
                previous_version=previous_version,
                new_version=previous_version,
                sections_revised=[],
                changes=["Gemini returned no matching section revisions; draft left unchanged"],
                issues_addressed=[],
                attempt_number=1,
                engine_version=f"{self.VERSION}+noop",
                revised_at=utc_now(),
            )

        for issue_id in data.get("issues_addressed") or []:
            value = str(issue_id).strip()
            if value and value not in issues_addressed:
                issues_addressed.append(value)

        draft = copy.deepcopy(payload.draft)
        new_content = _strip_revision_meta(render_sections(sections))
        previous_version = int(draft.get("version") or 1)
        draft.update(
            {
                "id": str(uuid.uuid4()),
                "content": new_content,
                "total_words": count_words(new_content),
                "version": previous_version + 1,
                "created_at": utc_now().isoformat(),
            }
        )
        return RevisionResult(
            id=str(uuid.uuid4()),
            project_id=payload.project_id,
            draft=draft,
            previous_version=previous_version,
            new_version=previous_version + 1,
            sections_revised=sections_revised,
            changes=changes,
            issues_addressed=issues_addressed,
            attempt_number=1,
            engine_version=self.VERSION,
            revised_at=utc_now(),
        )


def _section_targets(payload: RevisionEngineInput) -> dict[str, int]:
    """Resolve per-section word targets from AssignmentSpec / requirement / blueprint."""
    targets: dict[str, int] = {}
    try:
        spec = build_assignment_spec(payload.requirement_json or {}, project_id=payload.project_id)
        for section in spec.writable_sections:
            targets[section.title.strip().lower()] = int(section.target_words)
    except Exception:  # noqa: BLE001
        pass
    budgets = dict((payload.requirement_json or {}).get("section_word_budgets") or {})
    for title, words in budgets.items():
        key = str(title).strip().lower()
        if key and int(words) > 0:
            targets.setdefault(key, int(words))
    for item in (payload.blueprint or {}).get("sections") or []:
        title = str(item.get("title") or "").strip().lower()
        words = int(item.get("estimated_words") or 0)
        if title and words > 0:
            targets.setdefault(title, words)
    return targets
