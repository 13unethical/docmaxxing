"""Tests for two-way Telegram support helpdesk."""

from __future__ import annotations

import os

import pytest

from services.economy.db import connect, init_db
from services.economy.support_chat import (
    SupportMessage,
    extract_user_id_from_telegram_text,
    format_telegram_outbound,
    list_support_messages,
    parse_admin_reply_from_update,
    save_support_message,
)


@pytest.fixture()
def economy_db(tmp_path, monkeypatch):
    db_path = tmp_path / "economy.db"
    monkeypatch.setenv("ECONOMY_DB_PATH", str(db_path))
    # Re-bind module path used by connect()
    import services.economy.db as db_mod

    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
            ("user@example.com", "Test User", "x"),
        )
        uid = int(conn.execute("SELECT id FROM users").fetchone()["id"])
    return uid


def test_support_message_roundtrip(economy_db):
    uid = economy_db
    saved = save_support_message(user_id=uid, sender="user", message="Hello support")
    assert isinstance(saved, SupportMessage)
    assert saved.id is not None
    assert saved.sender == "user"
    admin = save_support_message(user_id=uid, sender="admin", message="We got it")
    rows = list_support_messages(uid)
    assert [r.message for r in rows] == ["Hello support", "We got it"]
    assert rows[1].sender == "admin"
    assert admin.id > saved.id


def test_format_telegram_outbound_ends_with_user_id(economy_db):
    text = format_telegram_outbound(
        message="Need a refund",
        user_id=42,
        email="a@b.com",
        name="Ann",
    )
    assert text.strip().endswith("User ID: 42")
    assert "Need a refund" in text
    assert extract_user_id_from_telegram_text(text) == 42


def test_extract_user_id_variants():
    assert extract_user_id_from_telegram_text("hi\n\nUser ID: 7") == 7
    assert extract_user_id_from_telegram_text("User ID:99") == 99
    assert extract_user_id_from_telegram_text("no id here") is None


def test_parse_admin_reply_from_update():
    payload = {
        "message": {
            "text": "Sure, refunding now.",
            "reply_to_message": {
                "text": "Support from Ann\n\nNeed help\n\nUser ID: 15",
            },
            "chat": {"id": 1},
        }
    }
    parsed = parse_admin_reply_from_update(payload)
    assert parsed == {"user_id": 15, "message": "Sure, refunding now.", "via": "user_id_footer"}
    assert parse_admin_reply_from_update({"message": {"text": "no reply"}}) is None


def test_parse_admin_reply_via_telegram_map(economy_db):
    from services.economy.support_chat import bind_telegram_message

    uid = economy_db
    bind_telegram_message(telegram_message_id=555001, user_id=uid, support_message_id=None)
    parsed = parse_admin_reply_from_update(
        {
            "message": {
                "text": "Mapped reply",
                "reply_to_message": {"message_id": 555001, "text": "no footer here"},
            }
        }
    )
    assert parsed == {"user_id": uid, "message": "Mapped reply", "via": "telegram_map"}


def test_telegram_webhook_persists_admin_reply(economy_db, monkeypatch):
    uid = economy_db
    monkeypatch.setenv("CHAT_ID", "999")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)

    from app import app

    client = app.test_client()
    res = client.post(
        "/api/telegram-webhook",
        json={
            "message": {
                "text": "Here is the fix.",
                "chat": {"id": 999},
                "reply_to_message": {
                    "text": f"Hello\n\nUser ID: {uid}",
                },
            }
        },
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body.get("ok") is True
    rows = list_support_messages(uid)
    assert len(rows) == 1
    assert rows[0].sender == "admin"
    assert rows[0].message == "Here is the fix."


def test_chat_messages_requires_auth(economy_db):
    from app import app

    client = app.test_client()
    res = client.get("/api/chat/messages", headers={"Accept": "application/json"})
    assert res.status_code == 401
