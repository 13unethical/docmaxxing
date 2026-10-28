"""Russian humanizer: swap Cyrillic letters that look like Latin ones.

Only the pairs below are changed. Every other character stays as it was.
"""

from __future__ import annotations

_RU_TO_LATIN = str.maketrans(
    {
        "А": "A",
        "а": "a",
        "О": "O",
        "о": "o",
        "Х": "X",
        "х": "x",
        "С": "C",
        "с": "c",
        "Е": "E",
        "е": "e",
    }
)


def humanize_ru(text: str) -> str:
    return str(text or "").translate(_RU_TO_LATIN)
