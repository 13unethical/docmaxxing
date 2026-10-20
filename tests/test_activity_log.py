"""Admin activity ledger: event capture, history backfill, survival after delete."""

from __future__ import annotations

import pytest

from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy.activity_log import backfill_activity, list_activity
from services.economy.admin import AdminService
from services.economy.wallet import WalletService


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    economy_db.init_db()
    return tmp_path


def _actions(**kwargs) -> list[str]:
    return [e["action"] for e in list_activity(limit=500, **kwargs)["entries"]]


def test_register_wallet_and_admin_delete_are_logged(economy):
    admin = economy_auth.create_user("boss@example.com", "secret123")
    victim = economy_auth.create_user("victim@example.com", "secret123")
    WalletService().credit(victim["id"], 40, "topup", ref_id="t1")

    AdminService().delete_user(victim["id"], actor_id=admin["id"])

    entries = list_activity(user_id=victim["id"], limit=500)["entries"]
    actions = [e["action"] for e in entries]
    assert "user.register" in actions
    assert any(a.startswith("wallet.") for a in actions)
    deleted = next(e for e in entries if e["action"] == "admin.user_deleted")
    assert deleted["user_email"] == "victim@example.com"
    assert deleted["actor_id"] == admin["id"]
    assert deleted["details"]["balance_at_delete"] >= 40

    payload = list_activity(limit=500)
    assert payload["registered_events"] == 2
    assert payload["deleted_events"] == 1


def test_backfill_is_idempotent_and_skips_live_rows(economy):
    user = economy_auth.create_user("old@example.com", "secret123")
    WalletService().credit(user["id"], 5, "topup")
    before = list_activity(limit=500)["total"]

    with economy_db.connect() as conn:
        backfill_activity(conn)
        backfill_activity(conn)

    assert list_activity(limit=500)["total"] == before
    assert _actions(search="old@example.com").count("user.register") == 1


def test_backfill_imports_rows_created_before_the_ledger(economy):
    with economy_db.connect() as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES ('legacy@example.com', 'x', '2026-01-02 03:04:05')"
        )
        conn.execute("DELETE FROM activity_log")
        backfill_activity(conn)

    entries = list_activity(search="legacy@example.com", limit=50)["entries"]
    assert [e["action"] for e in entries] == ["user.register"]
    assert entries[0]["created_at"] == "2026-01-02 03:04:05"


def test_admin_activity_endpoint_requires_admin_and_logs_requests(economy):
    from app import app

    app.config["TESTING"] = True
    client = app.test_client()

    assert client.get("/api/admin/activity").status_code in {401, 403, 302}

    res = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "wrong"},
    )
    assert res.status_code == 401
    assert "auth.login_failed" in _actions(search="nobody@example.com")

    admin = economy_auth.create_user("root@example.com", "secret123")
    with economy_db.connect() as conn:
        conn.execute("UPDATE users SET is_admin = 1, is_verified = 1 WHERE id = ?", (admin["id"],))
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = admin["id"]

    res = client.get("/api/admin/activity?category=auth")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert all(e["category"] == "auth" for e in body["entries"])
