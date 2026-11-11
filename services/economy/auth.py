"""Account creation, credentials and Flask session helpers.

Email + password auth backed by the economy SQLite DB. Passwords are hashed
with Werkzeug (ships with Flask). New accounts may receive a welcome credit
bonus subject to soft IP / device fingerprint anti-abuse limits.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import os
import re
import secrets
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
AUTH_SID_KEY = "auth_sid"
_FINGERPRINT_RE = re.compile(r"^[a-fA-F0-9]{16,128}$")


class AuthError(Exception):
    """Base auth error."""


class DuplicateEmail(AuthError):
    """Raised when registering an email that already exists."""


class EmailNotVerified(AuthError):
    """Raised when a verified email is required."""


class WrongPassword(AuthError):
    """Raised when the current password given to confirm a change is wrong."""


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
        "is_blocked": bool(row["is_blocked"]) if "is_blocked" in keys else False,
        "account_flag": row["account_flag"] if "account_flag" in keys else None,
        "password_set": bool(row["password_set"]) if "password_set" in keys else True,
    }


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_fingerprint(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text or not _FINGERPRINT_RE.match(text):
        return None
    return text.lower()


def client_ip_from_request() -> str | None:
    """Client IP for signup checks and audit logs (forwarding headers only from a trusted proxy)."""
    from services.free_humanize import client_ip

    return client_ip(request)


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
    # Every account starts as an unverified non-admin, whatever ADMIN_EMAIL says: admin is
    # granted only to a verified account (admin panel or scripts/grant_admin.py).
    is_admin = 0
    is_verified = 0
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

    from .activity_log import log_activity

    log_activity(
        "user.register",
        category="account",
        user_id=user_id,
        user_email=email,
        actor_id=user_id,
        summary=f"Registered {email}",
        details={
            "referrer_id": referrer_id,
            "welcome_bonus": bool(grant_welcome),
        },
        source_ref=f"users:{user_id}",
    )
    try:
        from flask import has_request_context, session as flask_session

        from services.product_analytics import record as record_product_event

        record_product_event(
            "registration_completed",
            user_id=user_id,
            tool="auth",
            session=flask_session if has_request_context() else None,
            dedupe_key=f"registration_completed:u:{user_id}",
        )
    except Exception:
        pass
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
            "verification_code = NULL, verification_code_expires = NULL, verification_attempts = 0 "
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


OTP_DEFAULT_MAX_ATTEMPTS = 5
_OTP_DIGEST_PREFIX = "h1$"
_OTP_WRONG = "Incorrect code. Please try again."
_OTP_EXPIRED = "This code has expired. Please request a new one."
_OTP_NONE = "No verification code on file. Please request a new one."
_OTP_EXHAUSTED = "Too many incorrect codes. Please request a new one."


def otp_max_attempts() -> int:
    from services.rate_limit import env_limit

    return env_limit("OTP_MAX_ATTEMPTS", OTP_DEFAULT_MAX_ATTEMPTS)


def _otp_digest(user_id: int, code: str) -> str:
    """Keyed hash of a code for one account; the plaintext code is never stored."""
    key = (os.environ.get("SECRET_KEY") or "").encode("utf-8") or b"docmaxxing-otp"
    mac = hmac.new(key, f"otp:{int(user_id)}:{code}".encode("utf-8"), hashlib.sha256)
    return _OTP_DIGEST_PREFIX + mac.hexdigest()


def _otp_matches(user_id: int, stored: str, code: str) -> bool:
    if stored.startswith(_OTP_DIGEST_PREFIX):
        return hmac.compare_digest(stored, _otp_digest(user_id, code))
    # Plaintext codes written before hashing; they expire within OTP_TTL_MINUTES of deploy.
    return len(stored) == len(code) and hmac.compare_digest(stored, code)


def issue_verification_otp(user_id: int) -> str:
    """Create a fresh 6-digit OTP (15 min TTL); it replaces any earlier code and its attempts.

    Only a keyed hash is stored. The plaintext is returned once, for the email.
    """
    code = generate_otp_code()
    expires = datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES)
    expires_iso = expires.strftime("%Y-%m-%d %H:%M:%S")
    with connect() as conn:
        cur = conn.execute(
            "UPDATE users SET verification_code = ?, verification_code_expires = ?, "
            "verification_attempts = 0 WHERE id = ?",
            (_otp_digest(int(user_id), code), expires_iso, int(user_id)),
        )
        if cur.rowcount != 1:
            raise AuthError("User not found.")
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


def _check_and_consume_otp(user_id: int, code: str) -> str:
    """One locked read-check-write. Returns 'consumed', 'already', or a public error message.

    Wrong guesses are counted on the account row (shared by every worker); the code is erased
    when it expires or after ``OTP_MAX_ATTEMPTS`` wrong guesses. Only the request whose update
    clears the code it matched verifies the account, so a code works once.
    """
    max_attempts = otp_max_attempts()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT is_verified, verification_code, verification_code_expires, verification_attempts "
            "FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
        if row is None:
            return _OTP_NONE
        if bool(row["is_verified"]):
            return "already"
        stored = (row["verification_code"] or "").strip()
        if not stored:
            return _OTP_NONE
        expires = _parse_utc_naive(row["verification_code_expires"])
        if expires is None or datetime.utcnow() > expires:
            conn.execute(
                "UPDATE users SET verification_code = NULL, verification_code_expires = NULL "
                "WHERE id = ? AND verification_code = ?",
                (int(user_id), stored),
            )
            return _OTP_EXPIRED
        attempts = int(row["verification_attempts"] or 0)
        if attempts >= max_attempts:
            conn.execute(
                "UPDATE users SET verification_code = NULL, verification_code_expires = NULL "
                "WHERE id = ? AND verification_code = ?",
                (int(user_id), stored),
            )
            return _OTP_EXHAUSTED
        if not _otp_matches(int(user_id), stored, code):
            attempts += 1
            if attempts >= max_attempts:
                conn.execute(
                    "UPDATE users SET verification_attempts = ?, verification_code = NULL, "
                    "verification_code_expires = NULL WHERE id = ? AND verification_code = ?",
                    (attempts, int(user_id), stored),
                )
                return _OTP_EXHAUSTED
            conn.execute(
                "UPDATE users SET verification_attempts = ? WHERE id = ? AND verification_code = ?",
                (attempts, int(user_id), stored),
            )
            return _OTP_WRONG
        cur = conn.execute(
            "UPDATE users SET is_verified = 1, verification_code = NULL, "
            "verification_code_expires = NULL, verification_attempts = 0 "
            "WHERE id = ? AND is_verified = 0 AND verification_code = ?",
            (int(user_id), stored),
        )
        return "consumed" if cur.rowcount == 1 else _OTP_NONE


def verify_email_otp(user_id: int, code: str) -> dict[str, Any]:
    """Validate a submitted OTP and mark the user verified on success."""
    cleaned = re.sub(r"\D", "", (code or "").strip())
    if len(cleaned) != 6:
        raise AuthError("Enter the 6-digit code from your email.")

    outcome = _check_and_consume_otp(int(user_id), cleaned)
    if outcome == "already":
        user = get_user(int(user_id))
        if user is None:
            raise AuthError(_OTP_NONE)
        return user
    if outcome != "consumed":
        raise AuthError(outcome)

    try:
        g._economy_user = None
    except RuntimeError:
        pass
    user = get_user(user_id)
    if user is None:
        raise AuthError("User not found.")
    from .activity_log import log_activity

    log_activity(
        "user.email_verified",
        category="account",
        user_id=int(user_id),
        user_email=user.get("email"),
        actor_id=int(user_id),
        summary=f"Verified email {user.get('email')}",
    )
    try:
        from flask import has_request_context, session as flask_session

        from services.product_analytics import record as record_product_event

        record_product_event(
            "email_verified",
            user_id=int(user_id),
            tool="auth",
            session=flask_session if has_request_context() else None,
            dedupe_key=f"email_verified:u:{int(user_id)}",
        )
    except Exception:
        pass
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


_DUMMY_PASSWORD_HASH: list[str] = []


def _dummy_password_hash() -> str:
    if not _DUMMY_PASSWORD_HASH:
        _DUMMY_PASSWORD_HASH.append(generate_password_hash(secrets.token_urlsafe(16)))
    return _DUMMY_PASSWORD_HASH[0]


def verify_credentials(email: str, password: str) -> dict[str, Any] | None:
    """The account for a correct email + password, else None (same work for unknown emails)."""
    email = normalize_email(email)
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    if row is None:
        check_password_hash(_dummy_password_hash(), password or "")
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


def _sid_hash(sid: str) -> str:
    return hashlib.sha256(sid.encode("utf-8")).hexdigest()


# Rows idle longer than the 30-day session cookie lifetime (plus the last_seen refresh
# interval) can no longer match a live cookie; dropping a row only ever signs someone out.
_SESSION_IDLE_DAYS = 31
_SESSION_TOUCH_SECONDS = 3600
_MAX_SESSIONS_PER_USER = 50


def register_session(user_id: int) -> str:
    """Record a new sign-in server-side and return its id (only its hash is stored)."""
    sid = secrets.token_urlsafe(32)
    uid = int(user_id)
    with connect() as conn:
        conn.execute(
            "INSERT INTO auth_sessions (sid_hash, user_id) VALUES (?, ?)", (_sid_hash(sid), uid)
        )
        conn.execute(
            "DELETE FROM auth_sessions WHERE last_seen < datetime('now', ?)",
            (f"-{_SESSION_IDLE_DAYS} days",),
        )
        conn.execute(
            "DELETE FROM auth_sessions WHERE user_id = ? AND sid_hash NOT IN ("
            " SELECT sid_hash FROM auth_sessions WHERE user_id = ?"
            " ORDER BY last_seen DESC, created_at DESC LIMIT ?)",
            (uid, uid, _MAX_SESSIONS_PER_USER),
        )
    return sid


def _session_active(sid: str, user_id: int) -> bool:
    """True only while the server still holds this sign-in for this account."""
    with connect() as conn:
        row = conn.execute(
            "SELECT user_id, "
            " (julianday('now') - julianday(last_seen)) * 86400 AS idle_seconds "
            "FROM auth_sessions WHERE sid_hash = ?",
            (_sid_hash(sid),),
        ).fetchone()
        if row is None or int(row["user_id"]) != int(user_id):
            return False
        idle = float(row["idle_seconds"] or 0)
        if idle > _SESSION_IDLE_DAYS * 86400:
            return False
        if idle > _SESSION_TOUCH_SECONDS:
            conn.execute(
                "UPDATE auth_sessions SET last_seen = datetime('now') WHERE sid_hash = ?",
                (_sid_hash(sid),),
            )
    return True


def _end_session(sid: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE sid_hash = ?", (_sid_hash(sid),))


def end_all_sessions(user_id: int) -> None:
    """Sign the account out everywhere (every copy of every session cookie and the extension)."""
    with connect() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (int(user_id),))
        conn.execute(
            "UPDATE extension_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0", (int(user_id),)
        )


def _start_fresh_session() -> None:
    """Drop everything the previous (possibly attacker-prepared) session carried."""
    from services import csrf

    session.clear()
    csrf.rotate()


def login_user(user_id: int) -> None:
    previous = session.get(AUTH_SID_KEY)
    if isinstance(previous, str) and previous:
        _end_session(previous)
    _start_fresh_session()
    session[SESSION_KEY] = int(user_id)
    session[AUTH_SID_KEY] = register_session(int(user_id))
    session.permanent = True
    try:
        g._economy_user = None
    except RuntimeError:
        pass


def log_login_attempt(email: str, user: dict[str, Any] | None) -> None:
    from .activity_log import log_activity

    if user is None:
        log_activity(
            "auth.login_failed",
            category="auth",
            user_email=normalize_email(email) or None,
            summary=f"Failed login for {normalize_email(email) or '(empty)'}",
            status_code=401,
        )
        return
    log_activity(
        "auth.login",
        category="auth",
        user_id=int(user["id"]),
        user_email=user.get("email"),
        actor_id=int(user["id"]),
        summary=f"Signed in {user.get('email')}",
    )


def logout_user() -> None:
    uid = session.get(SESSION_KEY)
    if uid:
        from .activity_log import log_activity

        log_activity(
            "auth.logout",
            category="auth",
            user_id=int(uid),
            actor_id=int(uid),
            summary="Signed out",
        )
    sid = session.get(AUTH_SID_KEY)
    if isinstance(sid, str) and sid:
        _end_session(sid)
    g._economy_user = None
    _start_fresh_session()


def current_user() -> dict[str, Any] | None:
    """Return the logged-in user (cached per request via flask.g).

    The cookie authenticates only while its sign-in id is registered server-side for the
    same account. Cookies without one (issued before sign-in ids existed), signed-out,
    password-changed or unknown ids are cleared and the visitor must sign in again.
    The account row is re-read every request, so blocking, demotion or a lost email
    verification apply at once.
    """
    uid = session.get(SESSION_KEY)
    if not uid:
        return None
    cached = getattr(g, "_economy_user", None)
    if cached and cached.get("id") == uid:
        return cached
    sid = session.get(AUTH_SID_KEY)
    try:
        uid_int = int(uid)
    except (TypeError, ValueError):
        uid_int = None
    if uid_int is None or not isinstance(sid, str) or not sid or not _session_active(sid, uid_int):
        _start_fresh_session()
        g._economy_user = None
        return None
    user = get_user(uid_int)
    if user is None or user.get("is_blocked"):
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
    allow_set_without_current: bool = False,
) -> None:
    """Change password after verifying the current one.

    Every session of the account ends (database trigger on ``password_hash``); the route
    signs the caller back in with a fresh session.

    OAuth-only accounts (``password_set = 0``) may set a first password without the
    unusable current hash when ``allow_set_without_current`` is true.
    """
    if not new_password or len(new_password) < 6:
        raise AuthError("New password must be at least 6 characters.")
    with connect() as conn:
        row = conn.execute(
            "SELECT password_hash, password_set FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise AuthError("User not found.")
        keys = row.keys()
        has_password = bool(row["password_set"]) if "password_set" in keys else True
        if has_password or not allow_set_without_current:
            if not check_password_hash(row["password_hash"], current_password or ""):
                raise WrongPassword("Current password is incorrect.")
        conn.execute(
            "UPDATE users SET password_hash = ?, password_set = 1 WHERE id = ?",
            (generate_password_hash(new_password), user_id),
        )


def auth_meta(user_id: int) -> dict[str, Any]:
    """Providers linked to the account and whether a usable password exists."""
    from .oauth_login import linked_providers

    user = get_user(user_id)
    return {
        "hasPassword": bool(user.get("password_set", True)) if user else True,
        "linkedProviders": linked_providers(int(user_id)),
    }


def is_admin(user: dict[str, Any] | None = None) -> bool:
    """The one admin check: admin flag and a verified email, both from the account row."""
    user = user if user is not None else current_user()
    return bool(user and user.get("is_admin") is True and user_email_verified(user))


def admin_required(view: Callable) -> Callable:
    """Guard admin views. Requires login + :func:`is_admin`."""

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
        from services import csrf

        cross_site_api = request.path.startswith("/api/") and csrf.cross_site_request()
        if cross_site_api or not is_admin(user):
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

    wrapped.admin_guard = "admin_required"
    return wrapped


def _wants_json() -> bool:
    if request.path.startswith("/api/"):
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def _guest_page_preview_allowed() -> bool:
    """True for unsigned GET/HEAD navigations to HTML pages (not APIs)."""
    if request.method not in ("GET", "HEAD"):
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
        "/check",
        "/veil",
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
