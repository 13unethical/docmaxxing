"""Cross-process locks for long-running project mutations (multi-gunicorn safe)."""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from services.assignment_project.paths import assignment_storage_root


def _lock_path(project_id: str, name: str, root: Path) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (project_id or ""))
    return root / safe / f".{name}.lock"


@contextmanager
def project_file_lock(
    project_id: str,
    *,
    name: str = "writer",
    root: Path | str | None = None,
) -> Iterator[None]:
    """Exclusive flock so only one worker mutates a project's writer session at a time."""
    base = Path(root).resolve() if root is not None else assignment_storage_root()
    path = _lock_path(project_id, name, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
