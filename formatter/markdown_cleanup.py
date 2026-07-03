"""
Strip Markdown artifacts from academic document text.

Humanizers and AI tools often leave ## headings, *italics*, and orphan hash lines.
"""

from __future__ import annotations

import re

from docx import Document

_MD_HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_MD_ONLY_HASHES = re.compile(r"^\s*#{1,6}\s*$")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*([^*]+?)\*(?!\*)")
_MD_UNDERSCORE_ITALIC = re.compile(r"(?<!_)_([^_]+?)_(?!_)")


def strip_markdown_text(text: str) -> str | None:
    """
    Clean one paragraph's Markdown. Returns None when the paragraph should be removed
    (e.g. a standalone ``##`` line).
    """
    stripped = (text or "").strip()
    if not stripped:
        return ""

    if _MD_ONLY_HASHES.match(stripped):
        return None

    m = _MD_HEADING_LINE.match(stripped)
    if m:
        stripped = m.group(1).strip()

    stripped = _MD_BOLD.sub(r"\1", stripped)
    stripped = _MD_ITALIC.sub(r"\1", stripped)
    stripped = _MD_UNDERSCORE_ITALIC.sub(r"\1", stripped)

    return stripped.strip()


def clean_markdown_in_document(document: Document) -> int:
    """Remove Markdown syntax from every paragraph; drop orphan hash-only lines."""
    from formatter.headings import set_plain_paragraph_text

    removed = 0
    idx = 0
    while idx < len(document.paragraphs):
        paragraph = document.paragraphs[idx]
        old = paragraph.text
        new = strip_markdown_text(old)
        if new is None:
            p_el = paragraph._element
            p_el.getparent().remove(p_el)
            removed += 1
            continue
        if new != old:
            set_plain_paragraph_text(paragraph, new)
        idx += 1
    return removed
