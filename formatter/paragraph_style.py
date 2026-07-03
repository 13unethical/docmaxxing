"""Apply paragraph/run formatting from profile specs."""

from __future__ import annotations

from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from formatter.style_engine import apply_paragraph_spec
from styles.profile import ParagraphFormatSpec


def heading_style_for_level(level: int) -> Optional[str]:
    """Map logical levels to Word built-in heading styles."""
    if level == 1:
        return "Heading 1"
    if level == 2:
        return "Heading 2"
    if level == 3:
        return "Heading 3"
    return None


def format_paragraph(
    paragraph,
    document: Document,
    *,
    spec: ParagraphFormatSpec,
    space_before_pt: int,
    space_after_pt: int,
    heading_level: int = 0,
) -> None:
    """Apply one paragraph's layout from an active formatting profile."""
    apply_paragraph_spec(
        paragraph,
        document,
        spec,
        space_before_pt=space_before_pt,
        space_after_pt=space_after_pt,
        heading_level=heading_level,
    )


def apply_font_to_runs(paragraph, font_name: str, font_size_pt: int) -> None:
    """Legacy helper — prefer profile-driven apply_paragraph_spec."""
    for run in paragraph.runs:
        run.font.name = font_name
        from docx.shared import Pt

        run.font.size = Pt(font_size_pt)
        run.font.bold = False
