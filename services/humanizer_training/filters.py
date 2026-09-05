"""Deterministic quality checks for candidate training examples."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PUNCT_ONLY_RE = re.compile(r"^[\W_]+$", re.UNICODE)
_WS_MARKER_RE = re.compile(r"⟦\s*WS\s*:\s*(\d+)\s*⟧|\[\s*WS\s*:\s*(\d+)\s*\]", re.I)
_CITATION_RE = re.compile(r"\([^)]*?\d{4}[^)]*?\)")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?%")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_URL_RE = re.compile(r"https?://[^\s)]+", re.I)
_HEADING_RE = re.compile(r"(?m)^##\s+.+$")


@dataclass(slots=True)
class FilterResult:
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)


def evaluate_example(
    source_text: str,
    target_text: str,
    *,
    min_words: int,
    max_words: int,
) -> FilterResult:
    source = (source_text or "").strip()
    target = (target_text or "").strip()
    reasons: list[str] = []
    flags: list[str] = []

    if not source:
        reasons.append("EMPTY_SOURCE")
    if not target:
        reasons.append("EMPTY_TARGET")
    if reasons:
        return FilterResult(accepted=False, reasons=sorted(set(reasons)), quality_flags=[])

    if _is_punct_only(source):
        reasons.append("PUNCT_ONLY_SOURCE")
    if _is_punct_only(target):
        reasons.append("PUNCT_ONLY_TARGET")

    source_norm = _normalize_compare(source)
    target_norm = _normalize_compare(target)
    if source_norm == target_norm:
        reasons.append("UNCHANGED")

    src_words = _word_count(source)
    tgt_words = _word_count(target)
    if tgt_words < min_words:
        reasons.append("SHORT_TARGET")
    if src_words > max_words or tgt_words > max_words:
        reasons.append("MAX_WORDS_EXCEEDED")
    if src_words > 0:
        ratio = tgt_words / float(src_words)
        if ratio < 0.35 or ratio > 3.0:
            reasons.append("LENGTH_OUTLIER")

    if "[[[HEADING_" in target or target.count("## ") + 2 < source.count("## "):
        reasons.append("BROKEN_FORMAT")
    if _has_malformed_markers(source, target):
        reasons.append("BROKEN_MARKERS")

    # Structural/token checks: flagged for review, deterministic and non-LLM.
    if _missing_tokens(_CITATION_RE, source, target):
        flags.append("CITATION_MISMATCH")
    if _missing_tokens(_YEAR_RE, source, target):
        flags.append("YEAR_MISMATCH")
    if _missing_tokens(_PERCENT_RE, source, target):
        flags.append("PERCENT_MISMATCH")
    if _missing_tokens(_URL_RE, source, target):
        flags.append("URL_MISMATCH")
    if _heading_loss(source, target):
        flags.append("HEADING_MISMATCH")
    if _missing_numeric_tokens(source, target):
        flags.append("NUMERIC_MISMATCH")

    return FilterResult(
        accepted=not reasons,
        reasons=sorted(set(reasons)),
        quality_flags=sorted(set(flags)),
    )


def _word_count(text: str) -> int:
    return len([p for p in text.split() if p.strip()])


def _normalize_compare(text: str) -> str:
    return " ".join(text.lower().split())


def _is_punct_only(text: str) -> bool:
    candidate = "".join(text.split())
    return bool(candidate) and bool(_PUNCT_ONLY_RE.match(candidate))


def _has_malformed_markers(source: str, target: str) -> bool:
    src = _marker_ids(source)
    if not src:
        return False
    tgt = _marker_ids(target)
    if not tgt:
        return True
    return not set(src).issubset(set(tgt))


def _marker_ids(text: str) -> list[int]:
    ids: list[int] = []
    for match in _WS_MARKER_RE.finditer(text):
        value = match.group(1) or match.group(2)
        if value is None:
            continue
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def _missing_tokens(pattern: re.Pattern[str], source: str, target: str) -> bool:
    source_tokens = _match_tokens(pattern, source)
    if not source_tokens:
        return False
    target_tokens = _match_tokens(pattern, target)
    return not source_tokens.issubset(target_tokens)


def _match_tokens(pattern: re.Pattern[str], text: str) -> set[str]:
    return {m.group(0) for m in pattern.finditer(text)}


def _missing_numeric_tokens(source: str, target: str) -> bool:
    src = set(_NUMBER_RE.findall(source))
    if not src:
        return False
    tgt = set(_NUMBER_RE.findall(target))
    missing = src - tgt
    return len(missing) > 0


def _heading_loss(source: str, target: str) -> bool:
    src = len(_HEADING_RE.findall(source))
    if src == 0:
        return False
    tgt = len(_HEADING_RE.findall(target))
    return tgt < src

