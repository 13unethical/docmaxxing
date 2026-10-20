"""Bearer tokens that let the Veil extension act as a logged-in DocMaxxing user."""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from services.economy.auth import get_user
from services.economy.db import connect


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(user_id: int) -> str:
    """Create a token and revoke the user's previous ones. The raw token is returned once."""
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute("UPDATE extension_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0", (int(user_id),))
        conn.execute(
            "INSERT INTO extension_tokens (user_id, token_hash) VALUES (?, ?)",
            (int(user_id), _hash(token)),
        )
    return token


def user_for_token(token: str) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if len(raw) < 20:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT user_id FROM extension_tokens WHERE token_hash = ? AND revoked = 0",
            (_hash(raw),),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE extension_tokens SET last_used_at = datetime('now') WHERE token_hash = ?",
            (_hash(raw),),
        )
    return get_user(int(row["user_id"]))


def revoke_token(token: str) -> None:
    raw = (token or "").strip()
    if not raw:
        return
    with connect() as conn:
        conn.execute("UPDATE extension_tokens SET revoked = 1 WHERE token_hash = ?", (_hash(raw),))
