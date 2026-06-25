"""Backward-compatible re-exports — use services.document_structure_engine."""

from services.document_structure_engine import (
    DOCUMENT_TYPES,
    SECTION_ALIASES,
    SECTION_BLUEPRINTS,
    headings_exist,
    infer_assignment_title,
    is_heading_like,
    paragraphs_from_text,
    recover_structure,
    structure_tree_to_detected_sections,
)

__all__ = [
    "DOCUMENT_TYPES",
    "SECTION_ALIASES",
    "SECTION_BLUEPRINTS",
    "headings_exist",
    "infer_assignment_title",
    "is_heading_like",
    "paragraphs_from_text",
    "recover_structure",
    "structure_tree_to_detected_sections",
]
