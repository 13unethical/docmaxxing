"""Russian text is not supported yet: the old letter-swap endpoint refuses and charges nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy.wallet import WalletService

ROOT = Path(__file__).resolve().parents[1]


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


def test_ru_endpoint_refuses_without_charging(economy):
    user = economy_auth.create_user("ru-hz@example.com", "secret123")
    economy_auth.mark_email_verified(user["id"], user["email"])
    WalletService().set_balance(user["id"], 500)

    client = _client()
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    res = client.post("/api/browser/providers/ru/humanize", json={"text": "Собака ела орех"})
    body = res.get_json()
    assert res.status_code == 400
    assert body["error"] == "RU_NOT_SUPPORTED"
    assert WalletService().get_balance(user["id"]) == 500


def test_classic_page_has_no_language_switch():
    html = _client().get("/humanizer?classic=1").get_data(as_text=True)
    assert "data-hz-lang" not in html


def test_app_does_not_send_cyrillic_text_anywhere():
    js = (ROOT / "static/app2/api.js").read_text(encoding="utf-8")
    assert "/api/browser/providers/ru/humanize" not in js
    assert "RU_NOT_SUPPORTED" in js
    assert "/api/browser/providers/ru/humanize" not in (ROOT / "static/humanizer-page.js").read_text(encoding="utf-8")
