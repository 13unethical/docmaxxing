"""Normalize assignment requirements into a structured model for validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from services.document_checker import parse_requirements_for_check
from services.requirements_parser import _strict_requirements_from_text

_WORD_RANGE = re.compile(
    r"(?:between|from)\s+(\d{1,5})\s+(?:and|to|-)\s+(\d{1,5})\s*words?",
    re.I,
)
_WORD_RANGE_DASH = re.compile(r"\b(\d{1,5})\s*[-–]\s*(\d{1,5})\s*words?\b", re.I)
_MAX_WORDS = re.compile(r"(?:max(?:imum)?|no more than|up to|at most)\s+(\d{1,5})\s*words?", re.I)
_MIN_WORDS = re.compile(r"(?:min(?:imum)?|at least|no fewer than)\s+(\d{1,5})\s*words?", re.I)
_EXACT_WORDS = re.compile(r"\b(\d{1,5})\s*words?\b", re.I)
_PEER_REVIEWED = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
    r"(?:peer[-\s]?reviewed\s+)?(?:journal\s+)?(?:articles?|sources?|references?)\b",
    re.I,
)
_BODY_PARAGRAPHS = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+body\s+paragraphs?\b",
    re.I,
)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


@dataclass
class StructuredRequirements:
    word_min: int | None = None
    word_max: int | None = None
    word_count_confidence: float = 0.0
    citation_style: str | None = None
    peer_reviewed_refs: int | None = None
    peer_reviewed_confidence: float = 0.0
    references_required: bool | None = None
    required_sections: list[str] = field(default_factory=list)
    font_family: str | None = None
    font_size: int | None = None
    line_spacing: float | None = None
    margins: str | None = None
    alignment: str | None = None
    cover_page_required: bool | None = None
    page_numbers_required: bool | None = None
    body_paragraphs: int | None = None
    counterargument_required: bool | None = None
    parser_confidence: float = 0.0
    submission_format: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "word_min": self.word_min,
            "word_max": self.word_max,
            "word_count_confidence": self.word_count_confidence,
            "citation_style": self.citation_style,
            "peer_reviewed_refs": self.peer_reviewed_refs,
            "peer_reviewed_confidence": self.peer_reviewed_confidence,
            "references_required": self.references_required,
            "required_sections": list(self.required_sections),
            "font_family": self.font_family,
            "font_size": self.font_size,
            "line_spacing": self.line_spacing,
            "margins": self.margins,
            "alignment": self.alignment,
            "cover_page_required": self.cover_page_required,
            "page_numbers_required": self.page_numbers_required,
            "body_paragraphs": self.body_paragraphs,
            "counterargument_required": self.counterargument_required,
            "parser_confidence": self.parser_confidence,
            "submission_format": self.submission_format,
        }


def _parse_number_token(token: str) -> int | None:
    token = (token or "").strip().lower()
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token)


def parse_word_count_spec(spec: str | None) -> tuple[int | None, int | None, float]:
    """Parse word count string into min, max, confidence."""
    if not spec or not str(spec).strip():
        return None, None, 0.0
    text = str(spec).strip()
    low = text.lower()

    m = _WORD_RANGE.search(text) or _WORD_RANGE_DASH.search(text)
    if m:
        return int(m.group(1)), int(m.group(2)), 0.95

    m = _MAX_WORDS.search(text)
    if m:
        n = int(m.group(1))
        return None, n, 0.9

    m = _MIN_WORDS.search(text)
    if m:
        n = int(m.group(1))
        return n, None, 0.9

    m = _EXACT_WORDS.search(text)
    if m:
        n = int(m.group(1))
        if any(x in low for x in ("approximately", "around", "about", "roughly")):
            return int(n * 0.9), int(n * 1.1), 0.55
        if any(x in low for x in ("minimum", "min", "at least", "maximum", "max", "limit")):
            if "min" in low or "at least" in low:
                return n, None, 0.85
            return None, n, 0.85
        return n, n, 0.75

    if "sufficiently comprehensive" in low or "appropriate length" in low:
        return None, None, 0.35

    return None, None, 0.0


def extract_peer_reviewed_count(text: str) -> tuple[int | None, float]:
    m = _PEER_REVIEWED.search(text or "")
    if not m:
        return None, 0.0
    n = _parse_number_token(m.group(1))
    if n is None:
        return None, 0.0
    return n, 0.9 if m.group(1).isdigit() else 0.75


def extract_body_paragraphs(text: str) -> int | None:
    m = _BODY_PARAGRAPHS.search(text or "")
    if not m:
        return None
    return _parse_number_token(m.group(1))


def normalize_requirements(
    requirements_text: str,
    *,
    parsed_payload: dict[str, Any] | None = None,
    doc_type: str = "other",
) -> StructuredRequirements:
    """Merge AI/local parser payload with heuristic extraction from raw text."""
    text = (requirements_text or "").strip()
    local = parse_requirements_for_check(text)
    strict = _strict_requirements_from_text(text) if text else {}
    payload = dict(strict)
    if parsed_payload:
        for k, v in parsed_payload.items():
            if v is not None and v != "" and v != []:
                payload[k] = v

    word_min = local.get("word_limit_min")
    word_max = local.get("word_limit_max")
    word_conf = 0.0
    word_spec = payload.get("word_count")
    if word_spec:
        pmin, pmax, word_conf = parse_word_count_spec(str(word_spec))
        if pmin is not None:
            word_min = pmin
        if pmax is not None:
            word_max = pmax
    if word_min is None and word_max is None and text:
        pmin, pmax, word_conf = parse_word_count_spec(text)
        word_min = word_min or pmin
        word_max = word_max or pmax
    if word_min is not None or word_max is not None:
        word_conf = max(word_conf, 0.85)

    peer_n, peer_conf = extract_peer_reviewed_count(text)
    sections = payload.get("required_sections") or local.get("required_sections") or []
    if not sections:
        from services.document_checker import DEFAULT_REQUIRED_SECTIONS

        sections = list(DEFAULT_REQUIRED_SECTIONS.get(doc_type, []))

    refs_required = payload.get("references_required")
    if refs_required is None:
        refs_required = local.get("reference_list_required")
    if refs_required is None and payload.get("citation_style"):
        refs_required = True

    spacing = payload.get("spacing")
    if spacing is None:
        spacing = payload.get("line_spacing")
    if spacing is None:
        spacing = local.get("line_spacing")
    if isinstance(spacing, str):
        try:
            spacing = float(spacing)
        except ValueError:
            spacing = None

    font_size = payload.get("font_size") or local.get("font_size")
    if font_size is not None:
        try:
            font_size = int(font_size)
        except (TypeError, ValueError):
            font_size = None

    counterargument = None
    if text and re.search(r"\bcounter[-\s]?argument\b", text, re.I):
        counterargument = True
        if "counterargument" not in [s.lower() for s in sections]:
            sections = list(sections) + ["Counterargument"]

    parser_conf = float(payload.get("confidence_score") or 0.0)
    if parser_conf > 1:
        parser_conf = parser_conf / 100.0

    return StructuredRequirements(
        word_min=word_min,
        word_max=word_max,
        word_count_confidence=word_conf,
        citation_style=(payload.get("citation_style") or local.get("citation_style")),
        peer_reviewed_refs=peer_n,
        peer_reviewed_confidence=peer_conf,
        references_required=refs_required,
        required_sections=[str(s).strip() for s in sections if str(s).strip()],
        font_family=payload.get("font_family") or local.get("font_family"),
        font_size=font_size,
        line_spacing=spacing,
        margins=payload.get("margins") or local.get("margins"),
        alignment=payload.get("alignment") or local.get("alignment"),
        cover_page_required=payload.get("cover_page_required") if payload.get("cover_page_required") is not None else local.get("title_page"),
        page_numbers_required=(
            payload.get("page_numbers_required")
            if payload.get("page_numbers_required") is not None
            else local.get("page_numbers")
        ),
        body_paragraphs=extract_body_paragraphs(text),
        counterargument_required=counterargument,
        parser_confidence=parser_conf,
        submission_format=payload.get("submission_format"),
    )
