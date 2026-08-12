"""Coarse document-kind detection for Formatter V2."""

from __future__ import annotations

from enum import Enum

from formatter_v2.render.document import Block
from formatter_v2.resolve import ResolutionNotice
from formatter_v2.spec import ParagraphRole

_HEADING_ROLES = frozenset(
    {
        ParagraphRole.HEADING_1,
        ParagraphRole.HEADING_2,
        ParagraphRole.HEADING_3,
        ParagraphRole.HEADING_4,
    }
)
_BODY_ROLES = frozenset({ParagraphRole.BODY, ParagraphRole.BODY_FIRST})

_SLIDE_LINE_RE = __import__("re").compile(r"(?i)^\s*slide\s+\d+\b")
_TITLE_TEXT_NOTES = frozenset({"title", "text", "notes"})


class DocumentKind(str, Enum):
    SLIDE_SCRIPT = "slide_script"
    OUTLINE = "outline"
    ESSAY = "essay"


def _plain(block: Block) -> str:
    if isinstance(block.text, str):
        return block.text
    return str(block.text)


def detect_kind(blocks: list[Block]) -> DocumentKind:
    """Classify a flat block list as essay / outline / slide script."""
    if not blocks:
        return DocumentKind.ESSAY

    slide_hits = sum(1 for b in blocks if _SLIDE_LINE_RE.match(_plain(b).strip()))
    if slide_hits >= 3:
        return DocumentKind.SLIDE_SCRIPT

    labels = [_plain(b).strip().casefold() for b in blocks]
    title_text_notes = sum(1 for label in labels if label in _TITLE_TEXT_NOTES)
    # Repeating Title/Text/Notes pattern: at least two full cycles (6 labels)
    # or ≥3 of each label appearing.
    if title_text_notes >= 6:
        return DocumentKind.SLIDE_SCRIPT
    counts = {k: labels.count(k) for k in _TITLE_TEXT_NOTES}
    if all(counts[k] >= 3 for k in _TITLE_TEXT_NOTES):
        return DocumentKind.SLIDE_SCRIPT

    total = len(blocks)
    if total >= 20:
        heading_n = sum(1 for b in blocks if b.role in _HEADING_ROLES)
        body_n = sum(1 for b in blocks if b.role in _BODY_ROLES)
        if heading_n >= body_n:
            return DocumentKind.OUTLINE

    return DocumentKind.ESSAY


def kind_notices(kind: DocumentKind) -> list[ResolutionNotice]:
    if kind != DocumentKind.SLIDE_SCRIPT:
        return []
    return [
        ResolutionNotice(
            field="structure.document_kind",
            severity="deviation",
            message=(
                "This document looks like a slide script. "
                "Academic formatting does not apply well here — "
                "review the result by hand."
            ),
        )
    ]
