"""Formatter V2 end-to-end pipeline (feature-flagged; V1 remains default)."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument

from formatter_v2.profiles import load_profile
from formatter_v2.render.builder import build_document
from formatter_v2.render.document import Block
from formatter_v2.render.model import DocumentModel
from formatter_v2.resolve import ResolutionNotice, resolve_format_spec
from formatter_v2.spec import StyleName, UserOverrides
from formatter_v2.structure.document_kind import detect_kind, kind_notices
from formatter_v2.structure.from_heuristics import HeuristicsExtractor
from formatter_v2.structure.from_word_styles import (
    WordStylesExtractor,
    document_has_structural_styles,
)
from formatter_v2.structure.text_integrity import normalize_source

_STYLE_ALIASES: dict[str, StyleName] = {
    "harvard": StyleName.HARVARD,
    "apa": StyleName.APA7,
    "apa7": StyleName.APA7,
    "mla": StyleName.MLA9,
    "mla9": StyleName.MLA9,
    "chicago": StyleName.CHICAGO17,
    "chicago17": StyleName.CHICAGO17,
    "ieee": StyleName.IEEE,
}


@dataclass(frozen=True)
class FormatV2Result:
    docx_bytes: bytes
    notices: list[ResolutionNotice]
    extractor_name: str


def resolve_style_name(style: StyleName | str) -> StyleName:
    if isinstance(style, StyleName):
        if style == StyleName.CUSTOM:
            return StyleName.HARVARD
        return style
    key = str(style).strip().casefold().replace(" ", "").replace("_", "")
    key = key.replace("-", "")
    if key.startswith("apa"):
        return StyleName.APA7
    if key.startswith("mla"):
        return StyleName.MLA9
    if key.startswith("chicago") or key.startswith("turabian"):
        return StyleName.CHICAGO17
    if key.startswith("ieee"):
        return StyleName.IEEE
    if key.startswith("harvard") or "citethemright" in key:
        return StyleName.HARVARD
    return _STYLE_ALIASES.get(key, StyleName.HARVARD)


def _coerce_document(source: object) -> DocxDocument | None:
    """Return a Document when source is DOCX-like; None for bare text lists."""
    if isinstance(source, DocxDocument):
        return source
    if isinstance(source, (bytes, bytearray)):
        return Document(io.BytesIO(source))
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.is_file() and path.suffix.lower() == ".docx":
            return Document(str(path))
        return None
    if isinstance(source, list):
        return None
    return None


def select_extractor(source: object):
    """Prefer Word-style mapping when the DOCX is already marked up."""
    document = _coerce_document(source)
    if document is not None and document_has_structural_styles(document):
        return WordStylesExtractor(), "word_styles", document
    return HeuristicsExtractor(), "heuristics", document


def _all_blocks(model: DocumentModel) -> list[Block]:
    blocks: list[Block] = []
    blocks.extend(model.front_matter)
    blocks.extend(model.body)
    blocks.extend(model.references)
    blocks.extend(model.appendices)
    return blocks


def format_document_v2(
    source: object,
    overrides: UserOverrides | None = None,
    style: StyleName | str = StyleName.HARVARD,
) -> FormatV2Result:
    """Homoglyph-normalise → extract structure → resolve → build DOCX bytes.

    Returns DOCX bytes together with resolver / extraction notices. Does not
    touch V1.
    """
    overrides = overrides or UserOverrides()
    style_name = resolve_style_name(style)

    # Homoglyph cleanup must run *before* structure detection so heading /
    # references matching is not thrown off by lookalike letters.
    source, integrity_notices = normalize_source(source)

    expected_sections: list[str] = []
    if overrides.structure and overrides.structure.expected_sections:
        expected_sections = list(overrides.structure.expected_sections)

    extractor, extractor_name, document = select_extractor(source)
    extract_kwargs = {"expected_sections": expected_sections or None}
    if document is not None:
        model = extractor.extract(document, **extract_kwargs)
    else:
        model = extractor.extract(source, **extract_kwargs)

    extraction_notices: list[ResolutionNotice] = list(integrity_notices)

    if getattr(extractor, "last_notices", None):
        extraction_notices.extend(extractor.last_notices)

    if isinstance(extractor, WordStylesExtractor):
        from formatter_v2.structure.from_word_styles import implausible_heading_notices

        extraction_notices.extend(implausible_heading_notices(model))

    from formatter_v2.structure.numbered import numbered_section_notices

    extraction_notices.extend(numbered_section_notices(model))

    kind = detect_kind(_all_blocks(model))
    extraction_notices.extend(kind_notices(kind))

    profile = load_profile(style_name)
    resolution = resolve_format_spec(profile, overrides)
    built = build_document(model, resolution.spec)

    buffer = io.BytesIO()
    built.save(buffer)
    return FormatV2Result(
        docx_bytes=buffer.getvalue(),
        notices=[*resolution.notices, *extraction_notices],
        extractor_name=extractor_name,
    )


def format_document_v2_bytes(
    source: object,
    overrides: UserOverrides | None = None,
    style: StyleName | str = StyleName.HARVARD,
) -> tuple[bytes, list[ResolutionNotice]]:
    """Convenience wrapper matching the brief signature (bytes + notices)."""
    result = format_document_v2(source, overrides, style)
    return result.docx_bytes, result.notices
