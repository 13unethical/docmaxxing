"""Session-bound CSRF tokens for every state-changing request a browser can send with our cookie.

The token lives in the signed, HttpOnly session cookie and must come back in the
``X-CSRF-Token`` header (fetch/XHR) or the ``csrf_token`` form field (HTML forms). A cross-site
page can make the browser attach the cookie but cannot read the token, so it cannot forge the
second half. Pages get the token from ``<meta name="csrf-token">``; ``static/csrf.js`` attaches it
to same-origin requests and picks up the rotated value from the ``X-CSRF-Token`` response
header after login or logout.
"""

from __future__ import annotations

import hmac
import secrets
from typing import Any

from flask import g, jsonify, request, session

SESSION_KEY = "_csrf_token"
HEADER = "X-CSRF-Token"
FORM_FIELD = "csrf_token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_TOKEN_BYTES = 32
_MAX_TOKEN_LEN = 128

# Endpoints that never act on the browser's session cookie. Each one authenticates the
# caller some other way, checked inside the handler before anything changes.
EXEMPT_ENDPOINTS: dict[str, str] = {
    "api_paddle_webhook": "Paddle-Signature HMAC over the raw body (PADDLE_WEBHOOK_SECRET)",
    "api_lemon_squeezy_webhook": "X-Signature HMAC over the raw body (LEMON_SQUEEZY_WEBHOOK_SECRET)",
    "api_cryptomus_webhook": "Cryptomus body signature (payment key) plus optional source-IP allowlist",
    "api_telegram_webhook": "X-Telegram-Bot-Api-Secret-Token header must equal TELEGRAM_WEBHOOK_SECRET",
    "api_veil_ask": "Veil extension bearer token only; the session cookie is never read",
    "api_veil_revoke": "revokes the bearer token it is given; the session cookie is never read",
    "api_extension_humanize": "Veil extension bearer token (or JSON key) only; the session cookie is never read",
}


def _new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def get_token() -> str:
    """The current session's token, created on first use."""
    token = session.get(SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = _new_token()
        session[SESSION_KEY] = token
        g._csrf_issued = token
    return token


def page_token() -> str:
    """Token for templates; the page then carries a per-session secret and must not sit in a shared cache."""
    g._csrf_in_page = True
    return get_token()


def embedded_in_page() -> bool:
    return bool(g.get("_csrf_in_page"))


def rotate() -> str:
    """Replace the token (authentication boundary). Tokens copied from the old session stop working."""
    token = _new_token()
    session[SESSION_KEY] = token
    g._csrf_issued = token
    return token


def issued_token() -> str | None:
    """Token created or rotated during this request, if any (sent back in the response header)."""
    return g.get("_csrf_issued")


def _submitted_token() -> str:
    value = request.headers.get(HEADER)
    if not value and request.mimetype in ("application/x-www-form-urlencoded", "multipart/form-data"):
        value = request.form.get(FORM_FIELD)
    return value if isinstance(value, str) else ""


def token_valid() -> bool:
    expected = session.get(SESSION_KEY)
    submitted = _submitted_token()
    if not isinstance(expected, str) or not expected or not submitted:
        return False
    if len(submitted) > _MAX_TOKEN_LEN:
        return False
    return hmac.compare_digest(submitted.encode("utf-8"), expected.encode("utf-8"))


def cross_site_request() -> bool:
    """The browser says another site started this request (Sec-Fetch-Site; page scripts cannot set it).

    Defence in depth for admin endpoints: everything that changes state is POST and needs the
    CSRF token; this only also refuses cross-site requests to the read-only admin GETs.
    Clients without Fetch Metadata send no header and are not affected.
    """
    return (request.headers.get("Sec-Fetch-Site") or "").strip().lower() in ("cross-site", "same-site")


def requires_check() -> bool:
    if request.method in SAFE_METHODS:
        return False
    endpoint = request.endpoint
    if endpoint is None:
        return False  # 404/405: no handler will run
    return endpoint not in EXEMPT_ENDPOINTS


def rejection(wants_json: bool) -> Any:
    message = "Your session has expired. Refresh the page and try again."
    if wants_json:
        return jsonify({"success": False, "error": "CSRF_FAILED", "message": message}), 403
    return (
        f"<!doctype html><title>Session expired</title><p>{message}</p>",
        403,
        {"Content-Type": "text/html; charset=utf-8"},
    )
