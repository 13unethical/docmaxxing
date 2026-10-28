"""Extract measurable document metrics without AI."""

from __future__ import annotations

import re
from collections import Counter
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
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
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
            "has_cover_page": None,
            "alignment": None,
        }
    from services.document_analyzer import (
        _alignment_label,
        _approx_line_spacing_multiple,
        _docx_has_page_number_field,
    )

    defaults = _doc_default_formatting(doc)
    families: Counter[str] = Counter()
    sizes: Counter[int] = Counter()
    line_spacings: Counter[float] = Counter()
    alignments: set[str] = set()
    for p in doc.paragraphs:
        if not (p.text or "").strip():
            continue
        chain = _style_chain(p.style)
        ls = _first_value(
            [_approx_line_spacing_multiple(p.paragraph_format)]
            + [_approx_line_spacing_multiple(s.paragraph_format) for s in chain]
        )
        if ls is None:
            ls = defaults["line_spacing"]
        if ls is not None:
            line_spacings[round(ls, 2)] += len(p.text)
        al = _alignment_label(p.paragraph_format)
        if al:
            alignments.add(al)
        for r in p.runs:
            if not (r.text or "").strip():
                continue
            run_chain = _style_chain(r.style) if r.style is not None else []
            name = _first_value([r.font.name] + [s.font.name for s in run_chain + chain]) or defaults["font_family"]
            size = _first_value([r.font.size] + [s.font.size for s in run_chain + chain])
            pt = int(round(size.pt)) if size is not None else defaults["font_size"]
            if name:
                families[name.strip()] += len(r.text)
            if pt:
                sizes[pt] += len(r.text)
    alignment = next(iter(alignments)) if len(alignments) == 1 else None
    return {
        "font_family": _dominant(families),
        "font_size": _dominant(sizes),
        "line_spacing": _dominant(line_spacings),
        "has_page_numbers": _docx_has_page_number_field(doc),
        "has_cover_page": _docx_has_cover_page(doc),
        "alignment": alignment,
    }


def _paragraph_ends_page(p: Any) -> bool:
    xml = p._p.xml
    return 'w:type="page"' in xml or "<w:sectPr" in xml


def _docx_has_cover_page(doc: Document) -> bool:
    """A page break near the start with only short lines (title, name, course…) before it."""
    lines: list[str] = []
    for p in doc.paragraphs[:40]:
        if p.paragraph_format.page_break_before and lines:
            break
        text = (p.text or "").strip()
        if text:
            if len(text.split()) > 25 or len(lines) >= 15:
                return False
            lines.append(text)
        if _paragraph_ends_page(p):
            break
    else:
        return False
    return 0 < len(lines) and sum(len(t.split()) for t in lines) <= 120


def _style_chain(style: Any) -> list[Any]:
    chain: list[Any] = []
    while style is not None and style not in chain:
        chain.append(style)
        style = style.base_style
    return chain


def _first_value(values: list[Any]) -> Any:
    return next((v for v in values if v is not None), None)


def _dominant(counter: Counter) -> Any:
    return counter.most_common(1)[0][0] if counter else None


def _doc_default_formatting(doc: Document) -> dict[str, Any]:
    """Run/paragraph defaults from styles.xml docDefaults, used when no style sets a value."""
    out: dict[str, Any] = {"font_family": None, "font_size": None, "line_spacing": None}
    try:
        root = doc.styles.element
    except Exception:
        return out
    ns = {"w": _W_NS}
    fonts = root.find("w:docDefaults/w:rPrDefault/w:rPr/w:rFonts", ns)
    if fonts is not None:
        out["font_family"] = fonts.get(f"{{{_W_NS}}}ascii") or fonts.get(f"{{{_W_NS}}}hAnsi")
    size = root.find("w:docDefaults/w:rPrDefault/w:rPr/w:sz", ns)
    if size is not None:
        try:
            out["font_size"] = int(round(int(size.get(f"{{{_W_NS}}}val")) / 2))
        except (TypeError, ValueError):
            pass
    spacing = root.find("w:docDefaults/w:pPrDefault/w:pPr/w:spacing", ns)
    if spacing is not None and spacing.get(f"{{{_W_NS}}}lineRule", "auto") == "auto":
        try:
            out["line_spacing"] = round(int(spacing.get(f"{{{_W_NS}}}line")) / 240, 2)
        except (TypeError, ValueError):
            pass
    return out


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
        "has_cover_page": fmt["has_cover_page"],
        "alignment": fmt["alignment"],
        "grammar_signal_count": grammar_signals,
        "apa_reference_format_ok": apa_refs_ok,
        "legacy_issues": legacy.get("issues") or [],
    }
