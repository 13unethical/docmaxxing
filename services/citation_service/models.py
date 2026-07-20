"""Normalized citation data model shared across providers and the frontend."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Work:
    """A provider-agnostic scholarly work.

    Every :class:`CitationProvider` must return objects with exactly these
    fields, so the frontend never depends on provider-specific payloads.
    """

    title: str
    authors: list[str] = field(default_factory=list)  # display form, e.g. "Lehtola, T."
    year: str = "n.d."
    journal: str | None = None
    doi: str | None = None
    url: str | None = None

    # Optional extras used only for reference formatting (never required by FE).
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    publisher: str | None = None

    def author_families(self) -> list[str]:
        """Surnames only, e.g. ['Lehtola', 'Park']."""
        fams: list[str] = []
        for a in self.authors:
            a = (a or "").strip()
            if not a:
                continue
            fams.append(a.split(",")[0].strip() if "," in a else a.split()[-1])
        return fams

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "authors": list(self.authors),
            "year": self.year,
            "journal": self.journal,
            "doi": self.doi,
            "url": self.url,
        }
