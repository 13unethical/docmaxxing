"""Patch 3G: CSRF tokens, session cookies, verified-admin authorization and proxy IP trust.

CSRF tests use Flask's plain ``FlaskClient``; the conftest client (which sends the session token
like the real pages do) would hide a missing check. Handlers are replaced by spies, or watched
with ``sys.setprofile``, so a rejected request provably never reached the view.
"""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import logging
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from services import csrf, free_humanize
from services.economy import auth as economy_auth
from services.economy import db as economy_db
from tests.test_security_free_ai_quota import _prose, provider  # noqa: F401
from tests.test_security_paid_pipelines import economy  # noqa: F401

HDR = csrf.HEADER
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("TRUSTED_PROXIES", "INTERNAL_TOOLS_ENABLED", "TELEGRAM_WEBHOOK_SECRET", "PADDLE_WEBHOOK_SECRET",
                 "LEMON_SQUEEZY_WEBHOOK_SECRET", "DEV_INSECURE_COOKIES"):
        monkeypatch.delenv(name, raising=False)


def _app() -> Flask:
    from app import app

    app.config["TESTING"] = True
    return app


def _raw() -> FlaskClient:
    app = _app()
    return FlaskClient(app, app.response_class, use_cookies=True)


def _user(email, *, admin=False, verified=True):
    user = economy_auth.create_user(email, "secret123")
    with economy_db.connect() as conn:
        conn.execute(
            "UPDATE users SET is_admin = ?, is_verified = ? WHERE id = ?",
            (1 if admin else 0, 1 if verified else 0, user["id"]),
        )
    return economy_auth.get_user(user["id"])


def _signed_in(client, user, *, legacy=False):
    """``legacy=True`` builds a cookie as issued before sign-in ids existed (no ``auth_sid``)."""
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
        if not legacy:
            sess[economy_auth.AUTH_SID_KEY] = economy_auth.register_session(user["id"])
    return client


def _token(client) -> str:
    res = client.get("/api/csrf-token")
    assert res.status_code == 200 and res.headers["Cache-Control"] == "no-store"
    return res.get_json()["csrf_token"]


def _login(client, email, password="secret123"):
    res = client.post("/api/auth/login", json={"email": email, "password": password}, headers={HDR: _token(client)})
    assert res.status_code == 200, res.get_data(as_text=True)
    return res


def _authenticated(client) -> bool:
    return client.get("/api/economy/balance").get_json()["authenticated"]


def _cookie_name() -> str:
    return _app().config["SESSION_COOKIE_NAME"]


def _session_cookie(client) -> str | None:
    cookie = client.get_cookie(_cookie_name())
    return cookie.value if cookie else None


def _session_set_cookie(res) -> str:
    name = _cookie_name()
    found = [h for h in res.headers.getlist("Set-Cookie") if h.startswith(name + "=")]
    assert found, res.headers
    return found[-1]


def _csrf_rejected(res) -> bool:
    if res.status_code != 403:
        return False
    if res.is_json:
        return res.get_json().get("error") == "CSRF_FAILED"
    return "Session expired" in res.get_data(as_text=True)


class Spy:
    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return {"spy": True}


def _spy(monkeypatch, endpoint) -> Spy:
    spy = Spy()
    monkeypatch.setitem(_app().view_functions, endpoint, spy)
    return spy


def _spy_once(monkeypatch, spies: dict, endpoint) -> Spy:
    if endpoint not in spies:
        spies[endpoint] = _spy(monkeypatch, endpoint)
    return spies[endpoint]


def _url(rule) -> str:
    values = {}
    for arg in rule.arguments:
        kind = type(rule._converters[arg]).__name__
        values[arg] = 1 if kind in ("IntegerConverter", "NumberConverter", "FloatConverter") else "x"
    built = rule.build(values, append_unknown=False)
    return built[1] if isinstance(built, tuple) else built


def _unsafe_rules():
    for rule in _app().url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        for method in sorted((rule.methods or set()) - csrf.SAFE_METHODS):
            yield rule, method


class _Entered:
    """Records whether a function's own code object starts executing (sys.setprofile)."""

    def __init__(self, func):
        self.code = inspect.unwrap(func).__code__
        self.hit = False

    def __enter__(self):
        self._prev = sys.getprofile()

        def hook(frame, event, arg):
            if event == "call" and frame.f_code is self.code:
                self.hit = True

        sys.setprofile(hook)
        return self

    def __exit__(self, *exc):
        sys.setprofile(self._prev)
        return False


# ------------------------------------------------------------------ 1-4, 18. token checks before the view


def test_every_cookie_reachable_mutation_rejects_bad_tokens_before_the_view(economy, monkeypatch):
    victim = _user("victim@example.com")
    client = _signed_in(_raw(), victim)
    own = _token(client)
    foreign = _token(_raw())
    assert foreign != own

    attempts = [
        {},
        {HDR: ""},
        {HDR: "x" * 43},
        {HDR: foreign},
        {HDR: own + "A"},
        {HDR: own[:-1]},
        {HDR: "A" * 5000},
        {"X-Requested-With": "XMLHttpRequest", "Origin": "http://localhost", "Referer": "http://localhost/"},
        {"X-CSRFToken": own, "X-XSRF-TOKEN": own, "Cookie-Token": own},
    ]
    spies: dict[str, Spy] = {}
    checked = set()
    for rule, method in _unsafe_rules():
        if rule.endpoint in csrf.EXEMPT_ENDPOINTS:
            continue
        _spy_once(monkeypatch, spies, rule.endpoint)
        url = _url(rule)
        for headers in attempts:
            res = client.open(url, method=method, headers=headers, json={"csrf_token": own})
            assert _csrf_rejected(res), (method, url, headers, res.status_code)
        assert _csrf_rejected(client.open(url, method=method, data={"csrf_token": foreign}))
        assert _csrf_rejected(client.open(f"{url}?csrf_token={own}", method=method, data={"x": "1"}))
        checked.add((rule.rule, method))

    assert len(checked) >= 120
    assert all(_app().view_functions[e] is s for e, s in spies.items())
    assert sum(s.calls for s in spies.values()) == 0


def test_the_sessions_own_token_reaches_every_view(economy, monkeypatch):
    client = _signed_in(_raw(), _user("member@example.com"))
    own = _token(client)
    spies: dict[str, Spy] = {}
    for rule, method in _unsafe_rules():
        if rule.endpoint in csrf.EXEMPT_ENDPOINTS:
            continue
        spy = _spy_once(monkeypatch, spies, rule.endpoint)
        before = spy.calls
        res = client.open(_url(rule), method=method, headers={HDR: own}, json={})
        assert res.status_code == 200 and spy.calls == before + 1, (method, rule.rule, res.status_code)
        form = client.open(_url(rule), method=method, data={csrf.FORM_FIELD: own})
        assert form.status_code == 200 and spy.calls == before + 2, (method, rule.rule)


class _Records(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def test_tokens_are_random_session_bound_and_never_logged(economy):
    tokens = {_token(_raw()) for _ in range(20)}
    assert len(tokens) == 20 and all(len(t) >= 43 for t in tokens)

    client = _raw()
    token = _token(client)
    assert _token(client) == token  # stable within a session
    other = _raw()
    own = _token(other)
    records = _Records()
    loggers = (logging.getLogger(), _app().logger)
    for logger in loggers:
        logger.addHandler(records)
    try:
        res = other.post("/api/contact", json={"message": "hi"}, headers={HDR: token})
    finally:
        for logger in loggers:
            logger.removeHandler(records)
    assert _csrf_rejected(res)
    body = res.get_data(as_text=True)
    assert token not in body and own not in body
    assert any("csrf rejected" in line for line in records.lines)
    assert not any(token in line or own in line for line in records.lines)


def test_exemptions_are_exactly_the_independently_authenticated_endpoints():
    assert set(csrf.EXEMPT_ENDPOINTS) == {
        "api_paddle_webhook",
        "api_lemon_squeezy_webhook",
        "api_cryptomus_webhook",
        "api_telegram_webhook",
        "api_veil_ask",
        "api_veil_revoke",
        "api_extension_humanize",
    }
    app = _app()
    for endpoint in csrf.EXEMPT_ENDPOINTS:
        assert endpoint in app.view_functions, endpoint
    # No prefix-based shortcut: same-prefix routes are still checked.
    for endpoint in ("api_gumroad_webhook", "api_veil_unlock", "api_veil_email_link", "api_payments_create",
                     "api_free_ai_detector", "api_economy_topup"):
        assert endpoint not in csrf.EXEMPT_ENDPOINTS


def test_no_path_tricks_bypass_the_check(economy, monkeypatch):
    client = _signed_in(_raw(), _user("tricks@example.com"))
    _token(client)
    spy = _spy(monkeypatch, "api_account_profile")
    for path in (
        "/api/account/profile",
        "/api/account/profile?next=/api/webhooks/paddle",
        "/api/account/profile?endpoint=api_paddle_webhook",
        "/api/account/profile#/api/webhooks/paddle",
    ):
        assert _csrf_rejected(client.post(path, json={"name": "pwned"}, headers={"Paddle-Signature": "ts=1;h1=0"}))
    for path in ("/api/webhooks/paddle/../../api/account/profile", "//api/account/profile", "/api/account/profile/"):
        res = client.post(path, json={"name": "pwned"})
        assert res.status_code in (308, 403, 404, 405) and not (200 <= res.status_code < 300)
    # Method override headers don't turn a POST into a safe method.
    res = client.post("/api/account/profile", json={}, headers={"X-HTTP-Method-Override": "GET"})
    assert _csrf_rejected(res)
    assert spy.calls == 0


# ------------------------------------------------------------------ 5-7. authentication boundaries


def test_login_rotates_token_and_drops_pre_login_state(economy):
    _user("alice@example.com")
    client = _raw()
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "attacker-planted-token-value-0123456789abcdef"
        sess["attacker_key"] = "fixation"
        sess["guest_humanize_used"] = True
    planted_cookie = _session_cookie(client)

    res = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "secret123"},
        headers={HDR: "attacker-planted-token-value-0123456789abcdef"},
    )
    assert res.status_code == 200
    rotated = res.headers[HDR]
    assert rotated and rotated != "attacker-planted-token-value-0123456789abcdef"
    assert res.headers["Cache-Control"] == "no-store"
    assert _session_cookie(client) != planted_cookie
    with client.session_transaction() as sess:
        assert "attacker_key" not in sess and "guest_humanize_used" not in sess
        assert sess["_csrf_token"] == rotated
        first_sid = sess[economy_auth.AUTH_SID_KEY]

    assert _csrf_rejected(client.post("/api/account/profile", json={"name": "x"},
                                      headers={HDR: "attacker-planted-token-value-0123456789abcdef"}))
    assert client.post("/api/account/profile", json={"name": "Alice"}, headers={HDR: rotated}).status_code == 200

    client.post("/api/auth/logout", headers={HDR: rotated})
    _login(client, "alice@example.com")
    with client.session_transaction() as sess:
        assert sess[economy_auth.AUTH_SID_KEY] != first_sid


def test_login_csrf_is_blocked_for_json_and_form_login(economy, monkeypatch):
    _user("victim@example.com")
    attempts = []
    real = economy_auth.verify_credentials
    monkeypatch.setattr(economy_auth, "verify_credentials", lambda *a, **k: attempts.append(a) or real(*a, **k))

    client = _raw()
    assert _csrf_rejected(client.post("/api/auth/login", json={"email": "victim@example.com", "password": "secret123"}))
    res = client.post("/login", data={"email": "victim@example.com", "password": "secret123"})
    assert _csrf_rejected(res) and "javascript:" not in res.get_data(as_text=True)
    assert attempts == [] and not _authenticated(client)

    page = client.get("/login")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    token = _token(client)
    assert f'name="csrf_token" value="{token}"' in html and f'name="csrf-token" content="{token}"' in html
    ok = client.post("/login", data={"email": "victim@example.com", "password": "secret123", "csrf_token": token})
    assert ok.status_code == 302 and _authenticated(client)
    assert ok.headers[HDR] != token


def test_logout_requires_a_token(economy):
    _user("bob@example.com")
    client = _raw()
    _login(client, "bob@example.com")
    for path in ("/logout", "/api/auth/logout"):
        assert _csrf_rejected(client.post(path))
        assert _authenticated(client)
    token = _token(client)
    assert client.post("/logout", data={"csrf_token": token}).status_code == 302
    assert not _authenticated(client)


# ------------------------------------------------------------------ 8-14. sensitive categories, spies on the real routes

CATEGORIES = {
    "registration and account": ["register", "api_auth_register", "verify_email_code", "verify_email_resend", "account",
                                 "api_account_profile", "api_account_password", "api_upload_avatar"],
    "payments, refunds and wallet": ["api_economy_checkout", "api_economy_topup", "api_payments_create",
                                     "api_assignment_project_confirm_payment", "api_assignment_project_refund_failed",
                                     "api_admin_assignment_refund", "api_referral_convert", "api_referral_withdraw",
                                     "api_gumroad_webhook"],
    "assignment projects": ["api_assignment_project_create", "api_assignment_project_update_brief",
                            "api_assignment_stage_run", "api_assignment_writer_start", "api_assignment_project_restore_draft"],
    "uploads and documents": ["api_assignment_project_upload", "api_assignment_project_add_file", "api_extract_document",
                              "format_document", "api_workspace_export", "api_turnitin_delete"],
    "AI and paid generation": ["api_humanizer_run", "api_humanizer_session_create", "api_ai_detection_session_create",
                               "api_presentation_generate", "api_turnitin_check", "api_writer_session_create"],
    "admin mutations": ["api_admin_set_balance", "api_admin_set_role", "api_admin_delete_user", "api_admin_panel_credits",
                        "api_admin_site_settings", "api_admin_withdrawal_approve", "api_browser_restart"],
    "guest mutations": ["api_free_ai_detector", "api_structure_recovery", "api_check_document", "preview_formatted",
                        "parse_requirements_view", "api_extract_requirements", "api_contact", "api_feedback"],
}


@pytest.mark.parametrize("category", sorted(CATEGORIES))
def test_sensitive_categories_need_the_token(economy, monkeypatch, category):
    app = _app()
    slug = category.split()[0].lower()
    guest = _raw()
    member = _signed_in(_raw(), _user(f"member-{slug}@example.com"))
    admin = _signed_in(_raw(), _user(f"admin-{slug}@example.com", admin=True))
    for endpoint in CATEGORIES[category]:
        assert endpoint in app.view_functions, endpoint
        rules = [r for r in app.url_map.iter_rules() if r.endpoint == endpoint]
        spy = _spy(monkeypatch, endpoint)
        for rule in rules:
            for method in sorted((rule.methods or set()) - csrf.SAFE_METHODS):
                for client in (guest, member, admin):
                    assert _csrf_rejected(client.open(_url(rule), method=method, json={})), (endpoint, method)
        assert spy.calls == 0, endpoint


def test_guests_get_a_token_and_can_use_guest_tools(economy, monkeypatch):
    spy = _spy(monkeypatch, "api_free_ai_detector")
    guest = _raw()
    assert _csrf_rejected(guest.post("/api/detector/free", json={"text": "hello"}))
    page = guest.get("/")
    token = page.headers.get(HDR) or _token(guest)
    assert guest.post("/api/detector/free", json={"text": "hello"}, headers={HDR: token}).status_code == 200
    assert spy.calls == 1


# ------------------------------------------------------------------ 15. read-only requests need nothing


def test_safe_methods_never_need_a_token(economy):
    client = _signed_in(_raw(), _user("reader@example.com"))
    for path in ("/api/csrf-token", "/api/economy/balance", "/login", "/pricing", "/robots.txt"):
        for method in ("GET", "HEAD", "OPTIONS"):
            res = client.open(path, method=method)
            assert not _csrf_rejected(res), (method, path)
            assert res.status_code < 500
    assert client.get("/api/economy/balance").get_json()["authenticated"] is True


# ------------------------------------------------------------------ 16-17. signed webhooks keep working


def _paddle_sig(raw: bytes, secret: str, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    return f"ts={ts};h1=" + hmac.new(secret.encode(), f"{ts}:{raw.decode()}".encode(), hashlib.sha256).hexdigest()


def test_signed_webhooks_work_without_a_token_and_forged_ones_fail(economy, monkeypatch):
    import app as app_mod

    fulfilled = []
    monkeypatch.setattr(app_mod, "handle_webhook_event", lambda event: fulfilled.append(event) or {"stub": True})
    monkeypatch.setenv("PADDLE_WEBHOOK_SECRET", "paddle-test-secret")
    monkeypatch.setenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "lemon-test-secret")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "tg-test-secret")
    monkeypatch.setenv("CRYPTOMUS_API_KEY", "test_payment_api_key")
    monkeypatch.setenv("CRYPTOMUS_WEBHOOK_IP_CHECK", "0")

    # A logged-in browser cookie on the request must not matter either way.
    client = _signed_in(_raw(), _user("payer@example.com"))
    raw = json.dumps({"event_type": "transaction.completed", "data": {"id": "txn_1"}}).encode()

    ok = client.post("/api/webhooks/paddle", data=raw, content_type="application/json",
                     headers={"Paddle-Signature": _paddle_sig(raw, "paddle-test-secret")})
    assert ok.status_code == 200 and ok.get_json()["stub"] is True and len(fulfilled) == 1
    for bad in (_paddle_sig(raw, "wrong-secret"), _paddle_sig(raw, "paddle-test-secret", ts=1), "", "ts=1;h1=00"):
        res = client.post("/api/webhooks/paddle", data=raw, content_type="application/json",
                          headers={"Paddle-Signature": bad})
        assert res.status_code == 400 and res.get_json()["error"] == "invalid_signature"
    assert len(fulfilled) == 1

    lemon = client.post("/api/webhooks/lemon-squeezy", data=raw, content_type="application/json",
                        headers={"X-Signature": "nope"})
    assert lemon.status_code == 403 and not _csrf_rejected(lemon)

    update = {"message": {"text": "hi", "chat": {"id": 1}}}
    assert client.post("/api/telegram-webhook", json=update).status_code == 401
    assert client.post("/api/telegram-webhook", json=update,
                       headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}).status_code == 401
    assert client.post("/api/telegram-webhook", json=update,
                       headers={"X-Telegram-Bot-Api-Secret-Token": "tg-test-secret"}).status_code == 200
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET")
    assert client.post("/api/telegram-webhook?secret=", json=update).status_code == 401

    from services.economy.cryptomus_gateway import cryptomus_json_dumps, cryptomus_sign

    body = {"order_id": "dm_999_nope", "status": "paid", "is_final": True, "uuid": "u-1"}
    forged = client.post("/api/payments/cryptomus/webhook", json={**body, "sign": "0" * 32})
    assert forged.status_code == 400 and forged.get_json()["error"] == "invalid_signature"
    signed = {**body, "sign": cryptomus_sign(cryptomus_json_dumps(body), api_key="test_payment_api_key")}
    accepted = client.post("/api/payments/cryptomus/webhook", data=json.dumps(signed), content_type="application/json")
    assert accepted.status_code == 200 and not _csrf_rejected(accepted)


# ------------------------------------------------------------------ 19-24. session cookie


def test_session_cookie_flags_on_real_responses(economy):
    _user("cookie@example.com")
    client = _raw()
    header = _session_set_cookie(client.get("/api/csrf-token"))
    login = _login(client, "cookie@example.com")
    for header in (header, _session_set_cookie(login)):
        parts = [p.strip().lower() for p in header.split(";")]
        assert "secure" in parts
        assert "httponly" in parts
        assert "samesite=lax" in parts
        assert "path=/" in parts
        assert not any(p.startswith("domain=") for p in parts)


def test_pages_carrying_a_token_stay_out_of_shared_caches(economy):
    client = _raw()
    first = client.get("/login")
    assert first.status_code == 200 and first.headers["Cache-Control"] == "no-store"
    again = client.get("/login")
    assert again.status_code == 200 and HDR not in again.headers
    assert "private" in again.headers["Cache-Control"]
    assert "public" not in again.headers.get("Cache-Control", "")
    assert client.get("/robots.txt").headers.get("Cache-Control", "") != "private, no-cache"


def test_production_refuses_insecure_cookie_config(monkeypatch):
    import app as app_mod

    cfg = app_mod.app.config
    assert cfg["SESSION_COOKIE_SECURE"] is True and cfg["SESSION_COOKIE_HTTPONLY"] is True
    assert cfg["SESSION_COOKIE_SAMESITE"] == "Lax" and not cfg["SESSION_COOKIE_DOMAIN"]
    for key, value in (("SESSION_COOKIE_SECURE", False), ("SESSION_COOKIE_HTTPONLY", False),
                       ("SESSION_COOKIE_SAMESITE", None), ("SESSION_COOKIE_SAMESITE", "None"),
                       ("SESSION_COOKIE_DOMAIN", ".docmaxxing.com")):
        monkeypatch.setitem(cfg, key, value)
        with pytest.raises(SystemExit):
            app_mod._require_secure_session_cookies()
        monkeypatch.undo()
    app_mod._require_secure_session_cookies()


def test_imported_app_ignores_insecure_overrides_and_proxy_headers(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SESSION_COOKIE")}
    env.update(
        SECRET_KEY=secrets.token_urlsafe(48),
        DEV_INSECURE_COOKIES="1",
        SESSION_COOKIE_SECURE="0",
        FLASK_SESSION_COOKIE_SECURE="false",
    )
    code = (
        "import json, app\n"
        "c = app.app.config\n"
        "r = app.app.test_client().get('/api/csrf-token', headers={'X-Forwarded-Proto': 'http'})\n"
        "print(json.dumps([c['SESSION_COOKIE_SECURE'], c['SESSION_COOKIE_HTTPONLY'], c['SESSION_COOKIE_SAMESITE'],"
        " r.headers.get('Set-Cookie', '')]))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    secure, httponly, samesite, set_cookie = json.loads(out.stdout.strip().splitlines()[-1])
    assert (secure, httponly, samesite) == (True, True, "Lax")
    assert "Secure" in set_cookie and "HttpOnly" in set_cookie


def test_logout_invalidates_a_copied_cookie(economy):
    carol = _user("carol@example.com")
    client = _raw()
    _login(client, "carol@example.com")
    stolen = _session_cookie(client)
    token = _token(client)

    thief = _raw()
    thief.set_cookie(_cookie_name(), stolen)
    assert _authenticated(thief)

    assert client.post("/api/auth/logout", headers={HDR: token}).status_code == 200
    assert not _authenticated(client)

    replay = _raw()
    replay.set_cookie(_cookie_name(), stolen)
    assert not _authenticated(replay)
    res = replay.post("/api/account/profile", json={"name": "Mallory"}, headers={HDR: token})
    assert res.status_code in (401, 403) or res.is_json and res.get_json().get("success") is False
    assert economy_auth.get_user(carol["id"])["name"] != "Mallory"


def test_sessions_from_before_the_patch_must_sign_in_again(economy):
    user = _user("legacy@example.com")
    client = _signed_in(_raw(), user, legacy=True)  # cookie without auth_sid, as issued before Patch 3G
    stolen = _session_cookie(client)
    assert not _authenticated(client)
    replay = _raw()
    replay.set_cookie(_cookie_name(), stolen)
    assert not _authenticated(replay)


# ------------------------------------------------------------------ 25-29. admin authorization


def _admin_rules():
    app = _app()
    for rule in app.url_map.iter_rules():
        view = app.view_functions.get(rule.endpoint)
        guard = getattr(view, "admin_guard", None)
        if guard:
            yield rule, view, guard


def _expect_denied(client, rule, view, token):
    for method in sorted((rule.methods or set()) - {"HEAD", "OPTIONS"}):
        headers = {} if method in csrf.SAFE_METHODS else {HDR: token}
        with _Entered(view) as entered:
            res = client.open(_url(rule), method=method, headers=headers, json={})
        assert not entered.hit, (method, rule.rule)
        assert res.status_code in (302, 401, 403, 404), (method, rule.rule, res.status_code)
        body = res.get_data(as_text=True).lower()
        assert "traceback" not in body and "is_admin" not in body and "is_verified" not in body


def test_every_admin_route_denies_everyone_but_verified_admins(economy, monkeypatch):
    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    revoked = _user("revoked-admin@example.com", admin=True)
    callers = {
        "anonymous": _raw(),
        "ordinary verified": _signed_in(_raw(), _user("plain@example.com")),
        "ordinary unverified": _signed_in(_raw(), _user("fresh@example.com", verified=False)),
        "unverified admin": _signed_in(_raw(), _user("half-admin@example.com", admin=True, verified=False)),
        "verification revoked": _signed_in(_raw(), revoked),
    }
    tokens = {name: _token(c) for name, c in callers.items()}
    with economy_db.connect() as conn:
        conn.execute("UPDATE users SET is_verified = 0 WHERE id = ?", (revoked["id"],))

    guards = set()
    count = 0
    for rule, view, guard in _admin_rules():
        guards.add(guard)
        count += 1
        for name, client in callers.items():
            _expect_denied(client, rule, view, tokens[name])
    assert guards == {"admin_required", "admin_only", "internal_tool"}
    assert count >= 50


def test_verified_admin_keeps_access_through_each_guard(economy, monkeypatch):
    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    admin = _signed_in(_raw(), _user("boss@example.com", admin=True))
    target = _user("target@example.com")
    token = _token(admin)
    app = _app()

    assert admin.get("/api/admin/panel/overview").status_code == 200  # admin_required
    assert admin.get("/admin?classic=1").status_code == 200
    assert admin.get("/api/admin/pipeline-preflight").status_code == 200  # admin_only
    with _Entered(app.view_functions["api_debug_project_get"]) as entered:  # internal_tool
        admin.get("/api/debug/project/abc")
    assert entered.hit
    res = admin.post(f"/api/admin/panel/users/{target['id']}/credits",
                     json={"delta": 5, "reason": "Support compensation"}, headers={HDR: token})
    assert res.status_code == 200 and res.get_json()["success"] is True


def test_forged_admin_claims_are_ignored(economy):
    plain = _user("forger@example.com")
    client = _raw()
    with client.session_transaction() as sess:
        sess.update({economy_auth.SESSION_KEY: plain["id"], "is_admin": True, "is_verified": True, "role": "admin",
                     "admin": 1, "email_verified": True,
                     economy_auth.AUTH_SID_KEY: economy_auth.register_session(plain["id"])})
    token = _token(client)
    headers = {"X-Admin": "1", "X-Is-Admin": "true", "X-User-Role": "admin", HDR: token}
    assert client.get("/api/admin/panel/overview?is_admin=1", headers=headers).status_code == 403
    assert client.get("/api/admin/pipeline-preflight", headers=headers).status_code == 403
    assert client.get("/api/browser/metrics", headers=headers).status_code == 404
    assert client.patch("/api/admin/site-settings", json={"is_admin": True}, headers=headers).status_code == 403

    ghost = _raw()
    with ghost.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = 999_999
        sess["is_admin"] = True
    assert ghost.get("/api/admin/panel/overview").status_code in (401, 403)

    # A cookie signed with someone else's key is dropped entirely.
    admin = _user("real-admin@example.com", admin=True)
    other = Flask("forger")
    other.secret_key = "attacker-" + "k" * 40
    forged = other.session_interface.get_signing_serializer(other).dumps({economy_auth.SESSION_KEY: admin["id"]})
    evil = _raw()
    evil.set_cookie(_cookie_name(), forged)
    assert evil.get("/api/admin/panel/overview").status_code in (401, 403)
    assert not _authenticated(evil)


def test_admin_rights_follow_the_database_not_the_session(economy):
    admin = _user("ops@example.com", admin=True)
    client = _raw()
    _login(client, "ops@example.com")
    token = _token(client)
    assert client.get("/api/admin/panel/overview").status_code == 200

    with economy_db.connect() as conn:
        conn.execute("UPDATE users SET is_verified = 0 WHERE id = ?", (admin["id"],))
    assert client.get("/api/admin/panel/overview").status_code == 403
    assert client.get("/api/browser/metrics").status_code == 404
    assert client.patch("/api/admin/site-settings", json={}, headers={HDR: token}).status_code == 403

    with economy_db.connect() as conn:
        conn.execute("UPDATE users SET is_verified = 1, is_admin = 0 WHERE id = ?", (admin["id"],))
    assert client.get("/api/admin/panel/overview").status_code == 403
    assert economy_auth.is_admin({"is_admin": 1, "is_verified": True}) is False  # only a real True counts
    assert economy_auth.is_admin({"is_admin": True, "is_verified": 1}) is False


def test_all_admin_decorators_share_one_policy_and_refuse_cross_site_navigation(economy, monkeypatch):
    import app as app_mod

    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    source = Path(app_mod.__file__).read_text(encoding="utf-8")
    assert source.count("def _is_verified_admin") == 1
    assert "economy_auth.is_admin(user)" in source
    assert 'user.get("is_admin")' not in source

    admin = _signed_in(_raw(), _user("navigator@example.com", admin=True))
    token = _token(admin)
    views = app_mod.app.view_functions
    # Operational actions (launch Chrome, provider logins, live provider calls) are POST + CSRF;
    # Fetch Metadata still refuses them from another site even with a valid token.
    for path, endpoint, denied in (
        ("/api/admin/pipeline-preflight?browser=1", "api_admin_pipeline_preflight", 403),  # admin_required
        ("/api/browser/connect", "api_browser_connect", 404),  # admin_only
        ("/api/browser/providers/stealthwriter/verify-production", "api_browser_stealthwriter_verify_production", 404),
        ("/api/test/gemini", "api_test_gemini", 404),  # internal_tool
    ):
        assert getattr(views[endpoint], "admin_guard", None)
        for site in ("cross-site", "same-site"):
            with _Entered(views[endpoint]) as entered:
                res = admin.post(path, headers={"Sec-Fetch-Site": site, "Sec-Fetch-Mode": "navigate", HDR: token})
            assert res.status_code == denied and not entered.hit, (path, site)
    for site in ("same-origin", "none", None):
        headers = {"Sec-Fetch-Site": site} if site else {}
        assert admin.get("/api/admin/pipeline-preflight", headers=headers).status_code == 200
        with _Entered(views["api_debug_project_get"]) as entered:
            admin.get("/api/debug/project/abc", headers=headers)
        assert entered.hit
    # The admin HTML page stays reachable from links (it only renders; its API calls are same-origin).
    assert admin.get("/admin?classic=1", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


# ------------------------------------------------------------------ 30-32. client IP behind the proxy


def _ip(headers=None, remote="127.0.0.1"):
    app = _app()
    with app.test_request_context("/", headers=headers or {}, environ_base={"REMOTE_ADDR": remote}):
        from flask import request

        return free_humanize.client_ip(request)


def test_spoofed_x_real_ip_is_ignored_unless_the_peer_is_the_proxy(monkeypatch):
    assert _ip({"X-Real-IP": "1.2.3.4"}, remote="198.51.100.20") == "198.51.100.20"
    assert _ip({"X-Real-IP": "1.2.3.4"}, remote="127.0.0.1") == "1.2.3.4"
    assert _ip({"X-Real-IP": "127.0.0.1"}, remote="198.51.100.20") == "198.51.100.20"
    assert _ip({"X-Real-IP": "not-an-ip<script>"}, remote="127.0.0.1") == "127.0.0.1"
    assert _ip({"X-Real-IP": "1.2.3.4"}, remote="::1") == "1.2.3.4"
    assert _ip({"CF-Connecting-IP": "5.5.5.5"}, remote="198.51.100.20") == "198.51.100.20"

    monkeypatch.setenv("TRUSTED_PROXIES", "none")
    assert _ip({"X-Real-IP": "1.2.3.4"}, remote="127.0.0.1") == "127.0.0.1"
    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.0/8, garbage")
    assert _ip({"X-Real-IP": "1.2.3.4"}, remote="10.9.8.7") == "1.2.3.4"
    assert _ip({"X-Real-IP": "1.2.3.4"}, remote="127.0.0.1") == "127.0.0.1"


def test_spoofed_x_forwarded_for_is_ignored(monkeypatch):
    assert _ip({"X-Forwarded-For": "1.1.1.1"}, remote="198.51.100.20") == "198.51.100.20"
    assert _ip({"X-Forwarded-For": "6.6.6.6, 7.7.7.7, 2.2.2.2"}, remote="127.0.0.1") == "2.2.2.2"
    assert _ip({"X-Forwarded-For": "6.6.6.6, bogus"}, remote="127.0.0.1") == "127.0.0.1"
    assert _ip({"Forwarded": "for=9.9.9.9", "True-Client-IP": "9.9.9.9"}, remote="198.51.100.20") == "198.51.100.20"
    headers = {"X-Forwarded-For": "1.1.1.1", "X-Real-IP": "1.1.1.1"}
    with _app().test_request_context("/", headers=headers, environ_base={"REMOTE_ADDR": "198.51.100.20"}):
        assert economy_auth.client_ip_from_request() == "198.51.100.20"  # registration / audit IP


def test_guest_quota_cannot_be_reset_with_forwarding_headers(provider, monkeypatch):  # noqa: F811
    monkeypatch.setenv("FREE_DOC_AI_GUEST_DAILY", "100")
    monkeypatch.setenv("FREE_DOC_AI_GUEST_IP_DAILY", "2")
    monkeypatch.setenv("FREE_DOC_AI_RATE_PER_MIN", "0")
    outcomes = []
    for n in range(5):
        guest = _app().test_client()
        res = guest.post(
            "/api/structure-recovery",
            data={"pasted_text": _prose()},
            headers={"X-Real-IP": f"192.0.2.{n}", "X-Forwarded-For": f"198.51.100.{n}", "CF-Connecting-IP": f"192.0.2.{n}"},
            environ_base={"REMOTE_ADDR": "203.0.113.50"},
        )
        outcomes.append(res.get_json()["ai_powered"])
    assert outcomes == [True, True, False, False, False]
    assert provider.count("document") == 2
