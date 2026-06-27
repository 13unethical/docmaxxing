"""Extract measurable document metrics without AI."""

from __future__ import annotations

import re
from typing import Any

from docx import Document

from formatter.headings import REFS_HEADINGS, normalize_paragraph_text
from services.document_analyzer import analyze_document, normalize_expected
from services.document_checker import _IN_TEXT_CITATION, _word_count
from services.document_structure_engine import is_heading_like, structure_tree_to_detected_sections

_YEARISH = re.compile(r"\(?(19|20)\d{2}[a-z]?\)?|n\.d\.")


def _paragraphs_from_text(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", (text or "").strip())
    return [b.strip() for b in blocks if b.strip()]


def _references_section_index(paragraphs: list[str]) -> int | None:
    for i, p in enumerate(paragraphs):
        if normalize_paragraph_text(p) in REFS_HEADINGS:
            return i
    return None


def _count_reference_entries(paragraphs: list[str]) -> int:
    idx = _references_section_index(paragraphs)
    if idx is None:
        return 0
    count = 0
    for line in paragraphs[idx + 1 :]:
        if is_heading_like(line):
            break
        stripped = line.strip()
        if not stripped:
            continue
        if _YEARISH.search(stripped) or re.search(r"\bet al\.|\bdoi:|\bhttp", stripped, re.I):
            count += 1
        elif len(stripped.split()) >= 4:
            count += 1
    return count


def _count_body_paragraphs(paragraphs: list[str]) -> int:
    return sum(1 for p in paragraphs if not is_heading_like(p) and len(p.split()) >= 20)


def _detect_formatting_from_doc(doc: Document | None) -> dict[str, Any]:
    if doc is None:
        return {
            "font_family": None,
            "font_size": None,
            "line_spacing": None,
            "has_page_numbers": None,
            "alignment": None,
        }
    from services.document_analyzer import _approx_line_spacing_multiple, _alignment_label, _collect_explicit_fonts, _docx_has_page_number_field

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


def extract_document_metrics(
    *,
    text: str,
    paragraphs: list[str] | None = None,
    doc: Document | None = None,
    structure_tree: list[dict[str, Any]] | None = None,
    expected_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return measurable facts about the document."""
    paras = paragraphs if paragraphs is not None else _paragraphs_from_text(text)
    wc = _word_count(text)
    in_text = len(_IN_TEXT_CITATION.findall(text or ""))
    ref_idx = _references_section_index(paras)
    has_refs_section = ref_idx is not None
    ref_entries = _count_reference_entries(paras)
    detected_sections = structure_tree_to_detected_sections(structure_tree or [])
    if not detected_sections:
        detected_sections = [
            {"title": p.strip()[:80], "canonical": normalize_paragraph_text(p)}
            for p in paras
            if is_heading_like(p)
        ]

    fmt = _detect_formatting_from_doc(doc)
    legacy = analyze_document(text=text, doc=doc, expected=normalize_expected(expected_format or {}))

    grammar_signals = 0
    if re.search(r"  +", text or ""):
        grammar_signals += 1
    body_lens = [len(p.split()) for p in paras if not is_heading_like(p)]
    if body_lens and sum(1 for n in body_lens if n < 15) > len(body_lens) * 0.4:
        grammar_signals += 1

    apa_refs_ok = False
    if has_refs_section and ref_entries:
        tail = paras[(ref_idx or 0) + 1 : (ref_idx or 0) + 4]
        apa_refs_ok = any(re.search(r"\(\d{4}\)", line) or re.search(r"\d{4}\.", line) for line in tail)

    return {
        "word_count": wc,
        "paragraph_count": len(paras),
        "body_paragraph_count": _count_body_paragraphs(paras),
        "heading_count": sum(1 for p in paras if is_heading_like(p)),
        "reference_entries": ref_entries,
        "has_references_section": has_refs_section,
        "in_text_citations": in_text,
        "detected_sections": detected_sections,
        "font_family": fmt["font_family"],
        "font_size": fmt["font_size"],
        "line_spacing": fmt["line_spacing"],
        "has_page_numbers": fmt["has_page_numbers"],
        "alignment": fmt["alignment"],
        "grammar_signal_count": grammar_signals,
        "apa_reference_format_ok": apa_refs_ok,
        "legacy_issues": legacy.get("issues") or [],
    }
