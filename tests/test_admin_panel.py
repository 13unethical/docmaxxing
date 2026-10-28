"""Admin panel API (/api/admin/panel/*), account blocking and the Veil JSON endpoints."""

from __future__ import annotations

import pytest

from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy.pricing import WELCOME_BONUS, feature_cost
from services.economy.wallet import WalletService


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    economy_db.init_db()
    return tmp_path


def _client():
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


def _user(email, *, admin=False, name=""):
    user = economy_auth.create_user(email, "secret123", name=name)
    economy_auth.mark_email_verified(user["id"], user["email"])
    if admin:
        with economy_db.connect() as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user["id"],))
    return economy_auth.get_user(user["id"])


def _signed_in(client, user):
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    return client


def test_panel_is_admin_only(economy):
    client = _signed_in(_client(), _user("plain@example.com"))
    assert client.get("/api/admin/panel/overview").status_code in (302, 403)
    assert client.get("/api/admin/panel/users").status_code in (302, 403)


def test_overview_hides_staff_and_flags_lookalikes(economy):
    admin = _user("admin@example.com", admin=True, name="Boss")
    _user("gg@example.com", name="gg")
    _user("gg+1@example.com", name="gg")
    _user("real@example.com", name="Real")
    client = _signed_in(_client(), admin)

    data = client.get("/api/admin/panel/overview").get_json()
    assert data["success"] is True
    assert set(data["periods"]) == {"today", "d7", "d30", "all"}
    signups_real, signups_all = data["periods"]["today"]["k"][0][1:3]
    assert (signups_real, signups_all) == ("3", "4")
    assert data["hiddenNote"]["staff"] == 1

    users = client.get("/api/admin/panel/users?filter=susp").get_json()
    assert {u["email"] for u in users["users"]} == {"gg@example.com", "gg+1@example.com"}
    assert users["counts"]["susp"] == 2
    assert all(u["reasons"] for u in users["users"])

    csv = client.get("/api/admin/panel/users.csv")
    assert csv.status_code == 200
    assert "real@example.com" in csv.get_data(as_text=True)


def test_credit_delta_block_and_flags(economy):
    admin = _user("admin@example.com", admin=True)
    target = _user("target@example.com")
    client = _signed_in(_client(), admin)
    base = f"/api/admin/panel/users/{target['id']}"

    added = client.post(f"{base}/credits", json={"delta": 100, "reason": "Support compensation"}).get_json()
    assert added["balance"] == WELCOME_BONUS + 100
    removed = client.post(f"{base}/credits", json={"delta": -10_000, "reason": "Correction"}).get_json()
    assert removed["delta"] == -(WELCOME_BONUS + 100) and removed["balance"] == 0
    assert client.post(f"{base}/credits", json={"delta": "5"}).status_code == 400

    detail = client.get(base).get_json()
    assert detail["ledger"][0]["label"] == "Admin adjustment"

    assert client.post(f"{base}/flag", json={"flag": "test"}).get_json()["accountFlag"] == "test"
    staff = client.get("/api/admin/panel/users?filter=staff").get_json()
    assert target["id"] in {u["id"] for u in staff["users"]}

    blocked = client.post(f"{base}/block", json={"blocked": True}).get_json()
    assert blocked["blocked"] is True
    login = _client().post("/api/auth/login", json={"email": "target@example.com", "password": "secret123"})
    assert login.status_code == 403
    assert login.get_json()["error"] == "ACCOUNT_BLOCKED"

    self_block = client.post(f"/api/admin/panel/users/{admin['id']}/block", json={"blocked": True})
    assert self_block.status_code == 400

    feed = client.get("/api/admin/panel/activity?cat=admin&hide_staff=0").get_json()
    texts = " ".join(e["text"] for e in feed["events"])
    assert "Blocked" in texts and "by admin" in texts


def test_blocked_session_is_dropped(economy):
    admin = _user("admin@example.com", admin=True)
    target = _user("target@example.com")
    victim = _signed_in(_client(), target)
    assert victim.get("/api/billing").status_code == 200
    _signed_in(_client(), admin).post(f"/api/admin/panel/users/{target['id']}/block", json={"blocked": True})
    assert victim.get("/api/billing").status_code in (302, 401, 403)


def test_block_many_removes_unspent_bonus(economy):
    admin = _user("admin@example.com", admin=True)
    a = _user("a@example.com")
    b = _user("b@example.com")
    res = _signed_in(_client(), admin).post(
        "/api/admin/panel/users/block", json={"ids": [a["id"], b["id"], admin["id"]]}).get_json()
    assert sorted(res["blocked"]) == sorted([a["id"], b["id"]])
    assert WalletService().get_balance(a["id"]) == 0


def test_veil_unlock_json(economy):
    user = _user("veil@example.com")
    client = _signed_in(_client(), user)
    short = client.post("/api/veil/unlock", json={})
    assert short.status_code == 402
    assert short.get_json()["error"] == "INSUFFICIENT_COINS"

    price = feature_cost("veil")
    WalletService().set_balance(user["id"], price + 5)
    ok = client.post("/api/veil/unlock", json={}).get_json()
    assert ok["veil"]["active"] is True and ok["veil"]["expiresAt"]
    assert ok["balance"] == 5
    assert client.get("/veil/download").status_code == 200


def test_veil_email_link(economy, monkeypatch):
    from services.economy import email_verify

    sent = []
    monkeypatch.setattr(email_verify, "_smtp_send", lambda to, subject, text, html: sent.append((to, text)))
    client = _signed_in(_client(), _user("veil@example.com"))

    monkeypatch.setattr(email_verify, "smtp_configured", lambda: False)
    assert client.post("/api/veil/email-link", json={}).status_code == 503
    assert not sent

    monkeypatch.setattr(email_verify, "smtp_configured", lambda: True)
    res = client.post("/api/veil/email-link", json={})
    assert res.get_json() == {"success": True, "email": "veil@example.com"}
    assert sent[0][0] == "veil@example.com" and "/app#/veil" in sent[0][1]
