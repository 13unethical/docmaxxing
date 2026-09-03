"""Humanizer API error mapping and assignment pipeline preflight."""

from __future__ import annotations

from services.assignment_project.preflight import (
    static_provider_checks,
    with_stealthwriter_snapshot,
)
from services.humanizer_engine.client_errors import humanizer_fail_payload


def test_login_required_is_student_safe():
    body = humanizer_fail_payload(ValueError("LOGIN_REQUIRED"))
    assert body["error"] == "GENERATION_PAUSED"
    assert body["retryable"] is False
    assert "stealth" not in body["message"].lower()
    assert "humanizer" not in body["message"].lower()
    assert "signed in" not in body["message"].lower()
    assert body["message"] == "Something went wrong. Please try again."


def test_unchanged_text_is_student_safe():
    body = humanizer_fail_payload(ValueError("StealthWriter returned unchanged text"))
    assert body["error"] == "GENERATION_PAUSED"
    assert body["retryable"] is False
    assert "stealth" not in body["message"].lower()


def test_provider_sentence_not_leaked_to_client():
    body = humanizer_fail_payload(ValueError("Could not locate Humanize button."))
    assert body["error"] == "GENERATION_PAUSED"
    assert body["message"] == "Something went wrong. Please try again."
    assert "Humanize" not in body["message"]


def test_static_preflight_does_not_claim_generation(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("Claude_API_Key", raising=False)
    payload = static_provider_checks()
    assert payload["generates_assignment"] is False
    assert payload["spends_credits"] is False
    assert payload["ok"] is False
    assert "writer" in payload["blocking"]


def test_static_preflight_ok_with_gemini_only(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("Claude_API_Key", raising=False)
    payload = static_provider_checks()
    assert payload["ok"] is True
    assert payload["blocking"] == []


def test_stealthwriter_signed_out_is_blocking():
    base = {"ok": True, "checks": [], "blocking": []}
    out = with_stealthwriter_snapshot(
        base,
        {"logged_in": False, "current_url": "https://stealthwriter.ai/sign-in", "has_page": True},
    )
    assert out["ok"] is False
    assert "stealthwriter" in out["blocking"]
    assert out["stealthwriter"]["humanize_not_run"] is True


def test_pipeline_preflight_admin_skips_browser(tmp_path, monkeypatch):
    from services.economy import auth as economy_auth
    from services.economy import db as economy_db

    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    economy_db.init_db()
    user = economy_auth.create_user("admin-preflight@example.com", "secret123")
    with economy_db.connect() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user["id"],))

    from app import app

    app.config["TESTING"] = True
    client = app.test_client()
    guest = client.get("/api/admin/pipeline-preflight")
    assert guest.status_code == 401

    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    res = client.get("/api/admin/pipeline-preflight")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["generates_assignment"] is False
    assert data["spends_credits"] is False
    assert data["stealthwriter"]["skipped"] is True
    assert data["stealthwriter"]["humanize_not_run"] is True


def test_api_errors_js_has_no_provider_leak():
    from pathlib import Path

    js = Path(__file__).resolve().parents[1] / "static" / "api-errors.js"
    text = js.read_text(encoding="utf-8")
    assert "GENERATION_PAUSED:" in text
    assert "signed in on the server" not in text
    assert "StealthWriter" not in text
    assert "HUMANIZER_FAILED:" not in text


def test_assignment_js_does_not_retry_generic_try_again():
    from pathlib import Path

    js = Path(__file__).resolve().parents[1] / "static" / "assignment-page.js"
    text = js.read_text(encoding="utf-8")
    start = text.index("function isTransientApiError")
    end = text.index("function setProductionNotice")
    chunk = text[start:end]
    assert chunk
    assert 'msg.indexOf("try again")' not in chunk
    assert 'code === "GENERATION_PAUSED"' in chunk
    assert "looksLikeInternalPipeline" in text
    assert "throwHttpError" in text
