"""Account creation, credentials and Flask session helpers.

Email + password auth backed by the economy SQLite DB. Passwords are hashed
with Werkzeug (ships with Flask). New accounts receive a welcome coin bonus.
"""

from __future__ import annotations

import functools
import os
import sqlite3
from typing import Any, Callable

from flask import g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import connect
from .pricing import WELCOME_BONUS
from .wallet import WalletService

_wallet = WalletService()

SESSION_KEY = "user_id"


class AuthError(Exception):
    """Base auth error."""


class DuplicateEmail(AuthError):
    """Raised when registering an email that already exists."""


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


def create_user(
    email: str,
    password: str,
    *,
    name: str | None = None,
    referral_code: str | None = None,
) -> dict[str, Any]:
    """Create a user, wallet and welcome bonus. Raises on bad input/dupes."""
    from .referral import (
        REFERRAL_SIGNUP_BONUS,
        _generate_code,
        lookup_referrer_id,
    )

    email = normalize_email(email)
    if not email or "@" not in email:
        raise AuthError("A valid email is required.")
    if not password or len(password) < 6:
        raise AuthError("Password must be at least 6 characters.")

    password_hash = generate_password_hash(password)
    is_admin = 1 if is_bootstrap_admin_email(email) else 0
    referrer_id = lookup_referrer_id(referral_code)

    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)
        ).fetchone()
        if exists:
            raise DuplicateEmail("An account with this email already exists.")
        own_code = _generate_code(conn)
        # Prevent self-referral via own code (impossible for new user) and ignore invalid codes silently.
        if referrer_id is not None:
            # referrer_id already validated by lookup
            pass
        cur = conn.execute(
            "INSERT INTO users "
            "(email, name, password_hash, is_admin, referral_code, referrer_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                email,
                (name or "").strip() or None,
                password_hash,
                is_admin,
                own_code,
                referrer_id,
            ),
        )
        user_id = int(cur.lastrowid)

    _wallet.ensure_wallet(user_id)
    if WELCOME_BONUS > 0:
        _wallet.credit(user_id, WELCOME_BONUS, "welcome_bonus")
    if referrer_id is not None and REFERRAL_SIGNUP_BONUS > 0:
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
    }


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
    # Bust request cache if present (inside a Flask request).
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


def login_required(view: Callable) -> Callable:
    """Guard a view. API paths get 401 JSON; pages redirect to /login."""

    @functools.wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if current_user() is None:
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
        return view(*args, **kwargs)

    return wrapped
