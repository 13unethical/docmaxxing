"""Structured document content for Formatter V2 assembly."""

from __future__ import annotations

from dataclasses import dataclass, field

from formatter_v2.render.document import Block
from formatter_v2.spec import CoverPage


@dataclass
class DocumentModel:
    """Full-document content tree (not a flat block list).

    Table of contents and abbreviation list are NOT stored here — the builder
    generates them from ``FormatSpec`` and from heading outline in ``body``.
    """

    cover: CoverPage | None = None
    front_matter: list[Block] = field(default_factory=list)
    """Abstract heading/body, keywords, and similar front-matter blocks."""

    body: list[Block] = field(default_factory=list)
    references: list[Block] = field(default_factory=list)
    """References heading + entry blocks (or FormattedText entries)."""

    appendices: list[Block] = field(default_factory=list)
    """Flat list; each ``APPENDIX_HEADING`` starts a new appendix."""
