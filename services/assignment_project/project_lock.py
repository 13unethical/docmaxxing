"""Cross-process locks for long-running project mutations (multi-gunicorn safe).

Lock order, outermost first: payment gate -> writer/humanizer lock -> billing lock ->
document lock -> writer archive -> bundle lock -> SQLite transaction. Taking a lock that ranks at or above
one the thread already holds raises ``LockOrderError`` (re-entering the same lock is
fine), so an inverted nesting fails at once instead of deadlocking two workers. Neither the
billing lock, the bundle lock nor a SQLite transaction is ever held across an AI call.
flock locks belong to the open file, so a worker that dies releases them with its files.
"""

from __future__ import annotations

import fcntl
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from services.assignment_project.paths import assignment_storage_root

# Serializes payment confirmation, refunds, ledger reconciliation and every change to the
# billable inputs (requirements, files, quote) of one project.
BILLING_LOCK = "billing"
# Held only around one read-modify-write of bundle.json; nothing else is taken inside it.
BUNDLE_LOCK = "bundle"
# Held shared for a whole paid operation (payment check -> AI call -> output persisted ->
# evidence recorded) and exclusively by a refund, so the two never overlap.
PAYMENT_GATE_LOCK = "payment-gate"


WRITER_ARCHIVE_LOCK = "writer-archive"
# Held (briefly, never across AI) while generated text is checked against and written over
# the stored document, so a result computed from an older document cannot replace a newer one.
DOCUMENT_LOCK = "document"
_LOCK_RANKS = {
    PAYMENT_GATE_LOCK: 0,
    "writer": 10,
    "humanizer": 10,
    BILLING_LOCK: 20,
    DOCUMENT_LOCK: 22,
    WRITER_ARCHIVE_LOCK: 25,
    BUNDLE_LOCK: 30,
}


class LockBusyError(RuntimeError):
    """The exclusive payment gate could not be taken in time (a paid operation is running)."""


class LockOrderError(RuntimeError):
    """A lock was requested out of the documented order (it could deadlock another worker)."""


def _lock_path(project_id: str, name: str, root: Path) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (project_id or ""))
    return root / safe / f".{name}.lock"


def _rank(name: str) -> int:
    return _LOCK_RANKS.get(name, 15)


@contextmanager
def _ordered(key: str, name: str) -> Iterator[None]:
    """Record ``name`` as held by this thread; refuse it if an equal or inner lock is held."""
    stack: list[tuple[str, int]] = getattr(_order_held, "stack", None) or []
    _order_held.stack = stack
    rank = _rank(name)
    for held_key, held_rank in stack:
        if held_rank >= rank:
            raise LockOrderError(f"lock {name!r} requested while holding {held_key!r}")
    stack.append((key, rank))
    try:
        yield
    finally:
        stack.remove((key, rank))


@contextmanager
def project_file_lock(
    project_id: str,
    *,
    name: str = "writer",
    root: Path | str | None = None,
) -> Iterator[None]:
    """Exclusive flock so only one worker mutates a project's ``name`` state at a time.

    Re-entering the same lock from the thread that holds it is a no-op (a second flock on a
    new descriptor would deadlock against the first).
    """
    base = Path(root).resolve() if root is not None else assignment_storage_root()
    path = _lock_path(project_id, name, base)
    held: set[str] = getattr(_file_locks_held, "paths", None) or set()
    _file_locks_held.paths = held
    key = str(path)
    if key in held:
        yield
        return
    with _ordered(key, name):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            held.add(key)
            try:
                yield
            finally:
                held.discard(key)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


_file_locks_held = threading.local()
_gate_held = threading.local()
_order_held = threading.local()


def _forget_held_locks() -> None:
    # A forked child does not own its parent's locks: its own requests must really wait.
    _file_locks_held.paths = set()
    _gate_held.modes = {}
    _order_held.stack = []


os.register_at_fork(after_in_child=_forget_held_locks)


@contextmanager
def payment_gate(
    project_id: str,
    *,
    root: Path | str | None = None,
    exclusive: bool = False,
    wait_seconds: float = 0.0,
) -> Iterator[None]:
    """flock on the project's payment gate.

    Shared mode blocks until no refund holds the gate. Exclusive mode polls for at most
    ``wait_seconds`` and then raises LockBusyError instead of queueing behind a long AI
    call. Re-entering from the same thread is a no-op, except that a thread already inside
    a paid operation can never take the gate exclusively.
    """
    base = Path(root).resolve() if root is not None else assignment_storage_root()
    path = _lock_path(project_id, PAYMENT_GATE_LOCK, base)
    held: dict[str, str] = getattr(_gate_held, "modes", None) or {}
    _gate_held.modes = held
    key = str(path)
    mode = held.get(key)
    if mode is not None:
        if exclusive and mode != "exclusive":
            raise LockBusyError(project_id)
        yield
        return
    with _ordered(key, PAYMENT_GATE_LOCK):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as handle:
            if exclusive:
                deadline = time.monotonic() + max(0.0, wait_seconds)
                while True:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise LockBusyError(project_id) from None
                        time.sleep(0.02)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            held[key] = "exclusive" if exclusive else "shared"
            try:
                yield
            finally:
                held.pop(key, None)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
