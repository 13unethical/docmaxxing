"""Tests for the coin wallet and ledger."""

from __future__ import annotations

import pytest

from services.economy import db as economy_db
from services.economy.wallet import InsufficientCoins, WalletService


@pytest.fixture()
def wallet_and_user(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    with economy_db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("tester@example.com", "hash"),
        )
        user_id = int(cur.lastrowid)
    return WalletService(), user_id


def test_credit_then_debit_updates_balance(wallet_and_user):
    wallet, uid = wallet_and_user
    assert wallet.get_balance(uid) == 0
    wallet.credit(uid, 100, "topup")
    assert wallet.get_balance(uid) == 100
    wallet.debit(uid, 30, "humanize")
    assert wallet.get_balance(uid) == 70


def test_debit_insufficient_raises_and_keeps_balance(wallet_and_user):
    wallet, uid = wallet_and_user
    wallet.credit(uid, 10, "topup")
    with pytest.raises(InsufficientCoins) as exc:
        wallet.debit(uid, 25, "turnitin")
    assert exc.value.required == 25
    assert exc.value.balance == 10
    # Balance untouched by the failed debit.
    assert wallet.get_balance(uid) == 10


def test_refund_restores_balance(wallet_and_user):
    wallet, uid = wallet_and_user
    wallet.credit(uid, 50, "topup")
    wallet.debit(uid, 10, "humanize")
    wallet.refund(uid, 10, "humanize")
    assert wallet.get_balance(uid) == 50


def test_ledger_records_every_movement(wallet_and_user):
    wallet, uid = wallet_and_user
    wallet.credit(uid, 100, "topup")
    wallet.debit(uid, 10, "detect")
    wallet.refund(uid, 10, "detect")
    history = wallet.history(uid)
    assert [t["kind"] for t in history] == ["refund", "debit", "credit"]
    # balance_after is captured per row (newest first).
    assert history[0]["balance_after"] == 100
    assert history[1]["balance_after"] == 90
    assert history[2]["balance_after"] == 100


def test_zero_or_negative_amount_rejected(wallet_and_user):
    wallet, uid = wallet_and_user
    with pytest.raises(Exception):
        wallet.debit(uid, 0, "humanize")
