"""Section-level chat-SFT dataset from teacher documents, conditioned on rewrite level.

Whole teacher documents are ~4,500 words (too long to train on comfortably), but
headings survive the teacher exactly, so source and teacher align section by section.
Each example is one section body; the system message carries the StealthWriter level
so one student model can serve every level. Splits are by document (no leakage).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from services.humanizer_engine.heading_utils import split_off_references

DEFAULT_INPUT_GLOBS = (
    "data/humanizer_training/bulk/*/batch-*/documents.jsonl",
    "data/humanizer_training/synthetic_daily/*/teacher_raw/documents.jsonl",
)
DEFAULT_OUT = Path("data/humanizer_training/section_sft")
TEACHER_MODEL = "Legacy 5.1"

MIN_SECTION_WORDS = 40
MAX_SECTION_WORDS = 1200
CHUNK_WORDS = 600
RATIO_RANGE = (0.6, 1.9)
MAX_JACCARD = 0.9
VAL_SHARE = 0.05
TEST_SHARE = 0.05

_HEADING = re.compile(r"(?m)^##\s+(.+?)\s*$")
_WORD = re.compile(r"[a-z0-9']+")


def system_prompt(level: int) -> str:
    return (
        "Rewrite the user's text so it reads like natural writing by a student. Keep the meaning, "
        "facts, numbers, names, in-text citations and paragraph breaks. Do not add headings, "
        f"comments or new content. Rewrite strength: {int(level)}/10."
    )


@dataclass(slots=True)
class BuildReport:
    documents_seen: int = 0
    documents_used: int = 0
    examples: dict[str, int] = field(default_factory=lambda: {"train": 0, "val": 0, "test": 0})
    by_level: Counter[str] = field(default_factory=Counter)
    by_writer: Counter[str] = field(default_factory=Counter)
    document_rejects: Counter[str] = field(default_factory=Counter)
    section_rejects: Counter[str] = field(default_factory=Counter)
    source_words: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        words = sorted(self.source_words)
        total_words = sum(words)
        return {
            "documents_seen": self.documents_seen,
            "documents_used": self.documents_used,
            "examples": dict(self.examples),
            "examples_by_level": dict(sorted(self.by_level.items())),
            "documents_by_writer": dict(self.by_writer.most_common()),
            "document_rejects": dict(self.document_rejects.most_common()),
            "section_rejects": dict(self.section_rejects.most_common()),
            "source_words": {
                "total": total_words,
                "median": words[len(words) // 2] if words else 0,
                "max": words[-1] if words else 0,
            },
            # ~1.35 tokens per word, source + target (~1.3x longer) + prompt overhead.
            "approx_train_tokens": int(total_words * 1.35 * 2.3),
        }


def _wc(text: str) -> int:
    return len(text.split())


def _jaccard(a: str, b: str) -> float:
    left, right = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    return len(left & right) / len(left | right) if left | right else 1.0


def split_sections(body: str) -> list[tuple[str, str]]:
    """``## Title`` sections of a document body as (title, text) pairs."""
    matches = list(_HEADING.finditer(body))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out.append((m.group(1).strip(), body[m.end():end].strip()))
    return out


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def section_pairs(source: str, target: str) -> tuple[list[tuple[str, str]], str | None]:
    """Aligned (source, target) chunks; long sections split on matching paragraph breaks."""
    if _wc(source) <= CHUNK_WORDS * 1.5:
        return [(source, target)], None
    src_paras, tgt_paras = _paragraphs(source), _paragraphs(target)
    if len(src_paras) != len(tgt_paras):
        if _wc(source) <= MAX_SECTION_WORDS:
            return [(source, target)], None
        return [], "LONG_SECTION_UNALIGNED"
    chunks: list[tuple[str, str]] = []
    cur_s: list[str] = []
    cur_t: list[str] = []
    for s, t in zip(src_paras, tgt_paras):
        if cur_s and _wc("\n\n".join(cur_s + [s])) > CHUNK_WORDS:
            chunks.append(("\n\n".join(cur_s), "\n\n".join(cur_t)))
            cur_s, cur_t = [], []
        cur_s.append(s)
        cur_t.append(t)
    if cur_s:
        chunks.append(("\n\n".join(cur_s), "\n\n".join(cur_t)))
    return chunks, None


def _document_reject(doc: dict[str, Any]) -> str | None:
    if doc.get("status") != "accepted":
        return "NOT_ACCEPTED"
    if doc.get("source_kind") == "template":
        return "TEMPLATE_SOURCE"
    meta = doc.get("teacher_meta") or {}
    if not meta.get("selection_verified"):
        return "SELECTION_NOT_VERIFIED"
    if (meta.get("verified_model") or doc.get("teacher_model")) != TEACHER_MODEL:
        return "WRONG_MODEL"
    level = doc.get("teacher_level")
    if not isinstance(level, int) or meta.get("verified_level") != level:
        return "LEVEL_NOT_VERIFIED"
    return None


def _section_reject(source: str, target: str) -> str | None:
    if _wc(source) < MIN_SECTION_WORDS:
        return "TOO_SHORT"
    if not target.strip():
        return "EMPTY_TARGET"
    if _HEADING.search(target):
        return "HEADING_IN_TARGET"
    if len(_paragraphs(source)) > 1 and len(_paragraphs(target)) == 1:
        return "PARAGRAPHS_MERGED"
    ratio = _wc(target) / _wc(source)
    if not RATIO_RANGE[0] <= ratio <= RATIO_RANGE[1]:
        return "LENGTH_RATIO"
    if _jaccard(source, target) > MAX_JACCARD:
        return "UNCHANGED"
    return None


def split_for(document_id: str) -> str:
    point = int(hashlib.sha256(f"split|{document_id}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    if point < TEST_SHARE:
        return "test"
    if point < TEST_SHARE + VAL_SHARE:
        return "val"
    return "train"


def iter_documents(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


def build_section_sft(
    *,
    root: Path = Path("."),
    input_globs: tuple[str, ...] = DEFAULT_INPUT_GLOBS,
    output_dir: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    paths = sorted({p for pattern in input_globs for p in Path(root).glob(pattern)})
    output_dir.mkdir(parents=True, exist_ok=True)
    report = BuildReport()
    seen_sources: set[str] = set()
    seen_docs: set[str] = set()
    handles = {name: (output_dir / f"{name}.jsonl").open("w", encoding="utf-8") for name in ("train", "val", "test")}
    meta_out = (output_dir / "examples_meta.jsonl").open("w", encoding="utf-8")
    try:
        for doc in iter_documents(paths):
            report.documents_seen += 1
            doc_id = str(doc.get("document_id") or "")
            if doc_id in seen_docs:
                report.document_rejects["DUPLICATE_DOCUMENT"] += 1
                continue
            reason = _document_reject(doc)
            src_body, _ = split_off_references(str(doc.get("source_text") or ""))
            tgt_body, _ = split_off_references(str(doc.get("teacher_text") or ""))
            src_sections, tgt_sections = split_sections(src_body), split_sections(tgt_body)
            if reason is None and [t for t, _ in src_sections] != [t for t, _ in tgt_sections]:
                reason = "HEADINGS_DIFFER"
            if reason is None and not src_sections:
                reason = "NO_SECTIONS"
            if reason:
                report.document_rejects[reason] += 1
                continue
            seen_docs.add(doc_id)
            level = int(doc["teacher_level"])
            split = split_for(doc_id)
            used = 0
            for index, ((title, src), (_t, tgt)) in enumerate(zip(src_sections, tgt_sections)):
                pairs, why = section_pairs(src, tgt)
                if why:
                    report.section_rejects[why] += 1
                for part, (s, t) in enumerate(pairs):
                    why = _section_reject(s, t)
                    key = hashlib.sha256(s.encode("utf-8")).hexdigest()
                    if why is None and key in seen_sources:
                        why = "DUPLICATE_SOURCE"
                    if why:
                        report.section_rejects[why] += 1
                        continue
                    seen_sources.add(key)
                    handles[split].write(
                        json.dumps(
                            {
                                "messages": [
                                    {"role": "system", "content": system_prompt(level)},
                                    {"role": "user", "content": s},
                                    {"role": "assistant", "content": t},
                                ]
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    meta_out.write(
                        json.dumps(
                            {
                                "split": split,
                                "document_id": doc_id,
                                "section_index": index,
                                "part": part,
                                "section_title": title,
                                "level": level,
                                "writer": doc.get("source_writer"),
                                "domain": doc.get("domain"),
                                "document_type": doc.get("document_type"),
                                "source_words": _wc(s),
                                "target_words": _wc(t),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    report.examples[split] += 1
                    report.by_level[str(level)] += 1
                    report.source_words.append(_wc(s))
                    used += 1
            if used:
                report.documents_used += 1
                report.by_writer[str(doc.get("source_writer") or "unknown")] += 1
    finally:
        for fh in handles.values():
            fh.close()
        meta_out.close()

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "inputs": [str(p) for p in paths],
        "teacher_model": TEACHER_MODEL,
        "format": "chat messages: system (level) / user (source section) / assistant (teacher section)",
        "filters": {
            "min_section_words": MIN_SECTION_WORDS,
            "max_section_words": MAX_SECTION_WORDS,
            "chunk_words": CHUNK_WORDS,
            "length_ratio": list(RATIO_RANGE),
            "max_jaccard": MAX_JACCARD,
        },
        **report.as_dict(),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
