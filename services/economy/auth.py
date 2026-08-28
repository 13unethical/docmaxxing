"""Account creation, credentials and Flask session helpers.

Email + password auth backed by the economy SQLite DB. Passwords are hashed
with Werkzeug (ships with Flask). New accounts may receive a welcome credit
bonus subject to soft IP / device fingerprint anti-abuse limits.
"""

from __future__ import annotations

import functools
import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Callable

from flask import g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import connect
from .disposable_email import DisposableEmailError, assert_not_disposable
from .email_verify import OTP_TTL_MINUTES, generate_otp_code
from .pricing import WELCOME_BONUS
from .wallet import WalletService

_wallet = WalletService()

SESSION_KEY = "user_id"
_FINGERPRINT_RE = re.compile(r"^[a-fA-F0-9]{16,128}$")


class AuthError(Exception):
    """Base auth error."""


class DuplicateEmail(AuthError):
    """Raised when registering an email that already exists."""


class EmailNotVerified(AuthError):
    """Raised when a verified email is required."""


def _row_to_user(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    keys = row.keys()
    is_admin = bool(row["is_admin"]) if "is_admin" in keys else False
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "created_at": row["created_at"],
        "is_admin": is_admin,
        "is_verified": bool(row["is_verified"]) if "is_verified" in keys else False,
        "ip_address": row["ip_address"] if "ip_address" in keys else None,
        "device_fingerprint": row["device_fingerprint"] if "device_fingerprint" in keys else None,
        "avatar_file": row["avatar_file"] if "avatar_file" in keys else None,
        "welcome_bonus_granted": bool(row["welcome_bonus_granted"])
        if "welcome_bonus_granted" in keys
        else False,
        "referral_code": row["referral_code"] if "referral_code" in keys else None,
        "referrer_id": int(row["referrer_id"]) if "referrer_id" in keys and row["referrer_id"] is not None else None,
        "referral_balance_usd": float(row["referral_balance_usd"] or 0) if "referral_balance_usd" in keys else 0.0,
        "qualifying_referrals_count": int(row["qualifying_referrals_count"] or 0) if "qualifying_referrals_count" in keys else 0,
        "is_pro": bool(row["is_pro"]) if "is_pro" in keys else False,
        "free_turnitin_reports": int(row["free_turnitin_reports"] or 0) if "free_turnitin_reports" in keys else 0,
    }


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_bootstrap_admin_email(email: str) -> bool:
    configured = normalize_email(os.environ.get("ADMIN_EMAIL") or "")
    return bool(configured) and normalize_email(email) == configured


def normalize_fingerprint(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text or not _FINGERPRINT_RE.match(text):
        return None
    return text.lower()


def client_ip_from_request() -> str | None:
    """Best-effort client IP (honours first X-Forwarded-For hop when present)."""
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:64]
    addr = (request.remote_addr or "").strip()
    return addr[:64] if addr else None


def fingerprint_already_bonus(fingerprint: str | None) -> bool:
    if not fingerprint:
        return False
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM users "
            "WHERE device_fingerprint = ? AND welcome_bonus_granted = 1 "
            "LIMIT 1",
            (fingerprint,),
        ).fetchone()
    return row is not None


def should_grant_welcome_bonus(
    *,
    ip_address: str | None = None,
    device_fingerprint: str | None,
) -> bool:
    """Soft anti-abuse: deny welcome bonus only when this device already got one.

    ``ip_address`` is still recorded on the user row for analytics/logs, but it
    never gates the welcome bonus — shared campus/dorm Wi‑Fi must not block students.
    """
    _ = ip_address
    if WELCOME_BONUS <= 0:
        return False
    if fingerprint_already_bonus(device_fingerprint):
        return False
    return True


def create_user(
    email: str,
    password: str,
    *,
    name: str | None = None,
    referral_code: str | None = None,
    ip_address: str | None = None,
    device_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Create a user, wallet and (optionally) welcome bonus.

    Raises AuthError / DuplicateEmail / DisposableEmailError on bad input.
    """
    from .referral import (
        REFERRAL_SIGNUP_BONUS,
        _generate_code,
        lookup_referrer_id,
    )

    email = normalize_email(email)
    if not email or "@" not in email:
        raise AuthError("A valid email is required.")
    assert_not_disposable(email)
    if not password or len(password) < 6:
        raise AuthError("Password must be at least 6 characters.")

    password_hash = generate_password_hash(password)
    is_admin = 1 if is_bootstrap_admin_email(email) else 0
    # Bootstrap admin is treated as verified.
    is_verified = 1 if is_admin else 0
    referrer_id = lookup_referrer_id(referral_code)
    fingerprint = normalize_fingerprint(device_fingerprint)
    ip = (ip_address or "").strip()[:64] or None
    grant_welcome = should_grant_welcome_bonus(
        ip_address=ip, device_fingerprint=fingerprint
    )

    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)
        ).fetchone()
        if exists:
            raise DuplicateEmail("An account with this email already exists.")
        own_code = _generate_code(conn)
        cur = conn.execute(
            "INSERT INTO users "
            "(email, name, password_hash, is_admin, is_verified, "
            " referral_code, referrer_id, ip_address, device_fingerprint, "
            " welcome_bonus_granted) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                email,
                (name or "").strip() or None,
                password_hash,
                is_admin,
                is_verified,
                own_code,
                referrer_id,
                ip,
                fingerprint,
                1 if grant_welcome else 0,
            ),
        )
        user_id = int(cur.lastrowid)

    _wallet.ensure_wallet(user_id)
    if grant_welcome and WELCOME_BONUS > 0:
        _wallet.credit(
            user_id,
            WELCOME_BONUS,
            "welcome_bonus",
            meta={"ip": ip, "fingerprint": fingerprint},
        )
    if referrer_id is not None and REFERRAL_SIGNUP_BONUS > 0:
        # Referral signup bonus still applies (separate from welcome anti-abuse).
        _wallet.credit(
            user_id,
            REFERRAL_SIGNUP_BONUS,
            "referral_signup_bonus",
            ref_id=f"ref_signup_{user_id}",
            meta={"referrer_id": referrer_id, "code": (referral_code or "").strip().upper()},
        )
    return {
        "id": user_id,
        "email": email,
        "name": (name or "").strip() or None,
        "referral_code": own_code,
        "referrer_id": referrer_id,
        "is_verified": bool(is_verified),
        "welcome_bonus_granted": bool(grant_welcome),
        "avatar_file": None,
    }


def mark_email_verified(user_id: int, email: str | None = None) -> dict[str, Any]:
    """Mark the account verified and clear any pending OTP."""
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (int(user_id),)
        ).fetchone()
        if row is None:
            raise AuthError("User not found.")
        if email is not None and normalize_email(row["email"]) != normalize_email(email):
            raise AuthError("Verification does not match this account.")
        conn.execute(
            "UPDATE users SET is_verified = 1, "
            "verification_code = NULL, verification_code_expires = NULL "
            "WHERE id = ?",
            (int(user_id),),
        )
    try:
        g._economy_user = None
    except RuntimeError:
        pass
    user = get_user(user_id)
    if user is None:
        raise AuthError("User not found.")
    return user


def issue_verification_otp(user_id: int) -> str:
    """Create a fresh 6-digit OTP (15 min TTL) and persist it on the user row."""
    code = generate_otp_code()
    expires = datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES)
    expires_iso = expires.strftime("%Y-%m-%d %H:%M:%S")
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE id = ?", (int(user_id),)
        ).fetchone()
        if row is None:
            raise AuthError("User not found.")
        conn.execute(
            "UPDATE users SET verification_code = ?, verification_code_expires = ? "
            "WHERE id = ?",
            (code, expires_iso, int(user_id)),
        )
    try:
        g._economy_user = None
    except RuntimeError:
        pass
    return code


def _parse_utc_naive(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def verify_email_otp(user_id: int, code: str) -> dict[str, Any]:
    """Validate a submitted OTP and mark the user verified on success."""
    cleaned = re.sub(r"\D", "", (code or "").strip())
    if len(cleaned) != 6:
        raise AuthError("Enter the 6-digit code from your email.")

    with connect() as conn:
        row = conn.execute(
            "SELECT id, email, is_verified, verification_code, verification_code_expires "
            "FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
        if row is None:
            raise AuthError("User not found.")
        if bool(row["is_verified"]):
            return get_user(int(user_id))  # type: ignore[return-value]

        stored = (row["verification_code"] or "").strip()
        if not stored:
            raise AuthError("No verification code on file. Please request a new one.")
        if stored != cleaned:
            raise AuthError("Incorrect code. Please try again.")

        expires = _parse_utc_naive(row["verification_code_expires"])
        if expires is None or datetime.utcnow() > expires:
            raise AuthError("This code has expired. Please request a new one.")

        conn.execute(
            "UPDATE users SET is_verified = 1, "
            "verification_code = NULL, verification_code_expires = NULL "
            "WHERE id = ?",
            (int(user_id),),
        )

    try:
        g._economy_user = None
    except RuntimeError:
        pass
    user = get_user(user_id)
    if user is None:
        raise AuthError("User not found.")
    return user


def set_avatar_file(user_id: int, filename: str | None) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if row is None:
            raise AuthError("User not found.")
        conn.execute(
            "UPDATE users SET avatar_file = ? WHERE id = ?",
            ((filename or None), int(user_id)),
        )
    try:
        g._economy_user = None
    except RuntimeError:
        pass
    user = get_user(user_id)
    if user is None:
        raise AuthError("User not found.")
    return user


def verify_credentials(email: str, password: str) -> dict[str, Any] | None:
    email = normalize_email(email)
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    if row is None:
        return None
    if not check_password_hash(row["password_hash"], password or ""):
        return None
    return _row_to_user(row)


def get_user(user_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return _row_to_user(row)


def login_user(user_id: int) -> None:
    session[SESSION_KEY] = int(user_id)
    session.permanent = True


def logout_user() -> None:
    session.pop(SESSION_KEY, None)


def current_user() -> dict[str, Any] | None:
    """Return the logged-in user (cached per request via flask.g)."""
    uid = session.get(SESSION_KEY)
    if not uid:
        return None
    cached = getattr(g, "_economy_user", None)
    if cached and cached.get("id") == uid:
        return cached
    user = get_user(int(uid))
    if user is None:
        session.pop(SESSION_KEY, None)
        return None
    g._economy_user = user
    return user


def current_user_id() -> int | None:
    user = current_user()
    return int(user["id"]) if user else None


def update_profile(user_id: int, *, name: str | None = None) -> dict[str, Any]:
    """Update display name. Returns the refreshed user dict."""
    cleaned = (name or "").strip() or None
    with connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise AuthError("User not found.")
        conn.execute("UPDATE users SET name = ? WHERE id = ?", (cleaned, user_id))
    try:
        cached = getattr(g, "_economy_user", None)
        if cached and cached.get("id") == user_id:
            g._economy_user = None
    except RuntimeError:
        pass
    user = get_user(user_id)
    if user is None:
        raise AuthError("User not found.")
    return user


def change_password(
    user_id: int,
    *,
    current_password: str,
    new_password: str,
) -> None:
    """Change password after verifying the current one."""
    if not new_password or len(new_password) < 6:
        raise AuthError("New password must be at least 6 characters.")
    with connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise AuthError("User not found.")
        if not check_password_hash(row["password_hash"], current_password or ""):
            raise AuthError("Current password is incorrect.")
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), user_id),
        )


def is_admin(user: dict[str, Any] | None = None) -> bool:
    user = user if user is not None else current_user()
    return bool(user and user.get("is_admin"))


def admin_required(view: Callable) -> Callable:
    """Guard admin views. Requires login + is_admin flag."""

    @functools.wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        user = current_user()
        if user is None:
            if _wants_json():
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "AUTH_REQUIRED",
                            "message": "Please sign in to continue.",
                        }
                    ),
                    401,
                )
            return redirect(url_for("login", next=request.path))
        if not user.get("is_admin"):
            if _wants_json():
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "ADMIN_REQUIRED",
                            "message": "Admin access required.",
                        }
                    ),
                    403,
                )
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped


def _wants_json() -> bool:
    if request.path.startswith("/api/"):
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def _guest_page_preview_allowed() -> bool:
    """True for unsigned GET navigations to HTML pages (not APIs)."""
    if request.method != "GET":
        return False
    if request.path.startswith("/api/"):
        return False
    if _wants_json():
        return False
    return current_user() is None


# HTML paths where guests may browse the tool UI (modal on action).
GUEST_PREVIEW_PAGE_PATHS = frozenset(
    {
        "/",
        "/format-v2",
        "/assignment",
        "/assignments",
        "/humanizer",
        "/turnitin",
        "/workspace",
    }
)


def guest_preview_allowed_for_path(path: str) -> bool:
    normalized = (path or "").rstrip("/") or "/"
    if normalized not in GUEST_PREVIEW_PAGE_PATHS:
        return False
    return _guest_page_preview_allowed()


def login_required(
    view: Callable | None = None,
    *,
    allow_guest_preview: bool = False,
) -> Callable:
    """Guard a view. API paths get 401 JSON; pages redirect to /login.

    Pass ``allow_guest_preview=True`` only on whitelisted marketing/tool pages
    where guests should see the UI and hit the auth modal on action.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any):
            if current_user() is None:
                if allow_guest_preview and _guest_page_preview_allowed():
                    return fn(*args, **kwargs)
                if _wants_json():
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "AUTH_REQUIRED",
                                "message": "Please sign in to continue.",
                            }
                        ),
                        401,
                    )
                return redirect(url_for("login", next=request.path))
            return fn(*args, **kwargs)

        return wrapped

    if view is not None:
        return decorator(view)
    return decorator


def user_email_verified(user: dict[str, Any] | None) -> bool:
    """Strict check — only explicit True counts as verified."""
    if not user:
        return False
    return user.get("is_verified") is True


def email_verification_gate(*, allow_guest_preview: bool = False):
    """Return a Flask response if login/verify is required; else None."""
    user = current_user()
    if user is None:
        if allow_guest_preview and _guest_page_preview_allowed():
            return None
        if _wants_json():
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "AUTH_REQUIRED",
                        "message": "Please sign in to continue.",
                    }
                ),
                401,
            )
        return redirect(url_for("login", next=request.path))
    if not user_email_verified(user):
        if _wants_json():
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "EMAIL_NOT_VERIFIED",
                        "message": "Please verify your email before continuing.",
                    }
                ),
                403,
            )
        return redirect(url_for("verify_email_code"))
    return None


def email_verified_required(
    view: Callable | None = None,
    *,
    allow_guest_preview: bool = False,
) -> Callable:
    """Require login + verified email (Workspace and paid tools).

    ``allow_guest_preview=True`` lets unsigned guests open the HTML page only.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any):
            blocked = email_verification_gate(allow_guest_preview=allow_guest_preview)
            if blocked is not None:
                return blocked
            return fn(*args, **kwargs)

        return wrapped

    if view is not None:
        return decorator(view)
    return decorator
