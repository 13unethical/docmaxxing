"""Extract measurable document metrics without AI."""

from __future__ import annotations

import re
from typing import Any

from docx import Document

from services.document_analyzer import analyze_document, normalize_expected
from services.check_text import document_word_count, split_document_paragraphs
from services.check_citations import count_in_text_citation_hits, match_citations, paragraph_has_citation
from services.check_structure import (
    body_paragraph_count,
    body_text_for_citations,
    extract_document_model,
    heading_count,
    iter_section_paragraphs,
    model_to_detected_sections,
    reference_entry_lines,
)
from services.check_validator import heading_label_without_number, is_references_section_name

_YEARISH = re.compile(r"\(?(19|20)\d{2}[a-z]?\)?|n\.d\.")
_SKIP_BALANCE_SECTIONS = frozenset(
    {
        "references",
        "reference list",
        "bibliography",
        "works cited",
        "appendix",
        "appendices",
        "abstract",
    }
)
_ANALYTICAL_HINTS = (
    "analysis",
    "discussion",
    "literature",
    "findings",
    "results",
    "argument",
    "review",
    "evaluation",
    "theoretical",
    "background",
    "critique",
    "comparison",
)
_NON_ANALYTICAL_HINTS = (
    "introduction",
    "intro",
    "conclusion",
    "method",
    "methodology",
    "abstract",
    "reference",
    "appendix",
    "acknowledg",
    "title",
)


def _paragraphs_from_text(text: str) -> list[str]:
    return split_document_paragraphs(text)


def _detect_formatting_from_doc(doc: Document | None) -> dict[str, Any]:
    if doc is None:
        return {
            "font_family": None,
            "font_size": None,
            "line_spacing": None,
            "has_page_numbers": None,
            "alignment": None,
        }
    from services.document_analyzer import (
        _alignment_label,
        _approx_line_spacing_multiple,
        _collect_explicit_fonts,
        _docx_has_page_number_field,
    )

    sizes, names = _collect_explicit_fonts(doc)
    font_size = min(sizes) if sizes else None
    font_family = next(iter(names), None) if len(names) == 1 else (next(iter(names)) if names else None)
    line_spacings: set[float] = set()
    alignments: set[str] = set()
    for p in doc.paragraphs:
        if not (p.text or "").strip():
            continue
        ls = _approx_line_spacing_multiple(p.paragraph_format)
        if ls is not None:
            line_spacings.add(round(ls, 2))
        al = _alignment_label(p.paragraph_format)
        if al:
            alignments.add(al)
    line_spacing = None
    if len(line_spacings) == 1:
        line_spacing = next(iter(line_spacings))
    elif line_spacings:
        line_spacing = max(line_spacings)
    alignment = next(iter(alignments)) if len(alignments) == 1 else None
    return {
        "font_family": font_family,
        "font_size": font_size,
        "line_spacing": line_spacing,
        "has_page_numbers": _docx_has_page_number_field(doc),
        "alignment": alignment,
    }


def _section_share_metrics(sections: list[dict[str, Any]]) -> dict[str, Any]:
    scored: list[tuple[str, int]] = []
    for section in sections:
        title = str(section.get("title") or "")
        key = heading_label_without_number(title)
        if is_references_section_name(title) or key in _SKIP_BALANCE_SECTIONS:
            continue
        words = int(section.get("body_word_count") or 0)
        if words < 30:
            continue
        scored.append((title, words))
    total = sum(words for _title, words in scored)
    if total <= 0:
        return {
            "developed_section_count": 0,
            "largest_section_title": None,
            "largest_section_share": 0.0,
            "section_body_words": 0,
        }
    title, words = max(scored, key=lambda item: item[1])
    return {
        "developed_section_count": len(scored),
        "largest_section_title": title,
        "largest_section_share": round(words / total, 4),
        "section_body_words": total,
    }


def _is_analytical_section(canonical: str) -> bool:
    key = (canonical or "").lower()
    if any(hint in key for hint in _NON_ANALYTICAL_HINTS):
        return False
    return any(hint in key for hint in _ANALYTICAL_HINTS)


def _paragraph_quality_metrics(
    paragraphs: list[dict[str, Any]],
    *,
    citation_mode: str | None,
) -> dict[str, Any]:
    long_enough = [p for p in paragraphs if int(p.get("word_count") or 0) >= 20]
    lengths = [int(p["word_count"]) for p in long_enough]
    over_250 = sum(1 for n in lengths if n > 250)
    avg = round(sum(lengths) / len(lengths), 1) if lengths else 0.0
    share_long = round(over_250 / len(lengths), 4) if lengths else 0.0

    analytical = [p for p in long_enough if _is_analytical_section(str(p.get("section_canonical") or ""))]
    pool = analytical or [
        p
        for p in long_enough
        if not any(hint in str(p.get("section_canonical") or "").lower() for hint in _NON_ANALYTICAL_HINTS)
    ]
    uncited = 0
    for para in pool:
        if not paragraph_has_citation(str(para.get("text") or ""), mode=citation_mode):
            uncited += 1
    share_uncited = round(uncited / len(pool), 4) if pool else 1.0 if long_enough else 0.0
    return {
        "avg_paragraph_words": avg,
        "paragraphs_over_250": over_250,
        "share_paragraphs_over_250": share_long,
        "body_paragraphs_measured": len(long_enough),
        "analytical_paragraphs": len(pool),
        "analytical_paragraphs_without_citation": uncited,
        "share_analytical_without_citation": share_uncited,
    }


def extract_document_metrics(
    *,
    text: str,
    paragraphs: list[str] | None = None,
    doc: Document | None = None,
    structure_tree: list[dict[str, Any]] | None = None,
    expected_format: dict[str, Any] | None = None,
    expected_sections: list[str] | None = None,
) -> dict[str, Any]:
    """Return measurable facts about the document."""
    del structure_tree  # Check metrics come from formatter_v2.structure, not V1 trees.
    paras = paragraphs if paragraphs is not None else _paragraphs_from_text(text)
    model, extractor_name = extract_document_model(
        text=text,
        paragraphs=paras,
        doc=doc,
        expected_sections=expected_sections,
    )
    wc = document_word_count(text)
    ref_lines = reference_entry_lines(model)
    citation_match = match_citations(body_text=body_text_for_citations(model), reference_lines=ref_lines)
    in_text = int(citation_match.get("cited") or 0)
    has_refs_section = bool(model.references) or bool(ref_lines)
    ref_entries = len(ref_lines)
    detected_sections = model_to_detected_sections(model)
    headings = heading_count(model)
    body_paras = body_paragraph_count(model)
    section_shares = _section_share_metrics(detected_sections)
    para_quality = _paragraph_quality_metrics(
        iter_section_paragraphs(model),
        citation_mode=str(citation_match.get("mode") or "") or None,
    )
    in_text_hits = count_in_text_citation_hits(
        body_text=body_text_for_citations(model),
        mode=str(citation_match.get("mode") or "") or None,
    )
    if in_text_hits < int(citation_match.get("cited") or 0):
        in_text_hits = int(citation_match.get("cited") or 0)

    fmt = _detect_formatting_from_doc(doc)
    legacy = analyze_document(text=text, doc=doc, expected=normalize_expected(expected_format or {}))

    grammar_signals = 0
    if re.search(r"  +", text or ""):
        grammar_signals += 1
    body_lens = [
        document_word_count(p)
        for p in paras
        if len(p.split()) >= 8
    ]
    if body_lens and sum(1 for n in body_lens if n < 15) > len(body_lens) * 0.4:
        grammar_signals += 1

    apa_refs_ok = False
    if has_refs_section and ref_entries:
        apa_refs_ok = any(_YEARISH.search(line) for line in ref_lines[:3])

    return {
        "word_count": wc,
        "paragraph_count": len(paras),
        "body_paragraph_count": body_paras,
        "heading_count": headings,
        "reference_entries": ref_entries,
        "has_references_section": has_refs_section,
        "in_text_citations": in_text,
        "citation_match": citation_match,
        "detected_sections": detected_sections,
        "structure_extractor": extractor_name,
        "developed_section_count": section_shares["developed_section_count"],
        "largest_section_share": section_shares["largest_section_share"],
        "largest_section_title": section_shares["largest_section_title"],
        "avg_paragraph_words": para_quality["avg_paragraph_words"],
        "share_paragraphs_over_250": para_quality["share_paragraphs_over_250"],
        "paragraphs_over_250": para_quality["paragraphs_over_250"],
        "share_analytical_without_citation": para_quality["share_analytical_without_citation"],
        "analytical_paragraphs": para_quality["analytical_paragraphs"],
        "analytical_paragraphs_without_citation": para_quality["analytical_paragraphs_without_citation"],
        "in_text_citation_hits": in_text_hits,
        "font_family": fmt["font_family"],
        "font_size": fmt["font_size"],
        "line_spacing": fmt["line_spacing"],
        "has_page_numbers": fmt["has_page_numbers"],
        "alignment": fmt["alignment"],
        "grammar_signal_count": grammar_signals,
        "apa_reference_format_ok": apa_refs_ok,
        "legacy_issues": legacy.get("issues") or [],
    }
