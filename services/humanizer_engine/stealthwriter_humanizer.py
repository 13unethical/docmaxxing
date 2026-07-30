"""StealthWriter-backed text humanizer (Legacy 5.1)."""

from __future__ import annotations

import os
from typing import Any, Callable

from services.browser.providers.stealthwriter import DEFAULT_STEALTHWRITER_MODEL
from services.humanizer_engine.constants import MIN_HUMANIZE_CHARS
from services.humanizer_engine.heading_utils import (
    join_body_and_references,
    protect_markdown_headings,
    restore_markdown_headings,
    split_off_references,
)
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
        if len(text.strip()) < MIN_HUMANIZE_CHARS:
            return text.strip()

        # All prose goes through StealthWriter. Headings are temporarily protected
        # so structure survives, then restored after humanization. References never
        # enter the provider — bibliography must stay verbatim.
        body, refs = split_off_references(text)
        if not body.strip():
            return join_body_and_references(body, refs)

        protected, headings = protect_markdown_headings(body)
        chunks = split_text_by_word_limit(protected, max_words=self.max_words)
        outputs: list[str] = []
        for chunk in chunks:
            outputs.append(self._humanize_chunk(chunk))
        humanized_body = restore_markdown_headings("\n\n".join(outputs), headings)
        return join_body_and_references(humanized_body, refs)

    def _humanize_chunk(self, chunk: str) -> str:
        fn = self._humanize_fn
        last_error = "StealthWriter humanize failed"
        # Paid plans still occasionally return NO_CHANGE when the UI click did not
        # start generation — retry the full browser flow before failing hard.
        for attempt in range(1, 4):
            if fn is None:
                from services.browser.providers.stealthwriter import humanize_text
                from services.browser.thread_affinity import run_on_browser_thread

                def _call() -> dict[str, Any]:
                    return humanize_text(chunk, model=self.model)

                result = run_on_browser_thread(_call, timeout=240)
            else:
                result = fn(chunk, model=self.model)

            if result.get("success"):
                output = (result.get("humanized_text") or "").strip()
                if output and output != chunk.strip():
                    return output
                if output:
                    # Identical output is not acceptable for assignment pipeline.
                    last_error = "StealthWriter returned unchanged text"
                else:
                    last_error = "StealthWriter humanizer returned empty text"
            else:
                error = str(result.get("error") or "")
                message = str(result.get("message") or "")
                last_error = message or error or last_error
                if error.upper() != "NO_CHANGE" and "NO_CHANGE" not in error.upper():
                    raise ValueError(last_error)

            if attempt < 3:
                print(
                    f"[stealthwriter] humanize attempt {attempt} failed ({last_error}) — retrying",
                    flush=True,
                )
        raise ValueError(last_error)

    def estimate_ai_score(self, text: str) -> int:
        return self._fallback_scorer.estimate_ai_score(text)
