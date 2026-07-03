"""
High-level formatting pipeline: margins → page numbers → per-paragraph layout.

Structure is reconstructed before this module runs. All visual rules come from
the active FormattingProfile via the style engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from docx import Document
from docx.text.paragraph import Paragraph

from formatter.format_job import FormatJob
from formatter.heading_plan import (
    HeadingApplyDiagnostic,
    ParagraphHeadingAssignment,
    StructureRecoveryDebugReport,
    applied_style_name,
    resolve_paragraph_heading_level,
)
from formatter.headings import (
    apply_heading_caps,
    detect_heading_level,
    heading_level_from_word_style,
    is_references_heading,
)
from formatter.paragraph_style import format_paragraph
from formatter.requirement_headings import normalize_document_internal_spaces
from formatter.markdown_cleanup import clean_markdown_in_document
from formatter.style_engine import (
    apply_page_style,
    resolve_active_profile,
    resolve_contextual_spacing,
    role_for_paragraph,
    validate_and_correct_document,
)
from formatter.page_numbers import apply_page_numbers_to_document

logger = logging.getLogger(__name__)

__all__ = ["FormatJob", "format_document_full"]


def format_document_full(
    document: Document,
    job: FormatJob,
    paragraph_assignments: list[ParagraphHeadingAssignment] | None = None,
    *,
    structure_debug: bool = False,
    recovery_mode: str = "",
    ai_powered: bool = False,
) -> StructureRecoveryDebugReport | None:
    profile = resolve_active_profile(job)
    apply_page_style(document, profile.page)
    apply_page_numbers_to_document(document, profile.page.page_number_position)

    debug_report = StructureRecoveryDebugReport(
        recovery_mode=recovery_mode,
        ai_powered=ai_powered,
    )

    normalize_document_internal_spaces(document)
    clean_markdown_in_document(document)

    @dataclass
    class _ParaPlan:
        paragraph: Paragraph
        level: int
        stripped: str
        source_used: str
        recovered_level: int | None
        assignment: ParagraphHeadingAssignment | None

    plans: list[_ParaPlan] = []
    seen_nonempty_paragraph = False
    for idx, paragraph in enumerate(document.paragraphs):
        text = paragraph.text
        stripped = text.strip()
        is_first_nonempty = bool(stripped) and not seen_nonempty_paragraph
        if stripped:
            seen_nonempty_paragraph = True

        assignment = None
        if paragraph_assignments and idx < len(paragraph_assignments):
            assignment = paragraph_assignments[idx]

        word_style_level = heading_level_from_word_style(paragraph)

        heuristic_level = 0
        if assignment is None or not assignment.is_structure_locked:
            heuristic_level = detect_heading_level(
                text,
                job.auto_headings or job.requirement_headings,
                is_first_nonempty=is_first_nonempty,
                requirement_labels=None,
            )

        level, source_used, recovered_level = resolve_paragraph_heading_level(
            assignment=assignment,
            word_style_level=word_style_level,
            heuristic_level=heuristic_level,
            auto_headings=job.auto_headings or job.requirement_headings,
        )
        plans.append(
            _ParaPlan(
                paragraph=paragraph,
                level=level,
                stripped=stripped,
                source_used=source_used,
                recovered_level=recovered_level,
                assignment=assignment,
            )
        )

    in_refs_section = False
    for idx, plan in enumerate(plans):
        paragraph = plan.paragraph
        level = plan.level
        stripped = plan.stripped
        text = paragraph.text
        prev_level = plans[idx - 1].level if idx > 0 else 0
        next_level = plans[idx + 1].level if idx + 1 < len(plans) else 0
        prev_has_text = bool(plans[idx - 1].stripped) if idx > 0 else False

        refs_title = is_references_heading(text)
        if refs_title:
            in_refs_section = True

        if level > 0:
            diag = HeadingApplyDiagnostic(
                paragraph=stripped[:200],
                source=plan.source_used,
                level=level,
                recovered_level=plan.recovered_level,
                applied_style=applied_style_name(level),
                confidence=(
                    plan.assignment.confidence
                    if plan.assignment and plan.source_used == "ai"
                    else None
                ),
            )
            debug_report.headings.append(diag)
            payload = diag.to_dict()
            logger.info("Structure recovery heading: %s", payload)
            if structure_debug:
                print(payload)

        apply_heading_caps(paragraph, job.heading_all_caps, level)

        role = role_for_paragraph(
            level=level,
            in_refs_section=in_refs_section,
            is_refs_title=refs_title,
        )
        spec = profile.paragraph_spec_for_role(role)
        space_before_pt, space_after_pt = resolve_contextual_spacing(
            profile,
            role=role,
            prev_level=prev_level,
            next_level=next_level,
            prev_has_text=prev_has_text,
        )

        format_paragraph(
            paragraph,
            document,
            spec=spec,
            space_before_pt=space_before_pt,
            space_after_pt=space_after_pt,
            heading_level=level,
        )

    validate_and_correct_document(document, profile, plans)

    if structure_debug and debug_report.headings:
        print(
            "Structure Recovery Debug:",
            debug_report.to_dict(),
        )

    return debug_report if structure_debug else None
