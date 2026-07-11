"""Helpers for building parsed document inputs to the Research Engine."""

from __future__ import annotations

import uuid

from services.assignment_pipeline.models import utc_now
from services.assignment_project.models import ProjectFile
from services.research_engine.models import ParsedDocument


_MOCK_TEXT: dict[str, str] = {
    "assignment_brief": (
        "Assignment brief: critically evaluate organisational responses to digital transformation. "
        "Students must integrate theory, compare competing perspectives, and support claims with academic sources."
    ),
    "rubric": (
        "Rubric emphasis: structure 25%, critical analysis 30%, use of sources 20%, academic writing 15%, referencing 10%."
    ),
    "lecture_slides": "Lecture focus: sustainability transitions, stakeholder theory, and institutional change.",
    "reading_material": "Core reading highlights debates on policy effectiveness and implementation barriers.",
    "sample_assignment": "Sample assignment demonstrates thematic literature synthesis and evaluative conclusion.",
    "professor_notes": "Professor notes: avoid description-only paragraphs; prioritise argument and evidence weighting.",
    "additional_file": "Supplementary material provides contextual background and terminology guidance.",
}


def build_parsed_documents(files: list[ProjectFile], parsed_payload: list[dict] | None = None) -> list[ParsedDocument]:
    """Prefer explicit parsed payloads; otherwise generate mock parsed text from file metadata."""
    if parsed_payload:
        return [ParsedDocument.from_dict(item) for item in parsed_payload]

    documents: list[ParsedDocument] = []
    for file_record in files:
        text = _MOCK_TEXT.get(file_record.file_type.value, _MOCK_TEXT["additional_file"])
        text = f"[{file_record.original_filename}] {text}"
        documents.append(
            ParsedDocument(
                id=str(uuid.uuid4()),
                file_id=file_record.id,
                file_type=file_record.file_type.value,
                filename=file_record.original_filename,
                text=text,
                word_count=len(text.split()),
                parsed_at=utc_now(),
            )
        )
    return documents
