"""Claude-written source documents for teacher collection.

The nightly collector only spends StealthWriter quota; source texts are written
ahead of time into ``pending/`` and moved to ``used/`` once a teacher pair is
archived. Failed teacher attempts leave the document pending for the next run.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from services.humanizer_training.teacher.config import LANGUAGE
from services.humanizer_training.teacher.documents.generator import DocumentSamplingPlan
from services.humanizer_training.teacher.documents.schema import SyntheticDocument
from services.humanizer_training.teacher.documents.topic_catalog import (
    ANGLES,
    DOCUMENT_TYPES,
    DOCUMENT_TYPES_ALLOWING_REFERENCES,
    DOMAINS,
    TOPICS_BY_DOMAIN,
    build_generation_prompt,
)

DEFAULT_POOL_ROOT = Path("data/humanizer_training/source_pool")
DEFAULT_POOL_TARGET = 50
TARGET_WORDS_LOW = 3500
TARGET_WORDS_HIGH = 4500
MIN_WORDS = 2500
# StealthWriter accepts 5000 words per input; keep headroom for tokenizer differences.
MAX_WORDS = 4900
MIN_SECTIONS = 3
MIN_UNIQUE_SENTENCE_RATIO = 0.9
# Teacher attempts (across runs) before a source document is retired to failed/.
MAX_FAILURES = 2
MAX_TOKENS = 9000
# Gemini counts its thinking toward the output cap; 9000 cut documents mid-sentence.
GEMINI_MAX_TOKENS = 20000
TIMEOUT_S = 360

_FORBIDDEN = ("stealthwriter", "turnitin", "humaniz", "as an ai", "language model", "ai detector")
_HEADING_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_ENDS_SENTENCE = re.compile(r"[.!?)\]\"'”’]\s*$")

SYSTEM_PROMPT = (
    "You are an experienced academic writer producing coursework-style documents for "
    "university students. Write original, substantive prose with specific examples, "
    "varied sentence structure, and a clear argument. Output only the document in "
    "Markdown: start directly with the first `##` section heading, use `##` for every "
    "section heading, no title line, no preamble, no closing notes, no word count. "
    "Write continuous prose paragraphs only, separated by a blank line: no tables, "
    "no bullet or numbered lists, no code blocks, no diagrams or figures."
)

ReplyFn = Callable[..., tuple[str | None, dict[str, Any]]]


@dataclass(slots=True)
class PoolFillResult:
    pending_before: int
    requested: int
    generated: int = 0
    rejected: int = 0
    failed: int = 0
    pending_after: int = 0
    reject_reasons: dict[str, int] = field(default_factory=dict)
    by_writer: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _wc(text: str) -> int:
    return len([p for p in (text or "").split() if p.strip()])


def _split_refs(text: str) -> tuple[str, str]:
    match = re.search(r"(?im)^##\s+(References|Reference List|Bibliography|Works Cited)\s*$", text)
    if not match:
        return text, ""
    return text[: match.start()].rstrip(), text[match.start() :].strip()


def clean_source_text(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    first = re.search(r"(?m)^##\s+", text)
    if first:
        text = text[first.start() :]
    text = re.sub(r"(?m)^#{3,}\s+", "## ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fit_source_length(text: str, *, limit: int = TARGET_WORDS_HIGH) -> str:
    """Drop whole middle sections (never the first, the last body section or references)."""
    if _wc(text) <= MAX_WORDS:
        return text
    body, refs = _split_refs(text)
    starts = [m.start() for m in _HEADING_RE.finditer(body)]
    if len(starts) < 3:
        return text
    sections = [body[a:b].strip() for a, b in zip(starts, starts[1:] + [len(body)])]
    budget = limit - _wc(refs)
    keep = list(sections)
    while sum(_wc(s) for s in keep) > budget and len(keep) > MIN_SECTIONS:
        del keep[-2]
    return "\n\n".join(keep + ([refs] if refs else []))


def validate_source_text(text: str) -> list[str]:
    reasons: list[str] = []
    words = _wc(text)
    if words < MIN_WORDS:
        reasons.append("TOO_SHORT")
    if words > MAX_WORDS:
        reasons.append("TOO_LONG")
    if len(_HEADING_RE.findall(text)) < MIN_SECTIONS:
        reasons.append("TOO_FEW_SECTIONS")
    low = text.lower()
    if any(tok in low for tok in _FORBIDDEN):
        reasons.append("FORBIDDEN_TERM")
    body, _ = _split_refs(text)
    sentences = [
        s.strip()
        for s in _SENTENCE_SPLIT.split(_HEADING_RE.sub("", body))
        if len(s.split()) > 3
    ]
    if sentences and len(set(sentences)) / len(sentences) < MIN_UNIQUE_SENTENCE_RATIO:
        reasons.append("REPETITIVE")
    if not is_plain_prose(body):
        reasons.append("NON_PROSE")
    return reasons


def is_plain_prose(body: str) -> bool:
    """Every block is one line of prose: tables, lists and diagrams break section pairing."""
    for block in (body or "").split("\n\n"):
        lines = [ln for ln in block.split("\n") if ln.strip() and not ln.lstrip().startswith("## ")]
        if len(lines) > 1:
            return False
        if lines and re.match(r"^\s*(\||```|[-*•+]\s|\d+[.)]\s)", lines[0]):
            return False
    return True


def _document_id(combination_key: str, text: str) -> str:
    digest = hashlib.sha256(f"{combination_key}|{text}".encode("utf-8")).hexdigest()
    return f"src-{digest[:16]}"


def build_document(
    *,
    domain: str,
    topic: str,
    document_type: str,
    angle: str,
    text: str,
    seed: int,
) -> SyntheticDocument:
    body, refs = _split_refs(text)
    titles = _HEADING_RE.findall(text)
    key = f"{domain}|{topic}|{document_type}|{angle}"
    words = _wc(text)
    return SyntheticDocument(
        document_id=_document_id(key, text),
        source_text=text,
        domain=domain,
        document_type=document_type,
        language=LANGUAGE,
        seed=int(seed),
        word_count=words,
        body_word_count=_wc(body),
        references_present=bool(refs),
        references_word_count=_wc(refs),
        section_count=len(titles),
        section_titles=titles,
        length_bucket="claude_long" if words >= 3500 else "claude_medium",
        topic=topic,
        angle=angle,
        generation_prompt=build_generation_prompt(
            domain=domain,
            topic=topic,
            document_type=document_type,
            angle=angle,
            target_words_low=TARGET_WORDS_LOW,
            target_words_high=TARGET_WORDS_HIGH,
        ),
        combination_key=key,
    )


def _default_reply_fn() -> ReplyFn:
    from services.claude_client import generate_reply

    return generate_reply


def _reply_fn_for(provider: str) -> ReplyFn:
    if provider == "gemini":
        from services.gemini_client import generate_text

        return generate_text
    return _default_reply_fn()


def parse_source_mix(raw: str) -> list[tuple[str, str, float]]:
    """``"claude:claude-haiku-4-5:2,gemini:gemini-3.5-flash:3"`` -> [(provider, model, weight)]."""
    mix: list[tuple[str, str, float]] = []
    for part in (raw or "").split(","):
        if not part.strip():
            continue
        provider, model, *weight = [p.strip() for p in part.split(":")]
        if provider not in ("claude", "gemini") or not model:
            raise ValueError(f"bad source mix entry: {part!r}")
        mix.append((provider, model, float(weight[0]) if weight else 1.0))
    if not mix:
        raise ValueError("empty source mix")
    return mix


def pick_writer(combo_key: str, mix: list[tuple[str, str, float]]) -> tuple[str, str]:
    """Weighted writer choice, stable for a brief."""
    digest = hashlib.sha256(f"writer|{combo_key}".encode("utf-8")).digest()
    point = int.from_bytes(digest[:8], "big") / float(1 << 64) * sum(w for *_, w in mix)
    for provider, model, weight in mix:
        point -= weight
        if point < 0:
            return provider, model
    return mix[-1][0], mix[-1][1]


class SourcePool:
    def __init__(self, root: Path | str = DEFAULT_POOL_ROOT) -> None:
        self.root = Path(root)
        self.pending_dir = self.root / "pending"
        self.used_dir = self.root / "used"
        self.failed_dir = self.root / "failed"
        self.rejected_path = self.root / "rejected.jsonl"

    def _ensure(self) -> None:
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.used_dir.mkdir(parents=True, exist_ok=True)

    def pending_count(self) -> int:
        return len(list(self.pending_dir.glob("*.json"))) if self.pending_dir.is_dir() else 0

    def used_count(self) -> int:
        return len(list(self.used_dir.glob("*.json"))) if self.used_dir.is_dir() else 0

    def _read(self, path: Path) -> SyntheticDocument:
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = SyntheticDocument.__dataclass_fields__
        return SyntheticDocument(**{k: v for k, v in data.items() if k in fields})

    def peek(self, count: int) -> list[SyntheticDocument]:
        if count <= 0 or not self.pending_dir.is_dir():
            return []
        paths = sorted(self.pending_dir.glob("*.json"), key=lambda p: (p.stat().st_mtime, p.name))
        return [self._read(p) for p in paths[:count]]

    def mark_used(self, document_id: str) -> bool:
        self._ensure()
        src = self.pending_dir / f"{document_id}.json"
        if not src.is_file():
            return False
        src.replace(self.used_dir / src.name)
        return True

    def writer_of(self, document_id: str) -> str | None:
        """Model that wrote a pending source document, if recorded."""
        path = self.pending_dir / f"{document_id}.json"
        try:
            meta = json.loads(path.read_text(encoding="utf-8")).get("source_generator") or {}
        except (OSError, ValueError):
            return None
        return meta.get("model")

    def record_failure(self, document_id: str, *, max_failures: int = MAX_FAILURES) -> bool:
        """Count a failed teacher attempt; move the document to ``failed/`` at the limit.

        Rewriting the file also moves it to the back of the ``peek`` queue.
        Returns True when the document was retired.
        """
        path = self.pending_dir / f"{document_id}.json"
        if not path.is_file():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        data["failure_count"] = int(data.get("failure_count") or 0) + 1
        target = path
        if data["failure_count"] >= max_failures:
            self.failed_dir.mkdir(parents=True, exist_ok=True)
            target = self.failed_dir / path.name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(target)
        if target != path:
            path.unlink(missing_ok=True)
        return target != path

    def used_combination_keys(self) -> set[str]:
        keys: set[str] = set()
        for folder in (self.pending_dir, self.used_dir, self.failed_dir):
            if not folder.is_dir():
                continue
            for path in folder.glob("*.json"):
                try:
                    keys.add(str(json.loads(path.read_text(encoding="utf-8")).get("combination_key") or ""))
                except (OSError, ValueError):
                    continue
        keys.discard("")
        return keys

    def add(self, doc: SyntheticDocument, *, meta: dict[str, Any] | None = None) -> Path:
        self._ensure()
        payload = asdict(doc)
        payload["created_at"] = datetime.now(timezone.utc).isoformat()
        payload["source_generator"] = meta or {}
        path = self.pending_dir / f"{doc.document_id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        return path

    def record_rejection(self, payload: dict[str, Any]) -> None:
        self._ensure()
        with self.rejected_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def next_briefs(self, count: int, *, seed: int) -> list[tuple[str, str, str, str]]:
        used = self.used_combination_keys()
        combos = [
            (d, t, dt, a)
            for d in DOMAINS
            for t in TOPICS_BY_DOMAIN[d]
            for dt in DOCUMENT_TYPES
            for a in ANGLES
            if f"{d}|{t}|{dt}|{a}" not in used
        ]
        random.Random(seed).shuffle(combos)
        # Spread consecutive picks across domains so one fill is not single-subject.
        picked: list[tuple[str, str, str, str]] = []
        per_domain: Counter[str] = Counter()
        cap = max(1, count // max(1, len(DOMAINS)) + 1)
        for combo in combos:
            if len(picked) >= count:
                break
            if per_domain[combo[0]] >= cap:
                continue
            picked.append(combo)
            per_domain[combo[0]] += 1
        for combo in combos:
            if len(picked) >= count:
                break
            if combo not in picked:
                picked.append(combo)
        return picked


def generate_source_document(
    combo: tuple[str, str, str, str],
    *,
    seed: int,
    reply_fn: ReplyFn,
    model: str | None = None,
) -> tuple[SyntheticDocument | None, list[str], dict[str, Any]]:
    domain, topic, document_type, angle = combo
    prompt = build_generation_prompt(
        domain=domain,
        topic=topic,
        document_type=document_type,
        angle=angle,
        target_words_low=TARGET_WORDS_LOW,
        target_words_high=TARGET_WORDS_HIGH,
    )
    raw, diag = reply_fn(
        system_prompt=SYSTEM_PROMPT,
        content=prompt,
        temperature=0.9,
        model=model,
        timeout_s=TIMEOUT_S,
        max_tokens=GEMINI_MAX_TOKENS if str(model or "").startswith("gemini") else MAX_TOKENS,
    )
    if not raw:
        return None, ["CLAUDE_FAILED"], diag
    text = fit_source_length(clean_source_text(raw))
    reasons = validate_source_text(text)
    if diag.get("finish_reason") == "MAX_TOKENS" or not _ENDS_SENTENCE.search(text):
        reasons.append("TRUNCATED")
    if document_type not in DOCUMENT_TYPES_ALLOWING_REFERENCES and _split_refs(text)[1]:
        reasons.append("UNEXPECTED_REFERENCES")
    if reasons:
        diag = {**diag, "word_count": _wc(text), "text_preview": text[:400]}
        return None, reasons, diag
    doc = build_document(
        domain=domain,
        topic=topic,
        document_type=document_type,
        angle=angle,
        text=text,
        seed=seed,
    )
    return doc, [], diag


def fill_source_pool(
    *,
    target_pending: int = DEFAULT_POOL_TARGET,
    max_new: int | None = None,
    seed: int | None = None,
    root: Path | str = DEFAULT_POOL_ROOT,
    workers: int = 3,
    reply_fn: ReplyFn | None = None,
    model: str | None = None,
    mix: list[tuple[str, str, float]] | None = None,
) -> PoolFillResult:
    pool = SourcePool(root)
    pending = pool.pending_count()
    need = max(0, int(target_pending) - pending)
    if max_new is not None:
        need = min(need, max(0, int(max_new)))
    result = PoolFillResult(pending_before=pending, requested=need)
    if need == 0:
        result.pending_after = pending
        return result

    active_seed = int(seed) if seed is not None else int(datetime.now(timezone.utc).strftime("%Y%m%d%H"))
    combos = pool.next_briefs(need, seed=active_seed)
    reasons_counter: Counter[str] = Counter()

    def _one(combo: tuple[str, str, str, str]):
        if reply_fn is not None or not mix:
            provider, writer = "claude", model
            fn = reply_fn or _default_reply_fn()
        else:
            provider, writer = pick_writer("|".join(combo), mix)
            fn = _reply_fn_for(provider)
        return combo, provider, *generate_source_document(combo, seed=active_seed, reply_fn=fn, model=writer)

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        for combo, provider, doc, reasons, diag in executor.map(_one, combos):
            if doc is not None:
                pool.add(
                    doc,
                    meta={"provider": provider, "model": diag.get("model"), "latency_ms": diag.get("latency_ms")},
                )
                result.generated += 1
                result.by_writer[str(diag.get("model"))] = result.by_writer.get(str(diag.get("model")), 0) + 1
                continue
            reasons_counter.update(reasons)
            if reasons == ["CLAUDE_FAILED"]:
                result.failed += 1
            else:
                result.rejected += 1
            pool.record_rejection(
                {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "combination_key": "|".join(combo),
                    "writer": diag.get("model"),
                    "reasons": reasons,
                    "error_message": diag.get("error_message"),
                    "word_count": diag.get("word_count"),
                    "text_preview": diag.get("text_preview"),
                }
            )

    result.reject_reasons = dict(sorted(reasons_counter.items()))
    result.pending_after = pool.pending_count()
    return result


def sampling_plan_for(docs: list[SyntheticDocument]) -> DocumentSamplingPlan:
    def _count(values: list[str]) -> dict[str, int]:
        return dict(Counter(values))

    sections = Counter(d.section_count for d in docs)
    return DocumentSamplingPlan(
        document_types=_count([d.document_type for d in docs]),
        domains=_count([d.domain for d in docs]),
        topics=_count([d.topic for d in docs]),
        angles=_count([d.angle for d in docs]),
        length_buckets=_count([d.length_bucket for d in docs]),
        with_references=sum(1 for d in docs if d.references_present),
        section_count_histogram=dict(sorted(sections.items())),
        combinations=[d.combination_key for d in docs],
    )


__all__ = [
    "DEFAULT_POOL_ROOT",
    "DEFAULT_POOL_TARGET",
    "PoolFillResult",
    "SourcePool",
    "clean_source_text",
    "fill_source_pool",
    "generate_source_document",
    "sampling_plan_for",
    "validate_source_text",
]
