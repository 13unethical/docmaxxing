"""
Heading detection delegates to the document structure engine.
Word paragraph styling helpers remain here (docx-specific).
"""

from __future__ import annotations

from services.document_structure_engine import (
    COMMON_HEADINGS,
    REFS_HEADINGS,
    detect_heading_level,
    is_heading_like,
    is_references_heading,
    normalize_paragraph_text,
    split_embedded_heading_paragraph,
)

__all__ = [
    "COMMON_HEADINGS",
    "REFS_HEADINGS",
    "normalize_paragraph_text",
    "is_references_heading",
    "is_heading_like",
    "detect_heading_level",
    "split_embedded_heading_paragraph",
    "apply_heading_caps",
    "set_plain_paragraph_text",
]


def heading_level_from_word_style(paragraph) -> int | None:
    """Map an existing Word paragraph style to logical heading level 1–3."""
    name = (getattr(getattr(paragraph, "style", None), "name", None) or "").strip().lower()
    if not name:
        return None
    if name in {"title", "heading 1"}:
        return 1
    if name == "heading 2":
        return 2
    if name == "heading 3":
        return 3
    if name.startswith("heading "):
        try:
            n = int(name.split()[-1])
            if 1 <= n <= 3:
                return n
        except ValueError:
            pass
    return None


def apply_heading_caps(paragraph, enabled: bool, heading_level: int) -> None:
    """Uppercase section/subsection headings only; never the document title."""
    if not enabled or heading_level < 2:
        return
    plain = paragraph.text.strip()
    if not plain:
        return
    set_plain_paragraph_text(paragraph, plain.upper())


def set_plain_paragraph_text(paragraph, new_text: str) -> None:
    """Replace paragraph content with plain text while preserving paragraph props."""
    from docx.oxml.ns import qn

    p_el = paragraph._p
    for child in list(p_el):
        if child.tag == qn("w:pPr"):
            continue
        p_el.remove(child)
    if new_text:
        paragraph.add_run(new_text)
