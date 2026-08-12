"""Formatter V2 DOCX render layer."""

from formatter_v2.render.builder import build_document
from formatter_v2.render.document import Block, render_document
from formatter_v2.render.model import DocumentModel
from formatter_v2.render.rich_text import apply_formatted_text
from formatter_v2.render.styles import (
    apply_page_numbering,
    apply_page_setup,
    build_styles,
    enable_field_update,
    style_name_for_role,
)

__all__ = [
    "Block",
    "DocumentModel",
    "apply_formatted_text",
    "apply_page_numbering",
    "apply_page_setup",
    "build_document",
    "build_styles",
    "enable_field_update",
    "render_document",
    "style_name_for_role",
]
