"""Shared test helpers."""

from __future__ import annotations

from docx import Document

from formatter import FormatJob, format_document_full
from formatter.document_reconstruction import reconstruct_document_before_format
from formatter.heading_plan import ParagraphHeadingAssignment


def run_format_pipeline(
    doc: Document,
    job: FormatJob,
    *,
    document_type: str | None = None,
    required_sections: list[str] | None = None,
    paragraph_assignments: list[ParagraphHeadingAssignment] | None = None,
):
    """Reconstruct structure then format — matches production /api/format path.

    Tests force prefer_ai=False so heading detection stays deterministic.
    """
    if job.auto_headings or job.requirement_headings:
        recon = reconstruct_document_before_format(
            doc,
            document_type=document_type,
            required_sections=required_sections,
            prefer_ai=False,
        )
        paragraph_assignments = recon.assignments
    return format_document_full(doc, job, paragraph_assignments)
