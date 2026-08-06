"""Two-way support helpdesk backed by SQLite + Telegram Reply.

User messages are stored and forwarded to the admin Telegram chat with a
strict ``User ID: {id}`` footer. Replies are routed back via:
1) ``reply_to_message.message_id`` map (preferred), then
2) parsing ``User ID:`` from the replied-to text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from services.economy.db import connect

Sender = Literal["user", "admin"]

USER_ID_FOOTER_RE = re.compile(r"User ID:\s*(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
VALID_SENDERS = frozenset({"user", "admin"})


@dataclass
class SupportMessage:
    """Schema mirror for ``support_messages``."""

    id: int | None
    user_id: int
    sender: str
    message: str
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "sender": self.sender,
            "message": self.message,
            "created_at": self.created_at,
        }


def ensure_support_messages_schema(conn: Any) -> None:
    """Create ``support_messages`` (+ telegram map) if missing."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS support_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            sender      TEXT NOT NULL CHECK (sender IN ('user', 'admin')),
            message     TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_support_messages_user_created "
        "ON support_messages(user_id, created_at ASC)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS support_telegram_map (
            telegram_message_id INTEGER PRIMARY KEY,
            user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            support_message_id  INTEGER REFERENCES support_messages(id) ON DELETE SET NULL,
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_support_telegram_map_user "
        "ON support_telegram_map(user_id)"
    )


def save_support_message(*, user_id: int, sender: str, message: str) -> SupportMessage:
    """Persist a chat row and return it with id + created_at."""
    uid = int(user_id)
    who = (sender or "").strip().lower()
    text = (message or "").strip()
    if who not in VALID_SENDERS:
        raise ValueError("sender must be 'user' or 'admin'")
    if not text:
        raise ValueError("message is required")
    if uid < 1:
        raise ValueError("user_id must be a positive integer")

    with connect() as conn:
        ensure_support_messages_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO support_messages (user_id, sender, message)
            VALUES (?, ?, ?)
            """,
            (uid, who, text),
        )
        row_id = int(cur.lastrowid)
        row = conn.execute(
            "SELECT id, user_id, sender, message, created_at "
            "FROM support_messages WHERE id = ?",
            (row_id,),
        ).fetchone()
    return SupportMessage(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        sender=str(row["sender"]),
        message=str(row["message"]),
        created_at=str(row["created_at"]) if row["created_at"] else None,
    )


def bind_telegram_message(
    *,
    telegram_message_id: int,
    user_id: int,
    support_message_id: int | None = None,
) -> None:
    """Remember which site user owns an outbound Telegram message_id."""
    tg_id = int(telegram_message_id)
    uid = int(user_id)
    if tg_id < 1 or uid < 1:
        return
    with connect() as conn:
        ensure_support_messages_schema(conn)
        conn.execute(
            """
            INSERT INTO support_telegram_map
                (telegram_message_id, user_id, support_message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_message_id) DO UPDATE SET
                user_id = excluded.user_id,
                support_message_id = COALESCE(
                    excluded.support_message_id,
                    support_telegram_map.support_message_id
                )
            """,
            (tg_id, uid, int(support_message_id) if support_message_id else None),
        )


def lookup_user_id_by_telegram_message(telegram_message_id: int | None) -> int | None:
    if telegram_message_id is None:
        return None
    try:
        tg_id = int(telegram_message_id)
    except (TypeError, ValueError):
        return None
    if tg_id < 1:
        return None
    with connect() as conn:
        ensure_support_messages_schema(conn)
        row = conn.execute(
            "SELECT user_id FROM support_telegram_map WHERE telegram_message_id = ?",
            (tg_id,),
        ).fetchone()
    if not row:
        return None
    return int(row["user_id"])


def list_support_messages(
    user_id: int,
    *,
    after_id: int | None = None,
    limit: int = 200,
) -> list[SupportMessage]:
    """Return chronological chat history for one user."""
    uid = int(user_id)
    lim = max(1, min(int(limit or 200), 500))
    params: list[Any] = [uid]
    where = "user_id = ?"
    if after_id is not None:
        where += " AND id > ?"
        params.append(int(after_id))
    params.append(lim)
    with connect() as conn:
        ensure_support_messages_schema(conn)
        rows = conn.execute(
            f"""
            SELECT id, user_id, sender, message, created_at
            FROM support_messages
            WHERE {where}
            ORDER BY id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [
        SupportMessage(
            id=int(r["id"]),
            user_id=int(r["user_id"]),
            sender=str(r["sender"]),
            message=str(r["message"]),
            created_at=str(r["created_at"]) if r["created_at"] else None,
        )
        for r in rows
    ]


def format_telegram_outbound(
    *,
    message: str,
    user_id: int,
    email: str | None = None,
    name: str | None = None,
) -> str:
    """Build Telegram text with a strict ``User ID:`` footer for Reply routing."""
    body = (message or "").strip()
    header_bits: list[str] = []
    display = (name or "").strip()
    mail = (email or "").strip()
    if display or mail:
        who = display or mail
        if display and mail and display != mail:
            who = f"{display} <{mail}>"
        header_bits.append(f"Support from {who}")
    parts = []
    if header_bits:
        parts.append(header_bits[0])
        parts.append("")
    parts.append(body)
    parts.append("")
    parts.append(f"User ID: {int(user_id)}")
    return "\n".join(parts).strip()


def extract_user_id_from_telegram_text(text: str | None) -> int | None:
    """Parse ``User ID: {id}`` from a Telegram message the admin replied to."""
    if not text:
        return None
    raw = str(text).replace("\xa0", " ").strip()
    match = USER_ID_FOOTER_RE.search(raw)
    if not match:
        loose = re.search(r"User\s*ID\s*[:#]\s*(\d+)", raw, re.IGNORECASE)
        if not loose:
            return None
        match = loose
    try:
        uid = int(match.group(1))
    except (TypeError, ValueError):
        return None
    return uid if uid > 0 else None


def normalize_chat_id(value: Any) -> str:
    return str(value or "").strip().strip('"').strip("'")


def parse_admin_reply_from_update(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Extract admin reply text + target user_id from a Telegram Update.

    Returns ``{"user_id": int, "message": str, "via": str}`` or ``None``.
    """
    if not isinstance(payload, dict):
        return None
    message = payload.get("message") or payload.get("edited_message")
    if not isinstance(message, dict):
        return None
    reply_to = message.get("reply_to_message")
    if not isinstance(reply_to, dict):
        return None

    admin_text = (message.get("text") or message.get("caption") or "").strip()
    if not admin_text:
        return None

    via = ""
    user_id = lookup_user_id_by_telegram_message(reply_to.get("message_id"))
    if user_id is not None:
        via = "telegram_map"
    else:
        reply_text = reply_to.get("text") or reply_to.get("caption") or ""
        user_id = extract_user_id_from_telegram_text(str(reply_text))
        if user_id is not None:
            via = "user_id_footer"

    if user_id is None:
        return None
    return {"user_id": int(user_id), "message": admin_text, "via": via}
