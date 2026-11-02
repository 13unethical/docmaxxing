"""Free AI detector: our DeBERTa model trained on Turnitin highlights (served on Modal).

The model was trained on ~110-word windows of consecutive sentences. Every sentence gets
the mean probability of the windows that contain it; the document score is the share of
words in sentences above the threshold, like Turnitin's "% of text flagged as AI".

Environment:
  AI_DETECTOR_URL / AI_DETECTOR_API_KEY   Modal endpoint (ai_detector/serve_modal.py)
  AI_DETECTOR_THRESHOLD=0.5               sentence counts as AI above this probability
  FREE_DETECT_GUEST_WORDS=1500            words per check without an account
  FREE_DETECT_GUEST_DAILY=10              checks per UTC day without an account (per IP + session)
  FREE_DETECT_USER_WORDS=5000             words per check for a signed-in user
  FREE_DETECT_USER_DAILY=50               checks per UTC day for a signed-in user
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests

from services.free_humanize import RateLimiter

guest_rate_limiter = RateLimiter()

WINDOW_WORDS = 110
MIN_SCORED_WORDS = 40
_SENT = re.compile(r"(?<=[.!?])[\"'”’)]*\s+(?=[A-Z\"“(])")
_REFERENCE_HINT = re.compile(r"https?://|doi\.org|\bdoi:|\(\d{4}[a-z]?\)\.|Retrieved from", re.I)


class DetectorUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class DetectLimits:
    guest_words: int
    guest_daily: int
    user_words: int
    user_daily: int


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        return max(0, int(raw)) if raw else default
    except ValueError:
        return default


def limits() -> DetectLimits:
    return DetectLimits(
        guest_words=_env_int("FREE_DETECT_GUEST_WORDS", 1500),
        guest_daily=_env_int("FREE_DETECT_GUEST_DAILY", 10),
        user_words=_env_int("FREE_DETECT_USER_WORDS", 5000),
        user_daily=_env_int("FREE_DETECT_USER_DAILY", 50),
    )


def threshold() -> float:
    try:
        return float(os.environ.get("AI_DETECTOR_THRESHOLD") or 0.5)
    except ValueError:
        return 0.5


@dataclass
class Sentence:
    start: int
    end: int
    text: str
    words: int
    scored: bool
    prob: float | None = None


def split_sentences(text: str) -> list[Sentence]:
    """Sentences with offsets into ``text``; lines are split separately (headings, list items)."""
    out: list[Sentence] = []
    for line in re.finditer(r"[^\n]+", text):
        base, body = line.start(), line.group()
        reference_entry = bool(_REFERENCE_HINT.search(body)) and len(body.split()) <= 60
        cuts = [0, len(body)] if reference_entry else [0, *(m.end() for m in _SENT.finditer(body)), len(body)]
        for a, b in zip(cuts, cuts[1:]):
            chunk = body[a:b]
            stripped = chunk.strip()
            if not stripped:
                continue
            start = base + a + (len(chunk) - len(chunk.lstrip()))
            words = len(stripped.split())
            # Headings, short list items and reference entries are not prose the model knows.
            scored = words >= 4 and not _REFERENCE_HINT.search(stripped)
            out.append(Sentence(start, start + len(stripped), stripped, words, scored))
    return out


def windows(sentences: list[Sentence]) -> list[tuple[int, int]]:
    """Index ranges [i, j) of scored sentences, one window starting at each sentence."""
    idx = [k for k, s in enumerate(sentences) if s.scored]
    out = []
    for a in range(len(idx)):
        words, b = 0, a
        while b < len(idx) and words < WINDOW_WORDS:
            words += sentences[idx[b]].words
            b += 1
        out.append((a, b))
        if b == len(idx):
            break
    return [(idx[a], idx[b - 1] + 1) for a, b in out]


def _score_remote(texts: list[str]) -> tuple[list[float], str]:
    url = (os.environ.get("AI_DETECTOR_URL") or "").strip().rstrip("/")
    key = (os.environ.get("AI_DETECTOR_API_KEY") or "").strip()
    if not url or not key:
        raise DetectorUnavailable("AI detector is not configured")
    try:
        res = requests.post(
            f"{url}/score", json={"texts": texts}, headers={"Authorization": f"Bearer {key}"}, timeout=90
        )
        res.raise_for_status()
        body = res.json()
    except (requests.RequestException, ValueError) as exc:
        raise DetectorUnavailable(str(exc)) from exc
    probs = body.get("probs")
    if not isinstance(probs, list) or len(probs) != len(texts):
        raise DetectorUnavailable("bad detector response")
    return [float(p) for p in probs], str(body.get("model") or "")


def score_texts(texts: list[str]) -> list[float]:
    """AI probability of each text as one unit (no sentence windows); raises DetectorUnavailable."""
    return _score_remote(texts)[0] if texts else []


def detect(text: str, *, score=None) -> dict:
    score = score or _score_remote
    sentences = split_sentences(text)
    spans = windows(sentences)
    if sum(s.words for s in sentences if s.scored) < MIN_SCORED_WORDS or not spans:
        return {"too_short": True}
    texts = [" ".join(s.text for s in sentences[a:b] if s.scored) for a, b in spans]
    probs, model = score(texts)
    sums: dict[int, list[float]] = {}
    for (a, b), p in zip(spans, probs):
        for k in range(a, b):
            if sentences[k].scored:
                sums.setdefault(k, []).append(p)
    for k, ps in sums.items():
        sentences[k].prob = sum(ps) / len(ps)

    cut = threshold()
    scored_words = sum(s.words for s in sentences if s.prob is not None)
    flagged_words = sum(s.words for s in sentences if s.prob is not None and s.prob > cut)
    ai_percent = round(100 * flagged_words / scored_words) if scored_words else 0
    return {
        "ai_percent": ai_percent,
        "verdict": "ai" if ai_percent >= 60 else ("mixed" if ai_percent >= 20 else "human"),
        "words": len(text.split()),
        "scored_words": scored_words,
        "sentences": [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "ai_prob": None if s.prob is None else round(s.prob, 3),
                "flagged": s.prob is not None and s.prob > cut,
            }
            for s in sentences
        ],
        "model": model,
    }
