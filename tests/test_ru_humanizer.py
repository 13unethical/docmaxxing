"""Russian humanizer swaps lookalike Cyrillic letters and leaves the English path alone."""

from __future__ import annotations

import pytest

from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy.wallet import WalletService
from services.humanizer_engine.ru_humanizer import humanize_ru


def test_ru_humanizer_swaps_only_the_lookalike_letters():
    assert humanize_ru("Собака ела орех") == "Coбaкa eлa oрex"
    assert humanize_ru("АаОоХхСсЕе") == "AaOoXxCcEe"
    assert humanize_ru("Hello, мир!") == "Hello, мир!"
    assert humanize_ru("ВНМКТУ") == "ВНМКТУ"


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


def test_ru_endpoint_charges_and_does_not_call_the_english_humanizer(economy, monkeypatch):
    from app import job_manager

    def _must_not_run(*_args, **_kwargs):
        raise AssertionError("English humanizer should not run")

    if job_manager is not None:
        monkeypatch.setattr(job_manager, "create", _must_not_run)

    user = economy_auth.create_user("ru-hz@example.com", "secret123")
    economy_auth.mark_email_verified(user["id"], user["email"])
    WalletService().set_balance(user["id"], 500)
    before = WalletService().get_balance(user["id"])

    client = _client()
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    res = client.post("/api/browser/providers/ru/humanize", json={"text": "Собака ела орех"})
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["humanized_text"] == "Coбaкa eлa oрex"
    assert body["coins_charged"] > 0
    assert WalletService().get_balance(user["id"]) == before - body["coins_charged"]


def test_ru_page_defaults_to_english():
    from app import app

    app.config["TESTING"] = True
    html = app.test_client().get("/humanizer").get_data(as_text=True)
    assert 'data-hz-lang="eng"' in html
    assert 'data-hz-lang="ru"' in html
    assert 'data-hz-lang="eng" class="dm-segment-btn is-active"' in html or (
        'class="dm-segment-btn is-active"' in html and 'data-hz-lang="eng"' in html
    )
    eng = html.split('data-hz-lang="eng"')[0]
    assert "is-active" in eng[-80:]
