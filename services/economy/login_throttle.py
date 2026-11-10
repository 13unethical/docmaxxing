"""Failed password checks, limited per account and per client IP across every worker.

Before a password is checked, ``begin`` reserves one failure slot for the account key and one
for the IP key inside a ``BEGIN IMMEDIATE`` transaction of the economy SQLite DB, so concurrent
workers cannot run more checks than the limit allows. A wrong password keeps the reservation;
a correct one deletes the account's failures and its own IP slot. Nothing is ever locked for
longer than the window: a full window refuses new checks until its oldest failure ages out.

Defaults (environment overrides must be positive integers):
- ``LOGIN_MAX_FAILURES_PER_ACCOUNT`` = 5 per ``LOGIN_FAILURE_WINDOW_SECONDS`` = 900 (15 min)
- ``LOGIN_MAX_FAILURES_PER_IP`` = 30 per the same window (campus / dorm NAT share an IP)

Account keys are hashes of the normalised email, so unknown and existing emails are limited the
same way. The IP is ``client_ip`` (forwarding headers only from ``TRUSTED_PROXIES``), keyed as
the IPv4 address or the IPv6 /64, so rotating addresses inside one /64 shares a limit. A worker
that dies after reserving leaves a counted failure, which expires with the window.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass

from services.economy.db import connect
from services.rate_limit import env_limit, source_id

DEFAULT_MAX_FAILURES_PER_ACCOUNT = 5
DEFAULT_MAX_FAILURES_PER_IP = 30
DEFAULT_WINDOW_SECONDS = 900
_MAX_WINDOW_SECONDS = 86400


def _limits() -> tuple[int, int, int]:
    return (
        env_limit("LOGIN_MAX_FAILURES_PER_ACCOUNT", DEFAULT_MAX_FAILURES_PER_ACCOUNT),
        env_limit("LOGIN_MAX_FAILURES_PER_IP", DEFAULT_MAX_FAILURES_PER_IP),
        min(env_limit("LOGIN_FAILURE_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS), _MAX_WINDOW_SECONDS),
    )


def account_key(scope: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:40]
    return f"{scope}:acct:{digest}"


def ip_key(scope: str, ip: str | None) -> str:
    return f"{scope}:ip:{source_id(ip)}"


@dataclass
class Attempt:
    account_key: str
    account_row_id: int
    ip_row_id: int

    def succeeded(self) -> None:
        """The password was right: forget this account's failures and release the IP slot."""
        with connect() as conn:
            conn.execute("DELETE FROM auth_failures WHERE key = ?", (self.account_key,))
            conn.execute("DELETE FROM auth_failures WHERE id = ?", (self.ip_row_id,))

    def failed(self) -> None:
        """The password was wrong: the reserved slots stay counted."""

    def release(self) -> None:
        """No password was checked (input rejected first): drop only this attempt's slots."""
        with connect() as conn:
            conn.execute(
                "DELETE FROM auth_failures WHERE id IN (?, ?)", (self.account_row_id, self.ip_row_id)
            )


def begin(scope: str, identifier: str, ip: str | None) -> Attempt | int:
    """Reserve a password check, or return seconds until one is allowed (nothing recorded)."""
    max_account, max_ip, window = _limits()
    now = time.time()
    keys = ((account_key(scope, identifier), max_account), (ip_key(scope, ip), max_ip))
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM auth_failures WHERE ts < ?", (now - _MAX_WINDOW_SECONDS,))
        wait = 0
        for key, limit in keys:
            row = conn.execute(
                "SELECT COUNT(*) AS n, MIN(ts) AS oldest FROM auth_failures WHERE key = ? AND ts > ?",
                (key, now - window),
            ).fetchone()
            if int(row["n"] or 0) >= limit:
                oldest = float(row["oldest"] or now)
                wait = max(wait, max(1, math.ceil(oldest + window - now)))
        if wait:
            return wait
        account = conn.execute("INSERT INTO auth_failures (key, ts) VALUES (?, ?)", (keys[0][0], now))
        ip = conn.execute("INSERT INTO auth_failures (key, ts) VALUES (?, ?)", (keys[1][0], now))
        return Attempt(
            account_key=keys[0][0], account_row_id=int(account.lastrowid), ip_row_id=int(ip.lastrowid)
        )
