"""Security: disposable email, welcome anti-abuse, email tokens, avatar."""

from __future__ import annotations

import io

import pytest
from werkzeug.datastructures import FileStorage

from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy.avatar_upload import AvatarUploadError, validate_and_store_avatar
from services.economy.disposable_email import DisposableEmailError, assert_not_disposable
from services.economy.email_verify import generate_otp_code
from services.economy.wallet import WalletService


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    economy_db.init_db()
    return tmp_path


def test_disposable_email_blocked():
    with pytest.raises(DisposableEmailError):
        assert_not_disposable("someone@mailinator.com")
    assert_not_disposable("student@university.edu")


def test_welcome_bonus_same_ip_still_granted(economy):
    """Shared campus/dorm Wi‑Fi must not block welcome bonuses."""
    wallet = WalletService()
    users = [
        economy_auth.create_user(
            f"a{i}@example.com",
            "secret12",
            ip_address="1.2.3.4",
            device_fingerprint=(chr(ord("a") + i) * 32),
        )
        for i in range(3)
    ]
    assert all(u["welcome_bonus_granted"] is True for u in users)
    assert all(wallet.get_balance(u["id"]) > 0 for u in users)


def test_welcome_bonus_fingerprint_blocks(economy):
    fp = "d" * 32
    economy_auth.create_user(
        "b1@example.com",
        "secret12",
        ip_address="9.9.9.1",
        device_fingerprint=fp,
    )
    u2 = economy_auth.create_user(
        "b2@example.com",
        "secret12",
        ip_address="9.9.9.2",
        device_fingerprint=fp,
    )
    assert u2["welcome_bonus_granted"] is False
    assert WalletService().get_balance(u2["id"]) == 0


def test_email_otp_roundtrip(economy, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "y" * 40)
    user = economy_auth.create_user("v@example.com", "secret12")
    assert user["is_verified"] is False
    code = economy_auth.issue_verification_otp(user["id"])
    assert len(code) == 6 and code.isdigit()
    from services.economy.db import connect

    with connect() as conn:
        row = conn.execute(
            "SELECT verification_code, verification_code_expires FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()
    assert row["verification_code"] == code
    assert row["verification_code_expires"]

    with pytest.raises(economy_auth.AuthError):
        economy_auth.verify_email_otp(user["id"], "000000")

    verified = economy_auth.verify_email_otp(user["id"], code)
    assert verified["is_verified"] is True

    # Expired code
    user2 = economy_auth.create_user("v2@example.com", "secret12")
    code2 = economy_auth.issue_verification_otp(user2["id"])

    with connect() as conn:
        conn.execute(
            "UPDATE users SET verification_code_expires = ? WHERE id = ?",
            ("2000-01-01 00:00:00", user2["id"]),
        )
    with pytest.raises(economy_auth.AuthError, match="expired"):
        economy_auth.verify_email_otp(user2["id"], code2)

    assert len(generate_otp_code()) == 6


def test_avatar_rejects_bad_extension(economy, tmp_path):
    upload = FileStorage(
        stream=io.BytesIO(b"not-an-image"),
        filename="evil.exe",
        content_type="application/octet-stream",
    )
    with pytest.raises(AvatarUploadError):
        validate_and_store_avatar(upload, user_id=1, repo_root=tmp_path)


def test_avatar_accepts_png(economy, tmp_path):
    png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    upload = FileStorage(stream=io.BytesIO(png), filename="me.PNG", content_type="image/png")
    path = validate_and_store_avatar(upload, user_id=7, repo_root=tmp_path)
    assert path.startswith("uploads/avatars/")
    assert (tmp_path / "static" / path).is_file()


def test_wallet_atomic_debit(economy):
    user = economy_auth.create_user(
        "pay@example.com",
        "secret12",
        ip_address="8.8.8.8",
        device_fingerprint="e" * 32,
    )
    wallet = WalletService()
    # Force a known balance
    if wallet.get_balance(user["id"]) < 5:
        wallet.credit(user["id"], 5, "admin_adjustment")
    before = wallet.get_balance(user["id"])
    wallet.debit(user["id"], 3, "detect")
    assert wallet.get_balance(user["id"]) == before - 3


def test_user_email_verified_strict():
    assert economy_auth.user_email_verified(None) is False
    assert economy_auth.user_email_verified({"is_verified": False}) is False
    assert economy_auth.user_email_verified({"is_verified": 0}) is False
    assert economy_auth.user_email_verified({"is_verified": 1}) is False  # must be bool True
    assert economy_auth.user_email_verified({"is_verified": True}) is True


def test_email_verified_required_blocks_unverified(economy):
    from flask import Flask, jsonify

    user = economy_auth.create_user("wall@example.com", "secret12")
    assert user["is_verified"] is False

    app = Flask(__name__)
    app.secret_key = "x" * 40

    @app.get("/verify-email/code")
    def verify_email_code():
        return "please verify"

    @app.get("/login")
    def login():
        return "login"

    @app.get("/api/protected")
    @economy_auth.email_verified_required
    def protected():
        return jsonify({"ok": True})

    @app.get("/page")
    @economy_auth.email_verified_required
    def page():
        return "ok"

    client = app.test_client()
    res = client.get("/api/protected", headers={"Accept": "application/json"})
    assert res.status_code == 401
    assert res.get_json()["error"] == "AUTH_REQUIRED"

    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]

    res = client.get("/api/protected", headers={"Accept": "application/json"})
    assert res.status_code == 403
    assert res.get_json()["error"] == "EMAIL_NOT_VERIFIED"

    res = client.get("/page", follow_redirects=False)
    assert res.status_code in (301, 302)
    assert "/verify-email/code" in (res.headers.get("Location") or "")

    economy_auth.mark_email_verified(user["id"], user["email"])
    res = client.get("/api/protected", headers={"Accept": "application/json"})
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
