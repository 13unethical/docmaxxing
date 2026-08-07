"""Tests for Lemon Squeezy webhook credit fulfillment."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from services.economy.db import connect, init_db
from services.economy.lemon_squeezy_gateway import (
    LemonSqueezySignatureError,
    handle_webhook_event,
    verify_lemon_squeezy_signature,
)
from services.economy.wallet import WalletService


@pytest.fixture()
def economy_db(tmp_path, monkeypatch):
    db_path = tmp_path / "economy.db"
    monkeypatch.setenv("ECONOMY_DB_PATH", str(db_path))
    monkeypatch.setenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "test-secret")
    import services.economy.db as db_mod

    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
            ("buyer@example.com", "Buyer", "x"),
        )
        uid = int(conn.execute("SELECT id FROM users").fetchone()["id"])
    WalletService().ensure_wallet(uid)
    return uid


def _sign(body: bytes, secret: str = "test-secret") -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _order_payload(*, user_id: int, variant_id: str = "variant_1_id", order_id: str = "ord_1"):
    return {
        "meta": {
            "event_name": "order_created",
            "custom_data": {"user_id": str(user_id)},
        },
        "data": {
            "id": order_id,
            "attributes": {
                "user_email": "buyer@example.com",
                "first_order_item": {"variant_id": variant_id},
            },
        },
    }


def test_signature_valid(economy_db):
    body = b'{"ok":true}'
    verify_lemon_squeezy_signature(body, _sign(body))


def test_signature_invalid(economy_db):
    with pytest.raises(LemonSqueezySignatureError):
        verify_lemon_squeezy_signature(b"{}", "deadbeef")


def test_order_created_credits_user(economy_db):
    uid = economy_db
    result = handle_webhook_event(_order_payload(user_id=uid))
    assert result["status"] == "success"
    assert result["credits"] == 1000
    assert WalletService().get_balance(uid) == 1000

    # Idempotent redelivery
    again = handle_webhook_event(_order_payload(user_id=uid))
    assert again["already_credited"] is True
    assert WalletService().get_balance(uid) == 1000


def test_ignores_non_order_events(economy_db):
    uid = economy_db
    payload = _order_payload(user_id=uid)
    payload["meta"]["event_name"] = "subscription_created"
    result = handle_webhook_event(payload)
    assert result["status"] == "ignored"
    assert WalletService().get_balance(uid) == 0


def test_flask_route_signature_and_credit(economy_db, monkeypatch):
    uid = economy_db
    monkeypatch.setenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "test-secret")
    from app import app

    payload = _order_payload(user_id=uid, order_id="ord_route_1")
    raw = json.dumps(payload).encode("utf-8")
    client = app.test_client()

    bad = client.post(
        "/api/webhooks/lemon-squeezy",
        data=raw,
        headers={"Content-Type": "application/json", "X-Signature": "nope"},
    )
    assert bad.status_code == 403

    ok = client.post(
        "/api/webhooks/lemon-squeezy",
        data=raw,
        headers={"Content-Type": "application/json", "X-Signature": _sign(raw)},
    )
    assert ok.status_code == 200
    body = ok.get_json()
    assert body["status"] == "success"
    assert WalletService().get_balance(uid) == 1000
