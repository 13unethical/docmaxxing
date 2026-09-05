"""Deterministic deduplication and source grouping."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from services.humanizer_training.config import TrainingExample

_TOKEN_RE = re.compile(r"[a-z0-9]{3,}", re.I)


@dataclass(slots=True)
class DedupeOutcome:
    accepted: list[TrainingExample]
    dropped_exact_pair: int
    dropped_same_source: int
    dropped_near_source: int


def dedupe_examples(examples: list[TrainingExample]) -> DedupeOutcome:
    exact_seen: set[str] = set()
    source_seen: set[str] = set()
    accepted: list[TrainingExample] = []
    dropped_exact_pair = 0
    dropped_same_source = 0
    dropped_near_source = 0

    # Keep deterministic order.
    ordered = sorted(examples, key=lambda ex: (ex.source_hash, ex.dedupe_key))
    near_kept: list[tuple[TrainingExample, set[str]]] = []

    for ex in ordered:
        if ex.dedupe_key in exact_seen:
            dropped_exact_pair += 1
            continue
        if ex.source_hash in source_seen:
            dropped_same_source += 1
            continue

        token_set = _normalized_token_set(ex.source_text)
        if _is_near_duplicate(token_set, near_kept, candidate_text=ex.source_text):
            dropped_near_source += 1
            continue

        exact_seen.add(ex.dedupe_key)
        source_seen.add(ex.source_hash)
        accepted.append(ex)
        near_kept.append((ex, token_set))

    return DedupeOutcome(
        accepted=accepted,
        dropped_exact_pair=dropped_exact_pair,
        dropped_same_source=dropped_same_source,
        dropped_near_source=dropped_near_source,
    )


def make_source_hash(text: str) -> str:
    return _sha256(_normalize_text_for_hash(text))


def make_pair_hash(source_text: str, target_text: str) -> str:
    return _sha256(_normalize_text_for_hash(source_text) + "\n---\n" + _normalize_text_for_hash(target_text))


def make_source_group_key(text: str) -> str:
    """Group key for split leakage prevention (source-cluster identity)."""
    tokens = sorted(_normalized_token_set(text))
    joined = " ".join(tokens[:120])
    return _sha256(joined or _normalize_text_for_hash(text))


def _is_near_duplicate(
    token_set: set[str],
    existing: list[tuple[TrainingExample, set[str]]],
    *,
    candidate_text: str,
) -> bool:
    if not token_set:
        return False
    candidate_norm = _normalize_text_for_hash(candidate_text)
    candidate_words = len(candidate_norm.split())
    if candidate_words < 35:
        return False
    for example, known_set in existing:
        score = _jaccard(token_set, known_set)
        known_norm = _normalize_text_for_hash(example.source_text)
        known_words = len(known_norm.split())
        if known_words < 35:
            continue

        # Additional guards so terminology overlap alone does not drop distinct texts.
        size_ratio = min(candidate_words, known_words) / float(max(candidate_words, known_words))
        if size_ratio < 0.9:
            continue

        seq = SequenceMatcher(a=candidate_norm, b=known_norm).ratio()
        # "Very high confidence" near duplicate:
        # - almost identical sequence (cosmetic edits), OR
        # - very high token overlap + high sequence similarity.
        if seq >= 0.995 and score >= 0.9:
            return True
        if score >= 0.97 and seq >= 0.985:
            return True
    return False


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / float(len(union))


def _normalize_text_for_hash(text: str) -> str:
    return " ".join((text or "").lower().split())


def _normalized_token_set(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(_normalize_text_for_hash(text))}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

