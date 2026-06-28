"""Apply paragraph/run formatting: font, spacing, alignment, indent, Word heading styles."""

from __future__ import annotations

from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_UNDERLINE
from docx.shared import Inches, Pt, RGBColor


def _set_line_spacing(paragraph_format, multiple: float) -> None:
    """Map friendly multipliers to Word line-spacing rules."""
    if abs(multiple - 1.0) < 0.001:
        paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        paragraph_format.line_spacing = None
    elif abs(multiple - 2.0) < 0.001:
        paragraph_format.line_spacing_rule = WD_LINE_SPACING.DOUBLE
        paragraph_format.line_spacing = None
    else:
        paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        paragraph_format.line_spacing = multiple


def apply_font_to_runs(paragraph, font_name: str, font_size_pt: int) -> None:
    """Font name/size apply to every run (headings + body)."""
    for run in paragraph.runs:
        run.font.name = font_name
        run.font.size = Pt(font_size_pt)
        run.font.bold = False


def heading_style_for_level(level: int) -> Optional[str]:
    """Map logical levels to Word built-in heading styles (title = Heading 1)."""
    if level == 1:
        return "Heading 1"
    if level == 2:
        return "Heading 2"
    if level == 3:
        return "Heading 3"
    return None


# All detected headings share one academic style (left-aligned bold section title).
ACADEMIC_HEADING_PT = 16
_HEADING_RGB = RGBColor(0x00, 0x00, 0x00)


def _apply_academic_heading_runs(paragraph, font_name: str, size_pt: int) -> None:
    """Bold black text, no underline — overrides theme/link-like heading colors."""
    if not paragraph.runs and paragraph.text:
        paragraph.add_run(paragraph.text)
    for run in paragraph.runs:
        run.font.name = font_name
        run.font.size = Pt(size_pt)
        run.font.bold = True
        run.font.color.rgb = _HEADING_RGB
        run.font.underline = WD_UNDERLINE.NONE


def format_paragraph(
    paragraph,
    document: Document,
    *,
    font_name: str,
    font_size_pt: int,
    line_spacing: float,
    alignment: WD_ALIGN_PARAGRAPH,
    first_line_indent_inches: Optional[float],
    space_before_pt: int,
    space_after_pt: int,
    heading_level: int,
    heading_size_pt: int = ACADEMIC_HEADING_PT,
) -> None:
    """
    One paragraph’s layout + fonts.

    Body paragraphs honor the first-line indent toggle; detected headings use
    built-in Word styles and skip synthetic first-line indents so titles stay clean.
    """
    style_name = heading_style_for_level(heading_level)
    if style_name:
        try:
            paragraph.style = document.styles[style_name]
        except KeyError:
            # Rare templates might omit a built-in mapping
            pass

    pf = paragraph.paragraph_format
    _set_line_spacing(pf, line_spacing)
    if heading_level > 0:
        pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    else:
        pf.alignment = alignment
    pf.space_before = Pt(space_before_pt)
    pf.space_after = Pt(space_after_pt)

    if heading_level == 0:
        if first_line_indent_inches is not None:
            pf.first_line_indent = Inches(first_line_indent_inches)
        else:
            pf.first_line_indent = None
    else:
        pf.first_line_indent = None

    if heading_level == 0:
        apply_font_to_runs(paragraph, font_name, font_size_pt)
    else:
        _apply_academic_heading_runs(paragraph, font_name, heading_size_pt)
