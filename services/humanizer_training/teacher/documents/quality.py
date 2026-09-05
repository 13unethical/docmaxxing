"""Document-level quality checks for offline teacher collection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from services.humanizer_engine.heading_utils import split_off_references

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?%")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_URL_RE = re.compile(r"https?://[^\s)]+", re.I)
_CITATION_RE = re.compile(r"\([^)]*?\d{4}[^)]*?\)|\[\d+\]")
_HEADING_RE = re.compile(r"(?m)^##\s+.+$")


@dataclass(slots=True)
class DocumentQualityCheck:
    accepted: bool
    reject_reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def evaluate_teacher_document(
    source_text: str,
    teacher_text: str,
    *,
    max_words: int = 5000,
    source_refs: str = "",
    teacher_refs: str = "",
    chunks: list[dict] | None = None,
) -> DocumentQualityCheck:
    source = (source_text or "").strip()
    target = (teacher_text or "").strip()
    rejects: list[str] = []
    flags: list[str] = []

    if not source:
        rejects.append("EMPTY_SOURCE")
        return DocumentQualityCheck(accepted=False, reject_reasons=rejects, flags=flags)
    if not target:
        rejects.append("EMPTY_TEACHER")
        return DocumentQualityCheck(accepted=False, reject_reasons=rejects, flags=flags)

    src_words = _word_count(source)
    if src_words > max_words:
        rejects.append("DOCUMENT_TOO_LARGE")

    if _normalize(source) == _normalize(target):
        rejects.append("UNCHANGED")

    tgt_words = _word_count(target)
    if src_words > 0:
        ratio = tgt_words / float(src_words)
        if ratio < 0.4 or ratio > 2.7:
            rejects.append("EXTREME_LENGTH_CHANGE")

    if target.endswith("...") or target.endswith("…"):
        rejects.append("TRUNCATION")
    if src_words >= 80 and tgt_words < 30:
        rejects.append("TRUNCATION")

    body_src, refs_src = split_off_references(source)
    body_tgt, refs_tgt = split_off_references(target)
    if source_refs:
        refs_src = source_refs
    if teacher_refs:
        refs_tgt = teacher_refs

    if refs_src.strip():
        if _normalize(refs_src) != _normalize(refs_tgt):
            flags.append("REFERENCES_CHANGED")
        # Body should not suddenly contain the full references block title as mixed content
        # when original refs existed and teacher refs are empty-ish.
        if refs_tgt.strip() and "## " in body_tgt and "reference" in body_tgt.lower():
            # Soft signal only when refs also remain (possible mixing)
            if _normalize(refs_src) in _normalize(body_tgt):
                flags.append("BODY_REFERENCE_MIXING")

    if _missing_tokens(_HEADING_RE, body_src, body_tgt):
        flags.append("HEADING_MISMATCH")
    if _missing_tokens(_CITATION_RE, body_src, body_tgt):
        flags.append("CITATION_MISMATCH")
    if _missing_tokens(_YEAR_RE, body_src, body_tgt):
        flags.append("YEAR_MISMATCH")
    if _missing_tokens(_PERCENT_RE, body_src, body_tgt):
        flags.append("PERCENT_MISMATCH")
    if _missing_tokens(_URL_RE, body_src, body_tgt):
        flags.append("URL_MISMATCH")
    if _missing_tokens(_NUMBER_RE, body_src, body_tgt):
        flags.append("NUMERIC_MISMATCH")

    chunk_flags = _evaluate_chunks(chunks or [])
    flags.extend(chunk_flags)

    return DocumentQualityCheck(
        accepted=not rejects,
        reject_reasons=sorted(set(rejects)),
        flags=sorted(set(flags)),
    )


def _evaluate_chunks(chunks: list[dict]) -> list[str]:
    if not chunks:
        return []
    flags: list[str] = []
    indexes = [int(c.get("index", -1)) for c in chunks]
    if any(i < 0 for i in indexes):
        flags.append("MISSING_CHUNK")
    expected = list(range(len(chunks)))
    if sorted(indexes) != expected:
        if len(set(indexes)) != len(indexes):
            flags.append("DUPLICATE_CHUNK")
        if indexes != expected:
            flags.append("WRONG_CHUNK_ORDER")
    statuses = [str(c.get("status") or "") for c in chunks]
    if any(s in {"failed", "missing"} for s in statuses):
        flags.append("MISSING_CHUNK")
    # Overlap heuristic: identical consecutive source texts
    sources = [str(c.get("source_text") or "") for c in chunks]
    for left, right in zip(sources, sources[1:]):
        if left and right and left == right:
            flags.append("CHUNK_OVERLAP")
            break
    return flags


def _missing_tokens(pattern: re.Pattern[str], source: str, target: str) -> bool:
    src = {m.group(0) for m in pattern.finditer(source or "")}
    if not src:
        return False
    tgt = {m.group(0) for m in pattern.finditer(target or "")}
    return not src.issubset(tgt)


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _word_count(text: str) -> int:
    return len([p for p in (text or "").split() if p.strip()])
