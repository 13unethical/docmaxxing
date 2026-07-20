"""Tests for account creation and credentials."""

from __future__ import annotations

import pytest

from services.economy import auth
from services.economy import db as economy_db
from services.economy.pricing import WELCOME_BONUS
from services.economy.wallet import WalletService


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    return WalletService()


def test_create_user_grants_welcome_bonus(fresh_db):
    wallet = fresh_db
    user = auth.create_user("New.User@Example.com", "secret123", name="New")
    assert user["email"] == "new.user@example.com"  # normalized
    assert wallet.get_balance(user["id"]) == WELCOME_BONUS


def test_duplicate_email_rejected(fresh_db):
    auth.create_user("dupe@example.com", "secret123")
    with pytest.raises(auth.DuplicateEmail):
        auth.create_user("dupe@example.com", "another123")


def test_weak_password_rejected(fresh_db):
    with pytest.raises(auth.AuthError):
        auth.create_user("weak@example.com", "123")


def test_invalid_email_rejected(fresh_db):
    with pytest.raises(auth.AuthError):
        auth.create_user("not-an-email", "secret123")


def test_verify_credentials(fresh_db):
    auth.create_user("login@example.com", "secret123")
    assert auth.verify_credentials("login@example.com", "secret123") is not None
    assert auth.verify_credentials("LOGIN@example.com", "secret123") is not None  # case-insensitive
    assert auth.verify_credentials("login@example.com", "wrong") is None
    assert auth.verify_credentials("missing@example.com", "secret123") is None
