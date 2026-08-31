"""Tests for Lemon Squeezy webhook credit fulfillment."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from services.economy.db import connect, init_db
from services.economy.lemon_squeezy_gateway import (
    LemonSqueezyGatewayError,
    LemonSqueezySignatureError,
    handle_webhook_event,
    resolve_variant_credits,
    summarize_webhook_payload,
    verify_lemon_squeezy_signature,
)
from services.economy.wallet import WalletService


@pytest.fixture()
def economy_db(tmp_path, monkeypatch):
    db_path = tmp_path / "economy.db"
    monkeypatch.setenv("ECONOMY_DB_PATH", str(db_path))
    monkeypatch.setenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "test-secret")
    # Real Lemon webhook sends numeric variant_id; checkout uses UUID separately.
    monkeypatch.setenv("LEMON_VARIANT_ID_CREDITS_1000", "1111111")
    monkeypatch.setenv("LEMON_VARIANT_ID_CREDITS_2200", "1992940")
    monkeypatch.setenv(
        "LEMON_CHECKOUT_UUID_CREDITS_2200",
        "8bd0501d-302f-4054-a905-302112b8e267",
    )
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


def _order_payload(
    *,
    user_id: int,
    variant_id: str | int = "variant_1_id",
    order_id: str = "ord_1",
    order_number: int = 4450641,
    total_usd: int = 2000,
):
    return {
        "meta": {
            "event_name": "order_created",
            "custom_data": {"user_id": str(user_id)},
        },
        "data": {
            "id": order_id,
            "attributes": {
                "user_email": "buyer@example.com",
                "order_number": order_number,
                "total_usd": total_usd,
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


def test_numeric_variant_id_credits_pro_package(economy_db):
    """Regression: Lemon webhooks send numeric variant_id, not checkout UUID."""
    uid = economy_db
    payload = _order_payload(
        user_id=uid,
        variant_id=1992940,  # int, as in real Lemon JSON
        order_id="ord_pro_numeric",
        order_number=4450641,
    )
    result = handle_webhook_event(payload)
    assert result["status"] == "success"
    assert result["credits"] == 2200
    assert result["variant_id"] == "1992940"
    assert WalletService().get_balance(uid) == 2200

    # String form of the same id also resolves.
    assert resolve_variant_credits("1992940") == 2200
    assert resolve_variant_credits(1992940) == 2200


def test_checkout_uuid_also_resolves_credits(economy_db):
    assert (
        resolve_variant_credits("8bd0501d-302f-4054-a905-302112b8e267") == 2200
    )


def test_unknown_numeric_variant_rejected(economy_db, monkeypatch):
    uid = economy_db
    alerts: list[str] = []

    def _fake_notify(reason, *, payload=None, detail=None):
        alerts.append(reason)

    monkeypatch.setattr(
        "services.economy.lemon_squeezy_gateway.notify_unhandled_payment",
        _fake_notify,
    )
    with pytest.raises(LemonSqueezyGatewayError, match="Unknown Lemon Squeezy variant"):
        handle_webhook_event(
            _order_payload(user_id=uid, variant_id=9999999, order_id="ord_unknown")
        )
    assert "unknown_variant" in alerts
    assert WalletService().get_balance(uid) == 0


def test_missing_user_id_alerts(economy_db, monkeypatch):
    alerts: list[str] = []
    monkeypatch.setattr(
        "services.economy.lemon_squeezy_gateway.notify_unhandled_payment",
        lambda reason, *, payload=None, detail=None: alerts.append(reason),
    )
    payload = _order_payload(user_id=1)
    payload["meta"]["custom_data"] = {}
    with pytest.raises(LemonSqueezyGatewayError, match="user_id"):
        handle_webhook_event(payload)
    assert "missing_user_id" in alerts


def test_numeric_variant_idempotent_redelivery(economy_db):
    uid = economy_db
    payload = _order_payload(
        user_id=uid,
        variant_id="1992940",
        order_id="ord_retry",
    )
    first = handle_webhook_event(payload)
    assert first["credits"] == 2200
    second = handle_webhook_event(payload)
    third = handle_webhook_event(payload)
    assert second["already_credited"] is True
    assert third["already_credited"] is True
    assert WalletService().get_balance(uid) == 2200


def test_ignores_non_order_events(economy_db):
    uid = economy_db
    payload = _order_payload(user_id=uid)
    payload["meta"]["event_name"] = "subscription_created"
    result = handle_webhook_event(payload)
    assert result["status"] == "ignored"
    assert WalletService().get_balance(uid) == 0


def test_summarize_webhook_payload_extracts_fields(economy_db):
    summary = summarize_webhook_payload(
        _order_payload(user_id=7, variant_id=1992940, order_number=4450641)
    )
    assert summary["event_name"] == "order_created"
    assert summary["variant_id"] == "1992940"
    assert summary["order_number"] == 4450641
    assert summary["user_id"] == 7
    assert summary["email"] == "buyer@example.com"


def test_flask_route_logs_before_signature_and_credits(economy_db, monkeypatch, caplog):
    uid = economy_db
    monkeypatch.setenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "test-secret")
    from app import app

    payload = _order_payload(
        user_id=uid,
        variant_id=1992940,
        order_id="ord_route_pro",
        order_number=4450641,
    )
    raw = json.dumps(payload).encode("utf-8")
    client = app.test_client()

    with caplog.at_level("INFO"):
        bad = client.post(
            "/api/webhooks/lemon-squeezy",
            data=raw,
            headers={
                "Content-Type": "application/json",
                "X-Signature": "nope",
                "X-Event-Name": "order_created",
            },
        )
    assert bad.status_code == 403
    assert any("lemon-squeezy webhook received" in r.message for r in caplog.records)
    assert any("variant_id=1992940" in r.message for r in caplog.records)

    ok = client.post(
        "/api/webhooks/lemon-squeezy",
        data=raw,
        headers={"Content-Type": "application/json", "X-Signature": _sign(raw)},
    )
    assert ok.status_code == 200
    body = ok.get_json()
    assert body["status"] == "success"
    assert body["credits"] == 2200
    assert WalletService().get_balance(uid) == 2200


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
