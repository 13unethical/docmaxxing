"""Patch 3H: residual hardening.

Admin actions are POST + CSRF, sessions from before the session registry must sign in again, a
password change ends every other session, redirects stay local, outgoing links use
PUBLIC_BASE_URL only, project content fails closed, Turnitin routes check ownership and
entitlement, Veil questions are rate limited per account, and exception text never reaches
clients.

Everything runs offline: browser, AI providers, Turnitin/PlagDetect, email and payments are
recording stubs or tripwires.
"""

from __future__ import annotations

import io
import json
import logging
import multiprocessing
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

from services import rate_limit
from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy.wallet import WalletService
from services.public_errors import admin_detail, is_public_text, public_text
from services.public_origin import PublicOriginError, normalize_public_base_url
from services.safe_redirect import safe_local_path
from tests.test_security_csrf_sessions_admin import (
    HDR,
    REPO,
    _app,
    _authenticated,
    _cookie_name,
    _csrf_rejected,
    _Entered,
    _login,
    _raw,
    _session_cookie,
    _token,
)
from tests.test_security_csrf_sessions_admin import _signed_in as _signed_in_raw
from tests.test_security_csrf_sessions_admin import _user as _account
from tests.test_security_paid_pipelines import economy  # noqa: F401  (fixture)
from tests.test_security_refund_integrity import (  # noqa: F401  (refund_app is a fixture)
    CONTENT_ROUTES,
    _admin_refund,
    _call,
    _completed_project_with_delivery,
    _draft_marker,
    _url,
    refund_app,
)

FORK = multiprocessing.get_context("fork")

SECRET_BLOB = (
    "Traceback (most recent call last): File \"/srv/docmaxxing/services/x.py\", line 12 "
    "sqlite3.OperationalError: no such table: users SELECT * FROM users WHERE id=1 "
    "sk-ant-api03-SECRETSECRETSECRET ANTHROPIC_API_KEY=abc123 PLAGDETECT_PASSWORD=hunter2 "
    "https://provider.internal/v1 Bearer tok_live_ABCDEFGHIJKLMNOP"
)
SECRET_MARKERS = ("/srv/docmaxxing", "sqlite3", "SELECT", "sk-ant", "ANTHROPIC_API_KEY", "hunter2",
                  "provider.internal", "tok_live", "Traceback")


def _no_secrets(text: str) -> None:
    for marker in SECRET_MARKERS:
        assert marker not in text, marker


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("TRUSTED_PROXIES", "INTERNAL_TOOLS_ENABLED", "DEV_INSECURE_COOKIES", "PUBLIC_BASE_URL",
                 "VEIL_ASK_LIMIT_PER_MINUTE", "VEIL_ASK_LIMIT_PER_HOUR", "VEIL_ASK_LIMIT_PER_DAY"):
        monkeypatch.delenv(name, raising=False)


def _client():
    app = _app()
    return app.test_client()


def _sign_in(client, user):
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
        sess[economy_auth.AUTH_SID_KEY] = economy_auth.register_session(user["id"])
    return client


def _sid(client) -> str | None:
    with client.session_transaction() as sess:
        return sess.get(economy_auth.AUTH_SID_KEY)


# ====================================================================== 2. admin actions are POST + CSRF

ACTION_ROUTES = [
    ("/api/browser/runtime-test", "api_browser_runtime_test"),
    ("/api/browser/cdp-diagnostics", "api_browser_cdp_diagnostics"),
    ("/api/browser/connect", "api_browser_connect"),
    ("/api/browser/providers/stealthwriter/health", "api_browser_stealthwriter_health"),
    ("/api/browser/providers/stealthwriter/session", "api_browser_stealthwriter_session"),
    ("/api/browser/providers/stealthwriter/login", "api_browser_stealthwriter_login"),
    ("/api/browser/providers/stealthwriter/check-login", "api_browser_stealthwriter_check_login"),
    ("/api/browser/providers/stealthwriter/status", "api_browser_stealthwriter_status"),
    ("/api/browser/providers/stealthwriter/verify-production", "api_browser_stealthwriter_verify_production"),
    ("/api/browser/providers/stealthwriter/open", "api_browser_stealthwriter_open"),
    ("/api/browser/providers/plagdetect/status", "api_browser_plagdetect_status"),
    ("/api/browser/providers/plagdetect/login", "api_browser_plagdetect_login"),
    ("/api/test/zerogpt", "api_test_zerogpt"),
    ("/api/test/zerogpt-humanizer", "api_test_zerogpt_humanizer"),
    ("/api/test/gemini", "api_test_gemini"),
    ("/api/admin/pipeline-preflight?browser=1", "api_admin_pipeline_preflight"),
]

READ_ONLY_DIAGNOSTICS = [
    "/api/browser/health",
    "/api/browser/metrics",
    "/api/browser/providers/plagdetect/config",
    "/api/admin/pipeline-preflight",
    "/api/admin/pipeline-preflight?browser=1",
]


@pytest.fixture()
def ops(economy, monkeypatch):
    """Every browser/provider entry point records its use instead of acting."""
    import app as app_mod

    calls: list[str] = []

    def record(name, result=None):
        def call(*_args, **_kwargs):
            calls.append(name)
            return result

        return call

    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    monkeypatch.setattr(app_mod, "ensure_engine_started", record("ensure_engine_started"))
    monkeypatch.setattr(app_mod, "_browser_submit", record("browser_submit", {"connected": True, "logged_in": True}))
    monkeypatch.setattr(app_mod, "zerogpt_client", SimpleNamespace(
        login=record("zerogpt.login"), detect=record("zerogpt.detect", {"ok": True}),
        humanize=record("zerogpt.humanize", {"ok": True})))
    monkeypatch.setattr(app_mod.requests, "post", record(
        "provider_http", SimpleNamespace(status_code=200, text="OK", json=lambda: {}, headers={})))
    monkeypatch.setattr("services.browser.cdp_compat.cdp_diagnostics", record("cdp_diagnostics", {"connect_ok": True}))

    class _Launcher:
        cdp_url = "http://127.0.0.1:9"
        pid = None

        def is_cdp_available(self):
            calls.append("cdp_probe")
            return False

        def memory_usage(self):
            return None

    monkeypatch.setattr("services.browser.chrome_launcher.ChromeLauncher", _Launcher)
    monkeypatch.setattr(app_mod, "_engine_started", False)
    monkeypatch.setitem(app_mod.app.config, "PROPAGATE_EXCEPTIONS", False)
    return SimpleNamespace(app=app_mod, calls=calls)


def test_get_never_reaches_a_browser_or_provider_action(ops):
    admin = _signed_in_raw(_raw(), _account("ops@example.com", admin=True))
    views = ops.app.app.view_functions
    for path, endpoint in ACTION_ROUTES:
        if endpoint == "api_admin_pipeline_preflight":
            continue  # GET stays read-only there; covered below
        with _Entered(views[endpoint]) as entered:
            res = admin.get(path, headers={"Sec-Fetch-Site": "same-origin"})
        assert res.status_code == 405, (path, res.status_code)
        assert not entered.hit, path
    preflight = admin.get("/api/admin/pipeline-preflight?browser=1")
    assert preflight.status_code == 200 and preflight.get_json()["stealthwriter"]["skipped"] is True
    assert ops.calls == []


def test_post_without_or_with_a_wrong_csrf_token_is_rejected(ops):
    admin = _signed_in_raw(_raw(), _account("ops@example.com", admin=True))
    _token(admin)
    views = ops.app.app.view_functions
    for path, endpoint in ACTION_ROUTES:
        for headers in ({}, {HDR: "forged-" + secrets.token_urlsafe(24)}):
            with _Entered(views[endpoint]) as entered:
                res = admin.post(path, headers=headers)
            assert _csrf_rejected(res), (path, res.status_code)
            assert not entered.hit, path
    assert ops.calls == []


def test_verified_admin_with_a_token_can_run_each_action(ops):
    admin = _signed_in_raw(_raw(), _account("ops@example.com", admin=True))
    token = _token(admin)
    views = ops.app.app.view_functions
    for path, endpoint in ACTION_ROUTES:
        with _Entered(views[endpoint]) as entered:
            res = admin.post(path, headers={HDR: token, "Sec-Fetch-Site": "same-origin"})
        assert entered.hit, path
        assert res.status_code not in (401, 403, 404, 405), (path, res.status_code)
        assert "traceback" not in res.get_data(as_text=True).lower()
    assert "browser_submit" in ops.calls and "zerogpt.detect" in ops.calls and "provider_http" in ops.calls


@pytest.mark.parametrize("kind", ["ordinary", "unverified admin"])
def test_ordinary_users_and_unverified_admins_are_denied(ops, kind):
    user = (_account("plain@example.com") if kind == "ordinary"
            else _account("half-admin@example.com", admin=True, verified=False))
    client = _signed_in_raw(_raw(), user)
    token = _token(client)
    views = ops.app.app.view_functions
    for path, endpoint in ACTION_ROUTES:
        with _Entered(views[endpoint]) as entered:
            res = client.post(path, headers={HDR: token})
        assert res.status_code in (401, 403, 404), (path, res.status_code)
        assert not entered.hit, path
    for path in READ_ONLY_DIAGNOSTICS:
        assert client.get(path).status_code in (401, 403, 404), path
    assert ops.calls == []


def test_read_only_diagnostics_still_work_with_get(ops):
    admin = _signed_in_raw(_raw(), _account("ops@example.com", admin=True))
    for path in READ_ONLY_DIAGNOSTICS:
        res = admin.get(path)
        assert res.status_code == 200, (path, res.status_code)
    assert admin.get("/api/browser/metrics").get_json()["engine_started"] is False
    assert not {"ensure_engine_started", "browser_submit"} & set(ops.calls)


def test_ops_scripts_hold_no_credentials_and_use_the_authenticated_client():
    scripts = REPO / "scripts"
    helper = (scripts / "admin_api.py").read_text(encoding="utf-8")
    assert "getpass" in helper and "X-CSRF-Token" in helper
    for name in ("fix_playwright_and_verify_browser.sh", "push_browser_profile_to_vps.sh",
                 "push_stealthwriter_session_to_vps.sh", "fix_chrome_profile_on_vps.sh",
                 "bootstrap_stealthwriter_login.py"):
        text = (scripts / name).read_text(encoding="utf-8")
        assert "curl -s http://127.0.0.1:5001/api/browser" not in text, name
        assert "password=" not in text.lower() or "getpass" in text, name
        for action in ("stealthwriter/status", "/api/browser/connect", "verify-production"):
            for line in text.splitlines():
                if action in line and "curl" in line:
                    raise AssertionError(f"{name}: unauthenticated call to {action}")


# ====================================================================== 3. sessions from before the registry

def _authenticated_in_a_new_process(cookies: list[str]) -> list[bool]:
    """Ask a freshly started app process (same DB and key, nothing in memory) about each cookie."""
    child = (
        "import json, sys\n"
        "import app as app_mod\n"
        "from flask.testing import FlaskClient\n"
        "app_mod.app.config['TESTING'] = True\n"
        "out = []\n"
        "for value in json.loads(sys.argv[1]):\n"
        "    c = FlaskClient(app_mod.app, app_mod.app.response_class, use_cookies=True)\n"
        "    c.set_cookie(app_mod.app.config['SESSION_COOKIE_NAME'], value)\n"
        "    out.append(c.get('/api/economy/balance').get_json()['authenticated'])\n"
        "print('RESULT ' + json.dumps(out))\n"
    )
    env = dict(os.environ)
    env.update(SECRET_KEY=_app().secret_key, ECONOMY_DB_PATH=str(economy_db.DB_PATH))
    out = subprocess.run([sys.executable, "-c", child, json.dumps(cookies)], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, out.stderr[-3000:]
    line = [row for row in out.stdout.splitlines() if row.startswith("RESULT ")][-1]
    return json.loads(line[len("RESULT "):])


@pytest.mark.parametrize("legacy_sid", [None, "random-pre-registry-id"])
def test_legacy_cookie_copied_into_two_clients_authenticates_neither(economy, legacy_sid):
    user = _account("legacy@example.com")
    original = _raw()
    with original.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
        if legacy_sid:
            sess[economy_auth.AUTH_SID_KEY] = legacy_sid + secrets.token_urlsafe(8)
    stolen = _session_cookie(original)
    copies = []
    for _ in range(2):
        copy = _raw()
        copy.set_cookie(_cookie_name(), stolen)
        copies.append(copy)
    for client in copies + [original]:
        assert not _authenticated(client)
        res = client.post("/api/account/profile", json={"name": "Mallory"}, headers={HDR: _token(client)})
        assert res.status_code in (401, 403)
    assert economy_auth.get_user(user["id"])["name"] != "Mallory"


def test_guest_sessions_are_untouched_and_a_new_login_works(economy):
    from services.free_humanize import GUEST_SESSION_KEY

    _account("legacy@example.com")
    guest = _raw()
    with guest.session_transaction() as sess:
        sess[GUEST_SESSION_KEY] = "guest-123"
    assert guest.get("/api/economy/balance").status_code == 200
    with guest.session_transaction() as sess:
        assert sess.get(GUEST_SESSION_KEY) == "guest-123"

    legacy = _raw()
    with legacy.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = 1
    assert not _authenticated(legacy)
    _login(legacy, "legacy@example.com")
    assert _authenticated(legacy)
    assert _sid(legacy)


def test_logout_revocation_survives_a_worker_restart(economy):
    _account("restart@example.com")
    stays = _raw()
    _login(stays, "restart@example.com")
    leaves = _raw()
    _login(leaves, "restart@example.com")
    copied = _session_cookie(leaves)
    legacy = _raw()
    with legacy.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = 1
    assert leaves.post("/api/auth/logout", headers={HDR: _token(leaves)}).status_code == 200
    assert _authenticated_in_a_new_process([_session_cookie(stays), copied, _session_cookie(legacy)]) == [
        True, False, False]


def test_session_table_stays_bounded(economy):
    user = _account("many@example.com")
    for _ in range(economy_auth._MAX_SESSIONS_PER_USER + 15):
        economy_auth.register_session(user["id"])
    with economy_db.connect() as conn:
        conn.execute("UPDATE auth_sessions SET last_seen = datetime('now', '-40 days') WHERE rowid IN "
                     "(SELECT rowid FROM auth_sessions LIMIT 5)")
    economy_auth.register_session(user["id"])
    with economy_db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM auth_sessions WHERE user_id = ?", (user["id"],)).fetchone()[0]
        stale = conn.execute("SELECT COUNT(*) FROM auth_sessions WHERE last_seen < datetime('now', '-31 days')"
                             ).fetchone()[0]
    assert count <= economy_auth._MAX_SESSIONS_PER_USER and stale == 0


# ====================================================================== 4. password change / reset

NEW_PASSWORD = "brand-new-pass-42"


def _change_password(client, *, extra: dict | None = None):
    body = {"current_password": "secret123", "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD}
    body.update(extra or {})
    return client.post("/api/account/password", json=body, headers={HDR: _token(client)})


def test_password_change_signs_out_every_other_session(economy):
    user = _account("owner@example.com")
    victim = _account("bystander@example.com")
    a = _raw()
    _login(a, "owner@example.com")
    b = _raw()
    _login(b, "owner@example.com")
    copy_of_a = _session_cookie(a)
    other = _raw()
    _login(other, "bystander@example.com")
    old_sid = _sid(a)

    res = _change_password(a, extra={"keep_session_ids": [_sid(b)], "session_id": _sid(b), "auth_sid": _sid(b),
                                     "user_id": victim["id"], "sessions": "keep"})
    assert res.status_code == 200 and res.get_json() == {"success": True, "other_sessions_signed_out": True}

    assert _authenticated(a)  # documented policy: the browser that proved the password continues
    assert _sid(a) and _sid(a) != old_sid
    assert not _authenticated(b)
    replay = _raw()
    replay.set_cookie(_cookie_name(), copy_of_a)
    assert not _authenticated(replay)
    assert _authenticated(other)  # forged ids in the body touched nobody else

    fresh = _raw()
    _login(fresh, "owner@example.com", NEW_PASSWORD)
    assert economy_auth.verify_credentials("owner@example.com", "secret123") is None
    assert _authenticated_in_a_new_process([_session_cookie(a), _session_cookie(b), copy_of_a]) == [True, False, False]
    assert user["id"] != victim["id"]


def test_failed_password_change_revokes_nothing(economy):
    _account("owner@example.com")
    a = _raw()
    _login(a, "owner@example.com")
    b = _raw()
    _login(b, "owner@example.com")
    res = a.post("/api/account/password", json={"current_password": "wrong", "new_password": NEW_PASSWORD,
                                                 "confirm_password": NEW_PASSWORD}, headers={HDR: _token(a)})
    assert res.status_code == 400
    assert _authenticated(a) and _authenticated(b)


def test_password_reset_outside_the_route_revokes_every_session(economy):
    """There is no self-service reset flow; any reset (support/operator) writes password_hash."""
    user = _account("reset@example.com")
    other = _account("other@example.com")
    a = _raw()
    _login(a, "reset@example.com")
    b = _raw()
    _login(b, "other@example.com")
    with economy_db.connect() as conn:
        conn.execute("UPDATE users SET name = 'Renamed' WHERE id = ?", (user["id"],))
    assert _authenticated(a)  # unrelated profile edits keep sessions
    with economy_db.connect() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash("reset-pass-1"), user["id"]))
    assert not _authenticated(a)
    assert _authenticated(b) and other["id"] != user["id"]
    assert _authenticated_in_a_new_process([_session_cookie(a), _session_cookie(b)]) == [False, True]


def test_forged_session_ids_cannot_take_over_or_end_other_sessions(economy):
    attacker = _account("attacker@example.com")
    victim = _account("victim@example.com")
    victim_client = _raw()
    _login(victim_client, "victim@example.com")
    victim_sid = _sid(victim_client)
    attacker_client = _raw()
    _login(attacker_client, "attacker@example.com")
    attacker_sid = _sid(attacker_client)

    swapped = _raw()  # attacker's own sign-in id presented for the victim's account
    with swapped.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = victim["id"]
        sess[economy_auth.AUTH_SID_KEY] = attacker_sid
    assert not _authenticated(swapped)

    res = attacker_client.post("/api/auth/logout", json={"auth_sid": victim_sid, "sid": victim_sid,
                                                         "user_id": victim["id"]},
                               headers={HDR: _token(attacker_client)})
    assert res.status_code == 200
    assert _authenticated(victim_client)
    assert attacker["id"] != victim["id"]


# ====================================================================== 5. safe redirects

GOOD_TARGETS = ["/", "/app", "/app/projects?tab=open&x=1", "/veil/download", "/a/b%20c", "/humanizer#top"]
BAD_TARGETS = [
    "https://evil.example", "http://evil.example/app", "//evil.example", "///evil.example", "////evil.example",
    "/\\evil.example", "\\\\evil.example", "/\\/evil.example", "\\/evil.example", "/%5Cevil.example",
    "/%2F%2Fevil.example", "/%2fevil.example", "/%09/evil.example", "/\t/evil.example", "/\n/evil.example",
    "/%0d%0aSet-Cookie:x=1", "/%00", "javascript:alert(1)", "evil.example", "docmaxxing.com.evil.example/app",
    "https://docmaxxing.com.evil.example/", "https://docmaxxing.com@evil.example/", "@evil.example", "",
    " ", "/app %", "/app%zz", "/app%", "mailto:a@b.c", "data:text/html,x", "/" + "a" * 3000,
]


@pytest.mark.parametrize("target", GOOD_TARGETS)
def test_safe_local_paths_are_kept(target):
    assert safe_local_path(target) == target


@pytest.mark.parametrize("target", BAD_TARGETS)
def test_unsafe_redirect_targets_are_rejected(target):
    assert safe_local_path(target) is None


@pytest.mark.parametrize("value", [None, 1, ["/app"], {"next": "/app"}, b"/app"])
def test_non_string_redirect_targets_are_rejected(value):
    assert safe_local_path(value) is None


@pytest.mark.parametrize("target,expected", [
    ("/app/projects?tab=open", "/app/projects?tab=open"),
    ("https://evil.example", "/"),
    ("//evil.example", "/"),
    ("/\\evil.example", "/"),
    ("/%2F%2Fevil.example", "/"),
])
def test_login_redirects_only_to_local_paths(economy, target, expected):
    _account("login@example.com")
    client = _raw()
    token = _token(client)
    res = client.post("/login", data={"email": "login@example.com", "password": "secret123", "next": target,
                                      "csrf_token": token})
    assert res.status_code in (302, 303)
    location = res.headers["Location"]
    assert location == expected or location == "http://localhost" + expected
    assert "evil.example" not in location
    again = client.get("/login", query_string={"next": target})
    assert "evil.example" not in again.headers.get("Location", "")


# ====================================================================== 6. canonical origin

@pytest.mark.parametrize("raw,expected", [
    ("https://docmaxxing.com", "https://docmaxxing.com"),
    ("https://docmaxxing.com/", "https://docmaxxing.com"),
    ("HTTPS://DocMaxxing.com:8443", "https://docmaxxing.com:8443"),
])
def test_valid_public_base_url(raw, expected):
    assert normalize_public_base_url(raw) == expected


@pytest.mark.parametrize("raw", [
    None, "", "   ", "http://docmaxxing.com", "ftp://docmaxxing.com", "javascript://docmaxxing.com",
    "https://docmaxxing.com/app", "https://docmaxxing.com?x=1", "https://docmaxxing.com#x",
    "https://user:pass@docmaxxing.com", "https://docmaxxing.com\\@evil.example", "https://",
    "https://docmaxxing.com:99999", "https://exa mple.com", "docmaxxing.com", "//docmaxxing.com",
    "http://localhost:5001",
])
def test_invalid_public_base_url_fails_closed(raw):
    with pytest.raises(PublicOriginError):
        normalize_public_base_url(raw)


def test_local_dev_http_needs_the_explicit_dev_switch():
    assert normalize_public_base_url("http://localhost:5001", allow_dev_http=True) == "http://localhost:5001"
    assert normalize_public_base_url("http://127.0.0.1:5001", allow_dev_http=True) == "http://127.0.0.1:5001"
    with pytest.raises(PublicOriginError):
        normalize_public_base_url("http://evil.example", allow_dev_http=True)


POISON = {"X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "http", "Forwarded": "host=evil.example"}


@pytest.fixture()
def mailbox(economy, monkeypatch):
    from services.economy import email_verify

    sent: list[str] = []
    monkeypatch.setattr(email_verify, "smtp_configured", lambda: True)
    monkeypatch.setattr(email_verify, "_smtp_send", lambda to, subject, text, html: sent.append(text + html))
    return sent


def test_emailed_and_referral_links_use_the_configured_origin_despite_poisoned_headers(mailbox, monkeypatch):
    import app as app_mod

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://docmaxxing.com")
    client = _sign_in(_client(), _account("links@example.com"))
    res = client.post("/api/veil/email-link", json={}, headers=POISON)
    assert res.status_code == 200
    assert "https://docmaxxing.com/app#/veil" in mailbox[0] and "evil.example" not in mailbox[0]
    ref = client.get("/api/referral/me", headers=POISON)
    assert ref.status_code == 200
    assert ref.get_json()["referral_link"].startswith("https://docmaxxing.com/")
    # Host poisoning (the test client would not send the localhost cookie to another host).
    with app_mod.app.test_request_context("/api/referral/me", base_url="http://evil.example", headers=POISON):
        assert app_mod._public_origin() == "https://docmaxxing.com"


def test_poisoned_host_cannot_stand_in_for_a_missing_origin(economy):
    import app as app_mod

    for base in ("https://evil.example", "http://localhost:5001"):
        with app_mod.app.test_request_context("/", base_url=base, headers=POISON):
            assert app_mod._public_origin() is None


@pytest.mark.parametrize("configured", [None, "http://docmaxxing.com", "https://evil.example/path", "not a url"])
def test_missing_or_invalid_origin_in_production_fails_closed(mailbox, monkeypatch, configured):
    if configured:
        monkeypatch.setenv("PUBLIC_BASE_URL", configured)
    client = _sign_in(_client(), _account("links@example.com"))
    res = client.post("/api/veil/email-link", json={}, headers=POISON)
    assert res.status_code == 503 and res.get_json()["error"] == "ORIGIN_NOT_CONFIGURED"
    assert mailbox == []
    ref = client.get("/api/referral/me", headers=POISON)
    assert ref.status_code == 200 and ref.get_json()["referral_link"] is None


def test_local_development_origin(mailbox, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:5001")
    client = _sign_in(_client(), _account("dev@example.com"))
    assert client.post("/api/veil/email-link", json={}).status_code == 503
    monkeypatch.setenv("DEV_INSECURE_COOKIES", "1")
    assert client.post("/api/veil/email-link", json={}).status_code == 200
    assert "http://localhost:5001/app#/veil" in mailbox[0]


# ====================================================================== 7. project content fails closed

def _content_bodies(client, project_id):
    for method, suffix in CONTENT_ROUTES:
        yield suffix, _call(client, method, _url(project_id, suffix))
    yield "project", client.get(_url(project_id))


@pytest.mark.parametrize("failure", [
    sqlite3.OperationalError("database is locked at /srv/docmaxxing/economy.db"),
    RuntimeError("reconciliation exploded: SELECT * FROM transactions"),
])
def test_reconciliation_failure_returns_503_and_no_content(refund_app, monkeypatch, failure):
    owner = _account("owner@example.com")
    project_id, package_id, file_id = _completed_project_with_delivery(refund_app, owner)
    draft_text = _draft_marker(refund_app, project_id)
    client = _sign_in(_client(), owner)

    def boom(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(refund_app.service, "reconcile_payment_state", boom)
    for suffix, res in _content_bodies(client, project_id):
        body = res.get_data(as_text=True)
        assert res.status_code == 503, (suffix, res.status_code)
        assert res.get_json()["error"] == "PROJECT_UNAVAILABLE"
        assert draft_text not in body
        _no_secrets(body)
    for path in (f"/api/delivery/packages/{package_id}/download", f"/api/delivery/files/{file_id}"):
        res = client.get(path)
        assert res.status_code == 503 and b"PK-final-assignment" not in res.data
    listing = client.get("/api/assignment/projects")
    assert listing.status_code == 200 and draft_text not in listing.get_data(as_text=True)

    admin = _sign_in(_client(), _account("auditor@example.com", admin=True))
    assert draft_text in admin.get(_url(project_id, "draft")).get_data(as_text=True)


@pytest.mark.parametrize("stale", ["pre-refund snapshot", "refund flags removed"])
def test_stale_json_cannot_reopen_a_refunded_project(refund_app, stale):
    owner = _account("owner@example.com")
    project_id, package_id, file_id = _completed_project_with_delivery(refund_app, owner)
    draft_text = _draft_marker(refund_app, project_id)
    snapshot = json.loads(json.dumps(refund_app.service.store.require_project(project_id).artifacts))
    assert _admin_refund(refund_app, project_id).status_code == 200

    project = refund_app.service.store.require_project(project_id)
    if stale == "pre-refund snapshot":  # worker died after the ledger refund, before the JSON write
        project.artifacts = snapshot
    else:  # hand-edited / partially written file
        for key in ("payment_refunded", "payment_refunded_at", "payment_refund_coins"):
            project.artifacts.pop(key, None)
    refund_app.service.store.save_project(project)

    client = _sign_in(_client(), owner)
    for suffix, res in _content_bodies(client, project_id):
        assert draft_text not in res.get_data(as_text=True), suffix
        if suffix == "project":
            assert res.status_code == 200 and res.get_json()["content_locked"] is True
        else:
            assert res.status_code == 404, (suffix, res.status_code)
    for path in (f"/api/delivery/packages/{package_id}/download", f"/api/delivery/files/{file_id}",
                 _url(project_id, "download")):
        res = client.get(path)
        assert res.status_code == 404 and b"PK-final-assignment" not in res.data
    listing = client.get("/api/assignment/projects")
    assert draft_text not in listing.get_data(as_text=True)
    item = next(p for p in listing.get_json()["projects"] if p["id"] == project_id)
    assert item["can_download"] is False and item["has_delivery"] is False


def test_paid_owner_reads_and_strangers_do_not(refund_app):
    owner = _account("owner@example.com")
    project_id, package_id, _file_id = _completed_project_with_delivery(refund_app, owner)
    draft_text = _draft_marker(refund_app, project_id)
    client = _sign_in(_client(), owner)
    assert draft_text in client.get(_url(project_id, "draft")).get_data(as_text=True)
    assert client.get(f"/api/delivery/packages/{package_id}/download").data == b"PK-final-assignment"

    stranger = _sign_in(_client(), _account("stranger@example.com"))
    for suffix, res in _content_bodies(stranger, project_id):
        assert res.status_code in (403, 404), suffix
        assert draft_text not in res.get_data(as_text=True)
    assert stranger.get(f"/api/delivery/packages/{package_id}/download").status_code == 404


# ====================================================================== 8. Turnitin

@pytest.fixture()
def turnitin(economy, tmp_path, monkeypatch):
    import app as app_mod
    from services.turnitin_service import service as service_mod
    from services.turnitin_service import store as store_mod

    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "turnitin.db")
    for module in (store_mod, service_mod):
        monkeypatch.setattr(module, "UPLOAD_ROOT", tmp_path / "uploads")
        monkeypatch.setattr(module, "REPORT_ROOT", tmp_path / "reports")
    store_mod.init_db()
    svc = app_mod.turnitin_service
    calls: list[tuple] = []

    def recorder(name, *, delay=0.0):
        def call(*args, **kwargs):
            calls.append((name, args, kwargs))
            if delay:
                time.sleep(delay)
            return {}

        return call

    for name in ("start_plagdetect_api_highlights", "start_tca_highlights", "fetch_plagdetect_api_reports",
                 "fetch_tca_similarity_pdf", "start_plagdetect_api_check", "start_tca_check", "watch_job",
                 "watch_highlights_job", "watch_fetch_reports_job"):
        monkeypatch.setattr(svc, name, recorder(name))
    jobs: list[dict] = []

    class _Jobs:
        def create(self, provider, action, payload, **_kwargs):
            jobs.append({"provider": provider, "action": action, **payload})
            return SimpleNamespace(id=f"job-{len(jobs)}")

    monkeypatch.setattr(app_mod, "job_manager", _Jobs())
    monkeypatch.setattr(app_mod, "ensure_engine_started", lambda: calls.append(("ensure_engine_started", (), {})))
    monkeypatch.setattr("services.browser.providers.plagdetect._validate_urls", lambda: None)
    monkeypatch.setattr("services.turnitin_api.prefer_official_api", lambda: False)
    monkeypatch.setattr("services.plagdetect_api.prefer_plagdetect_api", lambda: True)
    monkeypatch.setitem(app_mod.app.config, "PROPAGATE_EXCEPTIONS", False)

    def submission(user, *, transport="api", status="completed", ai_score=55.0, provider="plagdetect"):
        sid = secrets.token_hex(6)
        svc.store.create(submission_id=sid, user_id=user["id"], filename="essay.docx", upload_path="x")
        svc.store.update(sid, status=status, external_id=f"ext-{sid}", ai_score=ai_score, similarity=12.0,
                         meta_json=json.dumps({"provider": provider, "transport": transport}))
        return sid

    def report_file(sid, name="similarity.pdf"):
        path = svc.report_dir(sid) / name
        path.write_bytes(b"%PDF-1.4 report of " + sid.encode())
        return path

    def refund(user, sid):
        app_mod.wallet.credit(user["id"], 100, "test_topup")
        app_mod.wallet.refund(user["id"], 10, "turnitin", ref_id=sid, meta={"reason": "test"})

    return SimpleNamespace(app=app_mod, svc=svc, calls=calls, jobs=jobs, submission=submission,
                           report_file=report_file, refund=refund)


def _turnitin_routes(sid):
    return [
        ("get", f"/api/turnitin/submissions/{sid}", None),
        ("post", f"/api/turnitin/submissions/{sid}/highlights", {}),
        ("post", f"/api/turnitin/submissions/{sid}/fetch-reports", {"similarity": True, "ai": True}),
        ("get", f"/api/turnitin/submissions/{sid}/report/similarity", None),
    ]


def _provider_calls(env):
    return [name for name, *_ in env.calls if name != "ensure_engine_started"]


def test_turnitin_anonymous_unverified_and_strangers_are_refused(turnitin):
    owner = _account("owner@example.com")
    sid = turnitin.submission(owner)
    turnitin.svc.store.update(sid, similarity_report_path=str(turnitin.report_file(sid)))
    callers = {
        "anonymous": (_client(), (401, 302, 403)),
        "unverified": (_sign_in(_client(), _account("fresh@example.com", verified=False)), (401, 302, 403)),
        "stranger": (_sign_in(_client(), _account("stranger@example.com")), (404,)),
    }
    for label, (client, allowed) in callers.items():
        for method, path, body in _turnitin_routes(sid):
            res = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
            assert res.status_code in allowed, (label, path, res.status_code)
            assert b"%PDF" not in res.data and b"ext-" not in res.data
        listing = client.get("/api/turnitin/reports")
        assert sid not in listing.get_data(as_text=True)
    assert _provider_calls(turnitin) == [] and turnitin.jobs == []


def test_turnitin_unpaid_owner_cannot_start_a_check(turnitin):
    user = _account("broke@example.com")
    WalletService().set_balance(user["id"], 0)
    client = _sign_in(_client(), user)
    res = client.post("/api/turnitin/check", data={"file": (io.BytesIO(b"essay"), "essay.docx")},
                      content_type="multipart/form-data")
    assert res.status_code == 402
    assert _provider_calls(turnitin) == [] and turnitin.svc.store.list_for_user(user["id"]) == []


def test_turnitin_refunded_check_reveals_nothing_and_cannot_use_the_provider(turnitin):
    owner = _account("owner@example.com")
    sid = turnitin.submission(owner)
    turnitin.svc.store.update(sid, similarity_report_path=str(turnitin.report_file(sid)))
    turnitin.refund(owner, sid)
    client = _sign_in(_client(), owner)

    row = client.get(f"/api/turnitin/submissions/{sid}").get_json()["report"]
    assert row["status"] == "refunded" and row["similarity"] is None and row["aiScore"] is None
    assert row["externalId"] is None and row["hasReport"] is False
    listed = client.get("/api/turnitin/reports").get_json()["reports"]
    assert [r["status"] for r in listed if r["id"] == sid] == ["refunded"]
    assert client.post(f"/api/turnitin/submissions/{sid}/highlights", json={}).status_code == 403
    assert client.post(f"/api/turnitin/submissions/{sid}/fetch-reports", json={}).status_code == 403
    download = client.get(f"/api/turnitin/submissions/{sid}/report/similarity")
    assert download.status_code == 404 and b"%PDF" not in download.data
    assert _provider_calls(turnitin) == []


def test_turnitin_ledger_outage_fails_closed(turnitin, monkeypatch):
    owner = _account("owner@example.com")
    sid = turnitin.submission(owner)
    turnitin.svc.store.update(sid, similarity_report_path=str(turnitin.report_file(sid)))

    def down(_user_id):
        raise sqlite3.OperationalError("database is locked at /srv/docmaxxing/economy.db")

    monkeypatch.setattr(turnitin.app, "_turnitin_refunded_ids", down)
    client = _sign_in(_client(), owner)
    for method, path, body in _turnitin_routes(sid) + [("get", "/api/turnitin/reports", None)]:
        res = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert res.status_code == 503, path
        assert b"%PDF" not in res.data
        _no_secrets(res.get_data(as_text=True))
    assert _provider_calls(turnitin) == []


def test_turnitin_paid_owner_uses_every_route(turnitin):
    owner = _account("owner@example.com")
    sid = turnitin.submission(owner)
    client = _sign_in(_client(), owner)

    assert client.get(f"/api/turnitin/submissions/{sid}").get_json()["report"]["status"] == "completed"
    started = client.post(f"/api/turnitin/submissions/{sid}/highlights", json={})
    assert started.status_code == 200 and started.get_json()["highlights_status"] == "running"
    assert client.post(f"/api/turnitin/submissions/{sid}/highlights", json={}).status_code == 409
    fetched = client.post(f"/api/turnitin/submissions/{sid}/fetch-reports", json={"similarity": True})
    assert fetched.status_code == 200
    assert [name for name in _provider_calls(turnitin)] == ["start_plagdetect_api_highlights", "fetch_plagdetect_api_reports"]
    assert turnitin.svc.store.claim_fetch(sid, owner["id"])  # the download slot was released

    path = turnitin.report_file(sid)
    turnitin.svc.store.update(sid, similarity_report_path=str(path))
    download = client.get(f"/api/turnitin/submissions/{sid}/report/similarity")
    assert download.status_code == 200 and download.data == path.read_bytes()

    turnitin.app.wallet.credit(owner["id"], 1000, "test_topup")
    before = turnitin.app.wallet.get_balance(owner["id"])
    res = client.post("/api/turnitin/check", data={"file": (io.BytesIO(b"essay"), "essay.docx")},
                      content_type="multipart/form-data")
    assert res.status_code == 200, res.get_data(as_text=True)
    new_sid = res.get_json()["submission_id"]
    assert turnitin.svc.store.get_for_user(new_sid, owner["id"]) is not None
    (_name, _args, kwargs), = [c for c in turnitin.calls if c[0] == "start_plagdetect_api_check"]
    assert kwargs["submission_id"] == new_sid and kwargs["user_id"] == owner["id"]
    assert turnitin.app.wallet.get_balance(owner["id"]) == before - res.get_json()["coins_charged"]


def test_turnitin_forged_ids_and_paths_are_ignored(turnitin):
    owner = _account("owner@example.com")
    victim = _account("victim@example.com")
    own = turnitin.submission(owner)
    theirs = turnitin.submission(victim)
    victim_pdf = turnitin.report_file(theirs)
    turnitin.svc.store.update(theirs, similarity_report_path=str(victim_pdf))
    client = _sign_in(_client(), owner)

    forged = {"user_id": victim["id"], "submission_id": theirs, "external_id": f"ext-{theirs}",
              "report_dir": str(victim_pdf.parent), "similarity": True}
    assert client.post(f"/api/turnitin/submissions/{theirs}/fetch-reports", json=forged).status_code == 404
    assert client.post(f"/api/turnitin/submissions/{theirs}/highlights", json=forged).status_code == 404

    turnitin.svc.store.update(own, similarity_report_path=str(victim_pdf))  # row tampered to point elsewhere
    res = client.get(f"/api/turnitin/submissions/{own}/report/similarity")
    assert res.status_code == 404 and victim_pdf.read_bytes() not in res.data

    res = client.post(f"/api/turnitin/submissions/{own}/fetch-reports", json=forged)
    assert res.status_code == 200
    (_name, args, kwargs), = [c for c in turnitin.calls if c[0] == "fetch_plagdetect_api_reports"]
    assert args == (own,) and set(kwargs) == {"fetch_similarity", "fetch_ai", "fetch_highlights"}
    for bad in ({"similarity": "yes"}, {"ai": 1}, {"highlights": None}, ["similarity"], "x"):
        res = client.post(f"/api/turnitin/submissions/{own}/fetch-reports", json=bad)
        assert res.status_code == 400, bad


def test_turnitin_browser_jobs_only_target_the_callers_own_check(turnitin):
    owner = _account("owner@example.com")
    victim = _account("victim@example.com")
    own = turnitin.submission(owner, transport="browser")
    theirs = turnitin.submission(victim, transport="browser")
    turnitin.svc.store.update(own, meta_json=json.dumps({"provider": "plagdetect", "transport": "browser",
                                                         "ai_score_display": "*%"}))
    client = _sign_in(_client(), owner)
    body = {"external_id": f"ext-{theirs}", "report_dir": "/tmp", "submission_id": theirs}
    assert client.post(f"/api/turnitin/submissions/{own}/highlights", json=body).status_code == 200
    assert client.post(f"/api/turnitin/submissions/{own}/fetch-reports",
                       json={"similarity": True, "ai": False}).status_code == 200
    assert client.post(f"/api/turnitin/submissions/{theirs}/highlights", json=body).status_code == 404
    assert len(turnitin.jobs) == 2
    own_dir = str(turnitin.svc.report_dir(own))
    for job in turnitin.jobs:
        assert job["submission_id"] == own and job["external_id"] == f"ext-{own}" and job["report_dir"] == own_dir


def test_turnitin_provider_errors_are_generic_and_logged(turnitin, monkeypatch):
    owner = _account("owner@example.com")
    sid = turnitin.submission(owner)
    client = _sign_in(_client(), owner)
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(self.format(record))

    handler = _Capture()
    handler.setFormatter(logging.Formatter("%(message)s %(exc_text)s"))
    turnitin.app.app.logger.addHandler(handler)
    try:
        def explode(*_args, **_kwargs):
            raise RuntimeError(SECRET_BLOB)

        monkeypatch.setattr(turnitin.svc, "start_plagdetect_api_highlights", explode)
        monkeypatch.setattr(turnitin.svc, "fetch_plagdetect_api_reports", explode)
        monkeypatch.setattr(turnitin.svc, "start_plagdetect_api_check", explode)
        res = client.post(f"/api/turnitin/submissions/{sid}/highlights", json={})
        assert res.status_code == 502 and res.get_json()["error"] == "HIGHLIGHTS_START_FAILED"
        _no_secrets(res.get_data(as_text=True))
        assert turnitin.svc.store.get(sid)["highlights_status"] == "failed"

        res = client.post(f"/api/turnitin/submissions/{sid}/fetch-reports", json={})
        assert res.status_code == 502 and res.get_json()["error"] == "REPORT_DOWNLOAD_FAILED"
        _no_secrets(res.get_data(as_text=True))
        assert turnitin.svc.store.claim_fetch(sid, owner["id"])

        turnitin.app.wallet.credit(owner["id"], 1000, "test_topup")
        before = turnitin.app.wallet.get_balance(owner["id"])
        res = client.post("/api/turnitin/check", data={"file": (io.BytesIO(b"essay"), "essay.docx")},
                          content_type="multipart/form-data")
        assert res.status_code == 502 and res.get_json()["error"] == "CHECK_START_FAILED"
        _no_secrets(res.get_data(as_text=True))
        assert turnitin.app.wallet.get_balance(owner["id"]) == before
    finally:
        turnitin.app.app.logger.removeHandler(handler)
    assert any("hunter2" in line for line in records)  # the detail stays in the server log

    turnitin.svc.store.update(sid, status="failed", error_message="sqlite3.OperationalError: no such table: users")
    shown = client.get(f"/api/turnitin/submissions/{sid}").get_json()["report"]["errorMessage"]
    assert "sqlite" not in shown.lower() and "users" not in shown


def test_turnitin_concurrent_requests_start_the_provider_once(turnitin, monkeypatch):
    owner = _account("owner@example.com")
    sid = turnitin.submission(owner)
    starts: list[str] = []

    def slow(**_kwargs):
        starts.append("highlights")
        time.sleep(0.2)

    def slow_fetch(*_args, **_kwargs):
        starts.append("fetch")
        time.sleep(0.2)

    monkeypatch.setattr(turnitin.svc, "start_plagdetect_api_highlights", slow)
    monkeypatch.setattr(turnitin.svc, "fetch_plagdetect_api_reports", slow_fetch)
    clients = [_sign_in(_client(), owner) for _ in range(6)]

    def burst(path, body):
        barrier = threading.Barrier(len(clients))
        codes: list[int] = []

        def run(client):
            barrier.wait()
            codes.append(client.post(path, json=body).status_code)

        threads = [threading.Thread(target=run, args=(c,)) for c in clients]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return sorted(codes)

    assert burst(f"/api/turnitin/submissions/{sid}/highlights", {}) == [200] + [409] * 5
    assert burst(f"/api/turnitin/submissions/{sid}/fetch-reports", {"similarity": True}) == [200] + [409] * 5
    assert sorted(starts) == ["fetch", "highlights"]


# ====================================================================== 9. Veil rate limit

@pytest.fixture()
def veil(economy, monkeypatch):
    from services.veil_access import purchase_pass
    from services.veil_tokens import issue_token

    asked: list[dict] = []

    def reply(**kwargs):
        asked.append(kwargs)
        return "Short answer.", {"api_call_success": True}

    monkeypatch.setattr("services.claude_client.claude_enabled", lambda: True)
    monkeypatch.setattr("services.claude_client.generate_reply", reply)

    def member(email, *, paid=True):
        user = _account(email)
        if paid:
            WalletService().set_balance(user["id"], 10_000)
            purchase_pass(user["id"])
        return user, issue_token(user["id"])

    def ask(token, body=None, headers=None):
        app = _app()
        client = FlaskClient(app, app.response_class, use_cookies=False)  # the extension sends no cookie
        return client.post("/api/veil/ask", json={"text": "What is osmosis?"} if body is None else body,
                           headers={"Authorization": f"Bearer {token}", **(headers or {})})

    return SimpleNamespace(asked=asked, member=member, ask=ask)


def test_veil_over_limit_is_rejected_before_the_provider(veil, monkeypatch):
    monkeypatch.setenv("VEIL_ASK_LIMIT_PER_MINUTE", "3")
    _user, token = veil.member("student@example.com")
    assert [veil.ask(token).status_code for _ in range(3)] == [200, 200, 200]
    blocked = veil.ask(token)
    assert blocked.status_code == 429 and blocked.get_json()["error"] == "RATE_LIMITED"
    assert int(blocked.headers["Retry-After"]) >= 1 and blocked.get_json()["retry_after"] >= 1
    assert len(veil.asked) == 3


def test_veil_default_limit_and_bad_env_values(veil, monkeypatch):
    import app as app_mod

    assert app_mod.VEIL_ASK_DEFAULT_PER_MINUTE == 10
    for bad in ("0", "-5", "abc", "1e9", "", "  "):
        monkeypatch.setenv("VEIL_ASK_LIMIT_PER_MINUTE", bad)
        assert rate_limit.env_limit("VEIL_ASK_LIMIT_PER_MINUTE", 10) == 10
    monkeypatch.delenv("VEIL_ASK_LIMIT_PER_MINUTE")
    _user, token = veil.member("student@example.com")
    codes = [veil.ask(token).status_code for _ in range(11)]
    assert codes == [200] * 10 + [429] and len(veil.asked) == 10


def test_veil_spoofed_client_data_cannot_raise_the_limit(veil, monkeypatch):
    monkeypatch.setenv("VEIL_ASK_LIMIT_PER_MINUTE", "2")
    user, token = veil.member("student@example.com")
    other, other_token = veil.member("friend@example.com")
    spoof = {"text": "Q", "plan": "unlimited", "credits": 10**9, "user_id": other["id"], "limit": 1000,
             "rate_limit": 0, "pass_active": True}
    headers = {"X-Forwarded-For": "203.0.113.9", "X-Real-IP": "203.0.113.9", "X-User-Id": str(other["id"])}
    codes = [veil.ask(token, spoof, {**headers, "X-Forwarded-For": f"203.0.113.{i}"}).status_code for i in range(5)]
    assert codes == [200, 200, 429, 429, 429]
    assert veil.ask(other_token).status_code == 200  # the other account's own budget is untouched
    assert len(veil.asked) == 3 and user["id"] != other["id"]


def test_veil_concurrent_requests_cannot_bypass_the_limit(veil, monkeypatch):
    monkeypatch.setenv("VEIL_ASK_LIMIT_PER_MINUTE", "4")
    _user, token = veil.member("student@example.com")
    barrier = threading.Barrier(12)
    codes: list[int] = []

    def run():
        barrier.wait()
        codes.append(veil.ask(token).status_code)

    threads = [threading.Thread(target=run) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200] * 4 + [429] * 8
    assert len(veil.asked) == 4


def _child_hits(queue, barrier, key):
    barrier.wait()
    queue.put([rate_limit.hit(key, [(7, 60)]) is None for _ in range(5)])


def test_rate_limit_is_shared_by_separate_worker_processes(economy):
    queue = FORK.Queue()
    barrier = FORK.Barrier(4)
    procs = [FORK.Process(target=_child_hits, args=(queue, barrier, "veil_ask:user:77")) for _ in range(4)]
    for p in procs:
        p.start()
    results = [queue.get(timeout=60) for _ in procs]
    for p in procs:
        p.join(timeout=60)
    assert sum(sum(r) for r in results) == 7


def test_veil_unpaid_or_unverified_accounts_never_reach_the_provider(veil):
    _user, token = veil.member("nopass@example.com", paid=False)
    res = veil.ask(token)
    assert res.status_code == 402 and res.get_json()["error"] == "PASS_REQUIRED"
    unverified = _account("unverified@example.com", verified=False)
    from services.veil_tokens import issue_token

    res = veil.ask(issue_token(unverified["id"]))
    assert res.status_code == 403
    assert veil.ask("not-a-real-token").status_code == 401
    assert veil.asked == []


@pytest.mark.parametrize("body", [
    ["text"], "text", {"text": ["a"]}, {"text": {"a": 1}}, {"text": 5}, {"text": "Q", "extended": "true"},
    {"text": "Q", "extended": 1}, {"text": "Q", "model": ["deep"]}, {"text": "x" * 6001}, {"text": ""},
    {"text": "Q", "images": "data:image/png;base64,AAAA"},
])
def test_veil_input_is_validated_before_the_provider_and_quota(veil, monkeypatch, body):
    monkeypatch.setenv("VEIL_ASK_LIMIT_PER_MINUTE", "1")
    _user, token = veil.member("student@example.com")
    res = veil.ask(token, body)
    assert res.status_code == 400, body
    assert veil.asked == []
    assert veil.ask(token).status_code == 200  # rejected input did not use up the one allowed question


def test_veil_bearer_and_revoke_still_work(veil):
    _user, token = veil.member("student@example.com")
    assert veil.ask(token).status_code == 200
    app = _app()
    ext = FlaskClient(app, app.response_class, use_cookies=False)
    assert ext.post("/api/veil/revoke", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert veil.ask(token).status_code == 401
    assert ext.get("/api/veil/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# ====================================================================== 10. exception text never leaks

@pytest.mark.parametrize("text", [
    SECRET_BLOB, "no such table: users", "UNIQUE constraint failed: users.email", "KeyError: 'draft'", "'draft'",
    "[Errno 2] No such file or directory: '/srv/app/data/x.json'", "ANTHROPIC_API_KEY is not set",
    "Invalid API key sk-ant-api03-aaaaaaaaaaaaaaaaaaaa", "HTTPSConnectionPool(host='api.example.com')",
    "Expecting value: line 1 column 1 (char 0)", "'NoneType' object has no attribute 'get'",
    "SELECT id FROM transactions WHERE user_id = 1", "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
    "C:\\Users\\deploy\\app.py", "<html>502 Bad Gateway</html>", "ValueError", "",
])
def test_internal_exception_text_is_never_public(text):
    assert not is_public_text(text)
    assert public_text(RuntimeError(text), "Generic.") == "Generic."
    detail = admin_detail(RuntimeError(text))
    assert detail["exception_type"] == "RuntimeError"
    _no_secrets(detail["error"])


@pytest.mark.parametrize("text", [
    "Password must be at least 6 characters.", "Current password is incorrect.",
    "An account with this email already exists.", "Not enough credits.", "Project not found.",
    "Payment not confirmed. Confirm payment before research.",
])
def test_user_facing_validation_messages_stay(text):
    assert is_public_text(text) and public_text(ValueError(text)) == text


def test_unhandled_api_exception_returns_generic_json_and_logs_detail(economy, monkeypatch):
    import app as app_mod

    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(self.format(record))

    handler = _Capture()
    handler.setFormatter(logging.Formatter("%(message)s %(exc_text)s"))
    app_mod.app.logger.addHandler(handler)

    def explode(*_args, **_kwargs):
        raise RuntimeError(SECRET_BLOB)

    monkeypatch.setitem(app_mod.app.config, "PROPAGATE_EXCEPTIONS", False)
    monkeypatch.setattr("services.economy.referral.get_referral_profile", explode)
    client = _sign_in(_client(), _account("err@example.com"))
    try:
        res = client.get("/api/referral/me", headers={"Authorization": "Bearer tok_live_ABCDEFGHIJKLMNOP"})
    finally:
        app_mod.app.logger.removeHandler(handler)
    assert res.status_code == 500
    assert res.get_json() == {"success": False, "error": "INTERNAL_ERROR",
                              "message": "Something went wrong. Please try again."}
    _no_secrets(res.get_data(as_text=True))
    assert any("hunter2" in line for line in records)


def test_validation_errors_from_domain_code_are_filtered(economy, monkeypatch):
    from services.economy.referral import ReferralError

    def refuse(*_args, **_kwargs):
        raise ReferralError(SECRET_BLOB)

    monkeypatch.setattr("services.economy.referral.get_referral_profile", refuse)
    client = _sign_in(_client(), _account("err@example.com"))
    res = client.get("/api/referral/me")
    assert res.status_code == 400
    _no_secrets(res.get_data(as_text=True))

    def polite(*_args, **_kwargs):
        raise ReferralError("Referral program is paused.")

    monkeypatch.setattr("services.economy.referral.get_referral_profile", polite)
    assert client.get("/api/referral/me").get_json()["error"] == "Referral program is paused."


def test_pipeline_stage_failures_store_generic_text():
    from services.assignment_pipeline.handlers import StageHandlerRegistry
    from services.assignment_pipeline.service import AssignmentPipelineService
    from services.assignment_pipeline.stages import PIPELINE_STAGES

    class _Broken:
        stage = PIPELINE_STAGES[0]

        def run(self, _context):
            raise RuntimeError(SECRET_BLOB)

    registry = StageHandlerRegistry()
    registry.register(_Broken())
    service = AssignmentPipelineService(handlers=registry)
    project = service.create_project()
    failed = service.run_stage(project.id, _Broken.stage)
    text = json.dumps(failed.to_dict())
    _no_secrets(text)
    assert "This step failed. Please try again." in text


def test_llm_errors_use_fixed_messages():
    from services.llm_errors import user_friendly_llm_error

    for raw in (SECRET_BLOB, "Your credit balance is too low (org-abc123)", "429 rate limit for key sk-ant-xyz",
                "HTTPSConnectionPool read timeout https://api.anthropic.com"):
        message = user_friendly_llm_error(raw)
        _no_secrets(message)
        assert "sk-" not in message and "org-" not in message and "anthropic.com" not in message


def test_credentials_cookies_and_tokens_are_not_logged(economy):
    import app as app_mod

    _account("logs@example.com")
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            try:
                records.append(self.format(record))
            except Exception:  # noqa: BLE001
                records.append(str(record.msg))

    handler = _Capture(level=logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(name)s %(message)s %(exc_text)s"))
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    app_mod.app.logger.addHandler(handler)
    try:
        client = _raw()
        token = _token(client)
        client.post("/api/auth/login", json={"email": "logs@example.com", "password": "Wr0ng-Pa55-Unique"},
                    headers={HDR: token})
        _login(client, "logs@example.com")
        cookie = _session_cookie(client)
        client.post("/api/account/password", json={"current_password": "secret123", "new_password": NEW_PASSWORD,
                                                   "confirm_password": NEW_PASSWORD}, headers={HDR: _token(client)})
        FlaskClient(_app(), _app().response_class, use_cookies=False).post(
            "/api/veil/ask", json={"text": "hi"}, headers={"Authorization": "Bearer tok_live_ABCDEFGHIJKLMNOP"})
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
        app_mod.app.logger.removeHandler(handler)
    blob = "\n".join(records)
    for secret in ("Wr0ng-Pa55-Unique", "secret123", NEW_PASSWORD, cookie, token, "tok_live_ABCDEFGHIJKLMNOP"):
        assert secret not in blob
