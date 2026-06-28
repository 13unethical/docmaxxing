"""Server-side formatted preview HTML — same pipeline as /api/format (without file output)."""

from __future__ import annotations

from html import escape

from docx import Document

from formatter.document_io import build_document_from_inputs
from formatter.heading_plan import ParagraphHeadingAssignment
from formatter.headings import heading_level_from_word_style
from formatter.pipeline import FormatJob, format_document_full
from formatter.structure_rebuild import rebuild_document_from_recovery
from services.document_structure_engine import recover_structure


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
    paragraph_assignments: list[ParagraphHeadingAssignment] | None = None

    if job.auto_headings:
        recovery = recover_structure(doc=doc, document_type=document_type)
        if not recovery.get("error") and recovery.get("recovery_mode") == "ai_reconstructed":
            apply_result = rebuild_document_from_recovery(doc, recovery)
            if apply_result:
                paragraph_assignments = apply_result.assignments

    format_document_full(doc, job, paragraph_assignments, required_sections=required_sections)
    return _document_to_preview_html(doc, job)


def _document_to_preview_html(doc: Document, job: FormatJob) -> str:
    body_pt = job.font_size_pt
    font = job.font_family
    lh = job.line_spacing
    heading_pt = job.heading_size_pt
    body_align = "justify" if job.alignment == "justify" else "left"
    indent = "2em" if job.first_line_indent else "0"
    parts: list[str] = []

    for paragraph in doc.paragraphs:
        stripped = paragraph.text.strip()
        if not stripped:
            continue
        level = heading_level_from_word_style(paragraph) or 0
        if level > 0:
            parts.append(
                f'<h3 class="preview-p preview-p--heading" style="'
                f"font-family:{escape(font)},serif;font-size:{heading_pt}pt;"
                f"font-weight:700;text-align:left;line-height:{lh};"
                f'margin:0.85rem 0 0.35rem;">{escape(stripped)}</h3>'
            )
        else:
            parts.append(
                f'<p class="preview-p preview-p--body" style="'
                f"font-family:{escape(font)},serif;font-size:{body_pt}pt;"
                f"font-weight:400;text-align:{body_align};text-indent:{indent};"
                f'line-height:{lh};margin:0 0 0.65rem;">{escape(stripped)}</p>'
            )

    return (
        f'<div class="preview-doc preview-doc--after" style="font-family:{escape(font)},serif;'
        f'font-size:{body_pt}pt;line-height:{lh};text-align:{body_align};">'
        + "".join(parts)
        + "</div>"
    )
