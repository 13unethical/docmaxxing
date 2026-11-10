"""Patch 4C: Veil tokens, ADMIN_EMAIL, password and OTP brute force, and secrets in logs.

Audit findings: F-03 / F-03b (Veil tokens without expiry or revocation; GET mints tokens),
F-04 (registering ADMIN_EMAIL made a verified admin), F-07 (no login / OTP attempt limits,
non-constant-time OTP compare), F-08 (OTP in logs), resend without limits.

Concurrent workers are forked processes (separate gunicorn workers); a worker restart is a fresh
interpreter on the same database. Email, Claude, Telegram and the browser humanizer are traps or
fakes: nothing leaves the machine.
"""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import re
import subprocess
import sys
import threading
import traceback
from types import SimpleNamespace

import pytest

from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy.wallet import WalletService
from services.veil_tokens import issue_token, revoke_user_tokens, user_for_token
from tests.test_extension_humanize import _patch_humanizer
from tests.test_security_paid_pipelines import _client, _signed_in, _user, economy  # noqa: F401

FORK = multiprocessing.get_context("fork")
WAIT = 60
PASSWORD = "secret123"
ATTACKER_IP = "203.0.113.50"

_ENV_KNOBS = (
    "ADMIN_EMAIL", "MAIL_SERVER", "EXPOSE_VERIFY_CODE", "TRUSTED_PROXIES", "VEIL_TOKEN_TTL_DAYS",
    "LOGIN_MAX_FAILURES_PER_ACCOUNT", "LOGIN_MAX_FAILURES_PER_IP", "LOGIN_FAILURE_WINDOW_SECONDS",
    "OTP_MAX_ATTEMPTS", "OTP_RESEND_LIMIT_PER_HOUR", "OTP_RESEND_LIMIT_PER_DAY",
    "OTP_RESEND_LIMIT_PER_IP_HOUR", "OTP_VERIFY_LIMIT_PER_IP_15MIN",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENV_KNOBS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def traps(economy, monkeypatch):
    """Every outbound integration an auth flow could reach records the call instead."""
    import app as app_mod

    calls: list[tuple[str, str]] = []
    sent = threading.Event()

    def _smtp(to_email, subject, text_body, html_body):
        calls.append(("smtp", text_body))
        sent.set()

    def _forbidden(name):
        def _call(*args, **kwargs):
            calls.append((name, repr(args)[:200]))
            raise AssertionError(f"{name} must not be called")

        return _call

    def _codes():
        found = (re.search(r"code is: (\d{6})", body) for name, body in calls if name == "smtp")
        return [m.group(1) for m in found if m]

    monkeypatch.setattr("services.economy.email_verify._smtp_send", _smtp)
    monkeypatch.setattr("services.claude_client.generate_reply", _forbidden("claude"))
    monkeypatch.setattr(app_mod, "_send_telegram_text", _forbidden("telegram"))
    _patch_humanizer(monkeypatch)  # the browser humanizer is a fake job, never Chrome
    # Its dataset hook writes from a background thread that could outlive this test's database.
    monkeypatch.setattr("services.dataset_logger.log_humanization_event", lambda *_a, **_k: None)
    return SimpleNamespace(calls=calls, sent=sent, codes=_codes)


def _api_login(client, email, password, *, ip=ATTACKER_IP, headers=None):
    return client.post("/api/auth/login", json={"email": email, "password": password},
                       environ_base={"REMOTE_ADDR": ip}, headers=headers or {})


def _html_login(client, email, password, *, ip=ATTACKER_IP):
    return client.post("/login", data={"email": email, "password": password},
                       environ_base={"REMOTE_ADDR": ip})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _row(sql, *args):
    with economy_db.connect() as conn:
        return conn.execute(sql, args).fetchone()


def _exec(sql, *args):
    with economy_db.connect() as conn:
        conn.execute(sql, args)


def _db_dump() -> str:
    with economy_db.connect() as conn:
        return "\n".join(conn.iterdump())


def _log_text(caplog) -> str:
    fmt = logging.Formatter("%(name)s %(levelname)s %(message)s")
    return "\n".join(fmt.format(record) for record in caplog.records)


def _child(fn, args):
    code = 0
    try:
        fn(*args)
    except BaseException:  # noqa: BLE001
        traceback.print_exc()
        code = 1
    finally:
        os._exit(code)


def _run_workers(fn, n, *extra):
    """``fn(i, barrier, queue, *extra)`` in n forked workers released together; returns results."""
    barrier = FORK.Barrier(n)
    queue = FORK.SimpleQueue()
    procs = [FORK.Process(target=_child, args=(fn, (i, barrier, queue, *extra))) for i in range(n)]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(WAIT)
        if proc.is_alive():
            proc.kill()
            proc.join(WAIT)
            pytest.fail("worker hung")
        assert proc.exitcode == 0, f"worker failed with exit code {proc.exitcode}"
    results = []
    while not queue.empty():
        results.append(queue.get())
    assert len(results) == n
    return results


def _fresh_interpreter(code: str) -> dict:
    """Run ``code`` in a new Python process (a restarted worker) on the same database."""
    env = dict(os.environ)
    env["ECONOMY_DB_PATH"] = str(economy_db.DB_PATH)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [os.getcwd(), env.get("PYTHONPATH", "")]))
    out = subprocess.run(
        [sys.executable, "-c", "import json, sys\n" + code],
        env=env, capture_output=True, text=True, timeout=120, cwd=os.getcwd(),
    )
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _connect_token(client) -> str:
    res = client.post("/api/veil/connect")
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()["token"]


def _veil_routes(client, token):
    """Every route that accepts a Veil bearer token; returns status codes."""
    return {
        "me": client.get("/api/veil/me", headers=_bearer(token)).status_code,
        "ask": client.post("/api/veil/ask", json={"text": "What is 2+2?"}, headers=_bearer(token)).status_code,
        "humanize": client.post("/api/extension/humanize", json={"text": "Rewrite me please."},
                                headers=_bearer(token)).status_code,
        "humanize_key": client.post("/api/extension/humanize",
                                    json={"text": "Rewrite me please.", "key": token}).status_code,
    }


ALL_401 = {"me": 401, "ask": 401, "humanize": 401, "humanize_key": 401}


# =============================================================== Veil tokens (F-03, F-03b)


def test_01_forged_tokens_are_rejected_everywhere(traps, monkeypatch):
    monkeypatch.setattr("services.claude_client.claude_enabled", lambda: True)
    user = _user("veil-owner@example.com")
    real = issue_token(user["id"])
    stored_hash = _row("SELECT token_hash FROM extension_tokens WHERE user_id = ?", user["id"])["token_hash"]
    client = _client()
    forged = [
        "A" * 43,
        real[:-1] + ("A" if real[-1] != "A" else "B"),
        real.upper() if real.upper() != real else real.lower(),
        stored_hash,  # the database value is not a credential
        str(user["id"]),
        "x" * 5000,
        "",
    ]
    for token in forged:
        assert _veil_routes(client, token) == ALL_401, token
    assert client.get("/api/veil/me").status_code == 401
    assert client.get("/api/veil/me", headers={"Authorization": real}).status_code == 401
    assert [c for c in traps.calls if c[0] != "smtp"] == []


def test_02_another_users_token_acts_only_as_that_user_and_is_not_retrievable(traps):
    alice = _user("alice@example.com")
    bob = _user("bob@example.com")
    alice_client = _signed_in(_client(), alice)
    bob_client = _signed_in(_client(), bob)
    alice_token = _connect_token(alice_client)

    # Bob's session plus Alice's token is Alice (the bearer token is the whole credential) ...
    me = bob_client.get("/api/veil/me", headers=_bearer(alice_token)).get_json()
    assert me["email"] == "alice@example.com"
    # ... and Bob cannot obtain or rotate Alice's token with forged identifiers.
    res = bob_client.post("/api/veil/connect", json={"user_id": alice["id"], "email": "alice@example.com"},
                          headers={"X-User-Id": str(alice["id"])})
    bob_token = res.get_json()["token"]
    assert user_for_token(bob_token)["id"] == bob["id"]
    assert user_for_token(alice_token)["id"] == alice["id"]  # untouched by Bob's connect
    assert bob_token != alice_token
    with economy_db.connect() as conn:
        live = conn.execute("SELECT user_id FROM extension_tokens WHERE revoked = 0 ORDER BY user_id").fetchall()
    assert [r["user_id"] for r in live] == [alice["id"], bob["id"]]


def test_03_token_is_not_a_session_or_project_credential(traps):
    user = _user("proj-owner@example.com")
    token = issue_token(user["id"])
    client = _client()
    for method, path in [
        ("get", "/api/assignment/projects"),
        ("get", "/api/assignment/projects/0123456789abcdef0123"),
        ("post", "/api/veil/unlock"),
        ("post", "/api/veil/connect"),
        ("post", "/api/account/profile"),
        ("get", "/api/admin/users"),
    ]:
        res = getattr(client, method)(path, headers=_bearer(token), json={})
        assert res.status_code in (401, 403), (path, res.status_code)
        assert token not in res.get_data(as_text=True)
    page = client.get("/veil/connect", headers=_bearer(token), follow_redirects=False)
    assert page.status_code in (301, 302)


def test_04_expired_tokens_are_rejected(traps, monkeypatch):
    user = _user("expiry@example.com")
    client = _client()
    token = issue_token(user["id"])
    row = _row("SELECT expires_at, created_at FROM extension_tokens WHERE revoked = 0")
    assert row["expires_at"] > row["created_at"]
    assert client.get("/api/veil/me", headers=_bearer(token)).status_code == 200

    _exec("UPDATE extension_tokens SET expires_at = datetime('now', '-1 second')")
    assert user_for_token(token) is None
    assert _veil_routes(client, token) == ALL_401

    # A row without an expiry never authenticates.
    token2 = issue_token(user["id"])
    _exec("UPDATE extension_tokens SET expires_at = NULL WHERE revoked = 0")
    assert user_for_token(token2) is None

    # The TTL is configurable and bounded.
    monkeypatch.setenv("VEIL_TOKEN_TTL_DAYS", "2")
    issue_token(user["id"])
    days = _row("SELECT julianday(expires_at) - julianday(created_at) AS d FROM extension_tokens WHERE revoked = 0")["d"]
    assert 1.9 < days < 2.1


def test_04b_legacy_tokens_get_an_expiry_and_revoked_rows_stay_revoked(economy):
    user = _user("legacy@example.com")
    import hashlib

    def _legacy(raw, *, age_days, revoked):
        _exec(
            "INSERT INTO extension_tokens (user_id, token_hash, created_at, revoked, expires_at) "
            "VALUES (?, ?, datetime('now', ?), ?, NULL)",
            user["id"], hashlib.sha256(raw.encode()).hexdigest(), f"-{age_days} days", revoked,
        )

    old_live = "L" * 43
    old_revoked = "R" * 43
    _legacy(old_revoked, age_days=1, revoked=1)
    _legacy(old_live, age_days=40, revoked=0)
    economy_db.init_db()
    assert user_for_token(old_live) is None  # created 40 days ago: past the 30-day default
    assert user_for_token(old_revoked) is None
    assert _row("SELECT revoked FROM extension_tokens WHERE token_hash = ?",
                hashlib.sha256(old_revoked.encode()).hexdigest())["revoked"] == 1

    _exec("DELETE FROM extension_tokens")
    _exec("DROP INDEX idx_extension_tokens_one_live")
    recent_a, recent_b = "A" * 43, "B" * 43
    _legacy(recent_a, age_days=2, revoked=0)
    _legacy(recent_b, age_days=1, revoked=0)
    economy_db.init_db()
    assert user_for_token(recent_a) is None  # duplicate live rows: only the newest survives
    assert user_for_token(recent_b)["id"] == user["id"]
    economy_db.init_db()
    assert user_for_token(recent_a) is None


def test_05_revocation_is_enforced_and_never_undone(traps):
    user = _user("revoke@example.com")
    client = _signed_in(_client(), user)

    token = _connect_token(client)
    assert client.post("/api/veil/revoke", headers=_bearer(token)).status_code == 200
    assert _veil_routes(client, token) == ALL_401

    token = _connect_token(client)
    assert client.post("/api/account/password", json={
        "current_password": PASSWORD, "new_password": "newsecret1", "confirm_password": "newsecret1",
    }).status_code == 200
    assert user_for_token(token) is None

    token = _connect_token(client)
    economy_auth.end_all_sessions(user["id"])
    assert user_for_token(token) is None

    token = issue_token(user["id"])
    _exec("UPDATE users SET is_blocked = 1 WHERE id = ?", user["id"])
    assert user_for_token(token) is None
    _exec("UPDATE users SET is_blocked = 0 WHERE id = ?", user["id"])
    assert user_for_token(token) is None  # unblocking does not bring the token back

    token = issue_token(user["id"])
    _exec("UPDATE users SET is_verified = 0 WHERE id = ?", user["id"])
    assert user_for_token(token) is None
    _exec("UPDATE users SET is_verified = 1 WHERE id = ?", user["id"])
    assert user_for_token(token) is None

    token = issue_token(user["id"])
    revoke_user_tokens(user["id"])
    assert user_for_token(token) is None
    economy_db.init_db()
    assert user_for_token(token) is None
    assert _row("SELECT COUNT(*) AS n FROM extension_tokens WHERE revoked = 0")["n"] == 0


def test_05b_blocked_account_token_is_rejected_even_if_the_row_is_live(traps):
    user = _user("blocked@example.com")
    token = issue_token(user["id"])
    with economy_db.connect() as conn:
        conn.execute("DROP TRIGGER trg_extension_tokens_user_blocked")
        conn.execute("UPDATE users SET is_blocked = 1 WHERE id = ?", (user["id"],))
    assert _row("SELECT revoked FROM extension_tokens")["revoked"] == 0
    assert _veil_routes(_client(), token) == ALL_401


def test_06_rotation_keeps_one_live_token_and_get_never_rotates(traps):
    user = _user("rotate@example.com")
    client = _signed_in(_client(), user)
    first = _connect_token(client)
    for _ in range(3):
        assert client.get("/veil/connect").status_code == 200
    assert user_for_token(first)["id"] == user["id"]  # GET (any link) neither mints nor revokes
    second = _connect_token(client)
    assert user_for_token(first) is None
    assert user_for_token(second)["id"] == user["id"]
    assert _row("SELECT COUNT(*) AS n FROM extension_tokens WHERE revoked = 0")["n"] == 1
    with pytest.raises(Exception):
        _exec("INSERT INTO extension_tokens (user_id, token_hash, expires_at) "
              "VALUES (?, 'dup', datetime('now', '+1 day'))", user["id"])


def test_06b_connect_requires_session_csrf_and_verified_email(traps):
    from flask.testing import FlaskClient

    import app as app_mod

    verified = _user("csrf-veil@example.com")
    pending = _user("pending-veil@example.com", verified=False)
    assert _client().post("/api/veil/connect").status_code == 401
    assert _signed_in(_client(), pending).post("/api/veil/connect").status_code == 403
    plain = FlaskClient(app_mod.app, app_mod.app.response_class, use_cookies=True)
    with plain.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = verified["id"]
        sess[economy_auth.AUTH_SID_KEY] = economy_auth.register_session(verified["id"])
    assert plain.post("/api/veil/connect").status_code == 403  # no CSRF token
    assert _row("SELECT COUNT(*) AS n FROM extension_tokens")["n"] == 0


def test_07_replayed_old_tokens_stay_dead(traps):
    user = _user("replay@example.com")
    client = _signed_in(_client(), user)
    old = _connect_token(client)
    new = _connect_token(client)
    for _ in range(3):
        assert _veil_routes(client, old) == ALL_401
    assert client.get("/api/veil/me", headers=_bearer(new)).status_code == 200
    assert client.get("/api/veil/me", headers=_bearer(f"  {new}  ")).status_code == 200
    assert client.post("/api/veil/revoke", headers=_bearer(new)).status_code == 200
    for _ in range(3):
        assert client.get("/api/veil/me", headers=_bearer(new)).status_code == 401


def _issue_worker(i, barrier, queue, user_ids):
    barrier.wait(WAIT)
    queue.put((user_ids[i % len(user_ids)], issue_token(user_ids[i % len(user_ids)])))


def test_08_concurrent_issuing_leaves_exactly_one_live_token_per_account(traps):
    users = [_user("c1@example.com")["id"], _user("c2@example.com")["id"]]
    results = _run_workers(_issue_worker, 12, users)
    assert len({token for _uid, token in results}) == 12
    for uid in users:
        live = [t for u, t in results if u == uid and user_for_token(t) is not None]
        assert len(live) == 1
        assert user_for_token(live[0])["id"] == uid
        assert _row("SELECT COUNT(*) AS n FROM extension_tokens WHERE user_id = ? AND revoked = 0", uid)["n"] == 1


def test_09_revocation_and_expiry_survive_a_worker_restart(traps):
    user = _user("restart@example.com")
    revoked = issue_token(user["id"])
    live = issue_token(user["id"])
    expired_user = _user("restart-exp@example.com")
    expired = issue_token(expired_user["id"])
    _exec("UPDATE extension_tokens SET expires_at = datetime('now', '-1 minute') WHERE user_id = ?", expired_user["id"])
    out = _fresh_interpreter(
        "from services.economy.db import init_db\n"
        "from services.veil_tokens import user_for_token\n"
        "init_db()\n"
        f"r = {{k: (user_for_token(v) or {{}}).get('id') for k, v in "
        f"{{'revoked': {revoked!r}, 'live': {live!r}, 'expired': {expired!r}}}.items()}}\n"
        "print(json.dumps(r))\n"
    )
    assert out == {"revoked": None, "live": user["id"], "expired": None}


def test_10_tokens_are_random_and_never_leak_into_pages_storage_or_errors(traps, caplog):
    caplog.set_level(logging.DEBUG)
    tokens = {issue_token(_user(f"rand{i}@example.com")["id"]) for i in range(3)}
    import services.veil_tokens as vt

    many = {vt.secrets.token_urlsafe(32) for _ in range(500)}
    assert len(many) == 500 and all(len(t) >= 43 for t in many | tokens)

    user = _user("leak@example.com")
    client = _signed_in(_client(), user)
    page = client.get("/veil/connect").get_data(as_text=True)
    token = _connect_token(client)
    assert token not in page
    bodies = []
    for bad in (token[:-2] + "zz", "SYNTHBEARER4C" + "q" * 30):
        for res in (
            client.get("/api/veil/me", headers=_bearer(bad)),
            client.post("/api/veil/ask", json={"text": "hi"}, headers=_bearer(bad)),
            client.post("/api/extension/humanize", json={"text": "hi", "key": bad}),
        ):
            bodies.append(res.get_data(as_text=True))
            assert bad not in bodies[-1]
    client.post("/api/veil/revoke", headers=_bearer(token))
    for res in (client.get("/api/veil/me", headers=_bearer(token)),
                client.post("/api/veil/ask", json={"text": "hi"}, headers=_bearer(token))):
        assert token not in res.get_data(as_text=True)
    assert token not in _db_dump()
    assert "SYNTHBEARER4C" not in _db_dump()
    assert token not in _log_text(caplog)
    assert "SYNTHBEARER4C" not in _log_text(caplog)


def test_10b_legitimate_extension_flow(traps, monkeypatch):
    _patch_humanizer(monkeypatch, text_out="A natural paragraph.")
    user = _user("extension@example.com")
    WalletService().set_balance(user["id"], 500)
    client = _signed_in(_client(), user)
    assert client.get("/veil/connect").status_code == 200
    token = _connect_token(client)
    ext = _client()  # the extension carries no cookies
    me = ext.get("/api/veil/me", headers=_bearer(token))
    assert me.status_code == 200 and me.get_json()["email"] == user["email"]
    res = ext.post("/api/extension/humanize", json={"text": "Please rewrite this paragraph now."},
                   headers=_bearer(token))
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["humanized_text"] == "A natural paragraph."
    res = ext.post("/api/extension/humanize", json={"text": "Please rewrite this paragraph now.", "key": token})
    assert res.status_code == 200
    assert ext.post("/api/veil/revoke", headers=_bearer(token)).status_code == 200
    assert ext.get("/api/veil/me", headers=_bearer(token)).status_code == 401


# =============================================================== ADMIN_EMAIL (F-04) and admin rule


def _admin_api(client):
    return client.get("/api/admin/users").status_code


def test_11_admin_email_alone_never_grants_admin(traps, monkeypatch):
    from services.economy.admin import bootstrap_admin_from_env

    monkeypatch.setenv("ADMIN_EMAIL", "owner@example.com")
    client = _client()
    res = client.post("/api/auth/register", json={
        "email": "Owner@Example.com", "password": PASSWORD, "password_confirm": PASSWORD,
    })
    assert res.status_code == 200
    body = res.get_json()
    assert body["user"]["is_admin"] is False
    assert body["email_verification_required"] is True
    row = _row("SELECT id, is_admin, is_verified FROM users WHERE email = 'owner@example.com'")
    assert (row["is_admin"], row["is_verified"]) == (0, 0)
    assert _admin_api(client) == 403

    # Even once the address is verified, the env value grants nothing (at startup or later).
    economy_auth.mark_email_verified(row["id"])
    bootstrap_admin_from_env()
    assert _row("SELECT is_admin FROM users WHERE id = ?", row["id"])["is_admin"] == 0
    assert _admin_api(client) == 403

    # An ordinary account after ADMIN_EMAIL is changed to its address.
    plain = _user("plain@example.com")
    monkeypatch.setenv("ADMIN_EMAIL", "plain@example.com")
    bootstrap_admin_from_env()
    assert economy_auth.is_admin(economy_auth.get_user(plain["id"])) is False
    assert _admin_api(_signed_in(_client(), plain)) == 403


def test_12_verified_database_admin_keeps_access(traps, monkeypatch):
    from services.economy.admin import bootstrap_admin_from_env

    admin = _user("boss@example.com", admin=True)
    monkeypatch.setenv("ADMIN_EMAIL", "someone-else@example.com")
    bootstrap_admin_from_env()
    client = _signed_in(_client(), admin)
    assert _admin_api(client) == 200
    assert client.get("/admin").status_code == 200
    login = _api_login(_client(), "boss@example.com", PASSWORD)
    assert login.get_json()["user"]["is_admin"] is True


def test_13_unverified_database_admin_is_denied(traps):
    admin = _user("unverified-admin@example.com", admin=True, verified=False)
    assert economy_auth.get_user(admin["id"])["is_admin"] is True
    client = _signed_in(_client(), admin)
    assert _admin_api(client) == 403
    assert economy_auth.is_admin(economy_auth.get_user(admin["id"])) is False


def test_14_revoked_admin_is_denied_within_the_same_session(traps):
    admin = _user("revoked-admin@example.com", admin=True)
    client = _signed_in(_client(), admin)
    assert _admin_api(client) == 200
    _exec("UPDATE users SET is_admin = 0 WHERE id = ?", admin["id"])
    assert _admin_api(client) == 403
    _exec("UPDATE users SET is_admin = 1, is_verified = 0 WHERE id = ?", admin["id"])
    assert _admin_api(client) == 403
    _exec("UPDATE users SET is_verified = 1, is_blocked = 1 WHERE id = ?", admin["id"])
    assert _admin_api(client) == 401
    _exec("UPDATE users SET is_blocked = 0 WHERE id = ?", admin["id"])
    assert _admin_api(_signed_in(_client(), admin)) == 200


def _guarded(app_mod, guard, user):
    from flask import session

    with app_mod.app.test_request_context("/api/guard-probe", environ_base={"REMOTE_ADDR": "203.0.113.9"}):
        if user is not None:
            session[economy_auth.SESSION_KEY] = user["id"]
            session[economy_auth.AUTH_SID_KEY] = economy_auth.register_session(user["id"])
            session["email"] = "owner@example.com"
            session["is_admin"] = True
        return guard(lambda: "OK")() == "OK"


def test_15_every_admin_guard_applies_the_same_rule(traps, monkeypatch):
    import app as app_mod

    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    monkeypatch.setenv("ADMIN_EMAIL", "owner@example.com")
    accounts = {
        "verified_admin": (_user("va@example.com", admin=True), True),
        "unverified_admin": (_user("ua@example.com", admin=True, verified=False), False),
        "admin_email_owner": (_user("owner@example.com"), False),
        "ordinary": (_user("ord@example.com"), False),
        "guest": (None, False),
    }
    guards = {
        "admin_required": economy_auth.admin_required,
        "admin_only": app_mod.admin_only,
        "internal_tool": app_mod.internal_tool,
    }
    for gname, guard in guards.items():
        for aname, (user, allowed) in accounts.items():
            assert _guarded(app_mod, guard, user) is allowed, (gname, aname)

    # The real routes behind each guard, for the denied accounts.
    for aname, (user, allowed) in accounts.items():
        if allowed:
            continue
        client = _signed_in(_client(), user) if user else _client()
        assert client.get("/api/admin/users").status_code in (401, 403), aname
        assert client.get("/api/browser/health").status_code == 404, aname
        assert client.get("/api/debug/blueprint/0123456789abcdef0123").status_code == 404, aname
        assert client.post("/api/admin/assignment/projects/0123456789abcdef0123/refund",
                           json={}).status_code == 404, aname


def test_16_no_client_controlled_identity_grants_admin(traps, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "owner@example.com")
    user = _user("intruder@example.com")
    client = _signed_in(_client(), user)
    with client.session_transaction() as sess:
        sess["email"] = "owner@example.com"
        sess["is_admin"] = True
        sess["admin"] = 1
    forged = {"X-Admin": "1", "X-User-Email": "owner@example.com", "X-Forwarded-User": "owner@example.com"}
    assert client.get("/api/admin/users", headers=forged).status_code == 403
    assert client.patch(f"/api/admin/users/{user['id']}/admin", json={"is_admin": True, "email": "owner@example.com"},
                        headers=forged).status_code == 403
    assert client.post("/api/account/profile", json={"name": "x", "is_admin": True, "email": "owner@example.com"}
                       ).status_code == 200
    row = _row("SELECT email, is_admin FROM users WHERE id = ?", user["id"])
    assert (row["email"], row["is_admin"]) == ("intruder@example.com", 0)
    assert _admin_api(client) == 403


# =============================================================== passwords (F-07)


def _count_password_checks(monkeypatch):
    seen = []
    real = economy_auth.check_password_hash

    def _check(pwhash, password):
        seen.append(1)
        return real(pwhash, password)

    monkeypatch.setattr(economy_auth, "check_password_hash", _check)
    return seen


def test_17_password_failures_hit_a_bounded_threshold(traps, monkeypatch):
    _user("victim@example.com")
    checks = _count_password_checks(monkeypatch)
    client = _client()
    for _ in range(5):
        assert _api_login(client, "victim@example.com", "wrong-pass").status_code == 401
    assert len(checks) == 5
    blocked = _api_login(client, "victim@example.com", PASSWORD)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert len(checks) == 5  # refused before any password work
    assert _api_login(client, "victim@example.com", PASSWORD, ip="198.51.100.9").status_code == 429

    # Bounded: once the window passes the right password works again.
    _exec("UPDATE auth_failures SET ts = ts - 901")
    assert _api_login(client, "victim@example.com", PASSWORD).status_code == 200
    assert [c for c in traps.calls] == []


def _login_worker(i, barrier, queue):
    client = _client()
    barrier.wait(WAIT)
    res = _api_login(client, "shared@example.com", f"wrong-{i}", ip=f"198.51.100.{i + 1}")
    queue.put(res.status_code)


def test_18_failure_limit_is_shared_by_concurrent_workers(traps):
    _user("shared@example.com")
    statuses = _run_workers(_login_worker, 12)
    assert sorted(statuses) == [401] * 5 + [429] * 7
    assert _row("SELECT COUNT(*) AS n FROM auth_failures WHERE key LIKE 'login:acct:%'")["n"] == 5


def test_18b_lockout_survives_a_worker_restart(traps):
    _user("persist@example.com")
    client = _client()
    for _ in range(5):
        _api_login(client, "persist@example.com", "wrong-pass")
    out = _fresh_interpreter(
        "from services.economy import login_throttle\n"
        "r = login_throttle.begin('login', 'persist@example.com', '192.0.2.200')\n"
        "print(json.dumps({'wait': r if isinstance(r, int) else None}))\n"
    )
    assert out["wait"] and out["wait"] > 0
    assert _api_login(client, "persist@example.com", PASSWORD).status_code == 429


def test_19_account_identifier_is_normalised(traps):
    _user("norm@example.com")
    client = _client()
    for variant in ("Norm@Example.com", " norm@example.com ", "NORM@EXAMPLE.COM", "norm@EXAMPLE.com", "norm@example.com"):
        assert _api_login(client, variant, "wrong-pass", ip=f"198.51.100.{len(variant)}").status_code == 401
    assert _api_login(client, "nOrM@example.COM", PASSWORD, ip="192.0.2.77").status_code == 429


def test_20_spoofed_forwarding_headers_do_not_change_the_source(traps, monkeypatch):
    monkeypatch.setenv("LOGIN_MAX_FAILURES_PER_IP", "8")
    client = _client()
    for i in range(8):
        spoof = {"X-Forwarded-For": f"10.0.{i}.1", "X-Real-IP": f"10.1.{i}.1", "CF-Connecting-IP": f"10.2.{i}.1"}
        assert _api_login(client, f"user{i}@example.com", "x", ip=ATTACKER_IP, headers=spoof).status_code == 401
    spoof = {"X-Forwarded-For": "10.9.9.9", "X-Real-IP": "10.9.9.8"}
    assert _api_login(client, "fresh@example.com", "x", ip=ATTACKER_IP, headers=spoof).status_code == 429
    assert _api_login(client, "fresh@example.com", "x", ip="198.51.100.200").status_code == 401

    # Behind the trusted proxy, only the address nginx sets counts, not client-supplied XFF hops.
    for i in range(8):
        assert _api_login(client, f"p{i}@example.com", "x", ip="127.0.0.1",
                          headers={"X-Real-IP": "192.0.2.10", "X-Forwarded-For": f"10.3.{i}.1"}).status_code == 401
    assert _api_login(client, "p9@example.com", "x", ip="127.0.0.1",
                      headers={"X-Real-IP": "192.0.2.10", "X-Forwarded-For": "10.4.0.1"}).status_code == 429


def test_21_successful_login_resets_the_account_counter(traps):
    owner = _user("recover@example.com")
    client = _client()
    for _ in range(4):
        assert _api_login(client, "recover@example.com", "wrong-pass").status_code == 401
    assert _api_login(client, "recover@example.com", PASSWORD).status_code == 200
    economy_auth.end_all_sessions(owner["id"])
    client = _client()
    for _ in range(5):
        assert _api_login(client, "recover@example.com", "wrong-pass").status_code == 401
    assert _api_login(client, "recover@example.com", PASSWORD).status_code == 429
    _exec("UPDATE auth_failures SET ts = ts - 901")
    assert _api_login(client, "recover@example.com", PASSWORD).status_code == 200


def test_22_unknown_and_existing_emails_look_the_same(traps, monkeypatch):
    _user("exists@example.com")
    checks = _count_password_checks(monkeypatch)
    client = _client()
    known = [_api_login(client, "exists@example.com", "wrong-pass") for _ in range(6)]
    unknown = [_api_login(client, "ghost@example.com", "wrong-pass", ip="198.51.100.3") for _ in range(6)]
    assert [r.status_code for r in known] == [r.status_code for r in unknown] == [401] * 5 + [429]
    assert [r.get_json() for r in known] == [r.get_json() for r in unknown]
    assert len(checks) == 10  # unknown emails pay for a hash check too
    _user("exists2@example.com")
    html_known = _html_login(_client(), "exists2@example.com", "x", ip="198.51.100.4")
    html_unknown = _html_login(_client(), "ghost2@example.com", "x", ip="198.51.100.5")
    assert html_known.status_code == html_unknown.status_code == 401
    assert b"Incorrect email or password." in html_known.data
    assert b"Incorrect email or password." in html_unknown.data


def test_23_alternate_password_paths_share_the_limits(traps):
    user = _user("alt@example.com")
    client = _client()
    for _ in range(2):
        assert _html_login(client, "alt@example.com", "wrong-pass").status_code == 401
    for _ in range(3):
        assert _api_login(client, "alt@example.com", "wrong-pass").status_code == 401
    assert _html_login(client, "alt@example.com", PASSWORD).status_code == 429
    assert _api_login(client, "alt@example.com", PASSWORD).status_code == 429

    # Changing the password re-checks the current one: same limits, per account.
    other = _user("alt2@example.com")
    session_client = _signed_in(_client(), other)
    body = {"new_password": "brandnew1", "confirm_password": "brandnew1"}
    short = {"current_password": "wrong", "new_password": "x", "confirm_password": "x"}
    assert session_client.post("/api/account/password", json=short).status_code == 400  # not a guess
    for _ in range(5):
        res = session_client.post("/api/account/password", json={**body, "current_password": "wrong"})
        assert res.status_code == 400
    res = session_client.post("/api/account/password", json={**body, "current_password": PASSWORD})
    assert res.status_code == 429
    page = session_client.post("/account", data={"action": "password", "current_password": PASSWORD,
                                                  "new_password": "brandnew1", "confirm_password": "brandnew1"})
    assert b"Too many" in page.data
    assert economy_auth.verify_credentials("alt2@example.com", PASSWORD) is not None
    assert user["id"] != other["id"]
    assert traps.calls == []


# =============================================================== OTP (F-07, F-08, resend)


def _pending(email="otp@example.com"):
    return _user(email, verified=False)


def _submit(client, code, *, ip=ATTACKER_IP, **extra):
    return client.post("/verify-email/code", data={"action": "verify", "code": code, **extra},
                       environ_base={"REMOTE_ADDR": ip})


def _resend(client, *, ip=ATTACKER_IP):
    return client.post("/verify-email/code", data={"action": "resend"}, environ_base={"REMOTE_ADDR": ip})


def _wrong(code):
    return f"{(int(code) + 1) % 1_000_000:06d}"


def _verified(uid):
    return bool(_row("SELECT is_verified FROM users WHERE id = ?", uid)["is_verified"])


def test_24_invalid_attempts_are_bounded_per_code(traps):
    user = _pending()
    client = _signed_in(_client(), user)
    code = economy_auth.issue_verification_otp(user["id"])
    for i in range(4):
        assert b"Incorrect code" in _submit(client, _wrong(code)).data
    assert b"Too many incorrect codes" in _submit(client, _wrong(code)).data
    assert _row("SELECT verification_code FROM users WHERE id = ?", user["id"])["verification_code"] is None
    res = _submit(client, code)
    assert res.status_code == 200 and not _verified(user["id"])
    fresh = economy_auth.issue_verification_otp(user["id"])
    assert _submit(client, fresh).status_code in (301, 302)
    assert _verified(user["id"])


def test_25_expired_codes_are_rejected(traps):
    user = _pending()
    client = _signed_in(_client(), user)
    code = economy_auth.issue_verification_otp(user["id"])
    _exec("UPDATE users SET verification_code_expires = datetime('now', '-1 minute') WHERE id = ?", user["id"])
    assert b"expired" in _submit(client, code).data
    assert not _verified(user["id"])
    assert _row("SELECT verification_code FROM users WHERE id = ?", user["id"])["verification_code"] is None


def _verified_events(uid):
    return _row("SELECT COUNT(*) AS n FROM activity_log WHERE action = 'user.email_verified' AND user_id = ?", uid)["n"]


def test_26_a_code_works_once(traps):
    user = _pending()
    client = _signed_in(_client(), user)
    code = economy_auth.issue_verification_otp(user["id"])
    assert _submit(client, code).status_code in (301, 302)
    assert _verified_events(user["id"]) == 1
    assert _row("SELECT verification_code FROM users WHERE id = ?", user["id"])["verification_code"] is None
    # Even if the account loses verification, the consumed code cannot verify it again.
    _exec("UPDATE users SET is_verified = 0 WHERE id = ?", user["id"])
    with pytest.raises(economy_auth.AuthError):
        economy_auth.verify_email_otp(user["id"], code)
    assert not _verified(user["id"])
    assert _verified_events(user["id"]) == 1


def _consume_worker(i, barrier, queue, uid, codes):
    barrier.wait(WAIT)
    queue.put(economy_auth._check_and_consume_otp(uid, codes[i % len(codes)]))


def test_27_concurrent_validation_consumes_once_and_counts_every_guess(traps):
    user = _pending()
    code = economy_auth.issue_verification_otp(user["id"])
    results = _run_workers(_consume_worker, 10, user["id"], [code])
    assert results.count("consumed") == 1 and results.count("already") == 9
    assert _verified_events(user["id"]) == 0  # consumption itself; the route logs the event

    other = _pending("otp-race@example.com")
    code = economy_auth.issue_verification_otp(other["id"])
    guesses = [f"{(int(code) + k) % 1_000_000:06d}" for k in range(1, 13)]
    results = _run_workers(_consume_worker, 12, other["id"], guesses)
    assert results.count(economy_auth._OTP_WRONG) == 4
    assert results.count(economy_auth._OTP_EXHAUSTED) == 1
    assert results.count(economy_auth._OTP_NONE) == 7
    row = _row("SELECT verification_code, verification_attempts FROM users WHERE id = ?", other["id"])
    assert row["verification_code"] is None and row["verification_attempts"] == 5
    assert economy_auth._check_and_consume_otp(other["id"], code) == economy_auth._OTP_NONE


def test_28_resend_invalidates_the_old_code_and_is_limited(traps, monkeypatch):
    monkeypatch.setenv("MAIL_SERVER", "smtp.test.invalid")
    user = _pending()
    client = _signed_in(_client(), user)
    assert _resend(client).status_code == 200
    first = traps.codes()[-1]
    _submit(client, _wrong(first))
    _submit(client, _wrong(first))
    assert _resend(client).status_code == 200
    assert len(traps.codes()) == 2
    second = traps.codes()[-1]
    assert _row("SELECT verification_attempts FROM users WHERE id = ?", user["id"])["verification_attempts"] == 0
    if first != second:
        assert b"Incorrect code" in _submit(client, first).data
    for _ in range(3):
        assert _resend(client).status_code == 200
    sent_before = len(traps.codes())
    limited = _resend(client)
    assert limited.status_code == 429 and b"wait" in limited.data
    assert client.post("/verify-email/resend", environ_base={"REMOTE_ADDR": ATTACKER_IP}).status_code == 429
    assert len(traps.codes()) == sent_before
    latest = traps.codes()[-1]
    assert _submit(client, latest).status_code in (301, 302)
    assert _verified(user["id"])


def test_28b_old_code_rejected_after_resend(traps):
    user = _pending()
    client = _signed_in(_client(), user)
    old = economy_auth.issue_verification_otp(user["id"])
    new = economy_auth.issue_verification_otp(user["id"])
    while new == old:
        new = economy_auth.issue_verification_otp(user["id"])
    assert b"Incorrect code" in _submit(client, old).data
    assert _submit(client, new).status_code in (301, 302)


def _otp_wrong_worker(i, barrier, queue, uid, code):
    client = _signed_in(_client(), economy_auth.get_user(uid))
    barrier.wait(WAIT)
    out = []
    for k in range(2):
        out.append(_submit(client, _wrong(code) if k else f"{(int(code) + 7) % 1_000_000:06d}",
                           ip=f"198.51.100.{i + 1}").status_code)
    queue.put(out)


def test_29_attempt_limits_are_shared_across_workers(traps, monkeypatch):
    user = _pending()
    code = economy_auth.issue_verification_otp(user["id"])
    _run_workers(_otp_wrong_worker, 3, user["id"], code)
    row = _row("SELECT verification_code, verification_attempts FROM users WHERE id = ?", user["id"])
    assert row["verification_code"] is None and row["verification_attempts"] == 5
    assert b"No verification code" in _submit(_signed_in(_client(), user), code).data

    # The per-IP guess limit is shared as well.
    monkeypatch.setenv("OTP_VERIFY_LIMIT_PER_IP_15MIN", "4")
    other = _pending("otp-ip@example.com")
    code = economy_auth.issue_verification_otp(other["id"])
    statuses = [s for batch in _run_workers(_otp_ip_worker, 3, other["id"], code) for s in batch]
    assert statuses.count(429) == 2 and statuses.count(200) == 4


def _otp_ip_worker(i, barrier, queue, uid, code):
    client = _signed_in(_client(), economy_auth.get_user(uid))
    barrier.wait(WAIT)
    queue.put([_submit(client, _wrong(code), ip="198.51.100.250").status_code for _ in range(2)])


def test_30_attempts_survive_a_worker_restart(traps):
    user = _pending()
    client = _signed_in(_client(), user)
    code = economy_auth.issue_verification_otp(user["id"])
    for _ in range(3):
        _submit(client, _wrong(code))
    out = _fresh_interpreter(
        "from services.economy import auth\n"
        f"r = [auth._check_and_consume_otp({user['id']}, {_wrong(code)!r}) for _ in range(2)]\n"
        "print(json.dumps(r))\n"
    )
    assert out == [economy_auth._OTP_WRONG, economy_auth._OTP_EXHAUSTED]
    assert not _verified(user["id"])
    assert b"No verification code" in _submit(client, code).data


def test_31_forged_client_metadata_is_ignored(traps):
    user = _pending()
    victim = _pending("otp-victim@example.com")
    client = _signed_in(_client(), user)
    code = economy_auth.issue_verification_otp(user["id"])
    victim_code = economy_auth.issue_verification_otp(victim["id"])
    forged = {"attempts": "0", "verification_attempts": "0", "verification_code_expires": "2999-01-01 00:00:00",
              "expires": "2999-01-01", "user_id": str(victim["id"]), "email": "otp-victim@example.com"}
    for _ in range(3):
        _submit(client, _wrong(code), **forged)
    assert _row("SELECT verification_attempts FROM users WHERE id = ?", user["id"])["verification_attempts"] == 3
    if victim_code != code:
        assert b"Incorrect code" in _submit(client, victim_code, **forged).data
    assert not _verified(victim["id"])
    _exec("UPDATE users SET verification_code_expires = datetime('now', '-1 minute') WHERE id = ?", user["id"])
    assert b"expired" in _submit(client, code, **forged).data
    assert not _verified(user["id"])


def test_32_legitimate_verification_succeeds(traps, monkeypatch):
    monkeypatch.setenv("MAIL_SERVER", "smtp.test.invalid")
    client = _client()
    res = client.post("/api/auth/register", json={
        "email": "newbie@example.com", "password": PASSWORD, "password_confirm": PASSWORD,
    })
    assert res.status_code == 200 and res.get_json()["email_verification_required"] is True
    assert traps.sent.wait(10)
    code = traps.codes()[-1]
    stored = _row("SELECT verification_code FROM users WHERE email = 'newbie@example.com'")["verification_code"]
    assert code not in stored
    assert _submit(client, code).status_code in (301, 302)
    uid = _row("SELECT id FROM users WHERE email = 'newbie@example.com'")["id"]
    assert _verified(uid)
    assert _verified_events(uid) == 1

    # A plaintext code issued before this patch still works (once) until it expires.
    legacy = _pending("legacy-otp@example.com")
    _exec("UPDATE users SET verification_code = '482913', verification_code_expires = datetime('now', '+10 minutes') "
          "WHERE id = ?", legacy["id"])
    legacy_client = _signed_in(_client(), legacy)
    assert b"Incorrect code" in _submit(legacy_client, "482914").data
    assert _submit(legacy_client, "482913").status_code in (301, 302)
    assert _verified(legacy["id"])


# =============================================================== secrets in logs and errors (F-08)


SYNTH_OTP = "731946"
SYNTH_PASSWORD = "Pw!Synth-4c-QX7Zr9"
SYNTH_NEW_PASSWORD = "Pw!Synth-4c-NEW-QX7Zr9"


def test_33_otp_never_appears_in_logs_responses_or_storage(traps, monkeypatch, caplog):
    import smtplib

    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(economy_auth, "generate_otp_code", lambda: SYNTH_OTP)
    monkeypatch.setenv("EXPOSE_VERIFY_CODE", "1")
    bodies = []

    monkeypatch.delenv("MAIL_SERVER", raising=False)
    client = _client()
    bodies.append(client.post("/api/auth/register", json={
        "email": "otp-log@example.com", "password": PASSWORD, "password_confirm": PASSWORD,
    }).get_data(as_text=True))
    bodies.append(_resend(client).get_data(as_text=True))

    monkeypatch.setenv("MAIL_SERVER", "smtp.test.invalid")

    def _smtp_fails(to_email, subject, text_body, html_body):
        raise smtplib.SMTPDataError(554, f"rejected: {subject} {text_body}".encode())

    monkeypatch.setattr("services.economy.email_verify._smtp_send", _smtp_fails)
    bodies.append(_resend(client).get_data(as_text=True))
    from services.economy.email_verify import EmailVerifyError, send_verification_otp_email

    with pytest.raises(EmailVerifyError) as err:
        send_verification_otp_email(to_email="x@example.com", code=SYNTH_OTP)
    assert SYNTH_OTP not in str(err.value) and err.value.__cause__ is None
    bodies.append(_submit(client, "000001").get_data(as_text=True))
    assert _submit(client, SYNTH_OTP).status_code in (301, 302)

    for body in bodies:
        assert SYNTH_OTP not in body
    assert SYNTH_OTP not in _log_text(caplog)
    assert SYNTH_OTP not in _db_dump()


def test_34_passwords_and_hashes_never_appear_in_logs(traps, caplog):
    caplog.set_level(logging.DEBUG)
    client = _client()
    bodies = [client.post("/api/auth/register", json={
        "email": "pw-log@example.com", "password": SYNTH_PASSWORD, "password_confirm": SYNTH_PASSWORD,
    }).get_data(as_text=True)]
    uid = _row("SELECT id FROM users WHERE email = 'pw-log@example.com'")["id"]
    economy_auth.mark_email_verified(uid)
    economy_auth.end_all_sessions(uid)
    client = _client()
    for _ in range(6):
        bodies.append(_api_login(client, "pw-log@example.com", SYNTH_PASSWORD + "-WRONG").get_data(as_text=True))
    _exec("DELETE FROM auth_failures")
    bodies.append(_html_login(client, "pw-log@example.com", SYNTH_PASSWORD + "-WRONG").get_data(as_text=True))
    bodies.append(_api_login(client, "pw-log@example.com", SYNTH_PASSWORD).get_data(as_text=True))
    bodies.append(client.post("/api/account/password", json={
        "current_password": SYNTH_PASSWORD + "-WRONG", "new_password": SYNTH_NEW_PASSWORD,
        "confirm_password": SYNTH_NEW_PASSWORD}).get_data(as_text=True))
    bodies.append(client.post("/api/account/password", json={
        "current_password": SYNTH_PASSWORD, "new_password": SYNTH_NEW_PASSWORD,
        "confirm_password": SYNTH_NEW_PASSWORD}).get_data(as_text=True))
    pw_hash = _row("SELECT password_hash FROM users WHERE id = ?", uid)["password_hash"]
    logs = _log_text(caplog)
    dump = _db_dump()
    for secret in (SYNTH_PASSWORD, SYNTH_NEW_PASSWORD):
        assert secret not in logs
        assert secret not in dump
        assert all(secret not in body for body in bodies)
    assert pw_hash not in logs
    assert all(pw_hash not in body for body in bodies)


def test_35_bearer_tokens_never_appear_in_logs(traps, caplog):
    caplog.set_level(logging.DEBUG)
    user = _user("bearer-log@example.com")
    client = _signed_in(_client(), user)
    token = _connect_token(client)
    synthetic = "SYNTHBEARER4C" + "z" * 31
    for value in (token, synthetic):
        _veil_routes(client, value)
        client.get("/api/admin/users", headers=_bearer(value))
    client.post("/api/veil/revoke", headers=_bearer(token))
    _veil_routes(client, token)
    logs = _log_text(caplog)
    assert token not in logs and synthetic not in logs
    assert "Bearer" not in logs


def test_36_session_and_csrf_tokens_never_appear_in_logs(traps, caplog):
    import app as app_mod

    caplog.set_level(logging.DEBUG)
    _user("cookie-log@example.com")
    client = _client()
    assert _api_login(client, "cookie-log@example.com", PASSWORD).status_code == 200
    with client.session_transaction() as sess:
        csrf_token = sess["_csrf_token"]
        sid = sess[economy_auth.AUTH_SID_KEY]
    cookie = client.get_cookie(app_mod.app.config.get("SESSION_COOKIE_NAME", "session"))
    assert cookie is not None
    wrong_csrf = "SYNTHCSRF4C" + "w" * 30
    rejected = client.post("/api/account/profile", json={"name": "x"}, headers={"X-CSRF-Token": wrong_csrf})
    assert rejected.status_code == 403
    client.post("/api/account/profile", json={"name": "y"})
    client.post("/api/auth/logout")
    logs = _log_text(caplog)
    assert "csrf rejected" in logs
    for secret in (csrf_token, sid, cookie.value, wrong_csrf):
        assert secret not in logs
    dump = _db_dump()
    assert csrf_token not in dump and sid not in dump


def test_37_public_errors_carry_no_secrets(traps, monkeypatch):
    import smtplib

    from services.economy.email_verify import EmailVerifyError, send_veil_link_email, send_verification_otp_email

    monkeypatch.setenv("MAIL_SERVER", "smtp.test.invalid")

    def _smtp_fails(*_args, **_kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials for SYNTHSMTPSECRET")

    monkeypatch.setattr("services.economy.email_verify._smtp_send", _smtp_fails)
    for call in (lambda: send_verification_otp_email(to_email="a@example.com", code=SYNTH_OTP),
                 lambda: send_veil_link_email(to_email="a@example.com", link="https://example.com/x")):
        with pytest.raises(EmailVerifyError) as err:
            call()
        assert "SYNTHSMTPSECRET" not in str(err.value) and SYNTH_OTP not in str(err.value)

    user = _pending("errors@example.com")
    code = economy_auth.issue_verification_otp(user["id"])
    for attempt in (_wrong(code),) * 5 + (code,):
        try:
            economy_auth.verify_email_otp(user["id"], attempt)
        except economy_auth.AuthError as exc:
            assert code not in str(exc) and attempt not in str(exc)

    client = _client()
    body = _api_login(client, "errors@example.com", SYNTH_PASSWORD).get_data(as_text=True)
    assert SYNTH_PASSWORD not in body
    synthetic = "SYNTHBEARER4C" + "e" * 31
    for res in (client.get("/api/veil/me", headers=_bearer(synthetic)),
                client.post("/api/veil/ask", json={"text": "x"}, headers=_bearer(synthetic)),
                client.post("/api/extension/humanize", json={"text": "x", "key": synthetic}),
                client.post("/api/veil/revoke", headers=_bearer(synthetic))):
        assert synthetic not in res.get_data(as_text=True)
