"""Guest preview — only on explicitly whitelisted tool pages."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from services.economy import auth as economy_auth
from services.economy import db as economy_db

GUEST_PREVIEW_PAGES = (
    "/",
    "/assignment",
    "/humanizer",
    "/turnitin",
    "/workspace",
    "/check",
)

PROTECTED_PAGE_REDIRECTS = (
    "/account",
    "/earn",
    "/verify-email/code",
)

ADMIN_PATHS = (
    "/admin",
)


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


def test_guest_sees_page_not_redirect():
    client = _client()
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        for path in GUEST_PREVIEW_PAGES:
            res = client.get(path, follow_redirects=False)
            assert res.status_code == 200, path
            location = res.headers.get("Location") or ""
            assert "/login" not in location, path
            assert "/register" not in location, path


def test_action_triggers_modal_for_guest():
    res = _client().get("/assignment")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "data-auth-layer" in html
    assert "auth-modal.js" in html
    assert "guest-preview.js" in html
    assert "data-guest-tool" in html


def test_humanizer_guest_can_interact_without_tool_lock():
    res = _client().get("/humanizer")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "data-guest-tool" not in html
    assert "1 free run" in html
    assert "data-hz-run" in html


def test_admin_page_redirects_guest():
    client = _client()
    for path in ADMIN_PATHS:
        res = client.get(path, follow_redirects=False)
        assert res.status_code in (301, 302, 403), path
        location = res.headers.get("Location") or ""
        assert "/login" in location or res.status_code == 403, path


def test_account_page_redirects_guest():
    client = _client()
    for path in PROTECTED_PAGE_REDIRECTS:
        res = client.get(path, follow_redirects=False)
        assert res.status_code in (301, 302), path
        location = res.headers.get("Location") or ""
        assert "/login" in location, path


def test_only_whitelisted_pages_show_guest_preview():
    client = _client()
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        humanizer_html = client.get("/humanizer").get_data(as_text=True)
        assert "data-guest-tool" not in humanizer_html
        assert "1 free run" in humanizer_html

        assignment_html = client.get("/assignment").get_data(as_text=True)
        assert "data-guest-tool" in assignment_html

        format_html = client.get("/").get_data(as_text=True)
        assert 'data-guest-persist="v2_pasted_text"' in format_html
        assert "data-require-auth" in format_html

        for path in ("/account", "/earn"):
            res = client.get(path, follow_redirects=False)
            assert res.status_code in (301, 302), path
            assert "/login" in (res.headers.get("Location") or ""), path


GUEST_PREVIEW_TOOL_PAGES = ("/assignment", "/humanizer", "/turnitin", "/workspace", "/check")


def test_signed_in_humanizer_and_workspace_cost_is_25(economy):
    client = _client()
    user = economy_auth.create_user("hz25@example.com", "secret123")
    economy_auth.mark_email_verified(user["id"], user["email"])
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]

    hz = client.get("/humanizer").get_data(as_text=True)
    assert "1 free run" not in hz
    assert "25 Credits" in hz
    assert "hz-cost-strike" not in hz

    ws = client.get("/workspace").get_data(as_text=True)
    assert 'data-humanize-cost="25"' in ws


def test_guest_page_load_shows_no_error_banner():
    client = _client()
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        for path in GUEST_PREVIEW_TOOL_PAGES:
            html = client.get(path).get_data(as_text=True)
            assert "REGISTER_REQUIRED" not in html, path
            assert "AUTH_REQUIRED" not in html, path
        assignment_html = client.get("/assignment").get_data(as_text=True)
        assert 'data-asg-page-error hidden' in assignment_html.replace('"', "'") or (
            "data-asg-page-error" in assignment_html and "hidden" in assignment_html
        )


def test_guest_history_shows_empty_state_not_error():
    html = _client().get("/assignment").get_data(as_text=True)
    assert "Sign in to see history" in html


def test_guest_humanize_second_request_blocked():
    client = _client()
    with client.session_transaction() as sess:
        sess["guest_humanize_used"] = True
    res = client.post(
        "/api/browser/providers/stealthwriter/humanize",
        json={"text": "Sample paragraph for humanize."},
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 403
    data = res.get_json()
    assert data["error"] == "REGISTER_REQUIRED"


def test_internal_error_codes_never_reach_ui():
    js = Path(__file__).resolve().parents[1] / "static" / "api-errors.js"
    text = js.read_text(encoding="utf-8")
    assert "REGISTER_REQUIRED" in text
    assert "userMessage" in text
    assert "isInternalCode" in text

    client = _client()
    with client.session_transaction() as sess:
        sess["guest_humanize_used"] = True
    res = client.post(
        "/api/browser/providers/stealthwriter/humanize",
        json={"text": "Sample paragraph for humanize."},
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 403
    data = res.get_json()
    assert data["error"] == "REGISTER_REQUIRED"
    assert data.get("message")
    assert "REGISTER_REQUIRED" not in data["message"]


def test_after_signup_returns_to_original_page(economy, monkeypatch):
    monkeypatch.setenv("EXPOSE_VERIFY_CODE", "1")
    client = _client()
    res = client.post(
        "/register",
        data={
            "email": "return@example.com",
            "password": "secret12",
            "password_confirm": "secret12",
            "next": "/assignment",
        },
        follow_redirects=False,
    )
    assert res.status_code in (301, 302)
    location = res.headers.get("Location") or ""
    assert "/verify-email/" in location

    with client.session_transaction() as sess:
        assert sess.get("post_verify_next") == "/assignment"

    user = economy_auth.verify_credentials("return@example.com", "secret12")
    assert user is not None
    code = economy_auth.issue_verification_otp(user["id"])
    economy_auth.verify_email_otp(user["id"], code)

    res = client.get("/verify-email/code", follow_redirects=False)
    assert res.status_code in (301, 302)
    assert "/assignment" in (res.headers.get("Location") or "")


def test_form_state_survives_signup():
    js = Path(__file__).resolve().parents[1] / "static" / "auth-modal.js"
    text = js.read_text(encoding="utf-8")
    assert "dm_page_state:" in text
    assert "savePageState" in text
    assert "restorePageState" in text
    assert "data-guest-persist" in text

    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        html = _client().get("/").get_data(as_text=True)
    assert 'data-guest-persist="v2_pasted_text"' in html
    assert "api-errors.js" in html
