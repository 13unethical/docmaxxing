"""
High-level formatting pipeline: margins → page numbers → per-paragraph layout.

Keeps responsibilities split so each module stays small and test-friendly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph

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
    split_embedded_heading_paragraph,
)
from formatter.layout import apply_margin_preset
from formatter.page_numbers import apply_page_numbers_to_document
from formatter.paragraph_style import format_paragraph
from formatter.requirement_headings import expand_requirement_heading_paragraphs, normalize_document_internal_spaces

logger = logging.getLogger(__name__)


@dataclass
class FormatJob:
    """Options coming from the HTTP form (already validated)."""

    font_family: str
    font_size_pt: int
    line_spacing: float
    alignment: str  # "left" | "justify"
    first_line_indent: bool
    space_before_pt: int
    space_after_pt: int
    margin_preset: str
    page_number_position: str
    auto_headings: bool
    heading_all_caps: bool
    auto_justify_refs: bool
    requirement_headings: bool = False
    heading_size_pt: int = 16


def _expand_embedded_heading_paragraphs(document: Document) -> None:
    """Split paragraphs that combine a heading line and body on separate lines."""
    idx = 0
    while idx < len(document.paragraphs):
        paragraph = document.paragraphs[idx]
        heading, body = split_embedded_heading_paragraph(paragraph.text)
        if body is not None:
            paragraph.text = heading
            new_el = OxmlElement("w:p")
            paragraph._p.addnext(new_el)
            new_paragraph = Paragraph(new_el, paragraph._parent)
            new_paragraph.add_run(body)
        idx += 1


def format_document_full(
    document: Document,
    job: FormatJob,
    paragraph_assignments: list[ParagraphHeadingAssignment] | None = None,
    *,
    structure_debug: bool = False,
    recovery_mode: str = "",
    ai_powered: bool = False,
    required_sections: list[str] | None = None,
) -> StructureRecoveryDebugReport | None:
    apply_margin_preset(document, job.margin_preset)
    apply_page_numbers_to_document(document, job.page_number_position)

    default_align = (
        WD_ALIGN_PARAGRAPH.JUSTIFY if job.alignment == "justify" else WD_ALIGN_PARAGRAPH.LEFT
    )
    indent_body = 0.5 if job.first_line_indent else None

    in_refs_section = False
    seen_nonempty_paragraph = False
    debug_report = StructureRecoveryDebugReport(
        recovery_mode=recovery_mode,
        ai_powered=ai_powered,
    )

    normalize_document_internal_spaces(document)

    section_labels = list(required_sections or [])
    if section_labels and job.requirement_headings and not paragraph_assignments:
        expand_requirement_heading_paragraphs(document, section_labels)
    elif job.auto_headings and not paragraph_assignments:
        _expand_embedded_heading_paragraphs(document)

    req_label_set = frozenset(s.lower() for s in section_labels) if section_labels else None

    for idx, paragraph in enumerate(document.paragraphs):
        text = paragraph.text
        stripped = text.strip()
        is_first_nonempty = bool(stripped) and not seen_nonempty_paragraph
        if stripped:
            seen_nonempty_paragraph = True

        refs_title = is_references_heading(text)
        if refs_title:
            in_refs_section = True

        assignment = None
        if paragraph_assignments and idx < len(paragraph_assignments):
            assignment = paragraph_assignments[idx]

        word_style_level = heading_level_from_word_style(paragraph)

        heuristic_level = 0
        if assignment is None or not assignment.is_ai_locked:
            heuristic_level = detect_heading_level(
                text,
                job.auto_headings or job.requirement_headings,
                is_first_nonempty=is_first_nonempty,
                requirement_labels=req_label_set,
            )

        level, source_used, recovered_level = resolve_paragraph_heading_level(
            assignment=assignment,
            word_style_level=word_style_level,
            heuristic_level=heuristic_level,
            auto_headings=job.auto_headings or job.requirement_headings,
        )

        if level > 0:
            diag = HeadingApplyDiagnostic(
                paragraph=stripped[:200],
                source=source_used,
                level=level,
                recovered_level=recovered_level,
                applied_style=applied_style_name(level),
                confidence=assignment.confidence if assignment and source_used == "ai" else None,
            )
            debug_report.headings.append(diag)
            payload = diag.to_dict()
            logger.info("Structure recovery heading: %s", payload)
            if structure_debug:
                print(payload)

        apply_heading_caps(paragraph, job.heading_all_caps, level)

        align = default_align
        if job.auto_justify_refs and in_refs_section and level == 0 and not refs_title:
            align = WD_ALIGN_PARAGRAPH.JUSTIFY

        format_paragraph(
            paragraph,
            document,
            font_name=job.font_family,
            font_size_pt=job.font_size_pt,
            line_spacing=job.line_spacing,
            alignment=align,
            first_line_indent_inches=indent_body if level == 0 else None,
            space_before_pt=job.space_before_pt,
            space_after_pt=job.space_after_pt,
            heading_level=level,
            heading_size_pt=job.heading_size_pt,
        )

    if structure_debug and debug_report.headings:
        print(
            "Structure Recovery Debug:",
            debug_report.to_dict(),
        )

    return debug_report if structure_debug else None
