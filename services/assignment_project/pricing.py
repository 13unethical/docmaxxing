"""Assignment project pricing from requirement analysis output.

Price = volume (word count) x difficulty (1-10).

Complexity is captured entirely by the graded ``difficulty`` (the analyzer grades
it 1-10 from ALL requirements: academic level, assignment type, length, sources,
rubric depth, technical demand), so there is no separate level / type / sources
factor. There is no time/urgency multiplier — we cannot change how long an
assignment takes to prepare, so instead we return an *estimated* preparation time
(informational only) alongside the price. Every factor is returned for the UI.
"""

from __future__ import annotations

import re
from typing import Any

# --- volume ----------------------------------------------------------------
# $8 per 1000 words, strictly linear: 500 words -> $4, 100 words -> $0.80.
_BASE_USD_PER_1000_WORDS = 8.0
_DEFAULT_WORDS = 1200

# --- difficulty (1..10) ----------------------------------------------------
# Overall difficulty of the assignment, graded 1-10 from ALL requirements
# (level, type, length, sources, rubric depth, technical/analytical demand).
_DIFFICULTY_MULTIPLIERS = {
    1: 1.00,
    2: 1.10,
    3: 1.20,
    4: 1.35,
    5: 1.50,
    6: 1.70,
    7: 1.90,
    8: 2.15,
    9: 2.45,
    10: 2.80,
}

# --- estimated preparation time (informational, not a price factor) --------
# Minutes needed per 1000 words at difficulty 1; harder work takes longer.
_EST_MINUTES_PER_1000_WORDS = 4.0
_EST_MIN_MINUTES = 3


def _normalize_difficulty(raw: Any) -> int | None:
    """Return a 1..10 difficulty grade from numbers, ratings, or words."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return max(1, min(10, int(round(raw))))
    text = str(raw).strip()
    if not text:
        return None
    # "N/M" or "N out of M" -> rescale to /10.
    ratio = re.search(r"(\d+)\s*(?:/|out of)\s*(\d+)", text.lower())
    if ratio:
        value, scale = int(ratio.group(1)), int(ratio.group(2))
        if scale:
            return max(1, min(10, round(value / scale * 10)))
    # Star ratings are on a 5-point scale -> rescale to /10.
    stars = text.count("★")
    if stars:
        return max(1, min(10, round(stars / 5 * 10)))
    lowered = text.lower()
    text_map = (
        (("very high", "expert", "extremely", "very hard"), 9),
        (("high", "hard", "advanced", "challenging"), 7),
        (("medium", "moderate", "intermediate", "average"), 5),
        (("low", "easy", "basic", "simple", "beginner"), 3),
        (("very low", "trivial"), 2),
    )
    for keywords, value in text_map:
        if any(k in lowered for k in keywords):
            return value
    match = re.search(r"\b([1-9]|10)\b", lowered)
    if match:
        return max(1, min(10, int(match.group(1))))
    return None


def _difficulty_multiplier(stars: int) -> float:
    return _DIFFICULTY_MULTIPLIERS.get(max(1, min(10, stars)), 1.50)


def _estimate_difficulty(requirement: dict[str, Any]) -> int:
    """Fallback grade (1-10) when the analyzer did not return a usable value."""
    score = 5
    level = str(requirement.get("academic_level") or "").lower()
    if any(k in level for k in ("phd", "doctor")):
        score += 3
    elif any(k in level for k in ("master", "postgrad", "graduate")):
        score += 2
    elif any(k in level for k in ("high school", "secondary", "gcse", "school")):
        score -= 2

    type_text = str(requirement.get("assignment_type") or "").lower()
    if any(k in type_text for k in ("dissertation", "thesis", "capstone", "research")):
        score += 2
    if any(k in type_text for k in ("presentation", "slides", "poster")):
        score -= 1

    try:
        minimum_sources = int(requirement.get("minimum_sources") or 0)
    except (TypeError, ValueError):
        minimum_sources = 0
    if minimum_sources >= 20:
        score += 2
    elif minimum_sources >= 10:
        score += 1

    try:
        word_count = int(requirement.get("word_count") or 0)
    except (TypeError, ValueError):
        word_count = 0
    if word_count >= 5000:
        score += 1

    return max(1, min(10, score))


def estimate_preparation_minutes(word_count: int, difficulty_stars: int) -> int:
    """Rough preparation-time estimate in minutes (informational only)."""
    stars = max(1, min(10, int(difficulty_stars)))
    difficulty_factor = 1.0 + (stars - 1) * 0.09  # 1.0 at diff 1 -> ~1.81 at diff 10
    minutes = (word_count / 1000.0) * _EST_MINUTES_PER_1000_WORDS * difficulty_factor
    return max(_EST_MIN_MINUTES, int(round(minutes)))


def _round_multiplier(value: float) -> float:
    return round(value, 3)


def calculate_project_price(
    requirement: dict[str, Any],
    **_ignored: Any,
) -> dict[str, Any]:
    """Return a pricing breakdown and the final USD amount.

    Price depends only on volume (word count) and difficulty (1-10). Extra
    keyword arguments (e.g. legacy ``priority``) are accepted and ignored.
    """
    # --- volume (linear, no minimum) ---
    word_count = int(requirement.get("word_count") or requirement.get("estimatedWordCount") or _DEFAULT_WORDS)
    word_count = max(word_count, 1)
    base = (word_count / 1000.0) * _BASE_USD_PER_1000_WORDS

    # --- difficulty (the single complexity signal) ---
    difficulty_stars = _normalize_difficulty(requirement.get("difficulty"))
    difficulty_estimated = difficulty_stars is None
    if difficulty_estimated:
        difficulty_stars = _estimate_difficulty(requirement)
    difficulty_multiplier = _difficulty_multiplier(difficulty_stars)

    amount_usd = round(base * difficulty_multiplier, 2)
    estimated_minutes = estimate_preparation_minutes(word_count, difficulty_stars)

    return {
        "amount_usd": amount_usd,
        "currency": "USD",
        "word_count": word_count,
        "base_usd": round(base, 2),
        "assignment_type": requirement.get("assignment_type"),
        "difficulty_stars": difficulty_stars,
        "difficulty_multiplier": _round_multiplier(difficulty_multiplier),
        "difficulty_estimated": difficulty_estimated,
        "estimated_minutes": estimated_minutes,
    }
