"""Bearer tokens that let the Veil extension act as a logged-in DocMaxxing user.

Lifecycle:
- ``issue_token`` (POST /api/veil/connect, verified session + CSRF) creates a 256-bit random
  token, revokes every earlier token of the account in the same transaction and returns the raw
  value once. Only its SHA-256 is stored; a partial unique index keeps one live token per account.
- A token authenticates only while it is not revoked, not past ``expires_at``
  (``VEIL_TOKEN_TTL_DAYS``, default 30) and its account is not blocked. Routes that spend credits
  or call providers also require a verified email.
- Revocation is a database flag: sign-out from the extension, a new connect, a password change,
  blocking or losing email verification (triggers in ``economy/db.py``). It survives restarts and
  is never undone; account deletion removes the rows.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from services.economy.auth import get_user
from services.economy.db import VEIL_TOKEN_DEFAULT_TTL_DAYS, connect

_MIN_TOKEN_LEN = 20
_MAX_TOKEN_LEN = 256
_MAX_TTL_DAYS = 365


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_ttl_days() -> int:
    from services.rate_limit import env_limit

    return min(env_limit("VEIL_TOKEN_TTL_DAYS", VEIL_TOKEN_DEFAULT_TTL_DAYS), _MAX_TTL_DAYS)


def issue_token(user_id: int) -> str:
    """Create a token and revoke the user's previous ones. The raw token is returned once."""
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE extension_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0", (int(user_id),))
        conn.execute(
            "INSERT INTO extension_tokens (user_id, token_hash, expires_at) "
            "VALUES (?, ?, datetime('now', ?))",
            (int(user_id), _hash(token), f"+{token_ttl_days()} days"),
        )
    return token


def user_for_token(token: str) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if not _MIN_TOKEN_LEN <= len(raw) <= _MAX_TOKEN_LEN:
        return None
    digest = _hash(raw)
    with connect() as conn:
        row = conn.execute(
            "SELECT id, user_id, token_hash FROM extension_tokens "
            "WHERE token_hash = ? AND revoked = 0 "
            "AND expires_at IS NOT NULL AND expires_at > datetime('now')",
            (digest,),
        ).fetchone()
        if row is None or not hmac.compare_digest(str(row["token_hash"]), digest):
            return None
        conn.execute(
            "UPDATE extension_tokens SET last_used_at = datetime('now') WHERE id = ?",
            (int(row["id"]),),
        )
    user = get_user(int(row["user_id"]))
    if user is None or user.get("is_blocked"):
        return None
    return user


def revoke_token(token: str) -> None:
    raw = (token or "").strip()
    if not raw or len(raw) > _MAX_TOKEN_LEN:
        return
    with connect() as conn:
        conn.execute("UPDATE extension_tokens SET revoked = 1 WHERE token_hash = ?", (_hash(raw),))


def revoke_user_tokens(user_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE extension_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0", (int(user_id),))
