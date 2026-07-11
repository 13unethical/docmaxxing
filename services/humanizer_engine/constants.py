"""Humanizer provider limits and ZeroGPT mode settings."""

from __future__ import annotations

import os

MAX_WORDS_PER_INPUT = int(os.environ.get("ZEROGPT_MAX_WORDS_PER_INPUT") or "5000")
TRANSFORM_CHUNK_WORDS = int(os.environ.get("ZEROGPT_TRANSFORM_CHUNK_WORDS") or "4000")
MIN_HUMANIZE_CHARS = 50

ZEROGPT_HUMANIZER_MODES = frozenset({"humanize", "paraphrase", "advanced_paraphrase"})
DEFAULT_HUMANIZER_MODE = (
    os.environ.get("ZEROGPT_HUMANIZER_MODE") or "humanize"
).strip().lower()
if DEFAULT_HUMANIZER_MODE not in ZEROGPT_HUMANIZER_MODES:
    DEFAULT_HUMANIZER_MODE = "humanize"

ZEROGPT_PARAPHRASE_TONES = frozenset(
    {
        "Standard",
        "Academic",
        "Fluent",
        "Formal",
        "Simple",
        "Creative",
        "Engineer",
        "Doctor",
        "Lawyer",
        "Teenager",
    }
)


def normalize_humanizer_mode(mode: str | None) -> str:
    normalized = (mode or DEFAULT_HUMANIZER_MODE).strip().lower()
    if normalized in ZEROGPT_HUMANIZER_MODES:
        return normalized
    return DEFAULT_HUMANIZER_MODE


def map_academic_tone_to_zerogpt(academic_tone: str) -> str:
    tone = (academic_tone or "Academic").strip()
    if tone in ZEROGPT_PARAPHRASE_TONES:
        return tone
    normalized = tone.lower()
    aliases = {
        "academic": "Academic",
        "formal": "Formal",
        "standard": "Standard",
        "simple": "Simple",
        "creative": "Creative",
        "fluent": "Fluent",
        "natural": "Fluent",
        "professional": "Formal",
    }
    return aliases.get(normalized, "Academic")
