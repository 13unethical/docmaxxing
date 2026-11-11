"""Forgot-password OTP + OAuth identity linking (no live provider calls)."""

from __future__ import annotations

import pytest

from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy import oauth_login
from services.economy import password_reset
from services.economy.db import connect


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-password-reset-oauth")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://docmaxxing.com")
    economy_db.init_db()
    return tmp_path


def test_password_reset_roundtrip_and_generic_request(economy, monkeypatch):
    sent = []

    def _fake_send(*, to_email, code, name=None):
        sent.append({"to": to_email, "code": code, "name": name})
        return True

    monkeypatch.setattr(password_reset, "send_password_reset_otp_email", _fake_send)

    user = economy_auth.create_user("resetme@example.com", "oldpass1", name="Alex")
    economy_auth.mark_email_verified(user["id"])

    # Unknown email still looks successful (no account leak).
    unknown = password_reset.request_reset("nobody@example.com")
    assert unknown["ok"] is True
    assert sent == []

    known = password_reset.request_reset("ResetMe@example.com")
    assert known["ok"] is True
    assert len(sent) == 1
    code = sent[0]["code"]
    assert len(code) == 6 and code.isdigit()

    with connect() as conn:
        row = conn.execute(
            "SELECT code_hash, used_at FROM password_reset_tokens WHERE user_id = ?",
            (user["id"],),
        ).fetchone()
    assert row and row["code_hash"].startswith("h1$")
    assert code not in row["code_hash"]
    assert row["used_at"] is None

    with pytest.raises(password_reset.PasswordResetError):
        password_reset.reset_password(email="resetme@example.com", code="000000", new_password="newpass1")

    result = password_reset.reset_password(
        email="resetme@example.com", code=code, new_password="newpass1"
    )
    assert result["ok"] is True
    assert economy_auth.verify_credentials("resetme@example.com", "newpass1")
    assert economy_auth.verify_credentials("resetme@example.com", "oldpass1") is None
    assert economy_auth.get_user(user["id"])["is_verified"] is True

    # Code is single-use.
    with pytest.raises(password_reset.PasswordResetError):
        password_reset.reset_password(email="resetme@example.com", code=code, new_password="another1")


def test_oauth_links_existing_email_and_reuses_subject(economy, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google-secret")

    user = economy_auth.create_user("linked@example.com", "secret12")
    assert user["is_verified"] is False

    claims = {
        "sub": "google-sub-1",
        "email": "linked@example.com",
        "email_verified": True,
        "name": "Linked User",
        "iss": "https://accounts.google.com",
        "aud": "google-client",
        "exp": 9999999999,
        "nonce": "nonce-1",
    }

    def _fake_verify(provider, id_token, *, nonce=None):
        assert provider == "google"
        assert nonce == "nonce-1"
        return claims

    monkeypatch.setattr(oauth_login, "_verify_id_token", _fake_verify)
    monkeypatch.setattr(
        oauth_login,
        "_exchange_code",
        lambda provider, code, *, verifier: {"id_token": "tok"},
    )

    session = {
        oauth_login.SESSION_STATE_KEY: {
            "provider": "google",
            "state": "state-1",
            "nonce": "nonce-1",
            "verifier": "verifier-1",
            "next": "/app",
        }
    }
    first = oauth_login.complete_login(
        "google",
        code="auth-code",
        id_token=None,
        state="state-1",
        session=session,
    )
    assert first["user_id"] == user["id"]
    assert first["next"] == "/app"
    refreshed = economy_auth.get_user(user["id"])
    assert refreshed and refreshed["is_verified"] is True

    # Return visit with the same subject does not need email.
    claims_return = dict(claims)
    claims_return.pop("email")
    claims_return["nonce"] = "nonce-2"

    def _fake_verify2(provider, id_token, *, nonce=None):
        return claims_return

    monkeypatch.setattr(oauth_login, "_verify_id_token", _fake_verify2)
    session2 = {
        oauth_login.SESSION_STATE_KEY: {
            "provider": "google",
            "state": "state-2",
            "nonce": "nonce-2",
            "verifier": "verifier-2",
            "next": "",
        }
    }
    again = oauth_login.complete_login(
        "google",
        code="auth-code-2",
        id_token=None,
        state="state-2",
        session=session2,
    )
    assert again["user_id"] == user["id"]


def test_oauth_creates_verified_user_for_new_email(economy, monkeypatch):
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_ID", "ms-client")
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_SECRET", "ms-secret")

    claims = {
        "sub": "ms-sub-9",
        "preferred_username": "newbie@contoso.edu",
        "iss": "https://login.microsoftonline.com/tenant/v2.0",
        "aud": "ms-client",
        "exp": 9999999999,
        "nonce": "n-ms",
        "name": "New Student",
    }
    monkeypatch.setattr(oauth_login, "_verify_id_token", lambda *a, **k: claims)
    monkeypatch.setattr(
        oauth_login, "_exchange_code", lambda *a, **k: {"id_token": "tok"}
    )

    session = {
        oauth_login.SESSION_STATE_KEY: {
            "provider": "microsoft",
            "state": "st",
            "nonce": "n-ms",
            "verifier": "v",
            "next": "",
        }
    }
    result = oauth_login.complete_login(
        "microsoft", code="c", id_token=None, state="st", session=session
    )
    created = economy_auth.get_user(result["user_id"])
    assert created is not None
    assert created["email"] == "newbie@contoso.edu"
    assert created["is_verified"] is True
    assert created["name"] == "New Student"


def test_apple_without_email_or_identity_fails(economy, monkeypatch):
    monkeypatch.setenv("APPLE_OAUTH_CLIENT_ID", "com.docmaxxing.web")
    monkeypatch.setenv("APPLE_OAUTH_TEAM_ID", "TEAM")
    monkeypatch.setenv("APPLE_OAUTH_KEY_ID", "KEY")
    monkeypatch.setenv("APPLE_OAUTH_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nM\n-----END PRIVATE KEY-----")

    claims = {
        "sub": "apple.sub.first",
        "iss": "https://appleid.apple.com",
        "aud": "com.docmaxxing.web",
        "exp": 9999999999,
        "nonce": "apple-n",
    }
    monkeypatch.setattr(oauth_login, "_verify_id_token", lambda *a, **k: claims)

    session = {
        oauth_login.SESSION_STATE_KEY: {
            "provider": "apple",
            "state": "a1",
            "nonce": "apple-n",
            "verifier": "v",
            "next": "",
        }
    }
    with pytest.raises(oauth_login.OAuthError):
        oauth_login.complete_login(
            "apple",
            code=None,
            id_token="idtok",
            state="a1",
            session=session,
        )


def test_oauth_state_mismatch_rejected(economy, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google-secret")
    session = {
        oauth_login.SESSION_STATE_KEY: {
            "provider": "google",
            "state": "expected",
            "nonce": "n",
            "verifier": "v",
            "next": "",
        }
    }
    with pytest.raises(oauth_login.OAuthError):
        oauth_login.complete_login(
            "google", code="c", id_token=None, state="wrong", session=session
        )


def test_configured_providers_from_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("MICROSOFT_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("MICROSOFT_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("APPLE_OAUTH_CLIENT_ID", raising=False)
    assert oauth_login.configured_providers() == []

    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "g")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "s")
    assert oauth_login.configured_providers() == ["google"]
