"""ZeroGPT-only text humanizer."""

from __future__ import annotations

from services.humanizer_engine.constants import (
    MAX_WORDS_PER_INPUT,
    MIN_HUMANIZE_CHARS,
    TRANSFORM_CHUNK_WORDS,
    DEFAULT_HUMANIZER_MODE,
    map_academic_tone_to_zerogpt,
    normalize_humanizer_mode,
)
from services.humanizer_engine.mock_humanizer import MockTextHumanizer
from services.zerogpt_business.client import ZeroGPTClient, ZeroGPTError
from services.zerogpt_business.providers import (
    ZeroGPTDetectionProvider,
    ZeroGPTHumanizerProvider,
    ZeroGPTProviderError,
)

_MODE_VERSIONS = {
    "advanced_paraphrase": "zerogpt-advanced-paraphrase-1.0",
    "paraphrase": "zerogpt-paraphrase-1.0",
    "humanize": "zerogpt-humanizer-1.0",
}


def count_words(text: str) -> int:
    return len([part for part in (text or "").split() if part.strip()])


def split_text_by_word_limit(text: str, *, max_words: int = MAX_WORDS_PER_INPUT) -> list[str]:
    words = (text or "").split()
    if len(words) <= max_words:
        return [text]
    chunks: list[str] = []
    for index in range(0, len(words), max_words):
        chunks.append(" ".join(words[index : index + max_words]))
    return chunks


class ZeroGPTTextHumanizer:
    VERSION = _MODE_VERSIONS[DEFAULT_HUMANIZER_MODE]

    def __init__(self, client: ZeroGPTClient | None = None, *, mode: str | None = None) -> None:
        self.client = client or ZeroGPTClient()
        self.mode = normalize_humanizer_mode(mode)
        self.VERSION = _MODE_VERSIONS[self.mode]
        self._humanizer = ZeroGPTHumanizerProvider(client=self.client)
        self._detection = ZeroGPTDetectionProvider(client=self.client)
        self._fallback_scorer = MockTextHumanizer()

    def humanize(self, text: str, *, academic_tone: str = "formal", mode: str | None = None) -> str:
        if not text.strip():
            return text
        if len(text.strip()) < MIN_HUMANIZE_CHARS:
            return text.strip()

        from services.humanizer_engine.heading_utils import (
            protect_markdown_headings,
            restore_markdown_headings,
        )

        selected_mode = normalize_humanizer_mode(mode or self.mode)
        tone = map_academic_tone_to_zerogpt(academic_tone)
        chunk_words = min(MAX_WORDS_PER_INPUT, TRANSFORM_CHUNK_WORDS)
        # Entire draft body is humanized; markdown headings are protected then restored.
        protected, headings = protect_markdown_headings(text)
        chunks = split_text_by_word_limit(protected, max_words=chunk_words)
        outputs: list[str] = []
        for chunk in chunks:
            outputs.append(self._humanize_chunk(chunk, tone=tone, mode=selected_mode))
        return restore_markdown_headings("\n\n".join(outputs), headings)

    def _humanize_chunk(self, chunk: str, *, tone: str, mode: str) -> str:
        result = self._humanizer.humanize(chunk, tone=tone, mode=mode)
        output = (result.text or "").strip()
        if not output:
            raise ValueError("ZeroGPT humanizer returned empty text")
        return output

    def estimate_ai_score(self, text: str) -> int:
        from services.humanizer_engine.heading_utils import is_heading_only

        if not text.strip():
            return 0
        if is_heading_only(text):
            return 12
        try:
            detection = self._detection.detect(text)
            return int(round(float(detection.ai_score)))
        except (ZeroGPTError, ZeroGPTProviderError, ValueError, TypeError):
            return self._fallback_scorer.estimate_ai_score(text)
