"""Citation service abstraction.

Workspace -> CitationService -> CitationProvider -> CrossrefProvider (initial).

The frontend only ever talks to CitationService (through the workspace API) and
never depends on provider-specific fields. Providers return normalized ``Work``
objects, so future providers (OpenAlex, Semantic Scholar, ...) can be swapped in
without any frontend change.
"""

from services.citation_service.models import Work
from services.citation_service.provider import CitationProvider, CitationProviderError
from services.citation_service.crossref_provider import CrossrefProvider
from services.citation_service.service import CitationService, SUPPORTED_STYLES

__all__ = [
    "Work",
    "CitationProvider",
    "CitationProviderError",
    "CrossrefProvider",
    "CitationService",
    "SUPPORTED_STYLES",
]
