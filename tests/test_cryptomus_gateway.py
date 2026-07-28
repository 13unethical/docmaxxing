"""Cryptomus gateway: signature verification + idempotent credit fulfillment."""

from __future__ import annotations

import base64
import hashlib
import json

import pytest

from services.economy import auth
from services.economy import db as economy_db
from services.economy.cryptomus_gateway import (
    CryptomusGatewayError,
    CryptomusSignatureError,
    STATUS_PAID,
    STATUS_PENDING,
    create_invoice,
    cryptomus_json_dumps,
    cryptomus_sign,
    fulfill_paid_webhook,
    get_payment_by_order_id,
    handle_webhook,
    verify_cryptomus_webhook,
)
from services.economy.db import connect
from services.economy.wallet import WalletService


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    monkeypatch.setenv("CRYPTOMUS_API_KEY", "test_payment_api_key")
    monkeypatch.setenv("CRYPTOMUS_MERCHANT_ID", "11111111-2222-3333-4444-555555555555")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://docmaxxing.com")
    monkeypatch.setenv("CRYPTOMUS_WEBHOOK_IP_CHECK", "0")
    user = auth.create_user("crypto-buyer@example.com", "secret123")
    return user


def _sign_payload(payload: dict, api_key: str = "test_payment_api_key") -> dict:
    body = {k: v for k, v in payload.items() if k != "sign"}
    raw = cryptomus_json_dumps(body)
    signed = dict(body)
    signed["sign"] = cryptomus_sign(raw, api_key=api_key)
    return signed


def test_sign_matches_official_md5_base64_formula():
    body = '{"amount":"9.00","currency":"USD"}'
    key = "secret"
    expected = hashlib.md5(
        (base64.b64encode(body.encode()).decode() + key).encode()
    ).hexdigest()
    assert cryptomus_sign(body, api_key=key) == expected


def test_verify_webhook_signature_ok(economy):
    payload = _sign_payload(
        {
            "order_id": "dm_1_abc",
            "status": "paid",
            "is_final": True,
            "uuid": "62f88b36-a9d5-4fa6-aa26-e040c3dbf26d",
        }
    )
    verify_cryptomus_webhook(payload)


def test_verify_webhook_rejects_tamper(economy):
    payload = _sign_payload(
        {
            "order_id": "dm_1_abc",
            "status": "paid",
            "is_final": True,
        }
    )
    payload["status"] = "fail"
    with pytest.raises(CryptomusSignatureError):
        verify_cryptomus_webhook(payload)


def test_webhook_ip_allowlist(economy, monkeypatch):
    monkeypatch.setenv("CRYPTOMUS_WEBHOOK_IP_CHECK", "1")
    monkeypatch.setenv("CRYPTOMUS_WEBHOOK_IPS", "91.227.144.54")
    payload = _sign_payload(
        {"order_id": "x", "status": "process", "is_final": False}
    )
    with pytest.raises(CryptomusSignatureError):
        handle_webhook(payload, remote_addr="1.2.3.4")
    # Allowed IP + non-paid → ignored, not signature error
    result = handle_webhook(payload, remote_addr="91.227.144.54")
    assert result["ignored"] is True


def test_create_invoice_persists_pending_server_price(economy, monkeypatch):
    uid = int(economy["id"])

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "state": 0,
                "result": {
                    "uuid": "pay-uuid-1",
                    "url": "https://pay.cryptomus.com/pay/abc",
                },
            }

    def fake_post(url, headers=None, data=None, timeout=None):
        assert url.endswith("/payment")
        assert headers["merchant"]
        assert headers["sign"]
        body = json.loads(data.decode("utf-8").replace("\\/", "/"))
        assert body["amount"] == "9.00"
        assert body["currency"] == "USD"
        assert body["order_id"].startswith(f"dm_{uid}_")
        return _Resp()

    monkeypatch.setattr(
        "services.economy.cryptomus_gateway.requests.post", fake_post
    )

    result = create_invoice(user_id=uid, package_id="credits_1000")
    assert result["payment_url"] == "https://pay.cryptomus.com/pay/abc"
    assert result["credits"] == 1000
    assert result["amount"] == 9.0
    assert "price_id" not in (result.get("package") or {})
    payment = get_payment_by_order_id(result["order_id"])
    assert payment is not None
    assert payment["status"] == STATUS_PENDING
    assert payment["credits"] == 1000


def test_fulfill_uses_snapshotted_credits_not_catalog(economy, monkeypatch):
    """If catalog coins change after invoice create, paid credits stay snapshotted."""
    from services.economy import pricing

    uid = int(economy["id"])
    wallet = WalletService()
    before = wallet.get_balance(uid)
    order_id = f"dm_{uid}_snap01"

    with connect() as conn:
        conn.execute(
            "INSERT INTO cryptomus_payments "
            "(user_id, order_id, cryptomus_uuid, amount, currency, credits, "
            " package_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, order_id, "uuid-1", 9.0, "USD", 1000, "credits_1000", STATUS_PENDING),
        )

    pricing.TOPUP_PACKAGES["credits_1000"]["coins"] = 999999

    payload = _sign_payload(
        {
            "uuid": "uuid-1",
            "order_id": order_id,
            "amount": "0.01",
            "is_final": True,
            "status": "paid",
            "txid": "abc123txid",
        }
    )
    first = handle_webhook(payload)
    assert first["credits_added"] == 1000
    assert wallet.get_balance(uid) == before + 1000
    pricing.TOPUP_PACKAGES["credits_1000"]["coins"] = 1000


def test_fulfill_credits_once_and_idempotent(economy):
    uid = int(economy["id"])
    wallet = WalletService()
    before = wallet.get_balance(uid)
    order_id = f"dm_{uid}_idempotent01"

    with connect() as conn:
        conn.execute(
            "INSERT INTO cryptomus_payments "
            "(user_id, order_id, cryptomus_uuid, amount, currency, credits, "
            " package_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, order_id, "uuid-1", 9.0, "USD", 1000, "credits_1000", STATUS_PENDING),
        )

    payload = _sign_payload(
        {
            "type": "payment",
            "uuid": "uuid-1",
            "order_id": order_id,
            "amount": "9.00",
            "is_final": True,
            "status": "paid",
            "txid": "abc123txid",
            "currency": "USD",
        }
    )

    first = handle_webhook(payload)
    assert first["already_credited"] is False
    assert first["credits_added"] == 1000
    assert wallet.get_balance(uid) == before + 1000

    payment = get_payment_by_order_id(order_id)
    assert payment["status"] == STATUS_PAID
    assert payment["txid"] == "abc123txid"
    assert payment["paid_at"]

    second = handle_webhook(payload)
    assert second["already_credited"] is True
    assert second["credits_added"] == 0
    assert wallet.get_balance(uid) == before + 1000


def test_non_paid_webhook_ignored(economy):
    uid = int(economy["id"])
    order_id = f"dm_{uid}_pending_only"
    with connect() as conn:
        conn.execute(
            "INSERT INTO cryptomus_payments "
            "(user_id, order_id, amount, currency, credits, package_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, order_id, 20.0, "USD", 2500, "credits_2500", STATUS_PENDING),
        )

    payload = _sign_payload(
        {
            "order_id": order_id,
            "status": "process",
            "is_final": False,
            "uuid": "u2",
        }
    )
    result = handle_webhook(payload)
    assert result["ignored"] is True
    assert get_payment_by_order_id(order_id)["status"] == STATUS_PENDING


def test_paid_over_credits_when_final(economy):
    """Official success statuses include paid_over when is_final is true."""
    uid = int(economy["id"])
    wallet = WalletService()
    before = wallet.get_balance(uid)
    order_id = f"dm_{uid}_over"
    with connect() as conn:
        conn.execute(
            "INSERT INTO cryptomus_payments "
            "(user_id, order_id, amount, currency, credits, package_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, order_id, 9.0, "USD", 1000, "credits_1000", STATUS_PENDING),
        )
    payload = _sign_payload(
        {"order_id": order_id, "status": "paid_over", "is_final": True, "uuid": "u4"}
    )
    result = fulfill_paid_webhook(payload)
    assert result["already_credited"] is False
    assert result["credits_added"] == 1000
    assert wallet.get_balance(uid) == before + 1000
    assert get_payment_by_order_id(order_id)["status"] == STATUS_PAID


def test_paid_requires_is_final(economy):
    uid = int(economy["id"])
    order_id = f"dm_{uid}_not_final"
    with connect() as conn:
        conn.execute(
            "INSERT INTO cryptomus_payments "
            "(user_id, order_id, amount, currency, credits, package_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, order_id, 9.0, "USD", 1000, "credits_1000", STATUS_PENDING),
        )
    payload = _sign_payload(
        {"order_id": order_id, "status": "paid", "is_final": False, "uuid": "u3"}
    )
    result = fulfill_paid_webhook(payload)
    assert result["ignored"] is True
    assert get_payment_by_order_id(order_id)["status"] == STATUS_PENDING


def test_unknown_package_rejected(economy):
    with pytest.raises(CryptomusGatewayError):
        create_invoice(user_id=int(economy["id"]), package_id="nope")


def test_create_requires_auth_via_app(economy):
    from app import app

    client = app.test_client()
    res = client.post(
        "/api/payments/create",
        json={"package": "credits_1000", "credits": 999999, "amount": 0.01},
    )
    assert res.status_code == 401
    assert res.get_json()["error"] == "AUTH_REQUIRED"
