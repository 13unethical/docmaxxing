"""Pick the freshest multi-worker session/draft snapshot."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def artifact_rank(
    *,
    status: str | None,
    completed_count: int,
    progress: int,
    updated_at: datetime | None,
) -> tuple[int, int, int, float]:
    """Higher tuple wins when choosing among memory / disk / client snapshots."""
    status_l = (status or "").lower()
    status_rank = 3 if status_l == "merged" else 2 if status_l == "completed" else 1 if status_l else 0
    ts = updated_at.timestamp() if isinstance(updated_at, datetime) else 0.0
    return (status_rank, int(completed_count or 0), int(progress or 0), ts)


def pick_freshest(candidates: list[Any]) -> Any | None:
    best = None
    best_rank: tuple[int, int, int, float] | None = None
    for item in candidates:
        if item is None:
            continue
        status = getattr(item, "status", None)
        status_val = status.value if hasattr(status, "value") else str(status or "")
        completed = (
            getattr(item, "completed_section_ids", None)
            or getattr(item, "completed_paragraph_ids", None)
            or []
        )
        rank = artifact_rank(
            status=status_val,
            completed_count=len(completed),
            progress=int(getattr(item, "progress", 0) or 0),
            updated_at=getattr(item, "updated_at", None),
        )
        if best is None or best_rank is None or rank > best_rank:
            best = item
            best_rank = rank
    return best
