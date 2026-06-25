"""Section-level layout: margins (presets)."""

from __future__ import annotations

from docx import Document
from docx.shared import Inches

# All presets apply uniform margins on every side (common for coursework templates)
MARGIN_PRESETS_INCHES = {
    "normal": 1.0,
    "narrow": 0.5,
    "wide": 1.5,
}


def apply_margin_preset(document: Document, preset: str) -> None:
    inches = MARGIN_PRESETS_INCHES.get(preset, 1.0)
    length = Inches(inches)
    for section in document.sections:
        section.top_margin = length
        section.bottom_margin = length
        section.left_margin = length
        section.right_margin = length
