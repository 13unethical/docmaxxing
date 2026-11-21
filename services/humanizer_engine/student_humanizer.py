"""Our own humanizer: the fine-tuned student model served behind an OpenAI-compatible endpoint.

Prose paragraphs are grouped into ~600-word chunks (the size the model was trained on) and
rewritten in parallel. List items (short bullets and long numbered prose) are rewritten too.
Only true document structure stays verbatim: marked headings (markdown / bold-wrapped), tables,
figure markers, addresses, and the references block. Plain short lines are not guessed as
titles. Any chunk that fails the quality checks is retried, and if it still fails the whole
call raises so the caller can return an error (StealthWriter is not used as a fallback).

pick="document": each chunk is written once, then the AI detector scores the whole text in its
sentence windows and only the chunks holding flagged sentences are rewritten, judged in context.
"""

from __future__ import annotations

import bisect
import json
import logging
import os
import random
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from services.humanizer_engine.constants import MIN_HUMANIZE_CHARS
from services.humanizer_engine.heading_utils import (
    is_explicit_heading_text,
    is_references_section_title,
    is_sentence_start_fragment,
    join_body_and_references,
    split_off_references,
    title_core,
)
from services.humanizer_engine.mock_humanizer import MockTextHumanizer
from services.humanizer_engine.rich_html import (
    list_marker_ok,
    restore_list_marker,
    split_list_marker,
    unwrap_prose_newlines,
)

log = logging.getLogger(__name__)

PROVIDER = "DocMaxxing"
CHUNK_WORDS = 600
RATIO_RANGE = (0.6, 1.9)
MAX_JACCARD = 0.9
# Below this the rewrite drifted onto another topic (names/facts swapped out).
MIN_JACCARD = 0.28
ATTEMPTS = 3
# Sampling the Turnitin checks were run with; greedy decoding scored 40% AI.
TEMPERATURE = 1.0
TOP_P = 0.9
WARMUP_EVERY_SECONDS = 60.0
# Long enough for a scaled-to-zero server to boot, so the wake-up is never cut short.
WARMUP_TIMEOUT_SECONDS = 300.0
# A memory-snapshot restore takes ~10 s, so poll often while waiting for it.
BOOT_POLL_SECONDS = 2.0
MAX_CANDIDATES = 16
# pick="detector": a chunk whose best variant the AI detector still scores above this gets
# ``refine_sampling`` more variants before the final choice.
REFINE_ABOVE = 0.3
# When pick=detector: stop sampling more variants once the best score is at/below this.
# 0 disables early stop. Cuts GPU on easy chunks without changing hard ones.
EARLY_STOP_BELOW = 0.15
# Default pool: one temperature (higher rewrite diversity). Mix 1.0+1.2 was rarely winning on 1.0.
DEFAULT_SAMPLING = ((1.2, 8),)
# Extra variants for conclusion paragraphs (Turnitin flags them ~2–3× more often).
DEFAULT_CONCLUSION_SAMPLING = ((1.2, 16),)
# Fast mode (opt-in): fewer candidates, refine only when the chunk still looks AI.
FAST_SAMPLING = ((1.2, 4),)
FAST_REFINE_SAMPLING = ((1.2, 12),)
FAST_REFINE_ABOVE = 0.35
# Cap parallel chunk rewrites so vLLM is not flooded (n candidates × chunks).
DEFAULT_MAX_WORKERS = 8
# pick="document": rounds of "score the whole text, rewrite the flagged chunks", within this many seconds.
DOC_ROUNDS = 5
DOC_BUDGET_SECONDS = 90.0
# Stricter than the detector's default cut: rewrite a chunk if any sentence is above this.
DOC_FLAG_ABOVE = 0.22
# First-pass pool for document mode (still cheaper than full detector pick).
DOCUMENT_SAMPLING = ((1.2, 4),)
DOCUMENT_REFINE_SAMPLING = ((1.2, 16),)

_WORD = re.compile(r"[a-z0-9']+")
_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
_LETTER = re.compile(r"[^\W\d_]")
# Headings / fences / table rows — never rewritten. Every list item is rewritten (Turnitin flags
# both short bullets and long "1. Name: prose…" lines when left as AI paste).
_STRUCTURAL_LINE = re.compile(r"^\s*(#{1,6}\s|\||```)")
_LIST_ITEM_LINE = re.compile(r"^\s*(?:[-*•+]\s|\d+[.)]\s)")
_VERBATIM_LINE = re.compile(r"^\s*(#{1,6}\s|\||```|[-*•+]\s|\d+[.)]\s)")
_SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]]*\s*$")
# Marked headings only (``## …`` / ``**…**``); plain short lines are rewritten.
TITLE_MAX_WORDS = 12
# Text pasted from a PDF keeps its line breaks: lines of at most this many characters, the last line of
# each paragraph shorter than the rest.
WRAP_MAX_CHARS = 130
WRAP_FULL_LINE = 0.8
# A short piece the model always returns verbatim (a caption, a stray line) is kept rather than failing the text.
KEEP_UNCHANGED_MAX_WORDS = 30


class StudentHumanizerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StudentConfig:
    url: str
    api_key: str
    model: str
    share: float
    level: int
    timeout: float
    chunk_words: int = CHUNK_WORDS
    probe_timeout: float = 3.0
    events_log: str = ""
    temperature: float = TEMPERATURE
    # Variants sampled per chunk; the best one by ``pick`` is kept.
    candidates: int = 1
    pick: str = "changed"
    # (temperature, variants) per request; overrides temperature/candidates when set.
    sampling: tuple[tuple[float, int], ...] = ()
    refine_above: float = REFINE_ABOVE
    refine_sampling: tuple[tuple[float, int], ...] = ()
    # Extra variants always sampled for conclusion paragraphs (Turnitin flags ~2/3 of them vs ~1/4 of the rest).
    conclusion_sampling: tuple[tuple[float, int], ...] = ()
    # Detector pick: skip remaining waves / refine when best AI prob is already this low (0 = off).
    early_stop_below: float = EARLY_STOP_BELOW
    doc_rounds: int = DOC_ROUNDS
    doc_budget: float = DOC_BUDGET_SECONDS
    # pick=document: treat a sentence as flagged above this AI prob (lower = more rewrites).
    doc_flag_above: float = DOC_FLAG_ABOVE

    @property
    def configured(self) -> bool:
        return bool(self.url and self.api_key)

    @property
    def sampling_plan(self) -> tuple[tuple[float, int], ...]:
        return self.sampling or ((self.temperature, self.candidates),)


def parse_sampling(raw: str) -> tuple[tuple[float, int], ...]:
    """"1.0:4,1.2:4" -> ((1.0, 4), (1.2, 4)); malformed parts are skipped."""
    plan = []
    for part in (raw or "").split(","):
        temperature, _, n = part.strip().partition(":")
        try:
            plan.append((max(0.1, min(2.0, float(temperature))), max(1, min(MAX_CANDIDATES, int(n or 1)))))
        except ValueError:
            continue
    return tuple(plan)


def student_config() -> StudentConfig:
    def _float(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name) or default)
        except ValueError:
            return default

    return StudentConfig(
        url=(os.environ.get("HUMANIZER_STUDENT_URL") or "").strip().rstrip("/"),
        api_key=(os.environ.get("HUMANIZER_STUDENT_KEY") or "").strip(),
        model=(os.environ.get("HUMANIZER_STUDENT_MODEL") or "humanizer-v1").strip(),
        share=min(1.0, max(0.0, _float("HUMANIZER_STUDENT_SHARE", 1.0))),
        level=max(1, min(10, int(_float("HUMANIZER_STUDENT_LEVEL", 8)))),
        timeout=max(10.0, _float("HUMANIZER_STUDENT_TIMEOUT", 90.0)),
        chunk_words=max(80, int(_float("HUMANIZER_STUDENT_CHUNK_WORDS", CHUNK_WORDS))),
        probe_timeout=max(0.5, _float("HUMANIZER_STUDENT_PROBE_TIMEOUT", 3.0)),
        events_log=(os.environ.get("HUMANIZER_STUDENT_EVENTS_LOG") or "").strip(),
        temperature=max(0.1, min(2.0, _float("HUMANIZER_STUDENT_TEMPERATURE", TEMPERATURE))),
        candidates=max(1, min(MAX_CANDIDATES, int(_float("HUMANIZER_STUDENT_CANDIDATES", 1)))),
        pick=(os.environ.get("HUMANIZER_STUDENT_PICK") or "document").strip().lower(),
        sampling=parse_sampling(os.environ.get("HUMANIZER_STUDENT_SAMPLING") or "")
        or (
            DOCUMENT_SAMPLING
            if (os.environ.get("HUMANIZER_STUDENT_PICK") or "document").strip().lower() == "document"
            else DEFAULT_SAMPLING
        ),
        refine_above=_float(
            "HUMANIZER_STUDENT_REFINE_ABOVE",
            0.22
            if (os.environ.get("HUMANIZER_STUDENT_PICK") or "document").strip().lower() == "document"
            else REFINE_ABOVE,
        ),
        refine_sampling=parse_sampling(os.environ.get("HUMANIZER_STUDENT_REFINE_SAMPLING") or "")
        or (
            DOCUMENT_REFINE_SAMPLING
            if (os.environ.get("HUMANIZER_STUDENT_PICK") or "document").strip().lower() == "document"
            else ()
        ),
        conclusion_sampling=parse_sampling(os.environ.get("HUMANIZER_STUDENT_CONCLUSION_SAMPLING") or "")
        or DEFAULT_CONCLUSION_SAMPLING,
        early_stop_below=max(0.0, _float("HUMANIZER_STUDENT_EARLY_STOP", EARLY_STOP_BELOW)),
        doc_rounds=max(0, int(_float("HUMANIZER_STUDENT_DOC_ROUNDS", DOC_ROUNDS))),
        doc_budget=max(0.0, _float("HUMANIZER_STUDENT_DOC_BUDGET", DOC_BUDGET_SECONDS)),
        doc_flag_above=max(0.05, _float("HUMANIZER_STUDENT_DOC_FLAG_ABOVE", DOC_FLAG_ABOVE)),
    )


def student_config_for_mode(mode: str | None = None) -> StudentConfig:
    """Return config for ``quality`` (default) or opt-in ``fast`` sampling."""
    cfg = student_config()
    if (mode or "").strip().lower() != "fast":
        return cfg
    return replace(
        cfg,
        sampling=FAST_SAMPLING,
        refine_sampling=FAST_REFINE_SAMPLING,
        refine_above=FAST_REFINE_ABOVE,
    )


def student_max_workers() -> int:
    try:
        return max(1, min(32, int(os.environ.get("HUMANIZER_STUDENT_MAX_WORKERS") or DEFAULT_MAX_WORKERS)))
    except ValueError:
        return DEFAULT_MAX_WORKERS


def system_prompt(level: int) -> str:
    """Must match the prompt the model was trained with (services/humanizer_training/section_sft.py)."""
    return (
        "Rewrite the user's text so it reads like natural writing by a student. Keep the meaning, "
        "facts, numbers, names, in-text citations and paragraph breaks. Do not add headings, "
        f"comments or new content. Rewrite strength: {int(level)}/10."
    )


def is_english(text: str) -> bool:
    letters = len(_LETTER.findall(text))
    return letters > 0 and len(_CYRILLIC.findall(text)) / letters < 0.2


def repair_mojibake(text: str) -> str:
    """Undo UTF-8→Latin-1 mojibake (Ð/Ñ… from Cyrillic). No-op when text is clean."""
    if not text:
        return text
    markers = text.count("Ð") + text.count("Ñ") + text.count("Â")
    if markers < 3:
        return text
    try:
        fixed = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    if fixed.count("Ð") + fixed.count("Ñ") + fixed.count("Â") < markers:
        return fixed
    return text


def _wc(text: str) -> int:
    return len(text.split())


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _jaccard(a: str, b: str) -> float:
    left, right = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    return len(left & right) / len(left | right) if left | right else 1.0


def _is_list_item_line(line: str) -> bool:
    return bool(_LIST_ITEM_LINE.match(line))


def _is_list_item_block(block: str) -> bool:
    lines = [ln for ln in block.split("\n") if ln.strip()]
    return len(lines) == 1 and _is_list_item_line(lines[0])


def _is_verbatim(block: str) -> bool:
    lines = [ln for ln in block.split("\n") if ln.strip()]
    if not lines:
        return True
    stripped = block.strip()
    # Rich-HTML opaque tokens (tables / references) must survive a full-document rewrite.
    if stripped.startswith("⟦TABLE") or stripped.startswith("⟦OPAQUE"):
        return True
    if len(lines) != 1:
        return True
    line = lines[0]
    if "[[" in block:
        return True
    if _STRUCTURAL_LINE.match(line) or " | " in line:
        return True
    if _is_list_item_line(line):
        return False
    # Markdown / bold-wrapped headings stay put (export turns **…** into real bold).
    # Plain short lines are rewritten — no length-based title guessing.
    return _is_title(block)


def _split_block(block: str) -> tuple[list[str], bool]:
    """Paragraphs of a multi-line block, and whether its last paragraph runs on into the next block.

    Hard-wrapped lines are joined back into paragraphs; lines that are whole paragraphs already
    (a heading above its text, an address) become blocks of their own. Tables stay intact; a run
    of list items is split so each bullet/number line can be rewritten.
    """
    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
    if len(lines) >= 2 and all(_is_list_item_line(ln) for ln in lines):
        return lines, False
    if len(lines) < 2 or any(_VERBATIM_LINE.match(ln) or " | " in ln for ln in lines):
        return [block], False
    width = max(len(ln) for ln in lines)
    full = WRAP_FULL_LINE * width
    # A line followed by one starting in lowercase breaks mid-sentence.
    continued = [nxt[:1].islower() for nxt in lines[1:]] + [False]
    ends = [bool(_SENTENCE_END.search(ln)) for ln in lines]
    # Address / byline stacks: a few short lines, none a finished sentence — keep together
    # (do not peel each line off as if it were a heading). Longest line sets width, so
    # compare to an absolute cap, not to WRAP_FULL_LINE * width.
    if (
        2 <= len(lines) <= 6
        and width <= 80
        and not any(ends)
        and not any(continued)
    ):
        return [block], False
    if width > WRAP_MAX_CHARS or (sum(len(ln) >= full for ln in lines) < 2 and not any(continued)):
        return (lines if not all(_is_verbatim(ln) for ln in lines) else [block]), False
    # Short line above a wrapped paragraph (e.g. marked ``## Introduction`` already caught
    # upstream). Plain short lines stay their own block and are rewritten — not frozen as titles.
    heading = [len(ln) < full and not end and not cont for ln, end, cont in zip(lines, ends, continued)]
    paragraphs: list[str] = []
    current: list[str] = []
    for i, ln in enumerate(lines):
        current.append(ln)
        if continued[i]:
            continue
        if (len(ln) < full and (ends[i] or len(current) == 1)) or (ends[i] and i + 1 < len(lines) and heading[i + 1]):
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs, bool(current) and not _SENTENCE_END.search(lines[-1])


def normalize_wrapped(text: str) -> str:
    """Blank-line separated text with hard-wrapped paragraphs joined back into single lines."""
    if not re.search(r"\n\s*\n", text):
        return _unwrap_single_spaced(text)
    return "\n\n".join(_blocks(text, "\n\n"))


def _unwrap_single_spaced(text: str) -> str:
    """A hard-wrapped text without blank lines (pasted from a PDF) as paragraphs; anything else unchanged.

    The reference list stays line by line, as one block after its "References" title.
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    cut = next(
        (i for i, ln in enumerate(lines) if i > 0 and _wc(ln) <= 3 and is_references_section_title(ln.rstrip(":"))),
        len(lines),
    )
    paragraphs, _ = _split_block("\n".join(lines[:cut]))
    if not 1 < len(paragraphs) < cut:
        return text
    tail = [lines[cut], "\n".join(lines[cut + 1 :])] if cut < len(lines) else []
    return "\n\n".join(paragraphs + [t for t in tail if t])


def _blocks(body: str, separator: str) -> list[str]:
    if separator != "\n\n":
        return [b.strip() for b in body.split(separator) if b.strip()]
    blocks: list[str] = []
    runs_on = False
    for raw in (b.strip() for b in re.split(r"\n\s*\n", body)):
        if not raw:
            continue
        parts, next_runs_on = _split_block(raw)
        if runs_on and blocks and parts[0][:1].islower():
            blocks[-1] = f"{blocks[-1]} {parts.pop(0)}"
        blocks.extend(parts)
        runs_on = next_runs_on
    return _coalesce_sentence_start_blocks(blocks)


def _coalesce_sentence_start_blocks(blocks: list[str]) -> list[str]:
    """Join a lone ``The`` (blank-line split) onto the next paragraph."""
    out: list[str] = []
    i = 0
    while i < len(blocks):
        cur = blocks[i]
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        if nxt and is_sentence_start_fragment(cur) and not _is_list_item_block(nxt):
            glue = " " if nxt and not nxt[:1].isspace() else ""
            out.append(cur.rstrip() + glue + nxt.lstrip())
            i += 2
            continue
        out.append(cur)
        i += 1
    return out


_APPENDIX_LINE = re.compile(r"(?im)^\s*(appendix|appendices|annex)\b")
_YEAR_OR_URL = re.compile(r"\b(1[89]|20)\d\d\b|https?://|doi\.org")


def _ends_reference_list(block: str) -> bool:
    """A new section after the reference list: an appendix, or a heading that is no reference entry."""
    text = block.strip()
    return bool(_APPENDIX_LINE.search(text)) or (
        "\n" not in text
        and _wc(text) <= TITLE_MAX_WORDS
        and not _SENTENCE_END.search(text)
        and not _YEAR_OR_URL.search(text)
    )


def split_plain_references(body: str, separator: str) -> tuple[str, str, str]:
    """(before, references, after) around a plain-text reference list: a "References" line up to the next section.

    Markdown "## References" sections are handled upstream by split_off_references.
    """
    blocks = body.split(separator)
    for i, block in enumerate(blocks):
        title = block.strip().rstrip(":")
        if i > 0 and "\n" not in title and _wc(title) <= 3 and is_references_section_title(title):
            end = next((j for j in range(i + 1, len(blocks)) if _ends_reference_list(blocks[j])), len(blocks))
            return separator.join(blocks[:i]), separator.join(blocks[i:end]), separator.join(blocks[end:])
    return body, "", ""


def plan_chunks(body: str, separator: str, chunk_words: int = CHUNK_WORDS) -> list[tuple[str, bool]]:
    """Body as ordered (text, rewrite?) pieces: prose grouped up to ``chunk_words``, the rest verbatim.

    Long list items are rewritten alone (keeps numbering/markers stabler than mixing with paragraphs).
    Chunks run in parallel, so smaller chunks answer faster; ``chunk_words=1`` sends each paragraph alone.
    """
    pieces: list[tuple[str, bool]] = []
    prose: list[str] = []

    def _flush() -> None:
        if prose:
            pieces.append(("\n\n".join(prose), True))
            prose.clear()

    for block in _blocks(body, separator):
        if _is_verbatim(block):
            _flush()
            pieces.append((block, False))
            continue
        if _is_list_item_block(block):
            _flush()
            pieces.append((block, True))
            continue
        if prose and _wc("\n\n".join(prose + [block])) > chunk_words:
            _flush()
        prose.append(block)
    _flush()
    return pieces


_CONCLUSION_OPENER = re.compile(
    r"^\W*(in conclusion|to conclude|in summary|to summari[sz]e|to sum up|in sum|overall|ultimately|"
    r"in closing|all in all|taken together|in the end)\b",
    re.IGNORECASE,
)
_CONCLUSION_TITLE = re.compile(r"\b(conclusions?|concluding|summary|final thoughts|closing remarks)\b", re.IGNORECASE)


def _title_core(text: str) -> str:
    return title_core(text)


def _is_title(text: str) -> bool:
    return "\n" not in (text or "").strip() and is_explicit_heading_text(text, max_words=TITLE_MAX_WORDS)


def conclusion_pieces(pieces: list[tuple[str, bool]]) -> set[int]:
    """Indices of rewritten pieces that are conclusions: under a "Conclusion" heading, opening with
    "In conclusion"-style words, or else the last prose piece of the text."""
    found: set[int] = set()
    under_heading = False
    for i, (text, rewrite) in enumerate(pieces):
        if not rewrite or _is_title(text):
            under_heading = bool(_CONCLUSION_TITLE.search(text)) and _is_title(text)
            continue
        if under_heading or _CONCLUSION_OPENER.match(text):
            found.add(i)
    if not found:
        last = [i for i, (text, rewrite) in enumerate(pieces) if rewrite and not _is_title(text)]
        found.update(last[-1:])
    return found


def _strip_think(text: str) -> str:
    """Qwen3 sometimes leaks a <think>…</think> block even when thinking is off."""
    return re.sub(r"<think>[\s\S]*?</think>\s*", "", text, flags=re.I).strip()


_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
_SPACE_AFTER_OPEN = re.compile(r"([(\[])\s+")
_SPACE_BEFORE_CLOSE = re.compile(r"\s+([)\]])")


def _tidy_joined_prose(text: str) -> str:
    """Fix artifacts left when soft-wrapped lines like ``item\\n, next`` are joined."""
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN.sub(r"\1", text)
    text = _SPACE_BEFORE_CLOSE.sub(r"\1", text)
    return re.sub(r"[^\S\n]{2,}", " ", text).strip()


def _normalize_rewrite_layout(source: str, output: str, single_paragraph: bool) -> str:
    """Collapse model-invented soft wraps / blank splits so layout matches the source chunk.

    The student model often inserts single newlines mid-sentence (fake headings, one list item
    per line). The older fix only joined blank-line splits, so those soft wraps survived into
    the UI. Rich HTML already unwraps after rewrite; plain path needs the same here.
    """
    text = (output or "").strip()
    if not text:
        return text
    if single_paragraph:
        # One source paragraph → one line of prose (blank splits and soft wraps both go).
        return _tidy_joined_prose(unwrap_prose_newlines(text))
    # Keep real paragraph breaks; unwrap soft wraps inside each paragraph.
    return "\n\n".join(_tidy_joined_prose(unwrap_prose_newlines(p)) for p in _paragraphs(text))


def chunk_problem(source: str, output: str) -> str | None:
    """Why a rewritten chunk is unusable, or None when it is fine."""
    if not output.strip():
        return "EMPTY"
    if "<think>" in output or re.search(r"(?m)^##\s", output):
        return "EXTRA_MARKUP"
    if len(_paragraphs(output)) != len(_paragraphs(source)):
        return "PARAGRAPHS_CHANGED"
    ratio = _wc(output) / max(1, _wc(source))
    if not RATIO_RANGE[0] <= ratio <= RATIO_RANGE[1]:
        return "LENGTH_RATIO"
    overlap = _jaccard(source, output)
    if overlap > MAX_JACCARD:
        return "UNCHANGED"
    if overlap < MIN_JACCARD:
        return "DRIFTED"
    marker, _ = split_list_marker(source)
    if marker and not list_marker_ok(source, restore_list_marker(source, output)):
        return "LIST_MARKER"
    return None


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _lost_numbers(source: str, output: str) -> int:
    return len(set(_NUMBER.findall(source)) - set(_NUMBER.findall(output)))


@dataclass(frozen=True, slots=True)
class Candidate:
    text: str
    # Mean log-probability of the sampled tokens; lower means less predictable text.
    mean_logprob: float = 0.0


def pick_candidate(source: str, candidates: list[Candidate], pick: str = "changed") -> Candidate:
    """Best usable variant: keeps the source numbers first, then the most rewritten or least predictable."""
    if pick == "surprise":
        return min(candidates, key=lambda c: (_lost_numbers(source, c.text), c.mean_logprob))
    return min(candidates, key=lambda c: (_lost_numbers(source, c.text), _jaccard(source, c.text)))


def pick_least_ai(source: str, scored: list[tuple[Candidate, float]]) -> tuple[Candidate, float]:
    """Variant the AI detector scores lowest, among those that keep every source number if any do."""
    return min(scored, key=lambda cp: (_lost_numbers(source, cp[0].text) > 0, cp[1]))


def _detector_score(texts: list[str]) -> list[float]:
    from services import ai_detector

    return ai_detector.score_texts(texts)


class StudentTextHumanizer:
    """Same ``humanize(text)`` contract as ``StealthWriterTextHumanizer``."""

    VERSION = "docmaxxing-student-v1"

    def __init__(
        self,
        config: StudentConfig | None = None,
        *,
        complete_fn: Callable[[str], str] | None = None,
        score_fn: Callable[[list[str]], list[float]] | None = None,
        max_workers: int | None = None,
    ) -> None:
        self.config = config or student_config()
        self._complete_fn = complete_fn
        self._score_fn = score_fn or _detector_score
        self.max_workers = student_max_workers() if max_workers is None else max_workers
        self._fallback_scorer = MockTextHumanizer()

    def humanize(
        self,
        text: str,
        *,
        academic_tone: str = "formal",
        on_chunk: Callable[[dict[str, Any]], None] | None = None,
    ) -> str:
        """Rewrite prose. ``on_chunk`` is called as each piece is ready (passthrough or rewrite).

        Chunk event: ``{index, text, status, rewrite_total, rewrite_done, pieces}`` where
        ``status`` is ``pending`` (source text shown while rewriting), ``passthrough``,
        ``ready``, or ``final``.
        """
        del academic_tone
        if not text.strip():
            return text
        if len(text.strip()) < MIN_HUMANIZE_CHARS:
            return text.strip()

        body, refs = split_off_references(normalize_wrapped(text))
        separator = "\n\n" if "\n\n" in body or "\n" not in body.strip() else "\n"
        before, plain_refs, after = split_plain_references(body, separator)
        pieces = plan_chunks(before, separator, self.config.chunk_words)
        if plain_refs:
            pieces += [(plain_refs, False), *plan_chunks(after, separator, self.config.chunk_words)]
        conclusions = conclusion_pieces(pieces) if self.config.conclusion_sampling else set()
        rewrite_jobs: list[tuple[int, str, bool]] = [
            (i, piece, i in conclusions)
            for i, (piece, rewrite) in enumerate(pieces)
            if rewrite
        ]
        if not rewrite_jobs:
            raise StudentHumanizerError("No prose to rewrite")

        out: list[str | None] = [None] * len(pieces)
        rewrite_total = len(rewrite_jobs)
        rewrite_done = 0

        def _emit(index: int, text_out: str, status: str) -> None:
            if on_chunk is None:
                return
            on_chunk(
                {
                    "index": index,
                    "text": text_out,
                    "status": status,
                    "rewrite_total": rewrite_total,
                    "rewrite_done": rewrite_done,
                    "pieces": len(pieces),
                }
            )

        # Show the whole document immediately: originals for rewrite slots, passthrough as-is.
        for i, (piece, rewrite) in enumerate(pieces):
            if rewrite:
                _emit(i, piece, "pending")
            else:
                out[i] = piece
                _emit(i, piece, "passthrough")

        workers = max(1, min(self.max_workers, len(rewrite_jobs)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._rewrite_chunk, piece, conclusion): piece_i
                for piece_i, piece, conclusion in rewrite_jobs
            }
            for fut in as_completed(futures):
                piece_i = futures[fut]
                text_out = fut.result()
                out[piece_i] = text_out
                rewrite_done += 1
                _emit(piece_i, text_out, "ready")

        if any(part is None for part in out):
            raise StudentHumanizerError("Missing rewritten chunk")
        final = [part or "" for part in out]
        if self.config.pick == "document":
            final = self._fix_flagged(pieces, final, separator)
            if on_chunk is not None:
                for i, text_out in enumerate(final):
                    on_chunk(
                        {
                            "index": i,
                            "text": text_out,
                            "status": "final",
                            "rewrite_total": rewrite_total,
                            "rewrite_done": rewrite_total,
                            "pieces": len(pieces),
                        }
                    )
        if separator == "\n":
            final = [p.replace("\n\n", "\n") for p in final]
        return join_body_and_references(separator.join(final), refs)

    def _rewrite_chunk(self, chunk: str, conclusion: bool = False) -> str:
        problem = "NOT_RUN"
        # List markers stay outside the model: rewrite the body only, then put 1. / - back.
        marker, body = split_list_marker(chunk)
        source = body if marker else chunk
        # A paragraph the model only lightly edits should not sink the whole text.
        lightest: tuple[float, str] | None = None

        def _with_marker(text: str) -> str:
            return restore_list_marker(chunk, text) if marker else text

        for attempt in range(1, ATTEMPTS + 1):
            try:
                if self.config.pick == "detector":
                    text = self._detector_sample(source, conclusion)
                    if text is not None:
                        return _with_marker(text)
                    problem = "NO_VARIANTS"
                    continue
                # pick=document: first-pass pool (default 1.2:4), then _fix_flagged/_refit.
                # If the pool DRIFTED/echoes, pull refine_sampling in the same attempt.
                if self.config.pick == "document":
                    plan = self.config.sampling_plan or DOCUMENT_SAMPLING
                    variants = self._candidates(source, plan)
                    usable, problem, light = self._usable(source, variants)
                    if light is not None and (lightest is None or light[0] < lightest[0]):
                        lightest = (light[0], _with_marker(light[1]))
                    rescue = self.config.refine_sampling or DOCUMENT_REFINE_SAMPLING
                    # Near-echo against the least-AI pick (not "most changed") — otherwise a
                    # larger pool can look fine while the score-winner is still an echo.
                    need_rescue = not usable or (
                        usable and _jaccard(source, self._least_ai_or_changed(source, usable)) > 0.92
                    )
                    if need_rescue:
                        log.info(
                            "student humanizer document first-pass %s; rescuing with %s",
                            problem if not usable else "NEAR_ECHO",
                            rescue,
                        )
                        variants = self._candidates(source, rescue)
                else:
                    variants = self._candidates(source)
            except (requests.RequestException, StudentHumanizerError, KeyError, ValueError, IndexError) as exc:
                problem = f"REQUEST_FAILED: {exc}"
                log.info("student humanizer attempt %s failed: %s", attempt, problem)
                continue
            usable, problem, light = self._usable(source, variants)
            if light is not None and (lightest is None or light[0] < lightest[0]):
                lightest = (light[0], _with_marker(light[1]))
            if usable:
                # document: score the pool (least AI), then refine if still hot — never
                # "most changed", which made larger first-pass pools score worse on detectors.
                if self.config.pick == "document":
                    return _with_marker(self._pick_by_detector(source, usable, conclusion=False))
                return _with_marker(pick_candidate(source, usable, self.config.pick).text)
            log.info("student humanizer attempt %s failed: %s", attempt, problem)
        if lightest is not None:
            return lightest[1]
        # Tiny captions/labels may stay verbatim; real prose must not.
        if problem == "UNCHANGED" and _wc(source) <= 12:
            return chunk
        raise StudentHumanizerError(f"Chunk rejected after {ATTEMPTS} attempts: {problem}")

    def _usable(
        self, chunk: str, variants: list[Candidate]
    ) -> tuple[list[Candidate], str, tuple[float, str] | None]:
        """Variants passing the checks, the last problem seen, and the least similar UNCHANGED one."""
        single_paragraph = len(_paragraphs(chunk)) == 1
        usable: list[Candidate] = []
        problem = "NO_VARIANTS"
        lightest: tuple[float, str] | None = None
        for variant in variants:
            output = _normalize_rewrite_layout(chunk, variant.text.strip(), single_paragraph)
            problem = chunk_problem(chunk, output) or ""
            if not problem:
                usable.append(Candidate(output, variant.mean_logprob))
            elif problem == "UNCHANGED" and output.strip() != chunk.strip():
                similarity = _jaccard(chunk, output)
                if lightest is None or similarity < lightest[0]:
                    lightest = (similarity, output)
        return usable, problem, lightest

    def _sampling_waves(
        self, plan: tuple[tuple[float, int], ...]
    ) -> list[tuple[float, int]]:
        """Split the plan into waves so early-stop can skip later GPU work.

        A single large ``n`` becomes two half-batches; multi-temperature plans stay one wave each.
        """
        waves: list[tuple[float, int]] = []
        early = self.config.early_stop_below > 0
        for temperature, n in plan:
            if early and len(plan) == 1 and n >= 4:
                first = (n + 1) // 2
                waves.append((temperature, first))
                if n - first > 0:
                    waves.append((temperature, n - first))
            else:
                waves.append((temperature, n))
        return waves

    def _detector_sample(self, chunk: str, conclusion: bool = False) -> str | None:
        """Sample in waves, pick lowest AI score; early-stop skips later waves/refine when clean."""
        cfg = self.config
        scored: list[tuple[Candidate, float]] = []
        lightest: tuple[float, str] | None = None
        waves = self._sampling_waves(cfg.sampling_plan)
        for temperature, n in waves:
            usable, problem, light = self._usable(chunk, self._candidates(chunk, ((temperature, n),)))
            if light is not None and (lightest is None or light[0] < lightest[0]):
                lightest = light
            if not usable:
                log.info("student humanizer detector wave empty: %s", problem)
                continue
            try:
                scored += list(zip(usable, self._score_fn([c.text for c in usable])))
            except Exception as exc:  # noqa: BLE001
                log.info("AI detector unavailable for student pick: %s", exc)
                return pick_candidate(chunk, usable, "changed").text
            best = pick_least_ai(chunk, scored)
            # Conclusions still get their dedicated extras even when already clean.
            if (
                cfg.early_stop_below > 0
                and best[1] <= cfg.early_stop_below
                and not conclusion
            ):
                return best[0].text
        if not scored:
            return lightest[1] if lightest is not None else None
        best = pick_least_ai(chunk, scored)
        more = cfg.conclusion_sampling if conclusion else ()
        if not more and best[1] > cfg.refine_above:
            more = cfg.refine_sampling
        if more:
            try:
                extra, _, _ = self._usable(chunk, self._candidates(chunk, more))
                if extra:
                    scored += list(zip(extra, self._score_fn([c.text for c in extra])))
                    best = pick_least_ai(chunk, scored)
            except Exception as exc:  # noqa: BLE001
                log.info("student humanizer refine failed: %s", exc)
        return best[0].text

    def _least_ai_or_changed(self, chunk: str, usable: list[Candidate]) -> str:
        """Lowest AI score among ``usable``, or most-changed if the detector is down."""
        try:
            scored = list(zip(usable, self._score_fn([c.text for c in usable])))
            return pick_least_ai(chunk, scored)[0].text
        except Exception as exc:  # noqa: BLE001
            log.info("AI detector unavailable for document first pick: %s", exc)
            return pick_candidate(chunk, usable, "changed").text

    def _pick_by_detector(self, chunk: str, usable: list[Candidate], conclusion: bool = False) -> str:
        """Lowest AI-detector score among ``usable``; refine/conclusion extras when still flagged."""
        cfg = self.config
        try:
            scored = list(zip(usable, self._score_fn([c.text for c in usable])))
        except Exception as exc:  # noqa: BLE001
            log.info("AI detector unavailable for student pick: %s", exc)
            return pick_candidate(chunk, usable, "changed").text
        best = pick_least_ai(chunk, scored)
        if cfg.early_stop_below > 0 and best[1] <= cfg.early_stop_below and not conclusion:
            return best[0].text
        more = cfg.conclusion_sampling if conclusion else ()
        if not more and best[1] > cfg.refine_above:
            more = cfg.refine_sampling
        if more:
            try:
                extra, _, _ = self._usable(chunk, self._candidates(chunk, more))
                if extra:
                    scored += list(zip(extra, self._score_fn([c.text for c in extra])))
                    best = pick_least_ai(chunk, scored)
            except Exception as exc:  # noqa: BLE001
                log.info("student humanizer refine failed: %s", exc)
        return best[0].text

    def _detect(self, text: str) -> dict:
        from services import ai_detector

        return ai_detector.detect(text, score=lambda texts: (self._score_fn(texts), ""))

    def _fix_flagged(self, pieces: list[tuple[str, bool]], out: list[str], separator: str) -> list[str]:
        """Rewrite again only the chunks where the whole-text detector flags sentences."""
        cfg = self.config
        sources = [piece for piece, _ in pieces]
        rewrite = [flag for _, flag in pieces]
        deadline = time.monotonic() + cfg.doc_budget
        out = list(out)
        for _ in range(cfg.doc_rounds):
            if time.monotonic() >= deadline:
                break
            try:
                flagged = self._flagged_pieces(out, rewrite, separator)
            except Exception as exc:  # noqa: BLE001
                log.info("AI detector unavailable for the document check: %s", exc)
                break
            if not flagged:
                break
            with ThreadPoolExecutor(max_workers=max(1, min(self.max_workers, len(flagged)))) as pool:
                fixes = list(pool.map(lambda i: self._refit(i, sources[i], out, separator), flagged))
            for i, text in zip(flagged, fixes):
                out[i] = text
        return out

    def _flagged_pieces(self, out: list[str], rewrite: list[bool], separator: str) -> list[int]:
        result = self._detect(separator.join(out))
        if result.get("too_short"):
            return []
        starts, pos = [], 0
        for piece in out:
            starts.append(pos)
            pos += len(piece) + len(separator)
        cut = self.config.doc_flag_above
        hit = {
            bisect.bisect_right(starts, s["start"]) - 1
            for s in result["sentences"]
            if s.get("ai_prob") is not None and float(s["ai_prob"]) > cut
        }
        return sorted(i for i in hit if rewrite[i])

    def _refit(self, i: int, source: str, out: list[str], separator: str) -> str:
        """Best of the current text and fresh variants of chunk ``i``, scored with its neighbours around it."""
        current = out[i]
        cfg = self.config
        plan = cfg.refine_sampling or DOCUMENT_REFINE_SAMPLING
        try:
            fresh, _, _ = self._usable(source, self._candidates(source, plan))
        except (requests.RequestException, StudentHumanizerError, KeyError, ValueError, IndexError) as exc:
            log.info("student humanizer rewrite of a flagged chunk failed: %s", exc)
            return current
        options = [Candidate(current), *(c for c in fresh if c.text != current)]
        try:
            with ThreadPoolExecutor(max_workers=len(options)) as pool:
                scores = list(pool.map(lambda c: self._context_score(i, c.text, out, separator), options))
            scored = list(zip(options, scores))
        except Exception as exc:  # noqa: BLE001
            log.info("AI detector unavailable for a flagged chunk: %s", exc)
            return current
        best = pick_least_ai(source, scored)
        # Still hot after refine — one more higher-temp burst before giving up.
        if best[1] > cfg.refine_above:
            extra_plan = cfg.conclusion_sampling or ((1.3, 12),)
            try:
                more, _, _ = self._usable(source, self._candidates(source, extra_plan))
                if more:
                    with ThreadPoolExecutor(max_workers=len(more)) as pool:
                        more_scores = list(
                            pool.map(lambda c: self._context_score(i, c.text, out, separator), more)
                        )
                    scored += list(zip(more, more_scores))
                    best = pick_least_ai(source, scored)
            except Exception as exc:  # noqa: BLE001
                log.info("student humanizer extra refit failed: %s", exc)
        return best[0].text

    def _context_score(self, i: int, text: str, out: list[str], separator: str) -> float:
        """Word-weighted AI probability of ``text``'s sentences, read between its neighbouring chunks."""
        before = out[i - 1] if i > 0 else ""
        after = out[i + 1] if i + 1 < len(out) else ""
        start = len(before) + len(separator) if before else 0
        local = separator.join(p for p in (before, text, after) if p)
        result = self._detect(local)
        own = [
            (s["ai_prob"], len(s["text"].split()))
            for s in result.get("sentences") or []
            if s["ai_prob"] is not None and start <= s["start"] < start + len(text)
        ]
        if not own:
            return self._score_fn([text])[0]
        return sum(p * w for p, w in own) / sum(w for _, w in own)

    def _candidates(self, chunk: str, sampling: tuple[tuple[float, int], ...] = ()) -> list[Candidate]:
        cfg = self.config
        plan = sampling or cfg.sampling_plan
        if self._complete_fn is not None:
            return [Candidate(self._complete_fn(chunk)) for _, n in plan for _ in range(n)]
        if not cfg.configured:
            raise StudentHumanizerError("Student humanizer is not configured")
        if len(plan) == 1:
            return self._request(chunk, *plan[0])
        with ThreadPoolExecutor(max_workers=len(plan)) as pool:
            futures = [pool.submit(self._request, chunk, t, n) for t, n in plan]
        out: list[Candidate] = []
        errors: list[Exception] = []
        for future in futures:
            try:
                out += future.result()
            except (requests.RequestException, StudentHumanizerError, KeyError, ValueError, IndexError) as exc:
                errors.append(exc)
        if not out and errors:
            raise errors[0]
        return out

    def _request(self, chunk: str, temperature: float, n: int) -> list[Candidate]:
        cfg = self.config
        response = requests.post(
            f"{cfg.url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={
                "model": cfg.model,
                "messages": [
                    {"role": "system", "content": system_prompt(cfg.level)},
                    {"role": "user", "content": chunk},
                ],
                "temperature": temperature,
                "top_p": TOP_P,
                "n": n,
                "logprobs": cfg.pick == "surprise",
                # A memory-snapshot restore brings back the server's RNG state too, so without
                # a per-request seed every first request after a cold start samples identically.
                "seed": random.randrange(2**31),
                "max_tokens": int(_wc(chunk) * 1.35 * 2) + 64,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=cfg.timeout,
        )
        if response.status_code != 200:
            raise StudentHumanizerError(f"HTTP {response.status_code}: {response.text[:200]}")
        return [_candidate(choice) for choice in response.json()["choices"]]

    def is_warm(self) -> bool:
        """True when the model answers right away.

        A scaled-to-zero server restores from its snapshot in ~10 s; the probe itself starts
        that boot, so requests a few seconds later find the model ready.
        """
        if self._complete_fn is not None:
            return True
        cfg = self.config
        try:
            response = requests.get(
                f"{cfg.url}/v1/models",
                headers={"Authorization": f"Bearer {cfg.api_key}"},
                timeout=cfg.probe_timeout,
            )
        except requests.RequestException:
            return False
        return response.status_code == 200

    def estimate_ai_score(self, text: str) -> int:
        return self._fallback_scorer.estimate_ai_score(text)


def _candidate(choice: dict[str, Any]) -> Candidate:
    tokens = ((choice.get("logprobs") or {}).get("content")) or []
    mean = sum(t["logprob"] for t in tokens) / len(tokens) if tokens else 0.0
    return Candidate(_strip_think(choice["message"]["content"] or ""), mean)


def pick_student(config: StudentConfig | None = None, *, rng: Callable[[], float] = random.random) -> bool:
    cfg = config or student_config()
    return cfg.configured and cfg.share > 0 and rng() < cfg.share


_warmup_lock = threading.Lock()
_last_warmup = float("-inf")


def warm_up(
    config: StudentConfig | None = None,
    *,
    clock: Callable[[], float] = time.monotonic,
    ping: Callable[[StudentConfig], None] | None = None,
    force: bool = False,
) -> bool:
    """Wake the model in the background.

    At most one wake-up per ``WARMUP_EVERY_SECONDS`` per process; returns True when one was sent.
    ``force`` wakes it even when its share is 0 (StealthWriter is down).
    """
    global _last_warmup
    cfg = config or student_config()
    if not cfg.configured or (cfg.share <= 0 and not force):
        return False
    with _warmup_lock:
        now = clock()
        if now - _last_warmup < WARMUP_EVERY_SECONDS:
            return False
        _last_warmup = now
    threading.Thread(target=ping or _ping, args=(cfg,), daemon=True, name="student-warmup").start()
    return True


def _ping(cfg: StudentConfig) -> None:
    try:
        requests.get(
            f"{cfg.url}/v1/models",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            timeout=WARMUP_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        log.info("student humanizer wake-up failed: %s", exc)
    # Detector pick path cold-starts ~11 s; wake it with the model.
    try:
        from services import ai_detector

        ai_detector.score_texts(["Warm-up probe for the student humanizer."])
    except Exception as exc:  # noqa: BLE001
        log.info("AI detector wake-up failed: %s", exc)


def record_event(cfg: StudentConfig, outcome: str, **fields: Any) -> None:
    """One JSON line per routed request, so speed and fallback rate can be measured."""
    if not cfg.events_log:
        return
    row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "outcome": outcome, **fields}
    try:
        path = Path(cfg.events_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        log.exception("student humanizer event log write failed")


def _wait_until_warm(engine: StudentTextHumanizer, budget: float, sleep: Callable[[float], None]) -> bool:
    if engine.is_warm():
        return True
    if budget <= 0:
        return False
    warm_up(engine.config, force=True)
    # Cold Modal boots often take 20–40s; a 3s probe can miss a mid-boot server.
    # Temporarily lengthen the engine's probe while we poll via ``is_warm`` (testable).
    original = engine.config
    cold_probe = max(float(original.probe_timeout), 20.0)
    if cold_probe > original.probe_timeout:
        engine.config = replace(original, probe_timeout=cold_probe)
    try:
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            if engine.is_warm():
                return True
            sleep(BOOT_POLL_SECONDS)
        return engine.is_warm()
    finally:
        engine.config = original


def try_student_humanize(
    text: str,
    *,
    humanizer: StudentTextHumanizer | None = None,
    force: bool = False,
    wait_for_boot: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
    on_chunk: Callable[[dict[str, Any]], None] | None = None,
    mode: str | None = None,
) -> dict[str, Any] | None:
    """Humanize with the student model when this request falls into its share.

    ``force`` skips the share draw; ``wait_for_boot`` waits up to that many seconds for a
    sleeping model instead of giving up at once.
    ``on_chunk`` receives each finished piece as soon as it is ready (for SSE).
    ``mode="fast"`` uses fewer candidates (not the default).
    Returns a job-like result dict, or None when the caller should use StealthWriter.
    """
    engine = humanizer or StudentTextHumanizer(student_config_for_mode(mode))
    cfg = engine.config
    if not cfg.configured and engine._complete_fn is None:
        return None
    if not force and not pick_student(cfg):
        return None
    text = repair_mojibake(text)
    if not is_english(text):
        return None
    words = _wc(text)
    started = time.monotonic()
    warmed = _wait_until_warm(engine, wait_for_boot, sleep)
    waited = round(time.monotonic() - started, 1)
    if not warmed:
        # StealthWriter is gone — still try once; the chat call itself boots Modal.
        log.info("student humanizer still cold after %.1fs; attempting request anyway", waited)
        record_event(cfg, "cold_attempt", words=words, waited=waited)
    started = time.monotonic()
    ttfb: list[float] = []

    def _wrap_chunk(evt: dict[str, Any]) -> None:
        if evt.get("status") == "ready" and not ttfb:
            ttfb.append(round(time.monotonic() - started, 2))
        if on_chunk is not None:
            on_chunk(evt)

    try:
        output = engine.humanize(text, on_chunk=_wrap_chunk)
    except Exception as exc:  # noqa: BLE001
        log.warning("student humanizer failed: %s", exc)
        record_event(
            cfg, "failed", words=words, elapsed=round(time.monotonic() - started, 2), error=str(exc)[:200]
        )
        return None
    elapsed = round(time.monotonic() - started, 2)
    if not output.strip() or output.strip() == text.strip():
        record_event(cfg, "failed", words=words, elapsed=elapsed, error="UNCHANGED")
        return None
    if _jaccard(text, output) > 0.92:
        record_event(cfg, "failed", words=words, elapsed=elapsed, error="NEAR_UNCHANGED")
        return None
    record_event(
        cfg,
        "served",
        words=words,
        elapsed=elapsed,
        **({"waited": waited} if waited >= 1 else {}),
        **({"ttfb_chunk": ttfb[0]} if ttfb else {}),
    )
    return {
        "humanized_text": output,
        "elapsed_seconds": elapsed,
        "ttfb_chunk_seconds": ttfb[0] if ttfb else None,
        "provider": PROVIDER,
        "engine": engine.VERSION,
        "request_id": f"student-{uuid.uuid4().hex[:12]}",
    }


def try_student_humanize_rich(
    html_doc: str,
    *,
    humanizer: StudentTextHumanizer | None = None,
    force: bool = False,
    wait_for_boot: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
    on_chunk: Callable[[dict[str, Any]], None] | None = None,
    mode: str | None = None,
) -> dict[str, Any] | None:
    """Humanize HTML by rewriting prose blocks only (tables/headings never go to the model).

    Avoids sending ``⟦OPAQUE⟧`` / ``⟦TABLE⟧`` protect tokens through the LLM, which
    previously leaked into the visible output and scrambled section order.
    """
    from services.humanizer_engine.rich_html import html_to_plaintext, humanize_rich

    engine = humanizer or StudentTextHumanizer(student_config_for_mode(mode))
    cfg = engine.config
    if not cfg.configured and engine._complete_fn is None:
        return None
    if not force and not pick_student(cfg):
        return None
    plain_check = repair_mojibake(html_to_plaintext(html_doc))
    if not plain_check.strip():
        return None
    if not is_english(plain_check):
        return None
    # Keep HTML in sync when plaintext was mojibake-repaired.
    html_doc = repair_mojibake(html_doc)
    words = _wc(plain_check)
    started = time.monotonic()
    warmed = _wait_until_warm(engine, wait_for_boot, sleep)
    waited = round(time.monotonic() - started, 1)
    if not warmed:
        log.info("student rich humanizer still cold after %.1fs; attempting anyway", waited)
        record_event(cfg, "cold_attempt", words=words, waited=waited)
    started = time.monotonic()
    ttfb: list[float] = []

    failures: list[str] = []
    model_blocks = 0

    def rewrite(line: str) -> str:
        nonlocal model_blocks
        text = (line or "").strip()
        if not text or len(text) < MIN_HUMANIZE_CHARS:
            return line
        try:
            # Per-block rewrite; conclusion extras only for real closers (not every line).
            conclusion = bool(_CONCLUSION_OPENER.match(text))
            out = engine._rewrite_chunk(line, conclusion)
            model_blocks += 1
            return out
        except StudentHumanizerError as exc:
            failures.append(str(exc)[:160])
            raise

    def _wrap_chunk(evt: dict[str, Any]) -> None:
        if evt.get("status") == "ready" and not ttfb:
            ttfb.append(round(time.monotonic() - started, 2))
        if on_chunk is not None:
            on_chunk(evt)

    try:
        rich, text = humanize_rich(
            html_doc, rewrite, max_workers=engine.max_workers, on_chunk=_wrap_chunk
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("student rich humanizer failed: %s", exc)
        record_event(
            cfg,
            "failed",
            words=words,
            elapsed=round(time.monotonic() - started, 2),
            error=str(exc)[:200],
        )
        return None
    elapsed = round(time.monotonic() - started, 2)
    if not text.strip():
        record_event(cfg, "failed", words=words, elapsed=elapsed, error="EMPTY")
        return None
    unchanged = text.strip() == plain_check.strip()
    near = (not unchanged) and _jaccard(plain_check, text) > 0.92
    # Contenteditable HTML often splits into tiny lines that skip the model (0.01s
    # NEAR_UNCHANGED). Fall back to a real plaintext document rewrite.
    if unchanged or near or model_blocks == 0:
        reason = "UNCHANGED" if unchanged else ("NEAR_UNCHANGED" if near else "NO_MODEL_BLOCKS")
        record_event(cfg, "failed", words=words, elapsed=elapsed, error=f"{reason}_FALLBACK")
        log.info(
            "student rich humanizer %s (model_blocks=%s); plaintext fallback",
            reason,
            model_blocks,
        )
        return try_student_humanize(
            plain_check,
            humanizer=engine,
            force=True,
            wait_for_boot=0.0,
            sleep=sleep,
            on_chunk=on_chunk,
            mode=None,
        )
    record_event(
        cfg,
        "served",
        words=words,
        elapsed=elapsed,
        **({"waited": waited} if waited >= 1 else {}),
        **({"ttfb_chunk": ttfb[0]} if ttfb else {}),
    )
    return {
        "humanized_text": text,
        "humanized_html": rich,
        "elapsed_seconds": elapsed,
        "ttfb_chunk_seconds": ttfb[0] if ttfb else None,
        "provider": PROVIDER,
        "engine": engine.VERSION,
        "request_id": f"student-{uuid.uuid4().hex[:12]}",
    }
