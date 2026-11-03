"""Keep the teacher rewrites our Turnitin-trained detector finds most human, per rewrite level."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterator

from humanizer_student.data import level_of, split_messages

WINDOW_WORDS = 110
MIN_TAIL_WORDS = 40


def word_windows(text: str, size: int = WINDOW_WORDS) -> Iterator[tuple[str, int]]:
    """(window text, word count); a short tail joins the previous window."""
    words = (text or "").split()
    starts = list(range(0, len(words), size))
    if len(starts) > 1 and len(words) - starts[-1] < MIN_TAIL_WORDS:
        starts.pop()
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(words)
        yield " ".join(words[start:end]), end - start


def target_text(row: dict[str, Any]) -> str:
    return split_messages(row)[1]


def select_rows(
    rows: list[dict[str, Any]], scores: list[float], *, drop_share: float
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Drop the ``drop_share`` most AI-looking targets within each level; order is kept."""
    if len(rows) != len(scores):
        raise ValueError("rows and scores differ in length")
    by_level: dict[Any, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        by_level[level_of(row)].append(i)
    keep: set[int] = set()
    stats: dict[str, Any] = {}
    for level, idx in sorted(by_level.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
        ranked = sorted(idx, key=lambda i: scores[i])
        n_keep = len(ranked) - int(len(ranked) * drop_share)
        kept = ranked[:n_keep]
        keep.update(kept)
        mean = sum(scores[i] for i in idx) / len(idx)
        stats[str(level)] = {
            "rows": len(idx),
            "kept": len(kept),
            "mean_p": round(mean, 4),
            "kept_mean_p": round(sum(scores[i] for i in kept) / max(1, len(kept)), 4),
            "cutoff_p": round(scores[kept[-1]], 4) if kept else None,
        }
    return [r for i, r in enumerate(rows) if i in keep], stats
