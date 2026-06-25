"""
Append a References block to an already formatted document and style new paragraphs.
"""

from __future__ import annotations

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from formatter.headings import (
    apply_heading_caps,
    detect_heading_level,
    is_references_heading,
)
from formatter.paragraph_style import format_paragraph
from formatter.pipeline import FormatJob


def append_references_section(
    document: Document,
    job: FormatJob,
    citations: list[str],
    *,
    section_title: str = "References",
) -> None:
    """
    Add a blank line, a section heading (References / Works Cited / …), then one paragraph per citation.
    Applies the same heading/body rules as the main pipeline for these paragraphs only.
    """
    cleaned = [c.strip() for c in citations if c and str(c).strip()]
    if not cleaned:
        return

    heading = (section_title or "References").strip() or "References"
    n_before = len(document.paragraphs)
    document.add_paragraph("")
    document.add_paragraph(heading)
    for c in cleaned:
        document.add_paragraph(c)

    default_align = (
        WD_ALIGN_PARAGRAPH.JUSTIFY if job.alignment == "justify" else WD_ALIGN_PARAGRAPH.LEFT
    )
    indent_body = 0.5 if job.first_line_indent else None
    in_refs_section = False

    for paragraph in document.paragraphs[n_before:]:
        text = paragraph.text
        refs_title = is_references_heading(text)
        if refs_title:
            in_refs_section = True

        level = detect_heading_level(text, job.auto_headings, is_first_nonempty=False)
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
        )
