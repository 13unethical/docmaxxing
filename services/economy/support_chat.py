"""Two-way support helpdesk backed by SQLite + Telegram Reply.

User messages are stored and forwarded to the admin Telegram chat (the ``User ID: {id}`` footer
is only for the operator to read). An admin reply is accepted only when it arrives from the
configured admin chat, from an allowlisted Telegram user id, as a ``message`` that replies to a
bot message whose ``(chat_id, message_id)`` was recorded when the user's message was sent.
Text in the replied-to message never selects the recipient. Each ``update_id`` and each admin
message is stored once, in the same transaction as the reply, so retries, replays and the
webhook/poller pair cannot duplicate a reply.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Literal

from services.economy.db import connect

logger = logging.getLogger(__name__)

Sender = Literal["user", "admin"]

USER_ID_FOOTER_RE = re.compile(r"User ID:\s*(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
VALID_SENDERS = frozenset({"user", "admin"})
ADMIN_REPLY_MAX_CHARS = 4096
PROCESSED_UPDATE_RETENTION_S = 30 * 86400
_FORWARD_FIELDS = ("forward_origin", "forward_from", "forward_from_chat", "forward_sender_name", "forward_date")


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
    columns = {row[1] for row in conn.execute("PRAGMA table_info(support_telegram_map)").fetchall()}
    if "chat_id" not in columns:
        try:
            conn.execute("ALTER TABLE support_telegram_map ADD COLUMN chat_id TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_processed_updates (
            update_id   INTEGER PRIMARY KEY,
            chat_id     TEXT NOT NULL,
            message_id  INTEGER NOT NULL,
            received_at REAL NOT NULL,
            UNIQUE (chat_id, message_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_processed_updates_received "
        "ON telegram_processed_updates(received_at)"
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
    chat_id: Any = None,
) -> None:
    """Remember which site user owns an outbound Telegram message in ``chat_id``."""
    tg_id = int(telegram_message_id)
    uid = int(user_id)
    if tg_id < 1 or uid < 1:
        return
    chat = normalize_chat_id(chat_id) or None
    with connect() as conn:
        ensure_support_messages_schema(conn)
        conn.execute(
            """
            INSERT INTO support_telegram_map
                (telegram_message_id, user_id, support_message_id, chat_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_message_id) DO UPDATE SET
                user_id = excluded.user_id,
                chat_id = excluded.chat_id,
                support_message_id = COALESCE(
                    excluded.support_message_id,
                    support_telegram_map.support_message_id
                )
            """,
            (tg_id, uid, int(support_message_id) if support_message_id else None, chat),
        )


def lookup_user_id_by_telegram_message(telegram_message_id: int | None, chat_id: Any = None) -> int | None:
    """Owner of a bot message; rows recorded for another chat never match."""
    if telegram_message_id is None or isinstance(telegram_message_id, bool):
        return None
    try:
        tg_id = int(telegram_message_id)
    except (TypeError, ValueError):
        return None
    if tg_id < 1:
        return None
    chat = normalize_chat_id(chat_id)
    if not chat:
        return None
    with connect() as conn:
        ensure_support_messages_schema(conn)
        row = conn.execute(
            "SELECT user_id FROM support_telegram_map "
            "WHERE telegram_message_id = ? AND (chat_id = ? OR chat_id IS NULL)",
            (tg_id, chat),
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
    if isinstance(value, bool):
        return ""
    return str(value if value is not None else "").strip().strip('"').strip("'")


def _strict_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


@dataclass(frozen=True)
class TelegramSupportConfig:
    token: str
    chat_id: str
    admin_user_ids: frozenset[int]
    bot_id: int | None


def telegram_support_config() -> TelegramSupportConfig:
    """Server-side Telegram settings; admin ids come only from the environment.

    ``TELEGRAM_ADMIN_USER_IDS`` lists numeric Telegram user ids allowed to answer users. When it
    is empty and ``CHAT_ID`` is a private chat (a positive id, which equals the owner's user id),
    that owner is the only admin; a group chat without the list accepts nobody.
    """
    token = (os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = normalize_chat_id(os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID"))
    admins: set[int] = set()
    for part in re.split(r"[\s,;]+", os.environ.get("TELEGRAM_ADMIN_USER_IDS") or ""):
        if part.isdigit() and int(part) > 0:
            admins.add(int(part))
    if not admins and chat_id.isdigit() and int(chat_id) > 0:
        admins.add(int(chat_id))
    bot_part = token.split(":", 1)[0] if ":" in token else ""
    bot_id = int(bot_part) if bot_part.isdigit() else None
    return TelegramSupportConfig(token=token, chat_id=chat_id, admin_user_ids=frozenset(admins), bot_id=bot_id)


def _authorize_admin_message(
    payload: Any, config: TelegramSupportConfig
) -> tuple[dict[str, Any] | None, str]:
    """The update's admin message when every server-side check passes, else ``(None, reason)``."""
    if not isinstance(payload, dict) or _strict_int(payload.get("update_id")) is None:
        return None, "malformed"
    if payload["update_id"] < 0:
        return None, "malformed"
    message = payload.get("message")
    if not isinstance(message, dict):
        return None, "unsupported_update"
    if not config.chat_id:
        return None, "not_configured"
    chat = message.get("chat")
    if not isinstance(chat, dict) or normalize_chat_id(chat.get("id")) != config.chat_id:
        return None, "foreign_chat"
    if _strict_int(message.get("message_id")) is None or message["message_id"] < 1:
        return None, "malformed"
    sender = message.get("from")
    sender_id = _strict_int(sender.get("id")) if isinstance(sender, dict) else None
    if sender_id is None or sender.get("is_bot") is not False:
        return None, "unauthorized_sender"
    if not config.admin_user_ids:
        return None, "no_admins_configured"
    if sender_id not in config.admin_user_ids:
        return None, "unauthorized_sender"
    if message.get("sender_chat") is not None or message.get("via_bot") is not None:
        return None, "unauthorized_sender"
    if any(message.get(name) is not None for name in _FORWARD_FIELDS):
        return None, "forwarded"
    reply_to = message.get("reply_to_message")
    if not isinstance(reply_to, dict) or _strict_int(reply_to.get("message_id")) is None:
        return None, "not_a_reply"
    reply_chat = reply_to.get("chat")
    if not isinstance(reply_chat, dict) or normalize_chat_id(reply_chat.get("id")) != config.chat_id:
        return None, "foreign_chat"
    if config.bot_id is not None:
        author = reply_to.get("from")
        if not isinstance(author, dict) or _strict_int(author.get("id")) != config.bot_id:
            return None, "not_a_bot_message"
    text = message.get("text") if isinstance(message.get("text"), str) else message.get("caption")
    if not isinstance(text, str) or not text.strip():
        return None, "empty"
    return message, ""


def parse_admin_reply_from_update(
    payload: dict[str, Any], *, config: TelegramSupportConfig | None = None
) -> dict[str, Any] | None:
    """Recipient and text of an authorized admin reply.

    Returns ``{"user_id", "message", "via", "update_id", "chat_id", "message_id"}`` or ``None``.
    """
    cfg = config or telegram_support_config()
    message, _reason = _authorize_admin_message(payload, cfg)
    if message is None:
        return None
    user_id = lookup_user_id_by_telegram_message(message["reply_to_message"]["message_id"], cfg.chat_id)
    if user_id is None:
        return None
    text = (message.get("text") if isinstance(message.get("text"), str) else message.get("caption")).strip()
    return {
        "user_id": int(user_id),
        "message": text[:ADMIN_REPLY_MAX_CHARS],
        "via": "telegram_map",
        "update_id": int(payload["update_id"]),
        "chat_id": cfg.chat_id,
        "message_id": int(message["message_id"]),
    }


@dataclass
class AdminUpdateResult:
    status: Literal["saved", "duplicate", "ignored"]
    reason: str = ""
    message: SupportMessage | None = None


def process_admin_update(payload: Any, *, source: str) -> AdminUpdateResult:
    """Validate a Telegram update and store the admin reply once (webhook and poller)."""
    cfg = telegram_support_config()
    message, reason = _authorize_admin_message(payload, cfg)
    if message is None:
        logger.info(
            "telegram %s: update ignored reason=%s update_id=%s",
            source,
            reason,
            payload.get("update_id") if isinstance(payload, dict) else None,
        )
        return AdminUpdateResult("ignored", reason)
    parsed = parse_admin_reply_from_update(payload, config=cfg)
    if parsed is None:
        logger.info("telegram %s: reply to an unknown message ignored update_id=%s", source, payload.get("update_id"))
        return AdminUpdateResult("ignored", "unbound_reply")
    saved = _save_admin_reply_once(parsed)
    if saved is None:
        logger.info("telegram %s: duplicate update_id=%s ignored", source, parsed["update_id"])
        return AdminUpdateResult("duplicate", "duplicate")
    logger.info(
        "telegram %s: admin reply saved user_id=%s msg_id=%s update_id=%s",
        source,
        saved.user_id,
        saved.id,
        parsed["update_id"],
    )
    return AdminUpdateResult("saved", "", saved)


def _save_admin_reply_once(parsed: dict[str, Any]) -> SupportMessage | None:
    now = time.time()
    with connect() as conn:
        ensure_support_messages_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO telegram_processed_updates (update_id, chat_id, message_id, received_at) "
                "VALUES (?, ?, ?, ?)",
                (parsed["update_id"], parsed["chat_id"], parsed["message_id"], now),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            return None
        conn.execute(
            "DELETE FROM telegram_processed_updates WHERE received_at < ?",
            (now - PROCESSED_UPDATE_RETENTION_S,),
        )
        cur = conn.execute(
            "INSERT INTO support_messages (user_id, sender, message) VALUES (?, 'admin', ?)",
            (int(parsed["user_id"]), str(parsed["message"])),
        )
        row = conn.execute(
            "SELECT id, user_id, sender, message, created_at FROM support_messages WHERE id = ?",
            (int(cur.lastrowid),),
        ).fetchone()
    return SupportMessage(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        sender=str(row["sender"]),
        message=str(row["message"]),
        created_at=str(row["created_at"]) if row["created_at"] else None,
    )
