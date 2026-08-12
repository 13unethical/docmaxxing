"""Structure extraction package for Formatter V2."""

from formatter_v2.structure.base import StructureExtractor
from formatter_v2.structure.from_heuristics import HeuristicsExtractor
from formatter_v2.structure.from_word_styles import (
    WordStylesExtractor,
    document_has_structural_styles,
)

__all__ = [
    "HeuristicsExtractor",
    "StructureExtractor",
    "WordStylesExtractor",
    "document_has_structural_styles",
]
