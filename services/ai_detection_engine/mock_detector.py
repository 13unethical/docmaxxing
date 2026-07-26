"""Provider-agnostic AI detection protocol and mock implementation."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol


class AIDetector(Protocol):
    def detect(self, text: str) -> float:
        """Return AI probability score as percentage 0-100."""
        ...


class MockAIDetector:
    VERSION = "mock-1.0"

    def detect(self, text: str) -> float:
        from services.humanizer_engine.heading_utils import is_heading_only

        if not text or not text.strip():
            return 0.0
        if is_heading_only(text):
            return 2.0

        digest = hashlib.md5(text.encode("utf-8")).hexdigest()
        base = 8 + (int(digest[:2], 16) % 18)
        if len(text) > 200:
            base += 6
        if re.search(r"\b(furthermore|however|important to note|objective)\b", text, re.IGNORECASE):
            base += 10
        if re.search(r"\[Revision:", text):
            base += 4
        if text.startswith("[Rehumanized]"):
            base = max(3.0, base - 14)
        if "Nevertheless," in text or "Moreover," in text:
            base = max(4.0, base - 6)
        return min(96.0, float(base))
