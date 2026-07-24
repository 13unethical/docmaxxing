"""Paddle gateway: signature verification + idempotent credit fulfillment."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from services.economy import auth
from services.economy import db as economy_db
from services.economy.paddle_gateway import (
    PaddleGatewayError,
    PaddleSignatureError,
    apply_paid_purchase_atomic,
    fulfill_transaction_completed,
    handle_webhook_event,
    mock_topup_allowed,
    verify_paddle_signature,
)
from services.economy.paddle_purchases import STATUS_PAID, STATUS_PENDING, PaddlePurchaseService
from services.economy.wallet import WalletService


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    user = auth.create_user("buyer@example.com", "secret123")
    return user


def _sign(body: str, secret: str, ts: int | None = None) -> str:
    ts = int(ts if ts is not None else time.time())
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{ts}:{body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"ts={ts};h1={digest}"


def _stub_fetch(monkeypatch, *, txn_id: str, price_id: str, user_id: int, status: str = "completed"):
    def fake_fetch(transaction_id: str):
        assert transaction_id == txn_id
        return {
            "id": txn_id,
            "status": status,
            "currency_code": "USD",
            "custom_data": {"user_id": str(user_id), "package_id": "credits_1000"},
            "items": [{"price_id": price_id, "quantity": 1}],
            "details": {"totals": {"grand_total": "100"}},
        }

    monkeypatch.setattr(
        "services.economy.paddle_gateway.fetch_paddle_transaction",
        fake_fetch,
    )


def test_verify_signature_ok():
    secret = "pdl_ntfset_test_secret"
    body = '{"event_type":"transaction.completed"}'
    header = _sign(body, secret)
    verify_paddle_signature(body, header, secret=secret)


def test_verify_signature_rejects_tamper():
    secret = "pdl_ntfset_test_secret"
    body = '{"event_type":"transaction.completed"}'
    header = _sign(body, secret)
    with pytest.raises(PaddleSignatureError):
        verify_paddle_signature(body + " ", header, secret=secret)


def test_verify_signature_rejects_old_timestamp():
    secret = "pdl_ntfset_test_secret"
    body = "{}"
    header = _sign(body, secret, ts=int(time.time()) - 10_000)
    with pytest.raises(PaddleSignatureError):
        verify_paddle_signature(body, header, secret=secret, max_age_sec=300)


def test_mock_topup_disabled_in_production(monkeypatch):
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "production")
    monkeypatch.setenv("PADDLE_ALLOW_MOCK_TOPUP", "1")
    assert mock_topup_allowed() is False


def test_fulfill_credits_once(economy, monkeypatch):
    from services.economy import pricing

    pricing.TOPUP_PACKAGES["credits_1000"]["price_id"] = "pri_test_1000"

    uid = int(economy["id"])
    wallet = WalletService()
    before = wallet.get_balance(uid)
    txn_id = "txn_idempotent_001"
    _stub_fetch(monkeypatch, txn_id=txn_id, price_id="pri_test_1000", user_id=uid)

    data = {
        "id": txn_id,
        "currency_code": "USD",
        "custom_data": {
            "user_id": str(uid),
            "package_id": "credits_1000",
            "credits": "999999",  # must be ignored
        },
        "items": [{"price_id": "pri_test_1000", "quantity": 1}],
        "details": {"totals": {"grand_total": "900"}},
    }

    first = fulfill_transaction_completed(data)
    assert first["already_credited"] is False
    assert first["credits_added"] == 1000
    assert wallet.get_balance(uid) == before + 1000

    second = fulfill_transaction_completed(data)
    assert second["already_credited"] is True
    assert wallet.get_balance(uid) == before + 1000

    for _ in range(5):
        again = handle_webhook_event(
            {"event_type": "transaction.completed", "data": data}
        )
        assert again["already_credited"] is True
    assert wallet.get_balance(uid) == before + 1000

    purchases = PaddlePurchaseService().list_for_user(uid)
    assert purchases["total"] == 1
    assert purchases["purchases"][0]["status"] == STATUS_PAID

    ledger = wallet.history(uid, limit=10)
    topups = [
        t for t in ledger if t.get("feature") == "topup" and t.get("ref_id") == txn_id
    ]
    assert len(topups) == 1


def test_fulfill_rejects_unknown_price_id(economy, monkeypatch):
    uid = int(economy["id"])
    wallet = WalletService()
    before = wallet.get_balance(uid)
    txn_id = "txn_unknown_price"
    _stub_fetch(monkeypatch, txn_id=txn_id, price_id="pri_not_in_catalog", user_id=uid)
    with pytest.raises(PaddleGatewayError, match="Unknown Paddle price_id"):
        fulfill_transaction_completed(
            {
                "id": txn_id,
                "custom_data": {"user_id": str(uid), "credits": "500"},
                "items": [{"price_id": "pri_not_in_catalog"}],
            }
        )
    assert wallet.get_balance(uid) == before


def test_fulfill_rejects_non_completed_status(economy, monkeypatch):
    from services.economy import pricing

    pricing.TOPUP_PACKAGES["credits_1000"]["price_id"] = "pri_test_1000"
    uid = int(economy["id"])
    txn_id = "txn_not_completed"
    _stub_fetch(
        monkeypatch,
        txn_id=txn_id,
        price_id="pri_test_1000",
        user_id=uid,
        status="draft",
    )
    with pytest.raises(PaddleGatewayError, match="expected completed"):
        fulfill_transaction_completed({"id": txn_id})


def test_fulfill_pending_then_paid(economy, monkeypatch):
    from services.economy import pricing

    pricing.TOPUP_PACKAGES["credits_2500"]["price_id"] = "pri_test_2500"

    uid = int(economy["id"])
    purchases = PaddlePurchaseService()
    purchases.create(
        user_id=uid,
        paddle_transaction_id="txn_pending_then_paid",
        product_id="credits_2500",
        price_id="pri_test_2500",
        credits=2500,
        amount=20.0,
        status=STATUS_PENDING,
    )
    wallet = WalletService()
    before = wallet.get_balance(uid)

    def fake_fetch(transaction_id: str):
        return {
            "id": transaction_id,
            "status": "completed",
            "currency_code": "USD",
            "custom_data": {"user_id": str(uid)},
            "items": [{"price_id": "pri_test_2500"}],
            "details": {"totals": {"grand_total": "2000"}},
        }

    monkeypatch.setattr(
        "services.economy.paddle_gateway.fetch_paddle_transaction",
        fake_fetch,
    )

    result = fulfill_transaction_completed({"id": "txn_pending_then_paid"})
    assert result["already_credited"] is False
    assert result["credits_added"] == 2500
    assert wallet.get_balance(uid) == before + 2500
    row = purchases.get_by_paddle_transaction_id("txn_pending_then_paid")
    assert row["status"] == STATUS_PAID


def test_apply_paid_purchase_atomic(economy):
    uid = int(economy["id"])
    wallet = WalletService()
    before = wallet.get_balance(uid)
    result = apply_paid_purchase_atomic(
        user_id=uid,
        paddle_transaction_id="txn_atomic_1",
        product_id="credits_1000",
        price_id="pri_x",
        credits=1000,
        amount=9.0,
        meta={"mock": True},
    )
    assert result["already_credited"] is False
    assert wallet.get_balance(uid) == before + 1000
    again = apply_paid_purchase_atomic(
        user_id=uid,
        paddle_transaction_id="txn_atomic_1",
        product_id="credits_1000",
        price_id="pri_x",
        credits=1000,
        amount=9.0,
    )
    assert again["already_credited"] is True
    assert wallet.get_balance(uid) == before + 1000
