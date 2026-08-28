"""Shared plain-text splitting and word counting for Academic Check."""

from __future__ import annotations

import re


def split_document_paragraphs(text: str) -> list[str]:
    """Split pasted/uploaded document text into paragraph blocks.

    Uses blank-line boundaries first. When the document is a single block but
    contains multiple non-empty lines (common for pasted outlines), each line
    becomes its own paragraph so metrics match visible structure.
    """
    raw = (text or "").strip()
    if not raw:
        return []

    blocks = re.split(r"\n\s*\n", raw)
    blocks = [b.strip() for b in blocks if b.strip()]
    if len(blocks) > 1:
        return blocks

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) > 1:
        return lines

    return blocks


def document_word_count(text: str) -> int:
    """Count words in the full document text (not per-paragraph)."""
    return len(re.findall(r"\b[\w'-]+\b", text or ""))
