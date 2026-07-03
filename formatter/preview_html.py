"""Server-side formatted preview HTML — same pipeline as /api/format (without file output)."""

from __future__ import annotations

from html import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING

from formatter.document_io import build_document_from_inputs
from formatter.document_reconstruction import reconstruct_document_before_format
from formatter.headings import heading_level_from_word_style
from formatter import FormatJob, format_document_full


def build_formatted_preview_html(
    text: str,
    job: FormatJob,
    *,
    document_type: str | None = None,
    required_sections: list[str] | None = None,
) -> str:
    """
    Run structure recovery (when enabled) and formatting, then render After-preview HTML.
    Matches the downloaded .docx styling path.
    """
    doc = build_document_from_inputs(pasted_raw=text, file_bytes=None)
    paragraph_assignments = None

    if job.auto_headings or job.requirement_headings:
        recon = reconstruct_document_before_format(
            doc,
            document_type=document_type,
            required_sections=required_sections,
            prefer_ai=job.auto_headings,
        )
        paragraph_assignments = recon.assignments

    format_document_full(doc, job, paragraph_assignments)
    return _document_to_preview_html(doc, job)


def _pt(value) -> float:
    if value is None:
        return 0.0
    return round(float(value.pt), 2)


def _line_height_from_paragraph(paragraph, fallback: float) -> float:
    pf = paragraph.paragraph_format
    if pf.line_spacing_rule == WD_LINE_SPACING.DOUBLE:
        return 2.0
    if pf.line_spacing_rule == WD_LINE_SPACING.SINGLE:
        return 1.0
    if pf.line_spacing is not None:
        return round(float(pf.line_spacing), 2)
    return fallback


def _alignment_from_paragraph(paragraph, fallback: str) -> str:
    alignment = paragraph.paragraph_format.alignment
    if alignment == WD_ALIGN_PARAGRAPH.CENTER:
        return "center"
    if alignment == WD_ALIGN_PARAGRAPH.RIGHT:
        return "right"
    if alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
        return "justify"
    if alignment == WD_ALIGN_PARAGRAPH.LEFT:
        return "left"
    return fallback


def _font_size_pt(paragraph, fallback: int) -> int:
    for run in paragraph.runs:
        if run.font.size is not None:
            return int(round(run.font.size.pt))
    return fallback


def _paragraph_margin_style(paragraph) -> str:
    pf = paragraph.paragraph_format
    before = _pt(pf.space_before)
    after = _pt(pf.space_after)
    return f"margin:{before}pt 0 {after}pt;"


def _document_to_preview_html(doc: Document, job: FormatJob) -> str:
    body_pt = job.font_size_pt
    font = job.font_family
    default_lh = job.line_spacing
    heading_pt = job.heading_size_pt
    body_align = "justify" if job.alignment == "justify" else "left"
    indent = "2em" if job.first_line_indent else "0"
    parts: list[str] = []

    for paragraph in doc.paragraphs:
        stripped = paragraph.text.strip()
        if not stripped:
            continue

        level = heading_level_from_word_style(paragraph) or 0
        margin = _paragraph_margin_style(paragraph)
        line_height = _line_height_from_paragraph(paragraph, default_lh)
        size_pt = _font_size_pt(paragraph, heading_pt if level > 0 else body_pt)
        align = _alignment_from_paragraph(
            paragraph,
            "center" if level == 1 else ("left" if level > 0 else body_align),
        )

        if level == 1:
            parts.append(
                f'<h2 class="preview-p preview-p--title" style="'
                f"font-family:{escape(font)},serif;font-size:{size_pt}pt;"
                f"font-weight:700;color:#000;text-align:{align};line-height:{line_height};"
                f'text-decoration:none;{margin}">{escape(stripped)}</h2>'
            )
        elif level > 0:
            parts.append(
                f'<h3 class="preview-p preview-p--heading" style="'
                f"font-family:{escape(font)},serif;font-size:{size_pt}pt;"
                f"font-weight:700;color:#000;text-align:{align};line-height:{line_height};"
                f'text-decoration:none;{margin}">{escape(stripped)}</h3>'
            )
        else:
            parts.append(
                f'<p class="preview-p preview-p--body" style="'
                f"font-family:{escape(font)},serif;font-size:{size_pt}pt;"
                f"font-weight:400;color:#000;text-align:{align};text-indent:{indent};"
                f'line-height:{line_height};{margin}">{escape(stripped)}</p>'
            )

    return (
        f'<div class="preview-doc preview-doc--after" style="font-family:{escape(font)},serif;'
        f'font-size:{body_pt}pt;line-height:{default_lh};text-align:{body_align};">'
        + "".join(parts)
        + "</div>"
    )
