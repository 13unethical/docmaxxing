"""Tests for PaddlePurchase payment records."""

from __future__ import annotations

import pytest

from services.economy import auth
from services.economy import db as economy_db
from services.economy.admin import AdminService
from services.economy.paddle_purchases import (
    STATUS_FAILED,
    STATUS_PAID,
    STATUS_PENDING,
    STATUS_REFUNDED,
    PaddlePurchaseError,
    PaddlePurchaseService,
)
from services.economy.wallet import WalletService


@pytest.fixture()
def purchases_db(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    with economy_db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("buyer@example.com", "hash"),
        )
        user_id = int(cur.lastrowid)
    return PaddlePurchaseService(), user_id


def test_create_and_list_purchase(purchases_db):
    svc, uid = purchases_db
    row = svc.create(
        user_id=uid,
        paddle_transaction_id="txn_abc123",
        product_id="starter",
        price_id="price_starter",
        credits=500,
        amount=5.0,
        currency="USD",
        status=STATUS_PAID,
    )
    assert row["status"] == "Paid"
    assert row["credits"] == 500
    assert row["paddle_transaction_id"] == "txn_abc123"

    listed = svc.list_for_user(uid)
    assert listed["total"] == 1
    assert listed["purchases"][0]["id"] == row["id"]


def test_status_transitions(purchases_db):
    svc, uid = purchases_db
    row = svc.create(
        user_id=uid,
        paddle_transaction_id="txn_pending",
        product_id="student",
        price_id="price_student",
        credits=1500,
        amount=15.0,
        status=STATUS_PENDING,
    )
    paid = svc.update_status(row["id"], STATUS_PAID)
    assert paid["status"] == "Paid"
    refunded = svc.update_status(row["id"], STATUS_REFUNDED)
    assert refunded["status"] == "Refunded"


def test_duplicate_paddle_txn_rejected(purchases_db):
    svc, uid = purchases_db
    svc.create(
        user_id=uid,
        paddle_transaction_id="txn_dup",
        product_id="cram",
        price_id="price_cram",
        credits=2900,
        amount=29.0,
        status=STATUS_PAID,
    )
    with pytest.raises(PaddlePurchaseError):
        svc.create(
            user_id=uid,
            paddle_transaction_id="txn_dup",
            product_id="cram",
            price_id="price_cram",
            credits=2900,
            amount=29.0,
            status=STATUS_FAILED,
        )


def test_admin_get_purchases(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    user = auth.create_user("pay@example.com", "secret123")
    admin = AdminService(WalletService(), PaddlePurchaseService())
    admin.purchases.create(
        user_id=user["id"],
        paddle_transaction_id="txn_admin_view",
        product_id="starter",
        price_id="price_starter",
        credits=500,
        amount=5.0,
        status=STATUS_PAID,
    )
    payload = admin.get_purchases(user["id"])
    assert payload["user"]["email"] == "pay@example.com"
    assert payload["total"] == 1
    assert payload["purchases"][0]["status"] == "Paid"
