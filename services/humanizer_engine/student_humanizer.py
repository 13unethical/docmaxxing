"""Our own humanizer: the fine-tuned student model served behind an OpenAI-compatible endpoint.

Prose paragraphs are grouped into ~600-word chunks (the size the model was trained on) and
rewritten in parallel; headings, lists, tables, figure markers and references stay verbatim.
Any chunk that fails the quality checks is retried, and if it still fails the whole call
raises so the caller can fall back to StealthWriter.

pick="document": each chunk is written once, then the AI detector scores the whole text in its
~110-word windows and only the chunks holding flagged sentences are rewritten, judged in context.
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from services.humanizer_engine.constants import MIN_HUMANIZE_CHARS
from services.humanizer_engine.heading_utils import (
    is_references_section_title,
    join_body_and_references,
    split_off_references,
)
from services.humanizer_engine.mock_humanizer import MockTextHumanizer

log = logging.getLogger(__name__)

PROVIDER = "DocMaxxing"
CHUNK_WORDS = 600
RATIO_RANGE = (0.6, 1.9)
MAX_JACCARD = 0.9
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
# pick="document": rounds of "score the whole text, rewrite the flagged chunks", within this many seconds.
DOC_ROUNDS = 3
DOC_BUDGET_SECONDS = 45.0

_WORD = re.compile(r"[a-z0-9']+")
_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
_LETTER = re.compile(r"[^\W\d_]")
_VERBATIM_LINE = re.compile(r"^\s*(#{1,6}\s|\||```|[-*•+]\s|\d+[.)]\s)")
_SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]]*\s*$")
# Given a bare title, the model writes a whole paragraph after it.
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
    doc_rounds: int = DOC_ROUNDS
    doc_budget: float = DOC_BUDGET_SECONDS

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
        share=min(1.0, max(0.0, _float("HUMANIZER_STUDENT_SHARE", 0.0))),
        level=max(1, min(10, int(_float("HUMANIZER_STUDENT_LEVEL", 8)))),
        timeout=max(10.0, _float("HUMANIZER_STUDENT_TIMEOUT", 90.0)),
        chunk_words=max(1, int(_float("HUMANIZER_STUDENT_CHUNK_WORDS", CHUNK_WORDS))),
        probe_timeout=max(0.5, _float("HUMANIZER_STUDENT_PROBE_TIMEOUT", 3.0)),
        events_log=(os.environ.get("HUMANIZER_STUDENT_EVENTS_LOG") or "").strip(),
        temperature=max(0.1, min(2.0, _float("HUMANIZER_STUDENT_TEMPERATURE", TEMPERATURE))),
        candidates=max(1, min(MAX_CANDIDATES, int(_float("HUMANIZER_STUDENT_CANDIDATES", 1)))),
        pick=(os.environ.get("HUMANIZER_STUDENT_PICK") or "changed").strip().lower(),
        sampling=parse_sampling(os.environ.get("HUMANIZER_STUDENT_SAMPLING") or ""),
        refine_above=_float("HUMANIZER_STUDENT_REFINE_ABOVE", REFINE_ABOVE),
        refine_sampling=parse_sampling(os.environ.get("HUMANIZER_STUDENT_REFINE_SAMPLING") or ""),
        conclusion_sampling=parse_sampling(os.environ.get("HUMANIZER_STUDENT_CONCLUSION_SAMPLING") or ""),
        doc_rounds=max(0, int(_float("HUMANIZER_STUDENT_DOC_ROUNDS", DOC_ROUNDS))),
        doc_budget=max(0.0, _float("HUMANIZER_STUDENT_DOC_BUDGET", DOC_BUDGET_SECONDS)),
    )


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


def _wc(text: str) -> int:
    return len(text.split())


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _jaccard(a: str, b: str) -> float:
    left, right = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    return len(left & right) / len(left | right) if left | right else 1.0


def _is_verbatim(block: str) -> bool:
    lines = [ln for ln in block.split("\n") if ln.strip()]
    return (
        len(lines) != 1
        or bool(_VERBATIM_LINE.match(lines[0]))
        or "[[" in block
        or _wc(block) < 3
        or (_wc(block) <= TITLE_MAX_WORDS and not _SENTENCE_END.search(block))
    )


def _split_block(block: str) -> tuple[list[str], bool]:
    """Paragraphs of a multi-line block, and whether its last paragraph runs on into the next block.

    Hard-wrapped lines are joined back into paragraphs; lines that are whole paragraphs already
    (a heading above its text, an address) become blocks of their own. Lists and tables stay intact.
    """
    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
    if len(lines) < 2 or any(_VERBATIM_LINE.match(ln) or " | " in ln for ln in lines):
        return [block], False
    width = max(len(ln) for ln in lines)
    full = WRAP_FULL_LINE * width
    # A line followed by one starting in lowercase breaks mid-sentence.
    continued = [nxt[:1].islower() for nxt in lines[1:]] + [False]
    if width > WRAP_MAX_CHARS or (sum(len(ln) >= full for ln in lines) < 2 and not any(continued)):
        return (lines if not all(_is_verbatim(ln) for ln in lines) else [block]), False
    ends = [bool(_SENTENCE_END.search(ln)) for ln in lines]
    heading = [len(ln) < full and not end and not cont for ln, end, cont in zip(lines, ends, continued)]
    paragraphs: list[str] = []
    current: list[str] = []
    for i, ln in enumerate(lines):
        current.append(ln)
        if continued[i]:
            continue
        # A short line ends its paragraph and a short line on its own is a heading; a sentence
        # that ends right before a heading ends its paragraph too.
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
    return blocks


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


def _is_title(text: str) -> bool:
    return "\n" not in text.strip() and _wc(text) <= TITLE_MAX_WORDS and not _SENTENCE_END.search(text)


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
    if _jaccard(source, output) > MAX_JACCARD:
        return "UNCHANGED"
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
        max_workers: int = 32,
    ) -> None:
        self.config = config or student_config()
        self._complete_fn = complete_fn
        self._score_fn = score_fn or _detector_score
        self.max_workers = max_workers
        self._fallback_scorer = MockTextHumanizer()

    def humanize(self, text: str, *, academic_tone: str = "formal") -> str:
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
        todo = [piece for piece, rewrite in pieces if rewrite]
        if not todo:
            raise StudentHumanizerError("No prose to rewrite")
        conclusions = conclusion_pieces(pieces) if self.config.conclusion_sampling else set()
        flags = [i in conclusions for i, (_, rewrite) in enumerate(pieces) if rewrite]

        with ThreadPoolExecutor(max_workers=max(1, min(self.max_workers, len(todo)))) as pool:
            rewritten = iter(pool.map(self._rewrite_chunk, todo, flags))
        out = [next(rewritten) if rewrite else piece for piece, rewrite in pieces]
        if self.config.pick == "document":
            out = self._fix_flagged(pieces, out, separator)
        if separator == "\n":
            out = [p.replace("\n\n", "\n") for p in out]
        return join_body_and_references(separator.join(out), refs)

    def _rewrite_chunk(self, chunk: str, conclusion: bool = False) -> str:
        problem = "NOT_RUN"
        # A paragraph the model only lightly edits should not sink the whole text.
        lightest: tuple[float, str] | None = None
        for attempt in range(1, ATTEMPTS + 1):
            try:
                variants = self._candidates(chunk)
            except (requests.RequestException, StudentHumanizerError, KeyError, ValueError, IndexError) as exc:
                problem = f"REQUEST_FAILED: {exc}"
                log.info("student humanizer attempt %s failed: %s", attempt, problem)
                continue
            usable, problem, light = self._usable(chunk, variants)
            if light is not None and (lightest is None or light[0] < lightest[0]):
                lightest = light
            if usable:
                if self.config.pick == "detector":
                    return self._pick_by_detector(chunk, usable, conclusion)
                return pick_candidate(chunk, usable, self.config.pick).text
            log.info("student humanizer attempt %s failed: %s", attempt, problem)
        if lightest is not None:
            return lightest[1]
        if problem == "UNCHANGED" and _wc(chunk) <= KEEP_UNCHANGED_MAX_WORDS:
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
            output = variant.text.strip()
            if single_paragraph:
                # The model sometimes splits a long paragraph in two; keep the source layout.
                output = " ".join(_paragraphs(output))
            problem = chunk_problem(chunk, output) or ""
            if not problem:
                usable.append(Candidate(output, variant.mean_logprob))
            elif problem == "UNCHANGED" and output.strip() != chunk.strip():
                similarity = _jaccard(chunk, output)
                if lightest is None or similarity < lightest[0]:
                    lightest = (similarity, output)
        return usable, problem, lightest

    def _pick_by_detector(self, chunk: str, usable: list[Candidate], conclusion: bool = False) -> str:
        """Lowest AI-detector score; still-flagged chunks and conclusions get extra variants.
        Without the detector, "changed"."""
        cfg = self.config
        try:
            scored = list(zip(usable, self._score_fn([c.text for c in usable])))
        except Exception as exc:  # noqa: BLE001
            log.info("AI detector unavailable for student pick: %s", exc)
            return pick_candidate(chunk, usable, "changed").text
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
        hit = {bisect.bisect_right(starts, s["start"]) - 1 for s in result["sentences"] if s["flagged"]}
        return sorted(i for i in hit if rewrite[i])

    def _refit(self, i: int, source: str, out: list[str], separator: str) -> str:
        """Best of the current text and fresh variants of chunk ``i``, scored with its neighbours around it."""
        current = out[i]
        try:
            fresh, _, _ = self._usable(source, self._candidates(source, self.config.refine_sampling))
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
        return pick_least_ai(source, scored)[0].text

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
    return Candidate(choice["message"]["content"] or "", mean)


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
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        sleep(BOOT_POLL_SECONDS)
        if engine.is_warm():
            return True
    return False


def try_student_humanize(
    text: str,
    *,
    humanizer: StudentTextHumanizer | None = None,
    force: bool = False,
    wait_for_boot: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any] | None:
    """Humanize with the student model when this request falls into its share.

    ``force`` skips the share draw; ``wait_for_boot`` waits up to that many seconds for a
    sleeping model instead of giving up at once.
    Returns a job-like result dict, or None when the caller should use StealthWriter.
    """
    engine = humanizer or StudentTextHumanizer()
    cfg = engine.config
    if not cfg.configured and engine._complete_fn is None:
        return None
    if not force and not pick_student(cfg):
        return None
    if not is_english(text):
        return None
    words = _wc(text)
    started = time.monotonic()
    if not _wait_until_warm(engine, wait_for_boot, sleep):
        log.info("student humanizer is cold; using StealthWriter while it boots")
        record_event(cfg, "cold", words=words, waited=round(time.monotonic() - started, 1))
        return None
    waited = round(time.monotonic() - started, 1)
    started = time.monotonic()
    try:
        output = engine.humanize(text)
    except Exception as exc:  # noqa: BLE001
        log.warning("student humanizer failed, falling back to StealthWriter: %s", exc)
        record_event(
            cfg, "failed", words=words, elapsed=round(time.monotonic() - started, 2), error=str(exc)[:200]
        )
        return None
    elapsed = round(time.monotonic() - started, 2)
    if not output.strip() or output.strip() == text.strip():
        record_event(cfg, "failed", words=words, elapsed=elapsed, error="UNCHANGED")
        return None
    record_event(cfg, "served", words=words, elapsed=elapsed, **({"waited": waited} if waited >= 1 else {}))
    return {
        "humanized_text": output,
        "elapsed_seconds": elapsed,
        "provider": PROVIDER,
        "engine": engine.VERSION,
        "request_id": f"student-{uuid.uuid4().hex[:12]}",
    }
