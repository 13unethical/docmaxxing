"""ChatGPT-written student texts: AI examples for the detector and real-looking humanizer inputs.

Prompts imitate what students actually type into ChatGPT (short requests, 250–2500 words, with or
without headings), and the answers are flattened the way they look after copying from the ChatGPT
page. Each document is assigned to train or test by its id, so both uses share one split.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from services.humanizer_training.teacher.documents.topic_catalog import ANGLES, TOPICS_BY_DOMAIN

DEFAULT_OUT = Path("data/detector_corpus/chatgpt.jsonl")
DEFAULT_MODEL_MIX = "gpt-4o:3,gpt-5:2,gpt-4.1:2,gpt-5-mini:2,gpt-4o-mini:1"
TEST_SHARE = 15  # percent of documents held out
WINDOW_WORDS = 110
MIN_WINDOW_WORDS = 40
SOURCE = "openai_chatgpt"

KINDS = (
    "essay", "argumentative essay", "persuasive essay", "reflective essay", "compare and contrast essay",
    "cause and effect essay", "research paper", "literature review", "report", "case study analysis",
    "discussion board post", "critical analysis", "position paper", "annotated summary",
)
COURSES = (
    "English composition", "sociology", "psychology", "business", "nursing", "history", "economics",
    "environmental science", "education", "political science", "marketing", "public health", "philosophy",
)
WORD_TARGETS = ((250, 1), (400, 2), (600, 3), (800, 3), (1000, 3), (1500, 2), (2000, 1), (2500, 1))
TONES = (
    ("", 10),
    (" Use simple language.", 1),
    (" Write it in a formal academic tone.", 2),
    (" Make it sound like a college student wrote it.", 1),
    (" Make it sound human and natural.", 1),
    (" Include in-text citations in APA style.", 2),
)
TEMPLATES = (
    "Write a {words}-word {kind} on {topic}.{tone}",
    "Can you write me {a_kind} about {topic}? Around {words} words.{tone}",
    "I need a {words} word {kind} for my {course} class. The topic is {topic}.{tone}",
    "Write {a_kind} about {topic} with an introduction, body paragraphs and a conclusion. "
    "About {words} words.{tone}",
    "Write {a_kind} on {topic}, focusing on {angle}. {words} words, use headings.{tone}",
    "{topic} — write a {words} word {kind} for {course}.{tone}",
)

_MD_HEADING = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]*")
_MD_BULLET = re.compile(r"(?m)^[ \t]*(?:[-*•+]|\d+[.)])[ \t]+")
_MD_EMPH = re.compile(r"(\*\*|__|\*|`)")
_SENT = re.compile(r"(?<=[.!?])[\"'”’)]*\s+(?=[A-Z\"“(])")
_REFERENCE_HINT = re.compile(r"https?://|doi\.org|\bdoi:|\(\d{4}[a-z]?\)\.|Retrieved from", re.I)


def parse_model_mix(raw: str) -> list[tuple[str, float]]:
    out = []
    for part in (raw or "").split(","):
        if part.strip():
            model, _, weight = part.strip().partition(":")
            out.append((model.strip(), float(weight or 1)))
    if not out:
        raise ValueError("empty model mix")
    return out


def _weighted(rng: random.Random, items):
    return rng.choices([v for v, _ in items], weights=[w for _, w in items], k=1)[0]


@dataclass(slots=True)
class Brief:
    brief_id: str
    model: str
    prompt: str
    target_words: int

    @property
    def split(self) -> str:
        return split_of(self.brief_id)


def split_of(doc_id: str) -> str:
    return "test" if int(hashlib.sha256(doc_id.encode()).hexdigest()[:8], 16) % 100 < TEST_SHARE else "train"


def make_briefs(count: int, *, seed: int, model_mix: list[tuple[str, float]]) -> list[Brief]:
    rng = random.Random(seed)
    topics = [t.replace("_", " ") for ts in TOPICS_BY_DOMAIN.values() for t in ts]
    briefs = []
    for i in range(count):
        words = _weighted(rng, WORD_TARGETS)
        kind = rng.choice(KINDS)
        prompt = rng.choice(TEMPLATES).format(
            words=words,
            kind=kind,
            a_kind=("an " if kind[0] in "aeiou" else "a ") + kind,
            topic=rng.choice(topics),
            course=rng.choice(COURSES),
            angle=rng.choice(ANGLES).replace("_", " "),
            tone=_weighted(rng, TONES),
        )
        model = _weighted(rng, model_mix)
        brief_id = "gpt-" + hashlib.sha256(f"{seed}|{i}|{model}|{prompt}".encode()).hexdigest()[:16]
        briefs.append(Brief(brief_id, model, prompt, words))
    return briefs


def flatten_markdown(text: str) -> str:
    """Text as it looks after copying a rendered ChatGPT answer: no Markdown markers."""
    text = re.sub(r"(?m)^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$", "", text or "")
    text = _MD_HEADING.sub("", text)
    text = _MD_BULLET.sub("", text)
    text = _MD_EMPH.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def windows(text: str) -> Iterator[str]:
    """Consecutive sentences grouped to ~WINDOW_WORDS words, like the Turnitin label windows."""
    flat = re.sub(r"\s+", " ", text or "").strip()
    spans, start = [], 0
    for m in _SENT.finditer(flat):
        spans.append(flat[start : m.start()])
        start = m.end()
    spans.append(flat[start:])
    group: list[str] = []
    for span in spans:
        group.append(span)
        if len(" ".join(group).split()) >= WINDOW_WORDS:
            body = " ".join(group).strip()
            if len(body.split()) >= MIN_WINDOW_WORDS and not _REFERENCE_HINT.search(body):
                yield body
            group = []
    body = " ".join(group).strip()
    if len(body.split()) >= MIN_WINDOW_WORDS and not _REFERENCE_HINT.search(body):
        yield body


def detector_rows(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Training rows for ai_detector/train_modal.py (``/data/chatgpt_*.jsonl``)."""
    rows = []
    for d in docs:
        for w in windows(d["text"]):
            rows.append({"text": w, "ai": 1, "ai_frac": 1.0, "source": SOURCE, "doc": d["id"], "split": d["split"]})
    return rows


def read_docs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


ReplyFn = Callable[..., tuple[str | None, dict[str, Any]]]


def generate_one(brief: Brief, reply_fn: ReplyFn) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    max_tokens = 16000 if brief.model.startswith(("gpt-5", "o")) else int(brief.target_words * 2.2) + 600
    raw, diag = reply_fn(system_prompt="", content=brief.prompt, temperature=1.0, model=brief.model, max_tokens=max_tokens)
    if not raw or diag.get("finish_reason") == "MAX_TOKENS":
        return None, diag
    text = flatten_markdown(raw)
    if len(text.split()) < 150:
        return None, {**diag, "error_message": "too short"}
    return {
        "id": brief.brief_id,
        "model": diag.get("model") or brief.model,
        "requested_model": brief.model,
        "prompt": brief.prompt,
        "target_words": brief.target_words,
        "words": len(text.split()),
        "split": brief.split,
        "text": text,
        "cost_usd": diag.get("cost_usd"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, diag
