"""Offline comparison of student rewrites with the StealthWriter teacher.

Each prediction is scored against its source (did it keep paragraphs, citations,
numbers, length; how much did it change) and against the teacher text (chrF).
The teacher is scored the same way, so the report shows how close the student's
profile is to StealthWriter's, per rewrite level. Detector scores are separate.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Iterable

_WORD = re.compile(r"[a-z0-9']+")
_CITATION = re.compile(r"\([A-Z][^()]{0,80}?,\s*(?:\d{4}[a-z]?|n\.d\.)\)")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*%?")
_HEADING = re.compile(r"(?m)^\s*#")
UNCHANGED_JACCARD = 0.9


def words(text: str) -> int:
    return len(text.split())


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def jaccard(a: str, b: str) -> float:
    left, right = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    return len(left & right) / len(left | right) if left | right else 1.0


def _ngrams(text: str, n: int) -> Counter[str]:
    s = re.sub(r"\s+", " ", text).strip()
    return Counter(s[i : i + n] for i in range(len(s) - n + 1))


def chrf(hypothesis: str, reference: str, *, max_n: int = 6, beta: float = 2.0) -> float:
    """Character n-gram F-score (0..100), the usual chrF with averaged n-gram orders."""
    precisions, recalls = [], []
    for n in range(1, max_n + 1):
        hyp, ref = _ngrams(hypothesis, n), _ngrams(reference, n)
        if not hyp or not ref:
            continue
        overlap = sum((hyp & ref).values())
        precisions.append(overlap / sum(hyp.values()))
        recalls.append(overlap / sum(ref.values()))
    if not precisions:
        return 0.0
    p, r = mean(precisions), mean(recalls)
    if p == 0 and r == 0:
        return 0.0
    b2 = beta * beta
    return 100 * (1 + b2) * p * r / (b2 * p + r)


def _loose(text: str) -> str:
    """Citation text compared modulo ``&``/``and`` and accents, which the teacher rewrites."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    plain = re.sub(r"([aouAOU])e", r"\1", plain)
    return re.sub(r"\s+", " ", plain.replace("&", "and"))


def _kept(markers: list[str], text: str) -> float | None:
    if not markers:
        return None
    loose = _loose(text)
    return sum(1 for m in markers if m in text or _loose(m) in loose) / len(markers)


def score_rewrite(source: str, output: str, teacher: str | None = None) -> dict[str, Any]:
    src_words = words(source)
    overlap = jaccard(source, output)
    row: dict[str, Any] = {
        "empty": not output.strip(),
        "length_ratio": words(output) / src_words if src_words else 0.0,
        "paragraphs_match": len(paragraphs(output)) == len(paragraphs(source)),
        "change_rate": 1 - overlap,
        "unchanged": overlap > UNCHANGED_JACCARD,
        "heading_leak": bool(_HEADING.search(output)),
        "citations_kept": _kept(_CITATION.findall(source), output),
        "numbers_kept": _kept(_NUMBER.findall(source), output),
    }
    if teacher is not None:
        row["chrf_vs_teacher"] = chrf(output, teacher)
    return row


_RATE_KEYS = ("empty", "paragraphs_match", "unchanged", "heading_leak")
_MEAN_KEYS = ("length_ratio", "change_rate", "citations_kept", "numbers_kept", "chrf_vs_teacher")


def aggregate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    out: dict[str, Any] = {"n": len(rows)}
    if not rows:
        return out
    for key in _RATE_KEYS:
        out[key] = round(sum(1 for r in rows if r.get(key)) / len(rows), 4)
    for key in _MEAN_KEYS:
        values = [r[key] for r in rows if r.get(key) is not None]
        if values:
            out[key] = round(mean(values), 4)
    return out


def compare(examples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Student vs teacher profile, overall and per level.

    Each example needs ``source``, ``teacher``, ``prediction`` and optional ``level``.
    """
    student: dict[str, list[dict[str, Any]]] = defaultdict(list)
    teacher: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ex in examples:
        level = str(ex.get("level") or "?")
        s = score_rewrite(ex["source"], ex["prediction"], ex["teacher"])
        t = score_rewrite(ex["source"], ex["teacher"])
        for key in ("all", f"level_{level}"):
            student[key].append(s)
            teacher[key].append(t)
    return {
        key: {"student": aggregate(student[key]), "teacher": aggregate(teacher[key])}
        for key in sorted(student, key=lambda k: (k != "all", k))
    }
