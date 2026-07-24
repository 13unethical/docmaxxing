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


def test_credit_transaction_shape(wallet_and_user):
    wallet, uid = wallet_and_user
    wallet.credit(uid, 2000, "topup", ref_id="pkg_starter")
    wallet.debit(uid, 10, "humanize", ref_id="job_1")
    wallet.debit(uid, 300, "turnitin", ref_id="sub_1")
    wallet.refund(uid, 300, "turnitin", ref_id="sub_1")

    ledger = wallet.ledger(uid)
    assert ledger["balance"] == 1990
    assert ledger["total"] == 4
    entries = ledger["entries"]

    assert entries[0]["type"] == "REFUND"
    assert entries[0]["credits"] == 300
    assert entries[0]["reference_type"] == "Turnitin"
    assert entries[0]["balance_before"] == 1690
    assert entries[0]["balance_after"] == 1990

    assert entries[1]["type"] == "USAGE"
    assert entries[1]["credits"] == -300
    assert entries[1]["reference_type"] == "Turnitin"

    assert entries[2]["type"] == "USAGE"
    assert entries[2]["credits"] == -10
    assert entries[2]["reference_type"] == "Humanizer"

    assert entries[3]["type"] == "PURCHASE"
    assert entries[3]["credits"] == 2000
    assert entries[3]["reference_type"] == "Paddle"
    assert entries[3]["reference_id"] == "pkg_starter"


def test_admin_add_remove_types(wallet_and_user):
    wallet, uid = wallet_and_user
    wallet.credit(uid, 50, "admin_adjustment")
    wallet.debit(uid, 20, "admin_adjustment")
    entries = wallet.history(uid)
    assert entries[0]["type"] == "ADMIN_REMOVE"
    assert entries[0]["reference_type"] == "Admin"
    assert entries[1]["type"] == "ADMIN_ADD"


def test_zero_or_negative_amount_rejected(wallet_and_user):
    wallet, uid = wallet_and_user
    with pytest.raises(Exception):
        wallet.debit(uid, 0, "humanize")
