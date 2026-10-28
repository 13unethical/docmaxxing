"""Section titles as written in briefs ("Section 1: Executive Summary (Approx. 200 words)")."""

from __future__ import annotations

import re

# Labels that only number a part of the brief, so the real name follows the colon.
_GENERIC_LABEL_RE = re.compile(
    r"^(?:optional\s+)?(?:section|part|task|question|chapter|unit|step|stage|phase|activity|"
    r"(?:journal\s+)?entry|appendix)(?:\s*[\w.]{1,5})?$",
    re.I,
)
_WORD_BUDGET_SUFFIX_RE = re.compile(
    r"\s*(?:\([^()]*\)|[–\-]\s*(?:approx\.?\s*)?[\d,]{2,6}\s*words?)\s*$",
    re.I,
)
WORD_BUDGET_RE = re.compile(
    r"(?:[–\-]\s*|\()\s*(?:approx\.?|approximately|about|around|c\.|max\.?|maximum|up to)?\s*"
    r"(\d{2,4})\s*words?\b",
    re.I,
)


def strip_word_budget(text: str) -> str:
    """Drop a trailing "(Approx. 200 words)" / "(not included in word count)" / "– 200 words"."""
    return _WORD_BUDGET_SUFFIX_RE.sub("", str(text or "")).strip()


def section_name(title: str) -> str:
    """Name without a numbering label: "Section 2: Introduction to X" -> "Introduction to X"."""
    heading = section_heading(title)
    return heading.split(":", 1)[1].strip() if ":" in heading else heading


def section_heading(raw: str) -> str:
    """Heading to print for a required section.

    "Section 1: Executive Summary (Approx. 200 words)" -> "Section 1: Executive Summary";
    "Introduction: set the scene" -> "Introduction" (text after the colon is a description).
    """
    text = strip_word_budget(re.sub(r"\s+", " ", str(raw or "")).strip())
    if ":" not in text:
        return text
    head, tail = (part.strip() for part in text.split(":", 1))
    tail = strip_word_budget(tail)
    if _GENERIC_LABEL_RE.match(head) and tail and len(tail.split()) <= 8:
        return f"{head}: {tail}"
    return head or tail


def _key_matches(title: str, key: str) -> bool:
    if title == key:
        return True
    # "Section 1" must match "Section 1: Executive Summary" but not "Section 10: ...".
    if title.startswith(key) and not title[len(key) : len(key) + 1].isalnum():
        return True
    if key.startswith(title) and not key[len(title) : len(title) + 1].isalnum():
        return True
    name = title.split(":", 1)[1].strip() if ":" in title else ""
    return bool(name) and name == key


def budget_for(title: str, budgets: dict[str, int]) -> int | None:
    """Per-section word budget for a heading, tolerating short or long forms of the key."""
    if title in budgets:
        return int(budgets[title])
    wanted = section_heading(title).lower()
    for key, value in budgets.items():
        if _key_matches(wanted, section_heading(key).lower()):
            return int(value)
    return None
