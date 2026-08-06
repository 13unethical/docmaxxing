"""Email verification via 6-digit OTP + optional SMTP delivery.

Magic-link / itsdangerous tokens are intentionally NOT used here.
"""

from __future__ import annotations

import logging
import os
import secrets
import smtplib
from email.message import EmailMessage
from html import escape

logger = logging.getLogger(__name__)

OTP_LENGTH = 6
OTP_TTL_MINUTES = 15


class EmailVerifyError(Exception):
    """OTP or mail delivery failure."""


def generate_otp_code() -> str:
    """Cryptographically strong 6-digit code (zero-padded)."""
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


def _env_bool(name: str, default: bool = True) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "y", "on"):
        return True
    if raw in ("0", "false", "no", "n", "off"):
        return False
    return default


def _mail_setting(name: str, default: str = "") -> str:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            val = current_app.config.get(name)
            if val is not None and str(val).strip() != "":
                return str(val).strip()
    except RuntimeError:
        pass
    return (os.environ.get(name) or default).strip()


def smtp_configured() -> bool:
    return bool(_mail_setting("MAIL_SERVER"))


def _assert_otp_code(code: str) -> str:
    cleaned = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(cleaned) != OTP_LENGTH:
        raise EmailVerifyError("verification_code must be a 6-digit OTP")
    return cleaned


def send_verification_otp_email(
    *,
    to_email: str,
    code: str,
    name: str | None = None,
) -> bool:
    """Send ONLY the 6-digit OTP — never a magic link / verify URL."""
    to_email = (to_email or "").strip()
    if not to_email:
        raise EmailVerifyError("Missing recipient email")
    code = _assert_otp_code(code)

    subject = f"Your DocMaxxing Verification Code: {code}"
    greeting = f"Hi {name}," if name else "Hi,"
    text_body = (
        f"{greeting}\n\n"
        "Thanks for creating a DocMaxxing account.\n\n"
        f"Your verification code is: {code}\n\n"
        f"Enter this code on the verification page. It expires in {OTP_TTL_MINUTES} minutes.\n\n"
        "Do not share this code with anyone.\n"
        "If you did not sign up, you can ignore this message.\n\n"
        "— DocMaxxing\n"
    )
    # Guardrail: never ship a verify-email URL in OTP mail.
    if "verify-email/" in text_body.lower() or "http://" in text_body or "https://" in text_body:
        raise EmailVerifyError("Refusing to send OTP email that contains a URL")

    safe_code = escape(code)
    safe_greeting = escape(greeting)
    html_body = f"""\
<html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; color: #0f172a;">
    <p>{safe_greeting}</p>
    <p>Thanks for creating a DocMaxxing account.</p>
    <p style="font-size: 14px; color: #475569;">Your verification code:</p>
    <p style="font-size: 32px; font-weight: 700; letter-spacing: 0.35em; margin: 12px 0 20px;">
      {safe_code}
    </p>
    <p style="color: #475569;">
      Enter this code on the verification page. It expires in {OTP_TTL_MINUTES} minutes.
    </p>
    <p style="color: #64748b; font-size: 13px;">
      Do not share this code. If you did not sign up, ignore this message.
    </p>
    <p>— DocMaxxing</p>
  </body>
</html>
"""

    if not smtp_configured():
        logger.warning(
            "MAIL_SERVER not set — OTP for %s is %s (not emailed)",
            to_email,
            code,
        )
        return False

    host = _mail_setting("MAIL_SERVER")
    port_raw = _mail_setting("MAIL_PORT", "587")
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    username = _mail_setting("MAIL_USERNAME")
    password = _mail_setting("MAIL_PASSWORD")
    mail_from = _mail_setting("MAIL_FROM") or username or "noreply@docmaxxing.com"
    try:
        from flask import current_app, has_app_context

        if has_app_context() and "MAIL_USE_TLS" in current_app.config:
            use_tls = bool(current_app.config["MAIL_USE_TLS"])
        else:
            use_tls = _env_bool("MAIL_USE_TLS", True)
    except RuntimeError:
        use_tls = _env_bool("MAIL_USE_TLS", True)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    logger.info(
        "Sending OTP verification email to=%s subject=%r code=%s",
        to_email,
        subject,
        code,
    )

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send OTP email to %s", to_email)
        raise EmailVerifyError(f"Could not send verification email: {exc}") from exc
    return True


def send_verification_email(*args, **kwargs):  # noqa: ANN002, ANN003
    """Removed magic-link API — callers must use send_verification_otp_email."""
    raise EmailVerifyError(
        "Magic-link verification emails are disabled. Use send_verification_otp_email(code=...)."
    )
