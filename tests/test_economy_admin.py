"""Tests for admin user management."""

from __future__ import annotations

import pytest

from services.economy import auth
from services.economy import db as economy_db
from services.economy.admin import AdminError, AdminService, bootstrap_admin_from_env
from services.economy.pricing import WELCOME_BONUS
from services.economy.wallet import WalletService


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    wallet = WalletService()
    return AdminService(wallet)


def _make_admin(email: str = "admin@example.com") -> dict:
    user = auth.create_user(email, "secret123", name="Admin")
    with economy_db.connect() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user["id"],))
    refreshed = auth.get_user(user["id"])
    assert refreshed is not None
    assert refreshed["is_admin"] is True
    return refreshed


def test_list_users_includes_balance(fresh_db):
    admin = _make_admin()
    auth.create_user("user@example.com", "secret123", name="Regular")
    result = fresh_db.list_users()
    assert result["total"] == 2
    emails = {u["email"] for u in result["users"]}
    assert "admin@example.com" in emails
    assert "user@example.com" in emails
    regular = next(u for u in result["users"] if u["email"] == "user@example.com")
    assert regular["balance"] == WELCOME_BONUS
    assert regular["isAdmin"] is False


def test_set_balance_credit_and_debit(fresh_db):
    admin = _make_admin()
    user = auth.create_user("target@example.com", "secret123")
    start = WELCOME_BONUS

    updated = fresh_db.set_balance(user["id"], start + 40, admin_id=admin["id"])
    assert updated["balance"] == start + 40
    assert updated["delta"] == 40
    assert WalletService().get_balance(user["id"]) == start + 40

    updated = fresh_db.set_balance(user["id"], 10, admin_id=admin["id"])
    assert updated["balance"] == 10
    assert updated["previousBalance"] == start + 40
    assert updated["delta"] == 10 - (start + 40)
    assert WalletService().get_balance(user["id"]) == 10


def test_set_balance_is_absolute_not_increment(fresh_db):
    """Typing 1500 must land exactly 1500, even if the wallet already has coins."""
    admin = _make_admin()
    user = auth.create_user("absolute@example.com", "secret123")
    wallet = WalletService()
    wallet.credit(user["id"], 5000, "admin_adjustment")
    assert wallet.get_balance(user["id"]) == WELCOME_BONUS + 5000

    updated = fresh_db.set_balance(user["id"], 1500, admin_id=admin["id"])
    assert updated["balance"] == 1500
    assert wallet.get_balance(user["id"]) == 1500


def test_set_balance_rejects_appended_digits(fresh_db):
    admin = _make_admin()
    user = auth.create_user("concat@example.com", "secret123")
    wallet = WalletService()
    wallet.set_balance(user["id"], 505050110, feature="admin_set")

    with pytest.raises(AdminError, match="appended"):
        fresh_db.set_balance(user["id"], 505050110500, admin_id=admin["id"])

    assert wallet.get_balance(user["id"]) == 505050110


def test_set_balance_rejects_negative(fresh_db):
    admin = _make_admin()
    user = auth.create_user("target@example.com", "secret123")
    with pytest.raises(AdminError):
        fresh_db.set_balance(user["id"], -5, admin_id=admin["id"])


def test_get_ledger_for_user(fresh_db):
    admin = _make_admin()
    user = auth.create_user("ledger@example.com", "secret123")
    fresh_db.set_balance(user["id"], WELCOME_BONUS + 100, admin_id=admin["id"], reason="promo")

    payload = fresh_db.get_ledger(user["id"])
    assert payload["user"]["email"] == "ledger@example.com"
    assert payload["balance"] == WELCOME_BONUS + 100
    assert payload["total"] >= 2
    types = {e["type"] for e in payload["entries"]}
    assert "BONUS" in types or "ADMIN_SET" in types
    assert any(e["type"] == "ADMIN_SET" for e in payload["entries"])
    set_entry = next(e for e in payload["entries"] if e["type"] == "ADMIN_SET")
    assert set_entry["balance_after"] == WELCOME_BONUS + 100


def test_get_ledger_unknown_user(fresh_db):
    with pytest.raises(AdminError):
        fresh_db.get_ledger(99999)


def test_set_admin_grant_and_revoke(fresh_db):
    admin = _make_admin()
    user = auth.create_user("promote@example.com", "secret123")

    result = fresh_db.set_admin(user["id"], is_admin=True, actor_id=admin["id"])
    assert result["isAdmin"] is True

    refreshed = auth.get_user(user["id"])
    assert refreshed is not None
    assert refreshed["is_admin"] is True

    fresh_db.set_admin(user["id"], is_admin=False, actor_id=admin["id"])
    refreshed = auth.get_user(user["id"])
    assert refreshed is not None
    assert refreshed["is_admin"] is False


def test_cannot_remove_last_admin(fresh_db):
    admin = _make_admin()
    with pytest.raises(AdminError):
        fresh_db.set_admin(admin["id"], is_admin=False, actor_id=admin["id"])


def test_delete_user(fresh_db):
    admin = _make_admin()
    user = auth.create_user("gone@example.com", "secret123", name="Gone")
    uid = user["id"]
    result = fresh_db.delete_user(uid, actor_id=admin["id"])
    assert result["deleted"] is True
    assert result["email"] == "gone@example.com"
    assert auth.get_user(uid) is None
    assert fresh_db.list_users()["total"] == 1


def test_cannot_delete_self(fresh_db):
    admin = _make_admin()
    with pytest.raises(AdminError):
        fresh_db.delete_user(admin["id"], actor_id=admin["id"])


def test_cannot_delete_last_admin(fresh_db):
    admin = _make_admin()
    other = auth.create_user("other@example.com", "secret123")
    # Promote other then try deleting the only remaining path:
    # deleting admin while they are sole admin fails.
    with pytest.raises(AdminError):
        fresh_db.delete_user(admin["id"], actor_id=other["id"])


def test_bootstrap_admin_from_env(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    auth.create_user("owner@example.com", "secret123")
    monkeypatch.setenv("ADMIN_EMAIL", "owner@example.com")
    bootstrap_admin_from_env()
    user = auth.get_user(1)
    assert user is not None
    assert user["is_admin"] is True


def test_create_user_with_admin_email_becomes_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    monkeypatch.setenv("ADMIN_EMAIL", "newadmin@example.com")
    user = auth.create_user("newadmin@example.com", "secret123")
    refreshed = auth.get_user(user["id"])
    assert refreshed is not None
    assert refreshed["is_admin"] is True
