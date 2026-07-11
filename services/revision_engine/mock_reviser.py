"""Mock Section Reviser — targeted fixes only, never full rewrite."""

from __future__ import annotations

import copy
import uuid
from typing import Any, Protocol

from services.assignment_pipeline.models import utc_now
from services.revision_engine.models import RevisionEngineInput, RevisionResult, SectionRevision
from services.revision_engine.section_parser import (
    ensure_actionable_sections,
    find_section_index,
    parse_sections,
    render_sections,
    section_titles,
)
from services.writer_engine.models import count_words


class SectionReviser(Protocol):
    def revise(self, payload: RevisionEngineInput) -> RevisionResult:
        ...


class MockSectionReviser:
    VERSION = "mock-1.0"

    def revise(self, payload: RevisionEngineInput) -> RevisionResult:
        draft = copy.deepcopy(payload.draft)
        report = payload.review_report
        issues = list(report.get("issues") or [])
        if not issues:
            raise ValueError("Review report has no issues to fix")

        sections = ensure_actionable_sections(str(draft.get("content") or ""), payload.blueprint)
        blueprint_titles = section_titles(payload.blueprint)
        sections_revised: list[SectionRevision] = []
        changes: list[str] = []
        issues_addressed: list[str] = []

        for issue in issues:
            issue_id = str(issue.get("issue_id") or "")
            section_name = str(issue.get("section") or "")
            category = str(issue.get("category") or "")
            suggested_fix = str(issue.get("suggested_fix") or "")
            index = _resolve_issue_section_index(
                sections,
                section_name=section_name,
                category=category,
                blueprint_titles=blueprint_titles,
            )
            if index is None:
                continue

            original_body = sections[index]["body"]
            revised_body, change_description = _apply_targeted_fix(
                section_title=sections[index]["title"],
                body=original_body,
                issue=issue,
                suggested_fix=suggested_fix,
            )
            if revised_body == original_body and suggested_fix:
                revised_body = original_body.strip() + f"\n\n[Revision: {suggested_fix}]"
                change_description = f"Applied fix in {sections[index]['title']}"

            if revised_body == original_body:
                continue

            sections[index]["body"] = revised_body
            sections_revised.append(
                SectionRevision(
                    issue_id=issue_id,
                    section=sections[index]["title"],
                    category=category,
                    change_description=change_description,
                )
            )
            changes.append(change_description)
            issues_addressed.append(issue_id)

        if not sections_revised:
            fallback_index = _fallback_section_index(sections)
            if fallback_index is not None and issues:
                issue = issues[0]
                suggested_fix = str(issue.get("suggested_fix") or issue.get("description") or "Address review feedback.")
                sections[fallback_index]["body"] = (
                    sections[fallback_index]["body"].strip() + f"\n\n[Revision: {suggested_fix}]"
                )
                sections_revised.append(
                    SectionRevision(
                        issue_id=str(issue.get("issue_id") or ""),
                        section=sections[fallback_index]["title"],
                        category=str(issue.get("category") or ""),
                        change_description=f"Applied fallback fix in {sections[fallback_index]['title']}",
                    )
                )
                changes.append(sections_revised[-1].change_description)
                issues_addressed.append(str(issue.get("issue_id") or ""))

        if not sections_revised:
            raise ValueError("No affected sections could be located for revision")

        new_content = render_sections(sections)
        previous_version = int(draft.get("version") or 1)
        new_version = previous_version + 1

        draft.update(
            {
                "id": str(uuid.uuid4()),
                "content": new_content,
                "total_words": count_words(new_content),
                "version": new_version,
                "created_at": utc_now().isoformat(),
            }
        )

        return RevisionResult(
            id=str(uuid.uuid4()),
            project_id=payload.project_id,
            draft=draft,
            previous_version=previous_version,
            new_version=new_version,
            changes=changes,
            sections_revised=sections_revised,
            issues_addressed=issues_addressed,
            attempt_number=0,
            engine_version=self.VERSION,
            revised_at=utc_now(),
        )


def _apply_targeted_fix(
    *,
    section_title: str,
    body: str,
    issue: dict[str, Any],
    suggested_fix: str,
) -> tuple[str, str]:
    category = str(issue.get("category") or "").lower()
    issue_id = str(issue.get("issue_id") or "")

    if "critical" in category or issue_id == "issue-critical-analysis-1":
        addition = (
            "\n\nComparative evaluation: Competing theories are weighed directly. "
            "Theory A emphasises structural constraints, whereas Theory B foregrounds agency. "
            "This comparison clarifies which explanation better fits the evidence."
        )
        if "comparison" not in body.lower():
            return body.strip() + addition, f"Added comparison in {section_title}"

    if "counter" in category or issue_id == "issue-counterargument-1":
        addition = (
            "\n\nCounterargument: An alternative reading suggests limited generalisability. "
            "However, the weight of peer-reviewed evidence supports the primary argument after rebuttal."
        )
        if "counterargument" not in body.lower():
            return body.strip() + addition, f"Added counterargument evaluation in {section_title}"

    if "evidence" in category or issue_id == "issue-evidence-1":
        addition = (
            "\n\nAdditional academic references strengthen thematic balance: "
            "(Smith, 2021; Patel, 2022)."
        )
        if "smith" not in body.lower():
            return body.strip() + addition, f"Added 2 academic references in {section_title}"

    if "conclusion" in category.lower() or "conclusion" in section_title.lower():
        addition = "\n\nThe conclusion now explicitly resolves the research question with synthesised implications."
        if "resolves" not in body.lower():
            return body.strip() + addition, f"Improved conclusion in {section_title}"

    if suggested_fix:
        return body.strip() + f"\n\n[Revision: {suggested_fix}]", f"Applied fix in {section_title}"

    return body, ""


def _resolve_issue_section_index(
    sections: list[dict[str, str]],
    *,
    section_name: str,
    category: str,
    blueprint_titles: list[str],
) -> int | None:
    index = find_section_index(sections, section_name)
    if index is not None:
        return index
    for title in blueprint_titles:
        index = find_section_index(sections, title)
        if index is not None:
            return index
    return find_section_index(sections, category)


def _fallback_section_index(sections: list[dict[str, str]]) -> int | None:
    best_index: int | None = None
    best_words = 0
    for index, section in enumerate(sections):
        words = len(section.get("body", "").split())
        if words > best_words:
            best_words = words
            best_index = index
    if best_index is not None:
        return best_index
    return 0 if sections else None
