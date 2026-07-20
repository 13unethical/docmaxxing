"""Citation provider interface.

A provider knows how to talk to one bibliographic source (Crossref, OpenAlex,
Semantic Scholar, ...) and must return normalized :class:`Work` objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from services.citation_service.models import Work


class CitationProviderError(RuntimeError):
    """Raised when a provider cannot fulfil a request (network, parsing, ...)."""


class CitationProvider(ABC):
    """Interface every citation source must implement."""

    #: Short identifier, e.g. "crossref".
    name: str = "provider"

    @abstractmethod
    def search(self, query: str, *, limit: int = 5) -> list[Work]:
        """Return up to ``limit`` normalized works matching ``query``."""
        raise NotImplementedError

    def by_doi(self, doi: str) -> Work | None:  # optional capability
        """Return a single work for a DOI, or ``None`` if unsupported/not found."""
        return None
