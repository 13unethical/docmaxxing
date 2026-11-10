"""Patch 4E: sign-up email abuse, guest AI Detector quotas, and Feedback / Contact limits.

Every counter lives in the shared SQLite DB. Concurrent workers are forked processes; a worker
restart is a fresh interpreter on the same database. SMTP, the detector model, ZeroGPT and
Telegram are traps that record calls: nothing leaves the machine.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest
import requests

from services import ai_detector, free_humanize, rate_limit
from services.economy import auth as economy_auth
from services.economy import db as economy_db
from tests.test_ai_detector import AI, HUMAN
from tests.test_security_account_protection_4c import _run_workers
from tests.test_security_csrf_sessions_admin import _csrf_rejected, _raw
from tests.test_security_csrf_sessions_admin import _signed_in as _raw_signed_in
from tests.test_security_paid_pipelines import (  # noqa: F401
    _client,
    _priced_project,
    _signed_in,
    _user,
    economy,
    guarded_app,
)
from tests.test_security_ssrf_telegram_gemini_4d import (  # noqa: F401
    GROUP_CHAT,
    _admin_messages,
    _hook,
    _tg_update,
    tg,
)

PROSE = HUMAN + "\n" + AI
PASSWORD = "secret123"
ATTACKER = "203.0.113.66"
OTHER = "198.51.100.7"
THIRD = "192.0.2.44"

_KNOB_PREFIXES = ("REGISTER_", "VERIFY_EMAIL_", "OTP_", "FEEDBACK_", "CONTACT_", "FREE_DETECT_", "VEIL_EMAIL_",
                  "LOGIN_")
_KNOBS = ("TRUSTED_PROXIES", "MAIL_SERVER", "EXPOSE_VERIFY_CODE", "DISPOSABLE_EMAIL_API_URL", "AI_DETECTOR_EVENTS_LOG",
          "ZEROGPT_API_KEY", "ZEROGPT_EMAIL", "ZEROGPT_PASSWORD", "TELEGRAM_TOKEN", "CHAT_ID",
          "TELEGRAM_ADMIN_USER_IDS", "TELEGRAM_WEBHOOK_SECRET", "ADMIN_EMAIL", "PUBLIC_BASE_URL")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith(_KNOB_PREFIXES) or name in _KNOBS:
            monkeypatch.delenv(name, raising=False)


def _lock_free() -> bool:
    """True when another connection can take the write lock at once (no transaction is open)."""
    conn = sqlite3.connect(str(economy_db.DB_PATH), timeout=0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.rollback()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


class _InlineThread:
    """Runs the target on start(), so a background email has been sent when the request returns."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
        self._call = (target, args, kwargs or {})

    def start(self):
        target, args, kwargs = self._call
        target(*args, **kwargs)


@pytest.fixture()
def traps(economy, monkeypatch):
    import app as app_mod

    calls = SimpleNamespace(mails=[], detector=[], telegram=[], zerogpt=[], lock_free=[])

    def _smtp(to_email, subject, text_body, html_body):
        calls.lock_free.append(_lock_free())
        calls.mails.append((to_email, text_body))

    def _score(texts):
        calls.lock_free.append(_lock_free())
        calls.detector.append(len(texts))
        return [0.1] * len(texts), "trap-v1"

    def _telegram(text):
        calls.lock_free.append(_lock_free())
        calls.telegram.append(text)
        return {"ok": True, "result": {"message_id": 700_000 + len(calls.telegram)}}, None, 200

    def _zerogpt(text):
        calls.zerogpt.append(text)
        return {"data": {"fakePercentage": 10, "textWords": len(text.split()), "h": []}}

    shim = SimpleNamespace(**{k: getattr(threading, k) for k in dir(threading) if not k.startswith("__")})
    shim.Thread = _InlineThread
    monkeypatch.setattr(app_mod, "threading", shim)
    monkeypatch.setenv("MAIL_SERVER", "smtp.test.invalid")
    monkeypatch.setattr("services.economy.email_verify._smtp_send", _smtp)
    monkeypatch.setattr(ai_detector, "_score_remote", _score)
    monkeypatch.setattr(app_mod, "_send_telegram_text", _telegram)
    monkeypatch.setattr(app_mod.zerogpt_client, "detect", _zerogpt)
    calls.app = app_mod
    calls.codes = lambda: [m.group(1) for _to, body in calls.mails if (m := re.search(r"code is: (\d{6})", body))]
    return calls


def _row(sql, *args):
    with economy_db.connect() as conn:
        return conn.execute(sql, args).fetchone()


def _exec(sql, *args):
    with economy_db.connect() as conn:
        conn.execute(sql, args)


def _users() -> int:
    return _row("SELECT COUNT(*) AS n FROM users")["n"]


def _events(prefix: str) -> int:
    return _row("SELECT COUNT(*) AS n FROM rate_limit_events WHERE key LIKE ?", prefix + "%")["n"]


def _age_events(prefix: str, seconds: int) -> None:
    _exec("UPDATE rate_limit_events SET ts = ts - ? WHERE key LIKE ?", seconds, prefix + "%")


def _register(client=None, email="new@example.com", *, ip=ATTACKER, headers=None, html=False):
    client = client or _client()
    body = {"email": email, "name": "New", "password": PASSWORD, "password_confirm": PASSWORD}
    kwargs = {"environ_base": {"REMOTE_ADDR": ip}, "headers": headers or {}}
    if html:
        return client.post("/register", data=body, **kwargs)
    return client.post("/api/auth/register", json=body, **kwargs)


def _resend(client, *, ip=ATTACKER):
    return client.post("/verify-email/code", data={"action": "resend"}, environ_base={"REMOTE_ADDR": ip})


def _submit(client, code, *, ip=ATTACKER):
    return client.post("/verify-email/code", data={"action": "verify", "code": code}, environ_base={"REMOTE_ADDR": ip})


def _stored_code(email):
    return _row("SELECT verification_code, verification_attempts FROM users WHERE email = ?", email)


def _fresh_interpreter(code: str) -> dict:
    """``code`` in a new Python process (a restarted worker) on the same database, with a test client ``c``."""
    from app import app

    env = {k: v for k, v in os.environ.items() if k != "MAIL_SERVER"}
    env["ECONOMY_DB_PATH"] = str(economy_db.DB_PATH)
    env["SECRET_KEY"] = str(app.secret_key)  # every worker of one deployment shares it
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [os.getcwd(), env.get("PYTHONPATH", "")]))
    prelude = (
        "import json\n"
        "import app as m\n"
        "m.app.config['TESTING'] = True\n"
        "c = m.app.test_client()\n"
        "with c.session_transaction() as s:\n"
        "    s['_csrf_token'] = 'tok'\n"
        "H = {'X-CSRF-Token': 'tok'}\n"
    )
    out = subprocess.run([sys.executable, "-c", prelude + code], env=env, capture_output=True, text=True,
                         timeout=180, cwd=os.getcwd())
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


# =============================================================== registration and verification email


def test_01_repeated_registration_from_one_network_is_bounded(traps, monkeypatch):
    monkeypatch.setenv("REGISTER_LIMIT_PER_IP_HOUR", "3")
    assert _register(email="same@example.com").status_code == 200
    assert [_register(email="same@example.com").status_code for _ in range(2)] == [409, 409]
    limited = _register(email="same@example.com")
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) > 0
    assert limited.get_json()["code"] == "TOO_MANY_ATTEMPTS"
    assert _register(email="same@example.com", html=True).status_code == 429  # the form shares the counter
    assert _users() == 1 and len(traps.mails) == 1


def test_02_many_addresses_from_one_network_are_bounded_per_hour_and_day(traps, monkeypatch):
    monkeypatch.setenv("REGISTER_LIMIT_PER_IP_HOUR", "3")
    codes = [_register(email=f"user{i}@example.com").status_code for i in range(10)]
    assert codes == [200] * 3 + [429] * 7
    assert _users() == 3 and len(traps.mails) == 3
    assert _register(email="elsewhere@example.com", ip=OTHER).status_code == 200  # other networks unaffected

    monkeypatch.setenv("REGISTER_LIMIT_PER_IP_DAY", "4")
    _age_events("register:", 3601)
    assert [_register(email=f"later{i}@example.com").status_code for i in range(2)] == [200, 429]
    _age_events("register:", 3601)
    assert _register(email="later-again@example.com").status_code == 429
    _age_events("register:", 86400)
    assert _register(email="next-day@example.com").status_code == 200  # windows expire: no permanent lockout
    assert len(traps.mails) == _users() == 6


def test_03_sign_up_emails_per_network_are_bounded_and_skipped_codes_are_never_issued(traps, monkeypatch):
    monkeypatch.setenv("VERIFY_EMAIL_LIMIT_PER_IP_HOUR", "2")
    clients = [_client() for _ in range(3)]
    for i, client in enumerate(clients):
        res = _register(client, f"mail{i}@example.com")
        assert res.status_code == 200 and res.get_json()["email_verification_required"] is True
    assert [to for to, _body in traps.mails] == ["mail0@example.com", "mail1@example.com"]
    assert _stored_code("mail2@example.com")["verification_code"] is None
    assert _resend(clients[2]).status_code == 429  # same network: still no mail
    assert len(traps.mails) == 2
    assert _resend(clients[2], ip=OTHER).status_code == 200  # the account is not locked out
    assert traps.mails[-1][0] == "mail2@example.com"


def test_04_resends_from_many_accounts_share_the_network_budget(traps, monkeypatch):
    monkeypatch.setenv("VERIFY_EMAIL_LIMIT_PER_IP_HOUR", "5")
    clients = [_client() for _ in range(3)]
    for i, client in enumerate(clients):
        assert _register(client, f"multi{i}@example.com").status_code == 200
    statuses = [_resend(client).status_code for client in clients for _ in range(2)]
    assert statuses.count(200) == 2 and statuses.count(429) == 4
    assert len(traps.mails) == 5


def test_04b_recreating_an_account_does_not_reset_the_address_budget(traps, monkeypatch):
    monkeypatch.setenv("VERIFY_EMAIL_LIMIT_PER_ADDRESS_HOUR", "2")
    admin = _user("admin@example.com", admin=True)
    first = _client()
    assert _register(first, "victim@example.com").status_code == 200
    assert _resend(first).status_code == 200
    assert _resend(first).status_code == 429
    assert len(traps.mails) == 2
    old_id = _row("SELECT id FROM users WHERE email = ?", "victim@example.com")["id"]
    traps.app.admin_service.delete_user(old_id, actor_id=admin["id"])

    again = _client()
    assert _register(again, "Victim@Example.com", ip=OTHER).status_code == 200
    assert _stored_code("victim@example.com")["verification_code"] is None
    assert _resend(again, ip=OTHER).status_code == 429
    assert _resend(again, ip=THIRD).status_code == 429
    assert len(traps.mails) == 2


def _register_worker(i, barrier, queue):
    client = _client()
    barrier.wait(60)
    queue.put(_register(client, f"race{i}@example.com").status_code)


def test_05_concurrent_registrations_from_separate_processes(traps, monkeypatch):
    monkeypatch.setenv("REGISTER_LIMIT_PER_IP_HOUR", "4")
    results = _run_workers(_register_worker, 12)
    assert sorted(results) == [200] * 4 + [429] * 8
    assert _users() == 4
    assert _row("SELECT COUNT(*) AS n FROM users WHERE verification_code IS NOT NULL")["n"] == 4
    assert _events("register:ip:") == 4 and _events("verify_mail:addr:") == 4


def _resend_worker(i, barrier, queue, uid):
    client = _signed_in(_client(), economy_auth.get_user(uid))
    barrier.wait(60)
    queue.put(_resend(client).status_code)


def test_06_concurrent_resends_cannot_exceed_the_limit(traps, monkeypatch):
    monkeypatch.setenv("OTP_RESEND_LIMIT_PER_HOUR", "3")
    user = _user("resend-race@example.com", verified=False)
    results = _run_workers(_resend_worker, 10, user["id"])
    assert sorted(results) == [200] * 3 + [429] * 7
    assert _events("otp_issue:user:") == 3 and _events("verify_mail:addr:") == 3

    other = _user("resend-net@example.com", verified=False)
    monkeypatch.setenv("VERIFY_EMAIL_LIMIT_PER_IP_HOUR", "5")
    results = _run_workers(_resend_worker, 6, other["id"])
    assert results.count(200) == 2  # the network had 2 of its 5 emails left


def test_07_failed_delivery_keeps_its_slot_and_holds_no_lock(traps, monkeypatch):
    monkeypatch.setenv("VERIFY_EMAIL_LIMIT_PER_ADDRESS_HOUR", "2")
    attempts = []

    def _broken(to_email, subject, text_body, html_body):
        attempts.append(_lock_free())
        raise OSError("smtp down")

    monkeypatch.setattr("services.economy.email_verify._smtp_send", _broken)
    client = _client()
    assert _register(client, "fail@example.com").status_code == 200  # the account is created anyway
    assert _resend(client).status_code == 200
    for _ in range(3):
        assert _resend(client).status_code == 429
    assert attempts == [True, True]
    assert _events("verify_mail:addr:") == 2
    _age_events("verify_mail:addr:", 3601)
    assert _resend(client).status_code == 200 and len(attempts) == 3


def test_08_registration_limits_survive_a_worker_restart(traps, monkeypatch):
    monkeypatch.setenv("REGISTER_LIMIT_PER_IP_HOUR", "2")
    assert [_register(email=f"before{i}@example.com").status_code for i in range(2)] == [200, 200]
    out = _fresh_interpreter(
        "body = {'email': 'after@example.com', 'name': 'A', 'password': 'secret123', 'password_confirm': 'secret123'}\n"
        f"r = c.post('/api/auth/register', json=body, headers=H, environ_base={{'REMOTE_ADDR': '{ATTACKER}'}})\n"
        "print(json.dumps({'status': r.status_code}))\n"
    )
    assert out == {"status": 429}
    assert _users() == 2


def test_09_spoofed_forwarding_headers_and_ipv6_rotation_do_not_reset_limits(traps, monkeypatch):
    monkeypatch.setenv("REGISTER_LIMIT_PER_IP_HOUR", "2")

    def spoof(n):
        return {"X-Forwarded-For": f"10.0.{n}.1", "X-Real-IP": f"10.1.{n}.1", "CF-Connecting-IP": f"10.2.{n}.1"}

    codes = [_register(email=f"s{n}@example.com", headers=spoof(n)).status_code for n in range(5)]
    assert codes == [200, 200, 429, 429, 429]
    v6 = [_register(email=f"v6-{n}@example.com", ip=f"2001:db8:1:2::{n + 1:x}").status_code for n in range(4)]
    assert v6 == [200, 200, 429, 429]
    assert _register(email="v6-other@example.com", ip="2001:db8:1:3::1").status_code == 200
    # Behind the trusted proxy, the proxy's X-Real-IP is the client.
    assert _register(email="proxied@example.com", ip="127.0.0.1", headers={"X-Real-IP": OTHER}).status_code == 200
    assert _register(email="proxied2@example.com", ip="127.0.0.1", headers={"X-Real-IP": ATTACKER}).status_code == 429
    assert _users() == 6


def test_10_nobody_else_can_replace_or_invalidate_a_pending_code(traps):
    victim = _client()
    assert _register(victim, "victim@example.com", ip=OTHER).status_code == 200
    code = traps.codes()[-1]
    before = tuple(_stored_code("victim@example.com"))
    attacker = _client()
    for _ in range(4):
        assert _register(attacker, "victim@example.com").status_code == 409
    assert _register(attacker, " Victim@Example.COM ", html=True).status_code == 409
    assert _client().post("/verify-email/code", data={"action": "resend"}).status_code in (301, 302)
    assert _client().post("/verify-email/resend").status_code in (301, 302)
    assert _register(attacker, "attacker@example.com").status_code == 200
    assert _resend(attacker).status_code == 200  # resends only the attacker's own account
    assert _submit(attacker, "000000").status_code == 200
    assert tuple(_stored_code("victim@example.com")) == before
    assert [to for to, _body in traps.mails].count("victim@example.com") == 1
    assert _submit(victim, code, ip=OTHER).status_code in (301, 302)
    assert economy_auth.get_user(_row("SELECT id FROM users WHERE email = 'victim@example.com'")["id"])["is_verified"]


def test_11_legitimate_registration_and_verification(traps):
    client = _client()
    res = _register(client, "student@example.com")
    assert res.status_code == 200 and res.get_json()["success"] is True
    assert traps.mails[-1][0] == "student@example.com" and traps.lock_free == [True]
    assert _submit(client, traps.codes()[-1]).status_code in (301, 302)
    assert _row("SELECT is_verified FROM users WHERE email = 'student@example.com'")["is_verified"] == 1

    form = _client()
    page = _register(form, "form-student@example.com", html=True)
    assert page.status_code == 302 and "/verify-email" in page.headers["Location"]
    assert traps.mails[-1][0] == "form-student@example.com"


def test_12_existing_otp_limits_are_unchanged(traps, monkeypatch):
    user = _user("otp4c@example.com", verified=False)
    client = _signed_in(_client(), user)
    assert [_resend(client).status_code for _ in range(6)] == [200] * 5 + [429]
    code = traps.codes()[-1]
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    for _ in range(4):
        assert b"Incorrect code" in _submit(client, wrong).data
    assert b"Too many incorrect codes" in _submit(client, wrong).data
    assert _stored_code("otp4c@example.com")["verification_code"] is None

    monkeypatch.setenv("OTP_VERIFY_LIMIT_PER_IP_15MIN", "3")
    other = _signed_in(_client(), _user("otp4c-ip@example.com", verified=False))
    statuses = [_submit(other, "123456", ip=THIRD).status_code for _ in range(4)]
    assert statuses[-1] == 429


def test_12b_veil_link_email_is_limited_like_account_email(traps, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://docmaxxing.com")
    monkeypatch.setattr("services.economy.email_verify.smtp_configured", lambda: True)
    client = _signed_in(_client(), _user("veil-mail@example.com", verified=False))
    codes = [client.post("/api/veil/email-link", json={}, environ_base={"REMOTE_ADDR": ATTACKER}).status_code
             for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert len(traps.mails) == 3


# =============================================================================== guest AI Detector


def _detect(client, text=PROSE, *, ip=ATTACKER, **kwargs):
    return client.post("/api/detector/free", json={"text": text}, environ_base={"REMOTE_ADDR": ip}, **kwargs)


def test_13_14_guest_daily_limit_rejects_before_the_provider(traps, monkeypatch):
    monkeypatch.setenv("FREE_DETECT_GUEST_DAILY", "2")
    guest = _client()
    first = _detect(guest)
    assert first.status_code == 200 and first.get_json()["checks_left"] == 1
    assert _detect(guest).status_code == 200
    refused = _detect(guest)
    assert refused.status_code == 403 and refused.get_json()["error"] == "REGISTER_REQUIRED"
    assert len(traps.detector) == 2 and all(traps.lock_free)


def test_15_clearing_cookies_or_signing_out_gives_no_new_guest_checks(traps, monkeypatch):
    monkeypatch.setenv("FREE_DETECT_GUEST_DAILY", "2")
    assert ai_detector.limits().guest_ip_daily == 2
    assert [_detect(_client()).status_code for _ in range(4)] == [200, 200, 403, 403]
    assert len(traps.detector) == 2
    assert _detect(_client(), ip=OTHER).status_code == 200  # another network has its own allowance

    member = _signed_in(_client(), _user("member@example.com"))
    assert _detect(member).status_code == 200  # an account has its own allowance
    member.post("/api/auth/logout")
    assert _detect(member).status_code == 403
    assert len(traps.detector) == 4


def test_15b_guest_per_minute_limit_is_shared(traps, monkeypatch):
    monkeypatch.setenv("FREE_DETECT_GUEST_RATE_PER_MIN", "3")
    monkeypatch.setenv("FREE_DETECT_GUEST_DAILY", "50")
    codes = [_detect(_client()).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert len(traps.detector) == 3


_DETECTOR_CALLS = ("ai_detector.detect(", "ai_detector.score_texts(", "_score_remote(")


def test_16_no_other_route_reaches_the_free_detector_and_paid_routes_stay_closed(traps):
    app = traps.app.app
    reaching = set()
    for endpoint, view in app.view_functions.items():
        try:
            source = inspect.getsource(inspect.unwrap(view))
        except (OSError, TypeError):
            continue
        if any(call in source for call in _DETECTOR_CALLS):
            reaching.add(endpoint)
    assert reaching == {"api_free_ai_detector"}

    guest = _client()
    assert guest.post("/api/workspace/detect", json={"text": PROSE}).status_code in (401, 403)
    unverified = _signed_in(_client(), _user("unverified-detect@example.com", verified=False))
    assert unverified.post("/api/workspace/detect", json={"text": PROSE}).status_code in (401, 403)
    assert guest.post("/api/ai-detection/session", json={}).status_code == 401
    assert guest.post("/api/ai-detection/session/forged/advance").status_code in (401, 404)
    assert traps.zerogpt == [] and traps.detector == []


def test_17_forged_session_or_project_ids_never_return_someone_elses_result(traps, guarded_app, monkeypatch):
    app_mod, service, _calls = guarded_app
    alice = _user("alice-det@example.com")
    bob = _user("bob-det@example.com")
    stored = SimpleNamespace(to_dict=lambda: {"id": "det-alice", "owner": "alice", "score": 12})
    monkeypatch.setattr(app_mod.ai_detection_engine, "get_session", lambda sid: stored)
    app_mod._standalone_detection_owners.register("det-alice", alice["id"])
    alice_client = _signed_in(_client(), alice)
    bob_client = _signed_in(_client(), bob)
    assert alice_client.get("/api/ai-detection/session/det-alice").status_code == 200
    for client, status in ((bob_client, 404), (_client(), 401)):
        for res in (client.get("/api/ai-detection/session/det-alice"),
                    client.post("/api/ai-detection/session/det-alice/finalize")):
            assert res.status_code == status and "alice" not in res.get_data(as_text=True)
    assert alice_client.get("/api/ai-detection/session/det-forged-0001").status_code == 404

    project_id = _priced_project(service, user_id=str(alice["id"]))
    for path in ("ai-detection", "detection-report"):
        res = bob_client.get(f"/api/assignment/projects/{project_id}/{path}")
        assert res.status_code in (403, 404) and "alice" not in res.get_data(as_text=True)
        assert bob_client.get(f"/api/assignment/projects/proj-forged-000000/{path}").status_code in (403, 404)
    assert traps.zerogpt == [] and traps.detector == []


def test_18_oversized_or_malformed_input_is_rejected_before_the_provider(traps):
    guest = _client()
    long_text = " ".join([HUMAN] * 60)  # > 1,500 words
    res = _detect(guest, long_text)
    assert res.status_code == 403 and res.get_json()["error"] == "FREE_WORD_LIMIT"
    assert _detect(guest, "a" * 200_001).status_code == 400
    for body in ({"text": ["x"]}, {"text": 5}, {}, ["text"]):
        assert guest.post("/api/detector/free", json=body).status_code == 400
    member = _signed_in(_client(), _user("long@example.com"))
    huge = " ".join([HUMAN] * 200)  # > 5,000 words
    assert _detect(member, huge).get_json()["error"] == "FREE_WORD_LIMIT"
    assert traps.detector == []
    assert free_humanize.used_today("detect:user:%d" % _row("SELECT id FROM users")["id"]) == 0
    assert _row("SELECT COUNT(*) AS n FROM free_humanize_usage")["n"] == 0


def _detect_worker(i, barrier, queue):
    client = _client()
    barrier.wait(60)
    queue.put(_detect(client).status_code)


def test_19_concurrent_guest_checks_across_processes_stay_within_the_limit(traps, monkeypatch):
    monkeypatch.setenv("FREE_DETECT_GUEST_DAILY", "3")
    monkeypatch.setenv("FREE_DETECT_GUEST_RATE_PER_MIN", "100")
    results = _run_workers(_detect_worker, 10)
    assert sorted(results) == [200] * 3 + [403] * 7
    rows = _row("SELECT MAX(used) AS used FROM free_humanize_usage WHERE subject LIKE 'detect:guest-net:%'")
    assert rows["used"] == 3


def test_20_guest_counters_survive_a_worker_restart(traps, monkeypatch):
    monkeypatch.setenv("FREE_DETECT_GUEST_DAILY", "1")
    assert _detect(_client()).status_code == 200
    out = _fresh_interpreter(
        "from services import ai_detector\n"
        "calls = []\n"
        "ai_detector._score_remote = lambda texts: (calls.append(1), ([0.1] * len(texts), 'x'))[1]\n"
        f"text = {PROSE!r}\n"
        f"r = c.post('/api/detector/free', json={{'text': text}}, headers=H, environ_base={{'REMOTE_ADDR': '{ATTACKER}'}})\n"
        "print(json.dumps({'status': r.status_code, 'calls': len(calls)}))\n"
    )
    assert out == {"status": 403, "calls": 0}


def test_21_registered_quota_is_unchanged(traps, monkeypatch):
    lim = ai_detector.limits()
    assert (lim.guest_daily, lim.guest_words, lim.user_daily, lim.user_words) == (10, 1500, 50, 5000)
    assert (lim.guest_ip_daily, lim.unverified_ip_daily) == (10, 50)
    verified = _signed_in(_client(), _user("quota@example.com"))
    assert _detect(verified).get_json()["checks_left"] == 49

    monkeypatch.setenv("FREE_DETECT_USER_DAILY", "2")
    assert _detect(verified).status_code == 200
    limited = _detect(verified)
    assert limited.status_code == 429 and limited.get_json()["error"] == "FREE_LIMIT_REACHED"

    # Verified accounts never share a pool; unverified ones share one per network.
    monkeypatch.setenv("FREE_DETECT_UNVERIFIED_IP_DAILY", "1")
    for i in range(2):
        assert _detect(_signed_in(_client(), _user(f"verified{i}@example.com")), ip=OTHER).status_code == 200
    first = _signed_in(_client(), _user("fresh1@example.com", verified=False))
    second = _signed_in(_client(), _user("fresh2@example.com", verified=False))
    assert _detect(first, ip=THIRD).status_code == 200
    assert _detect(second, ip=THIRD).status_code == 429
    assert _detect(second, ip="192.0.2.99").status_code == 200


def test_22_paid_detector_is_unchanged(traps, monkeypatch):
    from services.economy.pricing import feature_cost

    monkeypatch.setenv("ZEROGPT_API_KEY", "zerogpt-test-key")
    monkeypatch.setenv("FREE_DETECT_GUEST_DAILY", "1")
    assert _detect(_client()).status_code == 200
    assert _detect(_client()).status_code == 403  # the free pool is spent; the paid route is separate
    user = _user("paid-detect@example.com")
    wallet = traps.app.wallet
    wallet.credit(user["id"], 50, "test_topup")
    before = wallet.get_balance(user["id"])
    client = _signed_in(_client(), user)
    res = client.post("/api/workspace/detect", json={"text": PROSE}, environ_base={"REMOTE_ADDR": ATTACKER})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert before - wallet.get_balance(user["id"]) == feature_cost("detect", word_count=traps.app.count_words(PROSE))
    assert len(traps.zerogpt) == 1

    broke = _user("broke-detect@example.com")
    if wallet.get_balance(broke["id"]):
        wallet.debit(broke["id"], wallet.get_balance(broke["id"]), "test_drain")
    res = _signed_in(_client(), broke).post("/api/workspace/detect", json={"text": PROSE})
    assert res.status_code == 402 and len(traps.zerogpt) == 1


# ======================================================================================== Feedback


def _feedback(client, body, *, ip=ATTACKER, path="/api/feedback"):
    return client.post(path, json=body, environ_base={"REMOTE_ADDR": ip})


def _saved(user_id=None) -> list[str]:
    with economy_db.connect() as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'support_messages'").fetchone()
        if not exists:
            return []
        if user_id is None:
            rows = conn.execute("SELECT message FROM support_messages WHERE sender = 'user' ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT message FROM support_messages WHERE sender = 'user' AND user_id = ? ORDER BY id", (user_id,)
            ).fetchall()
    return [r["message"] for r in rows]


def test_23_feedback_needs_the_session_csrf_token(traps):
    user = _user("csrf-feedback@example.com")
    raw = _raw_signed_in(_raw(), user)
    for path in ("/api/feedback", "/feedback"):
        assert _csrf_rejected(raw.post(path, json={"message": "hello"}))
        assert _csrf_rejected(raw.post(path, json={"message": "hello"}, headers={"X-CSRF-Token": "forged"}))
    assert _saved() == [] and traps.telegram == []
    assert _feedback(_client(), {"message": "hello"}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [["message"], {"message": 5}, {"message": ["hi"]}, {}, {"message": "   "},
     {"message": "hi", "user_id": 1}, {"message": "hi", "is_admin": True}, {"message": "hi", "email": "x@y.z"}],
)
def test_24_invalid_feedback_payloads_are_rejected(traps, body):
    client = _signed_in(_client(), _user("payload@example.com"))
    assert _feedback(client, body).status_code == 400
    assert _saved() == [] and traps.telegram == []


def test_25_oversized_feedback_is_rejected_and_the_limit_fits_telegram(traps):
    client = _signed_in(_client(), _user("long-feedback@example.com"))
    assert _feedback(client, {"message": "x" * 4001}).status_code == 400
    assert _saved() == [] and traps.telegram == []
    ok = _feedback(client, {"message": "y" * 4000})
    assert ok.status_code == 200
    assert _saved() == ["y" * 4000] and len(traps.telegram[0]) <= 4096


def test_26_repeated_feedback_is_limited_and_duplicates_are_dropped(traps, monkeypatch):
    monkeypatch.setenv("FEEDBACK_LIMIT_PER_USER_HOUR", "3")
    user = _user("chatty@example.com")
    client = _signed_in(_client(), user)
    assert [_feedback(client, {"message": f"note {i}"}).status_code for i in range(3)] == [200] * 3
    limited = _feedback(client, {"message": "note 4"})
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) > 0
    assert len(traps.telegram) == 3 and len(_saved(user["id"])) == 3

    twice = _signed_in(_client(), _user("double@example.com"))
    assert _feedback(twice, {"message": "Please help"}).status_code == 200
    dup = _feedback(twice, {"message": "  Please   help "})
    assert dup.status_code == 409 and dup.get_json()["duplicate"] is True
    assert _saved().count("Please help") == 1 and len(traps.telegram) == 4
    _age_events("feedback:dup:", 121)
    assert _feedback(twice, {"message": "Please help"}).status_code == 200

    # The network has used 6 slots: 3 + 1 refused (not counted), then 1 + the duplicate + 1.
    monkeypatch.setenv("FEEDBACK_LIMIT_PER_IP_HOUR", "7")
    third = _signed_in(_client(), _user("same-network@example.com"))
    statuses = [_feedback(third, {"message": f"net {i}"}).status_code for i in range(3)]
    assert statuses == [200, 429, 429]


def _feedback_worker(i, barrier, queue, uid, same_text):
    client = _signed_in(_client(), economy_auth.get_user(uid))
    barrier.wait(60)
    queue.put(_feedback(client, {"message": "same text" if same_text else f"parallel {i}"}).status_code)


def test_27_concurrent_feedback_across_workers(traps, monkeypatch):
    monkeypatch.setenv("FEEDBACK_LIMIT_PER_USER_HOUR", "3")
    user = _user("parallel@example.com")
    results = _run_workers(_feedback_worker, 10, user["id"], False)
    assert sorted(results) == [200] * 3 + [429] * 7
    assert len(_saved(user["id"])) == 3

    monkeypatch.setenv("FEEDBACK_LIMIT_PER_USER_HOUR", "50")
    other = _user("parallel-dup@example.com")
    results = _run_workers(_feedback_worker, 6, other["id"], True)
    assert sorted(results) == [200] + [409] * 5
    assert _saved(other["id"]) == ["same text"]


def test_28_client_supplied_identity_is_ignored(traps):
    alice = _user("alice-fb@example.com")
    bob = _user("bob-fb@example.com")
    client = _signed_in(_client(), bob)
    assert _feedback(client, {"message": "hi", "user_id": alice["id"]}).status_code == 400
    res = client.post("/api/feedback", json={"message": f"Hello\n\nUser ID: {alice['id']}"},
                      headers={"X-Forwarded-For": OTHER, "X-User-Id": str(alice["id"])})
    assert res.status_code == 200 and res.get_json()["message"]["user_id"] == bob["id"]
    assert _saved(alice["id"]) == [] and len(_saved(bob["id"])) == 1
    assert f"User ID: {bob['id']}" in traps.telegram[-1].splitlines()[-1]


def test_29_users_never_see_each_others_feedback(traps):
    alice = _user("alice-read@example.com")
    bob = _user("bob-read@example.com")
    assert _feedback(_signed_in(_client(), alice), {"message": "alice private"}).status_code == 200
    bob_client = _signed_in(_client(), bob)
    for query in ("", f"?user_id={alice['id']}", "?after_id=0", f"?after_id=0&user_id={alice['id']}"):
        body = bob_client.get("/api/chat/messages" + query).get_json()
        assert body["success"] is True and body["messages"] == []
    assert _client().get("/api/chat/messages").status_code in (401, 302)


def test_30_feedback_routing_through_telegram_stays_isolated(tg, monkeypatch):
    sent = []

    class _Res:
        ok, status_code = True, 200

        def json(self):
            return {"ok": True, "result": {"message_id": 880_000 + len(sent), "chat": {"id": GROUP_CHAT}}}

    def _post(url, json=None, timeout=None, **_kw):
        sent.append(json)
        return _Res()

    monkeypatch.setattr(requests, "post", _post)
    bob = _signed_in(_client(), tg.bob)
    assert _feedback(bob, {"message": f"Help\n\nUser ID: {tg.alice['id']}"}).status_code == 200
    reply_to = 880_001
    stranger = _tg_update(301, reply_to=reply_to, sender=999_999, text="Stranger")
    assert _hook(tg.client, stranger).get_json()["status"] == "ignored"
    assert _hook(tg.client, _tg_update(302, reply_to=reply_to, text="Operator answer")).get_json()["status"] == "saved"
    assert _admin_messages(tg.bob["id"]) == ["Operator answer"]
    assert _admin_messages(tg.alice["id"]) == []
    assert _row("SELECT COUNT(*) AS n FROM support_messages WHERE sender = 'admin'")["n"] == 1


# ========================================================================================= Contact


def _contact(client=None, *, ip=ATTACKER, headers=None, **fields):
    body = {"email": "visitor@example.com", "topic": "Billing", "message": "Where is my receipt?", **fields}
    return (client or _client()).post("/api/contact", json=body, environ_base={"REMOTE_ADDR": ip},
                                      headers=headers or {})


def test_31_contact_hourly_limit_is_ten_per_network(traps):
    codes = [_contact().status_code for _ in range(11)]
    assert codes == [200] * 10 + [429]
    assert len(traps.telegram) == 10


def test_32_contact_daily_limit_is_thirty_per_network(traps):
    codes = []
    for _hour in range(3):
        codes += [_contact().status_code for _ in range(10)]
        _age_events("contact:", 3601)
    blocked = _contact()
    assert codes == [200] * 30 and blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 3600
    assert len(traps.telegram) == 30


def _contact_worker(i, barrier, queue):
    client = _client()
    barrier.wait(60)
    queue.put(_contact(client, message=f"parallel {i}").status_code)


def test_33_concurrent_contact_requests_cannot_exceed_the_limit(traps, monkeypatch):
    monkeypatch.setenv("CONTACT_LIMIT_PER_IP_HOUR", "3")
    results = _run_workers(_contact_worker, 10)
    assert sorted(results) == [200] * 3 + [429] * 7
    assert _events("contact:ip:") == 3


def test_34_spoofed_proxy_headers_and_ipv6_rotation_do_not_bypass_contact_limits(traps, monkeypatch):
    codes = [_contact(headers={"X-Forwarded-For": f"10.9.{n}.1", "X-Real-IP": f"10.8.{n}.1",
                               "CF-Connecting-IP": f"10.7.{n}.1"}).status_code for n in range(11)]
    assert codes == [200] * 10 + [429]
    monkeypatch.setenv("CONTACT_LIMIT_PER_IP_HOUR", "2")
    v6 = [_contact(ip=f"2001:db8:9:9::{n + 1:x}").status_code for n in range(3)]
    assert v6 == [200, 200, 429]
    assert len(traps.telegram) == 12


def test_35_legitimate_contact_flow_and_validation(traps):
    res = _contact(message="My download link expired")
    assert res.status_code == 200 and res.get_json() == {"success": True}
    text = traps.telegram[-1]
    assert "visitor@example.com" in text and "Billing" in text and "My download link expired" in text
    assert _contact(email="not-an-email").status_code == 400
    assert _contact(message="").status_code == 400
    assert _contact(message="z" * 4001).status_code == 400
    assert _client().post("/api/contact", json=["message"]).status_code == 400
    assert len(traps.telegram) == 1
    assert _events("contact:ip:") == 1  # rejected bodies never take a slot
    with economy_db.connect() as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'support_telegram_map'").fetchone()
        mapped = conn.execute("SELECT COUNT(*) AS n FROM support_telegram_map").fetchone()["n"] if exists else 0
    assert mapped == 0  # a contact message is never bound to an account


def test_source_ids_group_ipv6_by_64_and_never_trust_the_raw_string():
    assert rate_limit.source_id("203.0.113.5") == "203.0.113.5"
    assert rate_limit.source_id("2001:db8:1:2::1") == rate_limit.source_id("2001:db8:1:2:ffff::9") == "2001:db8:1:2::/64"
    assert rate_limit.source_id("::ffff:203.0.113.5") == "203.0.113.5"
    assert rate_limit.source_id(None) == rate_limit.source_id("not-an-ip") == "unknown"


def test_hit_all_records_every_key_or_none(economy):
    assert rate_limit.hit_all([("a", [(1, 60)]), ("b", [(2, 60)])]) is None
    assert rate_limit.hit_all([("a", [(1, 60)]), ("b", [(2, 60)])]) is not None
    assert _events("a") == 1 and _events("b") == 1
    assert free_humanize.reserve_all([("p", 1), ("q", 2)]) is True
    assert free_humanize.reserve_all([("p", 1), ("q", 2)]) is False
    assert free_humanize.used_today("q") == 1
