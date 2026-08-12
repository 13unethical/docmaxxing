"""Structure extraction protocols for Formatter V2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from formatter_v2.render.model import DocumentModel


@runtime_checkable
class StructureExtractor(Protocol):
    """All structure backends (Word styles, heuristics, future LLM) share this."""

    def extract(self, source: object) -> DocumentModel:
        """Turn an input document / text into a typed ``DocumentModel``."""
        ...
