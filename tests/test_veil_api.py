"""Veil download, account connect, and credit charging."""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy.wallet import WalletService
from services.veil_tokens import issue_token, user_for_token


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


def _user(email="veil@example.com"):
    user = economy_auth.create_user(email, "secret123")
    economy_auth.mark_email_verified(user["id"], user["email"])
    return economy_auth.get_user(user["id"])


def _zip_points_at_this_site(res):
    assert res.status_code == 200
    assert res.mimetype == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(res.data))
    names = set(archive.namelist())
    assert "Veil/manifest.json" in names
    assert "Veil/content.js" in names
    assert "Veil/icons/icon128.png" in names
    assert not any("node_modules" in name or name.endswith("veil_landing.html") for name in names)
    background = archive.read("Veil/background.js").decode()
    popup = archive.read("Veil/popup.js").decode()
    assert "https://docmaxxing.com" in background
    assert "https://docmaxxing.com" in popup
    assert "__VEIL_API_BASE__" not in background


def test_download_appears_only_after_a_30_day_pass(economy):
    client = _client()
    guest = client.get("/veil/download", follow_redirects=False)
    assert guest.status_code in (301, 302)
    assert "/login" in (guest.headers.get("Location") or "")

    user = _user()
    WalletService().set_balance(user["id"], 100)
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    blocked = client.get("/veil/download", follow_redirects=False)
    assert blocked.status_code in (301, 302)
    assert "/veil" in (blocked.headers.get("Location") or "")

    short = client.post("/veil/unlock", follow_redirects=False)
    assert "error=credits" in (short.headers.get("Location") or "")
    assert WalletService().get_balance(user["id"]) == 100

    WalletService().set_balance(user["id"], 5000)
    bought = client.post("/veil/unlock", follow_redirects=False)
    assert "unlocked=1" in (bought.headers.get("Location") or "")
    assert WalletService().get_balance(user["id"]) == 5000 - 2200
    page = client.get("/veil")
    assert 'href="/veil/download"' in page.get_data(as_text=True)

    res = client.get(
        "/veil/download",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "docmaxxing.com"},
    )
    _zip_points_at_this_site(res)


def test_connect_requires_login_and_issues_a_token(economy):
    client = _client()
    guest = client.get("/veil/connect", follow_redirects=False)
    assert guest.status_code in (301, 302)
    assert "/login" in (guest.headers.get("Location") or "")

    user = _user()
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    page = client.get("/veil/connect")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Connected" in html or "Connecting" in html
    assert user["email"] in html
    match = re.search(r'token:\s*"([^"]+)"', html)
    assert match, html[html.lower().find("token") - 40 : html.lower().find("token") + 200]
    token = match.group(1)
    assert user_for_token(token)["id"] == user["id"]


def test_ask_needs_an_active_pass_and_does_not_charge_per_answer(economy, monkeypatch):
    from datetime import datetime

    from services.economy.db import connect
    from services.veil_access import pass_status, purchase_pass

    user = _user("ask@example.com")
    WalletService().set_balance(user["id"], 10000)
    token = issue_token(user["id"])
    monkeypatch.setattr("services.claude_client.claude_enabled", lambda: True)

    def _must_not_call(**_):
        raise AssertionError("Claude should not be called without a pass")

    monkeypatch.setattr("services.claude_client.generate_reply", _must_not_call)
    client = _client()
    blocked = client.post(
        "/api/veil/ask",
        json={"text": "Why is the time of flight 2.6 s?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert blocked.status_code == 402
    assert blocked.get_json()["error"] == "PASS_REQUIRED"
    assert WalletService().get_balance(user["id"]) == 10000

    first = purchase_pass(user["id"])
    second = purchase_pass(user["id"])
    first_end = datetime.fromisoformat(first["expires_at"])
    second_end = datetime.fromisoformat(second["expires_at"])
    assert (second_end - first_end).days == 30
    assert WalletService().get_balance(user["id"]) == 10000 - 4400

    monkeypatch.setattr(
        "services.claude_client.generate_reply",
        lambda **_: ("Because the vertical speed hits zero at the top.", {"api_call_success": True}),
    )
    before = WalletService().get_balance(user["id"])
    res = client.post(
        "/api/veil/ask",
        json={"text": "Why is the time of flight 2.6 s?", "extended": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = res.get_json()
    assert res.status_code == 200, body
    assert "vertical speed" in body["answer"]
    assert body["credits_used"] == 0
    assert body["balance"] == before

    monkeypatch.setattr("services.claude_client.generate_reply", lambda **_: (None, {"api_call_success": False}))
    failed = client.post(
        "/api/veil/ask",
        json={"text": "Again"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert failed.status_code == 502
    assert WalletService().get_balance(user["id"]) == before

    with connect() as conn:
        conn.execute(
            "UPDATE veil_passes SET expires_at = ? WHERE user_id = ?",
            ("2000-01-01 00:00:00", user["id"]),
        )
    assert pass_status(user["id"])["active"] is False
    expired = client.post(
        "/api/veil/ask",
        json={"text": "Again"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert expired.status_code == 402
    assert expired.get_json()["error"] == "PASS_REQUIRED"
    assert WalletService().get_balance(user["id"]) == before
    me = client.get("/api/veil/me", headers={"Authorization": f"Bearer {token}"})
    assert me.get_json()["pass_active"] is False


def test_deep_mode_routes_to_sonnet_with_images(economy, monkeypatch):
    from services.veil_access import purchase_pass

    user = _user("deep@example.com")
    WalletService().set_balance(user["id"], 5000)
    purchase_pass(user["id"])
    token = issue_token(user["id"])
    monkeypatch.setattr("services.claude_client.claude_enabled", lambda: True)
    seen = {}

    def _fake_claude(**kwargs):
        seen.update(kwargs)
        return "x = 4, because 2x = 8.", {"api_call_success": True}

    monkeypatch.setattr("services.claude_client.generate_reply", _fake_claude)
    png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    res = _client().post(
        "/api/veil/ask",
        json={"text": "Solve 2x = 8", "images": [png], "model": "deep", "extended": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["model"] == "deep"
    assert body["answer"].startswith("x = 4")
    assert seen["model"] == "claude-sonnet-5-5"
    assert body["credits_used"] == 0


def test_fast_mode_is_the_default(economy, monkeypatch):
    from services.veil_access import purchase_pass

    user = _user("fast@example.com")
    WalletService().set_balance(user["id"], 5000)
    purchase_pass(user["id"])
    token = issue_token(user["id"])
    monkeypatch.setattr("services.claude_client.claude_enabled", lambda: True)
    seen = {}

    def _fake_claude(**kwargs):
        seen.update(kwargs)
        return ("Claude answer", {})

    monkeypatch.setattr("services.claude_client.generate_reply", _fake_claude)
    res = _client().post(
        "/api/veil/ask",
        json={"text": "What is osmosis?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.get_json()["model"] == "fast"
    assert seen["model"] == "claude-haiku-5-5"


def test_ask_rejects_a_missing_token(economy):
    missing = _client().post("/api/veil/ask", json={"text": "hello"})
    assert missing.status_code == 401
