"""Academic Check page — live tool, guest preview, marketing copy."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.economy import auth as economy_auth
from services.economy import db as economy_db


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


def _verified_user(email: str = "check@example.com", password: str = "secret123"):
    user = economy_auth.create_user(email, password)
    economy_auth.mark_email_verified(user["id"], user["email"])
    return user


def test_check_page_renders_for_logged_in_user(economy):
    client = _client()
    user = _verified_user()
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    res = client.get("/check")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Academic Check" in html
    assert 'id="check_document_btn"' in html
    assert "Soon" not in html or "check-page" in html
    assert "data-check-page" in html or 'data-tour="check-page"' in html


def test_check_page_shows_guest_preview():
    res = _client().get("/check")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "data-guest-tool" in html
    assert "guest-preview.js" in html
    assert "auth-modal.js" in html
    assert "Academic Check" in html
    assert "REGISTER_REQUIRED" not in html
    assert "AUTH_REQUIRED" not in html


def test_check_not_listed_as_coming_soon():
    about = Path(__file__).resolve().parents[1] / "templates" / "info" / "about.html"
    faq = Path(__file__).resolve().parents[1] / "templates" / "info" / "faq.html"
    about_text = about.read_text(encoding="utf-8")
    faq_text = faq.read_text(encoding="utf-8")

    coming_about = about_text.split("<h2>Coming soon</h2>", 1)[-1]
    assert "Academic Check" not in coming_about.split("</ul>", 1)[0]

    assert "Academic Check" in about_text.split("<h2>What you can do today</h2>", 1)[-1]

    coming_faq = faq_text.split("<h2>Coming soon</h2>", 1)[-1]
    assert "Academic Check" not in coming_faq.split("<h2>", 1)[0]
    assert "Academic Check" in faq_text


def test_check_in_guest_preview_paths():
    from services.economy.auth import GUEST_PREVIEW_PAGE_PATHS

    assert "/check" in GUEST_PREVIEW_PAGE_PATHS
