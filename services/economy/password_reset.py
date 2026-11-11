"""Forgot-password flow: 6-digit email OTP → set a new password.

Uses a dedicated table so reset codes never collide with email-verification OTPs.
Raw codes are never stored — only an HMAC digest, same pattern as verify-email.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from werkzeug.security import generate_password_hash

from .db import connect
from .email_verify import OTP_LENGTH, OTP_TTL_MINUTES, EmailVerifyError, generate_otp_code

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RESET_MAX_ATTEMPTS = max(1, int(os.environ.get("PASSWORD_RESET_MAX_ATTEMPTS") or "5"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash     TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    attempts      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    used_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_password_reset_user
    ON password_reset_tokens(user_id, created_at DESC);
"""


class PasswordResetError(Exception):
    """User-facing reset failure (safe to show)."""


def ensure_schema(conn=None) -> None:
    if conn is not None:
        conn.executescript(_SCHEMA)
        return
    with connect() as owned:
        owned.executescript(_SCHEMA)


def _otp_secret() -> bytes:
    raw = (os.environ.get("SECRET_KEY") or "").strip() or "dev-only-secret"
    return raw.encode("utf-8")


def _hash_code(user_id: int, code: str) -> str:
    payload = f"{int(user_id)}|{code}".encode("utf-8")
    digest = hmac.new(_otp_secret(), payload, "sha256").hexdigest()
    return f"h1${digest}"


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _user_by_email(email: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, email, name, is_blocked FROM users WHERE lower(email) = ?",
            (_normalize_email(email),),
        ).fetchone()
    if row is None:
        return None
    if int(row["is_blocked"] or 0):
        return None
    return {"id": int(row["id"]), "email": row["email"], "name": row["name"]}


def send_password_reset_otp_email(*, to_email: str, code: str, name: str | None = None) -> bool:
    """Email a password-reset OTP. Never includes a URL."""
    from html import escape

    from .email_verify import _assert_otp_code, _smtp_send, smtp_configured

    to_email = (to_email or "").strip()
    if not to_email:
        raise EmailVerifyError("Missing recipient email")
    code = _assert_otp_code(code)
    greeting = f"Hi {name}," if name else "Hi,"
    subject = f"Your DocMaxxing password reset code: {code}"
    text_body = (
        f"{greeting}\n\n"
        "We received a request to reset your DocMaxxing password.\n\n"
        f"Your reset code is: {code}\n\n"
        f"Enter this code on the reset page. It expires in {OTP_TTL_MINUTES} minutes.\n\n"
        "If you did not ask for a reset, you can ignore this message.\n\n"
        "— DocMaxxing\n"
    )
    if "http://" in text_body.lower() or "https://" in text_body.lower():
        raise EmailVerifyError("Refusing to send reset email that contains a URL")
    html_body = f"""\
<html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; color: #0f172a;">
    <p>{escape(greeting)}</p>
    <p>We received a request to reset your DocMaxxing password.</p>
    <p style="font-size: 14px; color: #475569;">Your reset code:</p>
    <p style="font-size: 32px; font-weight: 700; letter-spacing: 0.35em; margin: 12px 0 20px;">{escape(code)}</p>
    <p style="color: #475569;">Enter this code on the reset page. It expires in {OTP_TTL_MINUTES} minutes.</p>
    <p style="color: #64748b; font-size: 13px;">If you did not ask for a reset, ignore this message.</p>
    <p>— DocMaxxing</p>
  </body>
</html>
"""
    if not smtp_configured():
        logger.warning("MAIL_SERVER not set — password reset code not emailed")
        return False
    logger.info("Sending password reset code email")
    try:
        _smtp_send(to_email, subject, text_body, html_body)
    except Exception:  # noqa: BLE001
        logger.error("Password reset email failed: %s", "SMTPError")
        raise EmailVerifyError("Could not send the email.") from None
    return True


def request_reset(email: str) -> dict[str, Any]:
    """Start a reset for ``email``. Always returns a generic result (no account leak)."""
    ensure_schema()
    cleaned = _normalize_email(email)
    generic = {
        "ok": True,
        "message": "If an account exists for that email, we sent a reset code.",
    }
    if not cleaned or not _EMAIL_RE.match(cleaned):
        return generic
    user = _user_by_email(cleaned)
    if user is None:
        return generic
    code = generate_otp_code()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    with connect() as conn:
        ensure_schema(conn)
        # One active challenge per user: clear unused rows.
        conn.execute(
            "DELETE FROM password_reset_tokens WHERE user_id = ? AND used_at IS NULL",
            (user["id"],),
        )
        conn.execute(
            "INSERT INTO password_reset_tokens (user_id, code_hash, expires_at) VALUES (?, ?, ?)",
            (user["id"], _hash_code(user["id"], code), expires),
        )
    try:
        send_password_reset_otp_email(to_email=user["email"], code=code, name=user.get("name"))
    except EmailVerifyError:
        # Still return generic — do not reveal delivery failure as "no account".
        logger.exception("password reset mail failed for user_id=%s", user["id"])
    return generic


def reset_password(*, email: str, code: str, new_password: str) -> dict[str, Any]:
    """Verify the OTP and set a new password. Raises PasswordResetError on failure."""
    ensure_schema()
    cleaned = _normalize_email(email)
    digits = re.sub(r"\D", "", code or "")
    if not cleaned or not _EMAIL_RE.match(cleaned):
        raise PasswordResetError("Enter the email for your account.")
    if len(digits) != OTP_LENGTH:
        raise PasswordResetError("Enter the 6-digit code from your email.")
    if not new_password or len(new_password) < 6:
        raise PasswordResetError("New password must be at least 6 characters.")

    user = _user_by_email(cleaned)
    if user is None:
        raise PasswordResetError("Invalid code or email.")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    expected = _hash_code(user["id"], digits)
    with connect() as conn:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT id, code_hash, expires_at, attempts FROM password_reset_tokens "
            "WHERE user_id = ? AND used_at IS NULL ORDER BY id DESC LIMIT 1",
            (user["id"],),
        ).fetchone()
        if row is None:
            raise PasswordResetError("Invalid code or email.")
        if str(row["expires_at"]) < now:
            conn.execute("DELETE FROM password_reset_tokens WHERE id = ?", (int(row["id"]),))
            raise PasswordResetError("That code has expired. Request a new one.")
        attempts = int(row["attempts"] or 0)
        if attempts >= RESET_MAX_ATTEMPTS:
            conn.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
                (now, int(row["id"])),
            )
            raise PasswordResetError("Too many incorrect codes. Request a new one.")
        if not hmac.compare_digest(str(row["code_hash"]), expected):
            conn.execute(
                "UPDATE password_reset_tokens SET attempts = ? WHERE id = ?",
                (attempts + 1, int(row["id"])),
            )
            raise PasswordResetError("Invalid code or email.")
        # Success: set password (revokes all sessions via trigger) and consume token.
        # The email OTP also proves mailbox ownership → mark verified.
        conn.execute(
            "UPDATE users SET password_hash = ?, password_set = 1, is_verified = 1, "
            "verification_code = NULL, verification_code_expires = NULL, "
            "verification_attempts = 0 WHERE id = ?",
            (generate_password_hash(new_password), user["id"]),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
            (now, int(row["id"])),
        )
        conn.execute(
            "DELETE FROM password_reset_tokens WHERE user_id = ? AND used_at IS NULL",
            (user["id"],),
        )
    return {"ok": True, "user_id": user["id"], "email": user["email"]}
