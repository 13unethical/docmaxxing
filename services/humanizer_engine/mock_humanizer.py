"""Provider-agnostic text humanizer protocol and mock implementation."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

from services.humanizer_engine.constants import MIN_HUMANIZE_CHARS


class TextHumanizer(Protocol):
    def humanize(self, text: str, *, academic_tone: str = "formal") -> str:
        ...


class MockTextHumanizer:
    VERSION = "mock-1.0"

    def humanize(self, text: str, *, academic_tone: str = "formal") -> str:
        if not text.strip():
            return text
        if len(text.strip()) < MIN_HUMANIZE_CHARS:
            return text.strip()

        output = text.strip()
        replacements = [
            (r"\bFurthermore,\b", "Moreover,"),
            (r"\bHowever,\b", "Nevertheless,"),
            (r"\bIn conclusion,\b", "To conclude,"),
            (r"\bIt is important to note that\b", "Notably,"),
            (r"\bThis essay\b", "This paper"),
            (r"\butilize\b", "use"),
            (r"\bleverage\b", "apply"),
        ]
        for pattern, replacement in replacements:
            output = re.sub(pattern, replacement, output, flags=re.IGNORECASE)

        if academic_tone.lower().startswith("formal") and not output.endswith("."):
            output += "."

        return output

    def estimate_ai_score(self, text: str) -> int:
        from services.humanizer_engine.heading_utils import is_heading_only

        if not text.strip():
            return 0
        if is_heading_only(text):
            return 12
        digest = hashlib.md5(text.encode("utf-8")).hexdigest()
        base = 52 + (int(digest[:2], 16) % 33)
        if len(text) > 220:
            base += 8
        if re.search(r"\b(furthermore|however|important to note)\b", text, re.IGNORECASE):
            base += 6
        return min(96, base)
