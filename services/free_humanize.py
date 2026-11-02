"""Free humanizer allowance (checked on the server only).

Environment (all optional):
  FREE_HUMANIZE_GUEST_WORDS=500       words per free run without an account
  FREE_HUMANIZE_GUEST_DAILY=1         free runs per day without an account (per IP + session)
  FREE_HUMANIZE_GUEST_IP_DAILY=3      free guest runs per day from one IP, whatever the session
                                      (clearing cookies doesn't give more; leaves room for shared Wi-Fi)
  FREE_HUMANIZE_USER_WORDS=1500       words per free run for a signed-in user
  FREE_HUMANIZE_USER_DAILY=10         free runs per day for a signed-in user (per user id)
  FREE_HUMANIZE_ENGINE=student        engine for free runs: "student" (our model) or "default"
                                      (same routing as paid runs)
  FREE_HUMANIZE_GUEST_RATE_PER_MIN=10 humanizer requests per minute per IP for guests
  HUMANIZE_MAX_WORDS=5000             hard cap on words per request for every humanizer endpoint

Days are UTC calendar days. A free run is reserved before the engine starts and released
if the engine fails, so failed runs never count. The guest rate limiter is in-memory, so
each worker process keeps its own window.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from services.economy.db import connect

GUEST_SESSION_KEY = "free_humanize_sid"
_KEEP_DAYS = 7


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        return max(0, int(raw)) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class FreeHumanizeLimits:
    guest_words: int
    guest_daily: int
    guest_ip_daily: int
    user_words: int
    user_daily: int
    engine: str
    guest_rate_per_minute: int
    max_words: int


def limits() -> FreeHumanizeLimits:
    engine = (os.environ.get("FREE_HUMANIZE_ENGINE") or "student").strip().lower() or "student"
    return FreeHumanizeLimits(
        guest_words=_env_int("FREE_HUMANIZE_GUEST_WORDS", 500),
        guest_daily=_env_int("FREE_HUMANIZE_GUEST_DAILY", 1),
        guest_ip_daily=_env_int("FREE_HUMANIZE_GUEST_IP_DAILY", 3),
        user_words=_env_int("FREE_HUMANIZE_USER_WORDS", 1500),
        user_daily=_env_int("FREE_HUMANIZE_USER_DAILY", 10),
        engine=engine,
        guest_rate_per_minute=_env_int("FREE_HUMANIZE_GUEST_RATE_PER_MIN", 10),
        max_words=_env_int("HUMANIZE_MAX_WORDS", 5000),
    )


def count_words(text: str) -> int:
    return len(text.split())


def today(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


# --- subjects ---------------------------------------------------------------


def user_subject(user_id: int) -> str:
    return f"user:{int(user_id)}"


def guest_subject(ip: str | None, session_id: str, salt: str) -> str:
    raw = f"{salt}|{ip or '-'}|{session_id}".encode("utf-8")
    return "guest:" + hashlib.sha256(raw).hexdigest()


def guest_ip_subject(ip: str | None, salt: str) -> str | None:
    if not ip:
        return None
    return "guest-ip:" + hashlib.sha256(f"{salt}|{ip}".encode("utf-8")).hexdigest()


def guest_session_id(session) -> str:
    """Random per-browser id kept in the signed Flask session."""
    sid = session.get(GUEST_SESSION_KEY)
    if not isinstance(sid, str) or len(sid) < 16:
        sid = secrets.token_urlsafe(16)
        session[GUEST_SESSION_KEY] = sid
    return sid


# https://www.cloudflare.com/ips/
_CLOUDFLARE_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
        "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
        "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
        "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
        "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
        "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
    )
)


def _is_cloudflare(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _CLOUDFLARE_NETWORKS)


def client_ip(request) -> str | None:
    """Client IP behind nginx (X-Real-IP, else the hop nginx appended to X-Forwarded-For).

    When that peer is a Cloudflare edge, the visitor is in CF-Connecting-IP. The header is
    only trusted from Cloudflare addresses, since anyone reaching the server directly can
    send it.
    """
    peer = (request.headers.get("X-Real-IP") or "").strip()
    if not peer:
        hops = [h.strip() for h in (request.headers.get("X-Forwarded-For") or "").split(",") if h.strip()]
        peer = hops[-1] if hops else (request.remote_addr or "").strip()
    visitor = (request.headers.get("CF-Connecting-IP") or "").strip()
    if visitor and peer and _is_cloudflare(peer):
        return visitor[:64]
    return peer[:64] or None


# --- daily counter ----------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS free_humanize_usage (
    subject TEXT NOT NULL,
    day     TEXT NOT NULL,
    used    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (subject, day)
)
"""


def used_today(subject: str, *, day: str | None = None) -> int:
    with connect() as conn:
        conn.execute(_SCHEMA)
        row = conn.execute(
            "SELECT used FROM free_humanize_usage WHERE subject = ? AND day = ?",
            (subject, day or today()),
        ).fetchone()
    return int(row["used"]) if row else 0


def remaining_today(subject: str, daily_limit: int, *, day: str | None = None) -> int:
    return max(0, int(daily_limit) - used_today(subject, day=day))


def reserve(subject: str, daily_limit: int, *, day: str | None = None) -> bool:
    """Take one free run for ``subject`` today. False when the daily allowance is spent."""
    if daily_limit <= 0:
        return False
    key = day or today()
    with connect() as conn:
        conn.execute(_SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT used FROM free_humanize_usage WHERE subject = ? AND day = ?", (subject, key)
        ).fetchone()
        if row is not None and int(row["used"]) >= daily_limit:
            return False
        conn.execute(
            "INSERT INTO free_humanize_usage (subject, day, used) VALUES (?, ?, 1) "
            "ON CONFLICT(subject, day) DO UPDATE SET used = used + 1",
            (subject, key),
        )
        if row is None:
            cutoff = (datetime.strptime(key, "%Y-%m-%d") - timedelta(days=_KEEP_DAYS)).strftime("%Y-%m-%d")
            conn.execute("DELETE FROM free_humanize_usage WHERE day < ?", (cutoff,))
    return True


def release(subject: str, *, day: str | None = None) -> None:
    """Give back a run reserved with :func:`reserve` (the engine failed)."""
    with connect() as conn:
        conn.execute(_SCHEMA)
        conn.execute(
            "UPDATE free_humanize_usage SET used = used - 1 WHERE subject = ? AND day = ? AND used > 0",
            (subject, day or today()),
        )


# --- guest rate limit -------------------------------------------------------


class RateLimiter:
    """Sliding one-minute window per key."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, per_minute: int) -> bool:
        if per_minute <= 0:
            return True
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= 60.0:
                hits.popleft()
            if len(hits) >= per_minute:
                return False
            hits.append(now)
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= 60.0]:
                    del self._hits[k]
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


guest_rate_limiter = RateLimiter()
