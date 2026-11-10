"""Server-side allowance for free AI calls (Gemini/Claude before any payment).

A free tool that can reach a paid LLM opens a :func:`scope` with a :class:`Grant` for the
caller. The first provider call inside the scope takes one unit from the caller's daily pool
(a later call in the same request reuses it), and the provider clients refuse to send
anything when the grant is spent. Free AI helpers that run inside a request without a scope
skip the AI path, so a new route cannot reach the provider by forgetting the gate.

Pools and environment (all optional, defaults in brackets):

  brief        brief -> formatting requirements: /api/extract-requirements-v2,
               /api/extract-requirements, /parse-requirements (the Formatter V2 settings)
                 SMARTFORM_RATE_PER_MIN [5]   SMARTFORM_USER_DAILY [20]
                 SMARTFORM_GUEST_DAILY [3]    SMARTFORM_GUEST_IP_DAILY [10]
                 SMARTFORM_BRIEF_MAX_CHARS [30000]
  document     AI structure recovery and check explanations: /api/format (auto headings),
               /api/structure-recovery, /api/check-document
                 FREE_DOC_AI_RATE_PER_MIN [5]   FREE_DOC_AI_USER_DAILY [10]
                 FREE_DOC_AI_GUEST_DAILY [3]    FREE_DOC_AI_GUEST_IP_DAILY [3]
                 FREE_DOC_AI_MAX_CHARS [48000]
  format_chat  Formatter V2 chat edits, verified accounts only
                 FORMAT_CHAT_RATE_PER_MIN [5]   FORMAT_CHAT_USER_DAILY [20]
                 FORMAT_CHAT_MAX_CHARS [30000]
  analyze      assignment requirement analysis before payment, verified accounts only
                 ASSIGNMENT_ANALYZE_RATE_PER_MIN [5]   ASSIGNMENT_ANALYZE_USER_DAILY [10]
                 ASSIGNMENT_ANALYZE_MAX_CHARS [200000]

Signed-in users with an unverified email are counted as guests (session + IP), since such
accounts cost nothing to create. Daily counters share the ``free_humanize_usage`` table
(UTC days); the one-minute window and the reservation ledger live in SQLite too, so every
worker process sees the same numbers. A reservation is returned only when no provider call
was made under it; a reservation abandoned by a crashed worker stays spent until the day
ends.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

logger = logging.getLogger(__name__)

_KEEP_DAYS = 7
_WINDOW_S = 60.0

PENDING = "pending"
RESERVED = "reserved"
DENIED = "denied"
RELEASED = "released"
CONSUMED = "consumed"

RATE_LIMITED = "RATE_LIMITED"
FREE_LIMIT_REACHED = "FREE_LIMIT_REACHED"
REGISTER_REQUIRED = "REGISTER_REQUIRED"
EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
QUOTA_UNAVAILABLE = "QUOTA_UNAVAILABLE"
INPUT_TOO_LONG = "INPUT_TOO_LONG"
NO_QUOTA_SCOPE = "NO_QUOTA_SCOPE"


@dataclass(frozen=True)
class Pool:
    name: str
    prefix: str
    rate_env: str
    rate_default: int
    user_env: str
    user_default: int
    guest_env: str | None
    guest_default: int
    guest_ip_env: str | None
    guest_ip_default: int
    max_chars_env: str
    max_chars_default: int

    @property
    def guests_allowed(self) -> bool:
        return self.guest_env is not None


POOLS: dict[str, Pool] = {
    "brief": Pool(
        "brief", "brief:",
        "SMARTFORM_RATE_PER_MIN", 5, "SMARTFORM_USER_DAILY", 20,
        "SMARTFORM_GUEST_DAILY", 3, "SMARTFORM_GUEST_IP_DAILY", 10,
        "SMARTFORM_BRIEF_MAX_CHARS", 30_000,
    ),
    "document": Pool(
        "document", "docai:",
        "FREE_DOC_AI_RATE_PER_MIN", 5, "FREE_DOC_AI_USER_DAILY", 10,
        "FREE_DOC_AI_GUEST_DAILY", 3, "FREE_DOC_AI_GUEST_IP_DAILY", 3,
        "FREE_DOC_AI_MAX_CHARS", 48_000,
    ),
    "format_chat": Pool(
        "format_chat", "fmtchat:",
        "FORMAT_CHAT_RATE_PER_MIN", 5, "FORMAT_CHAT_USER_DAILY", 20,
        None, 0, None, 0,
        "FORMAT_CHAT_MAX_CHARS", 30_000,
    ),
    "analyze": Pool(
        "analyze", "analyze:",
        "ASSIGNMENT_ANALYZE_RATE_PER_MIN", 5, "ASSIGNMENT_ANALYZE_USER_DAILY", 10,
        None, 0, None, 0,
        "ASSIGNMENT_ANALYZE_MAX_CHARS", 200_000,
    ),
}


def _env_int(name: str | None, default: int) -> int:
    raw = (os.environ.get(name) or "").strip() if name else ""
    try:
        return max(0, int(raw)) if raw else default
    except ValueError:
        return default


def pool(name: str) -> Pool:
    return POOLS[name]


def max_chars(name: str) -> int:
    p = POOLS[name]
    return _env_int(p.max_chars_env, p.max_chars_default)


class QuotaRefused(Exception):
    """A free AI step was refused before any provider call (quota, rate, or input size)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --- storage -----------------------------------------------------------------

_USAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS free_humanize_usage (
    subject TEXT NOT NULL,
    day     TEXT NOT NULL,
    used    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (subject, day)
)
"""

_RESERVATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS free_ai_reservations (
    id         TEXT PRIMARY KEY,
    pool       TEXT NOT NULL,
    rate_key   TEXT NOT NULL,
    day        TEXT NOT NULL,
    subjects   TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_ts REAL NOT NULL
)
"""

_RESERVATION_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_free_ai_reservations_rate "
    "ON free_ai_reservations(rate_key, created_ts)"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(_USAGE_SCHEMA)
    conn.execute(_RESERVATION_SCHEMA)
    conn.execute(_RESERVATION_INDEX)


def _reserve(grant: "Grant") -> str | None:
    """Take the minute slot and every daily subject in one transaction. Returns a refusal or None."""
    from services.economy.db import connect

    now = _now()
    day = now.strftime("%Y-%m-%d")
    ts = time.time()
    rate_limit = _env_int(grant.pool.rate_env, grant.pool.rate_default)
    with connect() as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        if rate_limit > 0:
            recent = conn.execute(
                "SELECT COUNT(*) AS n FROM free_ai_reservations WHERE rate_key = ? AND created_ts > ?",
                (grant.rate_key, ts - _WINDOW_S),
            ).fetchone()
            if int(recent["n"]) >= rate_limit:
                return RATE_LIMITED
        for subject, limit in grant.subjects:
            if limit <= 0:
                return FREE_LIMIT_REACHED
            row = conn.execute(
                "SELECT used FROM free_humanize_usage WHERE subject = ? AND day = ?", (subject, day)
            ).fetchone()
            if row is not None and int(row["used"]) >= limit:
                return FREE_LIMIT_REACHED
        for subject, _limit in grant.subjects:
            conn.execute(
                "INSERT INTO free_humanize_usage (subject, day, used) VALUES (?, ?, 1) "
                "ON CONFLICT(subject, day) DO UPDATE SET used = used + 1",
                (subject, day),
            )
        conn.execute(
            "INSERT INTO free_ai_reservations (id, pool, rate_key, day, subjects, status, created_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (grant.id, grant.pool.name, grant.rate_key, day,
             json.dumps([s for s, _ in grant.subjects]), RESERVED, ts),
        )
        cutoff = (now - timedelta(days=_KEEP_DAYS)).strftime("%Y-%m-%d")
        conn.execute("DELETE FROM free_ai_reservations WHERE day < ?", (cutoff,))
    return None


def _set_status(reservation_id: str, status: str) -> bool:
    """Move a reserved reservation to ``status``; a released one gives its units back. Idempotent."""
    from services.economy.db import connect

    with connect() as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT day, subjects FROM free_ai_reservations WHERE id = ? AND status = ?",
            (reservation_id, RESERVED),
        ).fetchone()
        if row is None:
            return False
        conn.execute("UPDATE free_ai_reservations SET status = ? WHERE id = ?", (status, reservation_id))
        if status == RELEASED:
            for subject in json.loads(row["subjects"] or "[]"):
                conn.execute(
                    "UPDATE free_humanize_usage SET used = used - 1 WHERE subject = ? AND day = ? AND used > 0",
                    (subject, row["day"]),
                )
    return True


def reservation_status(reservation_id: str) -> str | None:
    from services.economy.db import connect

    with connect() as conn:
        _ensure_schema(conn)
        row = conn.execute("SELECT status FROM free_ai_reservations WHERE id = ?", (reservation_id,)).fetchone()
    return str(row["status"]) if row else None


# --- grants ------------------------------------------------------------------


class Grant:
    """One request's claim on a pool. The reservation id is generated here and never leaves the server."""

    def __init__(
        self,
        pool_name: str,
        *,
        rate_key: str,
        subjects: list[tuple[str, int]],
        guest: bool,
        refusal: str | None = None,
    ) -> None:
        self.pool = POOLS[pool_name]
        self.rate_key = rate_key
        self.subjects = list(subjects)
        self.guest = guest
        self.id = secrets.token_hex(16)
        self.state = DENIED if refusal else PENDING
        self.reason: str | None = refusal
        self.provider_calls = 0
        self._lock = threading.Lock()

    @property
    def denied(self) -> bool:
        return self.state == DENIED

    def acquire(self) -> bool:
        with self._lock:
            if self.state in (RESERVED, CONSUMED):
                return True
            if self.state != PENDING:
                return False
            try:
                refusal = _reserve(self)
            except (sqlite3.Error, OSError):
                logger.exception("free AI quota store unavailable pool=%s", self.pool.name)
                refusal = QUOTA_UNAVAILABLE
            if refusal is None:
                self.state = RESERVED
                return True
            self.state = DENIED
            self.reason = refusal
            return False

    def note_provider_call(self) -> None:
        with self._lock:
            self.provider_calls += 1

    def skip(self, reason: str) -> None:
        """Record why the AI path was not taken (shown to the caller) without touching counters."""
        with self._lock:
            if self.state == PENDING:
                self.reason = reason

    def release_if_unused(self) -> bool:
        """Give the unit back when no provider call was made under it."""
        with self._lock:
            if self.state != RESERVED or self.provider_calls:
                return False
            try:
                released = _set_status(self.id, RELEASED)
            except (sqlite3.Error, OSError):
                logger.exception("free AI quota release failed pool=%s", self.pool.name)
                return False
            self.state = RELEASED
            return released

    def finish(self) -> None:
        with self._lock:
            if self.state != RESERVED:
                return
            try:
                _set_status(self.id, CONSUMED)
            except (sqlite3.Error, OSError):
                logger.exception("free AI quota finish failed pool=%s", self.pool.name)
            self.state = CONSUMED

    def notice(self) -> dict | None:
        """What the caller should know when the AI path was skipped."""
        if self.state in (RESERVED, CONSUMED) or not self.reason:
            return None
        return {"status": "skipped", "reason": self.reason, "register_required": self.guest}


def grant_for(
    pool_name: str,
    *,
    user_id: int | None,
    email_verified: bool,
    guest_subject: str | None,
    guest_ip_subject: str | None,
) -> Grant:
    """Build the caller's grant. Subjects come from the server session and trusted client IP only."""
    p = POOLS[pool_name]
    if user_id is not None and email_verified:
        return Grant(
            pool_name,
            rate_key=f"{p.name}:user:{int(user_id)}",
            subjects=[(f"{p.prefix}user:{int(user_id)}", _env_int(p.user_env, p.user_default))],
            guest=False,
        )
    if not p.guests_allowed:
        refusal = EMAIL_NOT_VERIFIED if user_id is not None else REGISTER_REQUIRED
        return Grant(pool_name, rate_key=f"{p.name}:denied", subjects=[], guest=user_id is None, refusal=refusal)
    subjects: list[tuple[str, int]] = []
    if guest_subject:
        subjects.append((p.prefix + guest_subject, _env_int(p.guest_env, p.guest_default)))
    if guest_ip_subject:
        subjects.append((p.prefix + guest_ip_subject, _env_int(p.guest_ip_env, p.guest_ip_default)))
    if not subjects:
        return Grant(pool_name, rate_key=f"{p.name}:denied", subjects=[], guest=True, refusal=REGISTER_REQUIRED)
    rate_key = f"{p.name}:{guest_ip_subject or guest_subject}"
    return Grant(pool_name, rate_key=rate_key, subjects=subjects, guest=True)


# --- request scope -----------------------------------------------------------

_ACTIVE: contextvars.ContextVar[Grant | None] = contextvars.ContextVar("free_ai_grant", default=None)


def active() -> Grant | None:
    return _ACTIVE.get()


@contextmanager
def scope(grant: Grant) -> Iterator[Grant]:
    token = _ACTIVE.set(grant)
    try:
        yield grant
    except BaseException:
        if not grant.release_if_unused():
            grant.finish()
        raise
    else:
        grant.finish()
    finally:
        _ACTIVE.reset(token)


def _in_request() -> bool:
    try:
        from flask import has_request_context
    except ImportError:  # pragma: no cover
        return False
    return has_request_context()


def allow(pool_name: str) -> bool:
    """Called by a free AI helper right before its first provider call."""
    grant = _ACTIVE.get()
    if grant is None:
        if _in_request():
            logger.warning("free AI helper ran without a quota scope pool=%s; AI skipped", pool_name)
            return False
        return True
    if grant.pool.name != pool_name:
        logger.warning("free AI pool mismatch scope=%s helper=%s; AI skipped", grant.pool.name, pool_name)
        return False
    return grant.acquire()


def skip(reason: str) -> None:
    grant = _ACTIVE.get()
    if grant is not None:
        grant.skip(reason)


def before_provider_call(provider: str) -> bool:
    """Provider-client hook: inside a free scope every outbound call needs the grant."""
    grant = _ACTIVE.get()
    if grant is None:
        return True
    if not grant.acquire():
        logger.warning("free AI provider call refused provider=%s pool=%s reason=%s",
                       provider, grant.pool.name, grant.reason)
        return False
    grant.note_provider_call()
    return True
