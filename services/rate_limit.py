"""Per-account sliding-window rate limits stored in the economy SQLite DB.

Every gunicorn worker (and every restart) sees the same counters: a request is checked and
recorded inside one ``BEGIN IMMEDIATE`` transaction, so concurrent workers cannot both take
the last slot. Events older than a day are deleted by the next request.
"""

from __future__ import annotations

import ipaddress
import math
import os
import time

from services.economy.db import connect

_MAX_WINDOW_SECONDS = 86400


def env_limit(name: str, default: int) -> int:
    """Positive integer from the environment; anything else keeps the default (never unlimited)."""
    raw = (os.environ.get(name) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def source_id(ip: str | None) -> str:
    """Limit identity of a client address: the IPv4 address, or the /64 of an IPv6 address.

    An IPv6 subscriber gets a whole /64, so a new address inside it must not reset a limit.
    """
    try:
        addr = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return "unknown"
    if addr.version == 6:
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


def hit(key: str, limits: list[tuple[int, int]]) -> int | None:
    """Record one request for ``key`` unless a ``(max_requests, window_seconds)`` limit is full.

    Returns ``None`` when the request is allowed (and counted), otherwise the number of
    seconds until a slot frees up (nothing is recorded).
    """
    return hit_all([(key, limits)])


def hit_all(entries: list[tuple[str, list[tuple[int, int]]]]) -> int | None:
    """:func:`hit` for several keys at once: the request is recorded under every key, or, when
    any key's limit is full, under none (seconds until all of them have room)."""
    now = time.time()
    wait = 0
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM rate_limit_events WHERE ts < ?", (now - _MAX_WINDOW_SECONDS,))
        for key, limits in entries:
            for max_requests, window in limits:
                window = min(int(window), _MAX_WINDOW_SECONDS)
                row = conn.execute(
                    "SELECT COUNT(*) AS n, MIN(ts) AS oldest FROM rate_limit_events WHERE key = ? AND ts > ?",
                    (key, now - window),
                ).fetchone()
                if int(row["n"] or 0) >= int(max_requests):
                    oldest = float(row["oldest"] or now)
                    wait = max(wait, max(1, math.ceil(oldest + window - now)))
        if wait:
            return wait
        for key, _limits in entries:
            conn.execute("INSERT INTO rate_limit_events (key, ts) VALUES (?, ?)", (key, now))
    return None
