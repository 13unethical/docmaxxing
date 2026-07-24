"""StealthWriter-backed text humanizer (Legacy 5.1)."""

from __future__ import annotations

import os
from typing import Any, Callable

from services.browser.providers.stealthwriter import DEFAULT_STEALTHWRITER_MODEL
from services.humanizer_engine.constants import MIN_HUMANIZE_CHARS
from services.humanizer_engine.mock_humanizer import MockTextHumanizer
from services.humanizer_engine.zerogpt_humanizer import split_text_by_word_limit

# Match paid StealthWriter input cap (5000 words); override via env if needed.
_STEALTHWRITER_MAX_WORDS = int(os.environ.get("STEALTHWRITER_MAX_WORDS") or "5000")


class StealthWriterTextHumanizer:
    """Assignment / pipeline humanizer that drives StealthWriter Legacy 5.1."""

    VERSION = "stealthwriter-legacy-5.1"

    def __init__(
        self,
        *,
        model: str | None = None,
        max_words: int | None = None,
        humanize_fn: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.model = (model or DEFAULT_STEALTHWRITER_MODEL).strip() or DEFAULT_STEALTHWRITER_MODEL
        self.max_words = max(50, int(max_words if max_words is not None else _STEALTHWRITER_MAX_WORDS))
        self._humanize_fn = humanize_fn
        self._fallback_scorer = MockTextHumanizer()

    def humanize(self, text: str, *, academic_tone: str = "formal") -> str:
        del academic_tone  # StealthWriter UI has no tone parameter for Legacy 5.1.
        if not text.strip():
            return text
        if text.strip().startswith("## "):
            return text.strip()
        if len(text.strip()) < MIN_HUMANIZE_CHARS:
            return text.strip()

        chunks = split_text_by_word_limit(text, max_words=self.max_words)
        outputs: list[str] = []
        for chunk in chunks:
            outputs.append(self._humanize_chunk(chunk))
        return "\n\n".join(outputs)

    def _humanize_chunk(self, chunk: str) -> str:
        fn = self._humanize_fn
        if fn is None:
            from services.browser.providers.stealthwriter import humanize_text as fn

        result = fn(chunk, model=self.model)
        if not result.get("success"):
            error = result.get("error") or result.get("message") or "StealthWriter humanize failed"
            raise ValueError(str(error))
        output = (result.get("humanized_text") or "").strip()
        if not output:
            raise ValueError("StealthWriter humanizer returned empty text")
        return output

    def estimate_ai_score(self, text: str) -> int:
        return self._fallback_scorer.estimate_ai_score(text)
