"""Our own humanizer: the fine-tuned student model served behind an OpenAI-compatible endpoint.

Prose paragraphs are grouped into ~600-word chunks (the size the model was trained on) and
rewritten in parallel; headings, lists, tables, figure markers and references stay verbatim.
Any chunk that fails the quality checks is retried, and if it still fails the whole call
raises so the caller can fall back to StealthWriter.
"""

from __future__ import annotations

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
from services.humanizer_engine.heading_utils import join_body_and_references, split_off_references
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

_WORD = re.compile(r"[a-z0-9']+")
_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
_LETTER = re.compile(r"[^\W\d_]")
_VERBATIM_LINE = re.compile(r"^\s*(##\s|\||```|[-*•+]\s|\d+[.)]\s)")


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

    @property
    def configured(self) -> bool:
        return bool(self.url and self.api_key)


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
    )


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

    for block in (b.strip() for b in body.split(separator)):
        if not block:
            continue
        if _is_verbatim(block):
            _flush()
            pieces.append((block, False))
            continue
        if prose and _wc("\n\n".join(prose + [block])) > chunk_words:
            _flush()
        prose.append(block)
    _flush()
    return pieces


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


class StudentTextHumanizer:
    """Same ``humanize(text)`` contract as ``StealthWriterTextHumanizer``."""

    VERSION = "docmaxxing-student-v1"

    def __init__(
        self,
        config: StudentConfig | None = None,
        *,
        complete_fn: Callable[[str], str] | None = None,
        max_workers: int = 32,
    ) -> None:
        self.config = config or student_config()
        self._complete_fn = complete_fn
        self.max_workers = max_workers
        self._fallback_scorer = MockTextHumanizer()

    def humanize(self, text: str, *, academic_tone: str = "formal") -> str:
        del academic_tone
        if not text.strip():
            return text
        if len(text.strip()) < MIN_HUMANIZE_CHARS:
            return text.strip()

        body, refs = split_off_references(text)
        separator = "\n\n" if "\n\n" in body or "\n" not in body.strip() else "\n"
        pieces = plan_chunks(body, separator, self.config.chunk_words)
        todo = [piece for piece, rewrite in pieces if rewrite]
        if not todo:
            raise StudentHumanizerError("No prose to rewrite")

        with ThreadPoolExecutor(max_workers=max(1, min(self.max_workers, len(todo)))) as pool:
            rewritten = iter(pool.map(self._rewrite_chunk, todo))
        out = [next(rewritten) if rewrite else piece for piece, rewrite in pieces]
        if separator == "\n":
            out = [p.replace("\n\n", "\n") for p in out]
        return join_body_and_references(separator.join(out), refs)

    def _rewrite_chunk(self, chunk: str) -> str:
        problem = "NOT_RUN"
        # A paragraph the model only lightly edits should not sink the whole text.
        lightest: tuple[float, str] | None = None
        for attempt in range(1, ATTEMPTS + 1):
            try:
                output = self._complete(chunk).strip()
            except (requests.RequestException, StudentHumanizerError, KeyError, ValueError) as exc:
                problem = f"REQUEST_FAILED: {exc}"
            else:
                problem = chunk_problem(chunk, output) or ""
                if not problem:
                    return output
                if problem == "UNCHANGED" and output.strip() != chunk.strip():
                    similarity = _jaccard(chunk, output)
                    if lightest is None or similarity < lightest[0]:
                        lightest = (similarity, output)
            log.info("student humanizer attempt %s failed: %s", attempt, problem)
        if lightest is not None:
            return lightest[1]
        raise StudentHumanizerError(f"Chunk rejected after {ATTEMPTS} attempts: {problem}")

    def _complete(self, chunk: str) -> str:
        if self._complete_fn is not None:
            return self._complete_fn(chunk)
        cfg = self.config
        if not cfg.configured:
            raise StudentHumanizerError("Student humanizer is not configured")
        response = requests.post(
            f"{cfg.url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={
                "model": cfg.model,
                "messages": [
                    {"role": "system", "content": system_prompt(cfg.level)},
                    {"role": "user", "content": chunk},
                ],
                "temperature": TEMPERATURE,
                "top_p": TOP_P,
                "max_tokens": int(_wc(chunk) * 1.35 * 2) + 64,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=cfg.timeout,
        )
        if response.status_code != 200:
            raise StudentHumanizerError(f"HTTP {response.status_code}: {response.text[:200]}")
        return response.json()["choices"][0]["message"]["content"] or ""

    def is_warm(self) -> bool:
        """True when the model answers right away.

        A scaled-to-zero server takes ~2 minutes to boot; the probe itself starts that boot,
        so requests in the next minutes find the model ready.
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
    """Wake the model in the background when a user opens a humanizer page.

    The boot takes about a minute, roughly the time it takes to paste a text. At most one
    wake-up per ``WARMUP_EVERY_SECONDS`` per process; returns True when one was sent.
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
        sleep(5)
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
    sleeping model instead of giving up at once (used when StealthWriter cannot answer).
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
