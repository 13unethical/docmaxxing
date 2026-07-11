"""Assignment project pricing from requirement analysis output."""

from __future__ import annotations

from typing import Any

_BASE_USD_PER_1000_WORDS = 15.0
_MINIMUM_USD = 29.0

_PRIORITY_MULTIPLIERS = {
    "standard": 1.0,
    "express": 1.35,
    "urgent": 1.75,
}


def _difficulty_multiplier(difficulty: str | None) -> float:
    if not difficulty:
        return 1.0
    stars = difficulty.count("★")
    if stars >= 5:
        return 1.45
    if stars >= 4:
        return 1.25
    if stars >= 3:
        return 1.1
    lowered = difficulty.lower()
    if "high" in lowered or "hard" in lowered:
        return 1.25
    if "medium" in lowered:
        return 1.1
    return 1.0


def calculate_project_price(
    requirement: dict[str, Any],
    *,
    priority: str = "standard",
) -> dict[str, Any]:
    """Return pricing breakdown and final USD amount."""
    word_count = int(requirement.get("word_count") or requirement.get("estimatedWordCount") or 1200)
    word_count = max(word_count, 500)
    sections = requirement.get("required_sections") or []
    section_count = len(sections) if isinstance(sections, list) else 0
    difficulty = str(requirement.get("difficulty") or "")
    priority_key = (priority or "standard").strip().lower()
    priority_multiplier = _PRIORITY_MULTIPLIERS.get(priority_key, 1.0)

    base = (word_count / 1000.0) * _BASE_USD_PER_1000_WORDS
    if section_count > 6:
        base *= 1.08
    elif section_count > 4:
        base *= 1.04

    difficulty_multiplier = _difficulty_multiplier(difficulty)
    subtotal = base * difficulty_multiplier * priority_multiplier
    amount_usd = round(max(subtotal, _MINIMUM_USD), 2)

    return {
        "amount_usd": amount_usd,
        "currency": "USD",
        "word_count": word_count,
        "section_count": section_count,
        "priority": priority_key,
        "priority_multiplier": priority_multiplier,
        "difficulty_multiplier": difficulty_multiplier,
        "base_usd": round(base, 2),
    }
