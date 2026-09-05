"""Conservative text cleanup for training examples."""

from __future__ import annotations

import re

from services.dataset_logger import clean_text_for_ml

_MULTI_BLANK_LINES_RE = re.compile(r"\n{3,}")
_TRAILING_SPACES_RE = re.compile(r"[ \t]+$", re.MULTILINE)


def normalize_text(text: str | None) -> str:
    """Normalize line endings + obvious whitespace noise only."""
    cleaned = clean_text_for_ml(text)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _TRAILING_SPACES_RE.sub("", cleaned)
    cleaned = _MULTI_BLANK_LINES_RE.sub("\n\n", cleaned)
    return cleaned.strip()

