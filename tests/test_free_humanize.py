"""Free humanizer allowance: word limits, daily counters, rate limit, free vs paid routing."""

from __future__ import annotations

import pytest

from services import free_humanize
from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy.wallet import WalletService

EN = "Please rewrite this paragraph so it reads like a person wrote it."
STUDENT = {
    "humanized_text": "Rewritten by our model.",
    "elapsed_seconds": 1.0,
    "provider": "DocMaxxing",
    "engine": "docmaxxing-student-v1",
    "request_id": "student-free",
}
URL = "/api/browser/providers/stealthwriter/humanize"


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    for name in (
        "FREE_HUMANIZE_GUEST_WORDS",
        "FREE_HUMANIZE_GUEST_DAILY",
        "FREE_HUMANIZE_GUEST_IP_DAILY",
        "FREE_HUMANIZE_USER_WORDS",
        "FREE_HUMANIZE_USER_DAILY",
        "FREE_HUMANIZE_ENGINE",
        "FREE_HUMANIZE_GUEST_RATE_PER_MIN",
        "HUMANIZE_MAX_WORDS",
    ):
        monkeypatch.delenv(name, raising=False)
    economy_db.init_db()
    return tmp_path


@pytest.fixture()
def engine(monkeypatch):
    """Student engine stub; StealthWriter must never start unless a test allows it."""
    import app as app_mod

    calls: list[bool] = []
    state = {"result": STUDENT}

    def fake_student(_text, *, rescue=False):
        calls.append(rescue)
        return state["result"]

    def no_stealthwriter():
        raise AssertionError("StealthWriter must not run")

    monkeypatch.setattr(app_mod, "_student_humanize", fake_student)
    monkeypatch.setattr(app_mod, "ensure_engine_started", no_stealthwriter)
    monkeypatch.setattr(app_mod, "_stealthwriter_down_until", 0.0)
    monkeypatch.setattr(app_mod, "health_monitor", None)
    return {"calls": calls, "state": state}


def _client():
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


def _user_client(email: str, balance: int = 500):
    user = economy_auth.create_user(email, "secret123")
    economy_auth.mark_email_verified(user["id"], user["email"])
    WalletService().set_balance(user["id"], balance)
    client = _client()
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    return client, user


def _words(n: int) -> str:
    return " ".join(["word"] * n)


# --- configuration -----------------------------------------------------------


def test_defaults_and_env_overrides(monkeypatch):
    for name in ("FREE_HUMANIZE_GUEST_WORDS", "FREE_HUMANIZE_ENGINE", "HUMANIZE_MAX_WORDS"):
        monkeypatch.delenv(name, raising=False)
    lim = free_humanize.limits()
    assert (lim.guest_words, lim.guest_daily, lim.user_words, lim.user_daily) == (1000, 3, 1500, 10)
    assert lim.guest_ip_daily == 3
    assert lim.engine == "student"
    assert lim.guest_rate_per_minute == 10
    assert lim.max_words == 5000
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_WORDS", "250")
    monkeypatch.setenv("FREE_HUMANIZE_ENGINE", "default")
    monkeypatch.setenv("HUMANIZE_MAX_WORDS", "nonsense")
    lim = free_humanize.limits()
    assert lim.guest_words == 250
    assert lim.engine == "default"
    assert lim.max_words == 5000


# --- counter -----------------------------------------------------------------


def test_reserve_counts_up_to_the_daily_limit_and_resets_next_day(economy):
    subject = free_humanize.user_subject(7)
    for _ in range(3):
        assert free_humanize.reserve(subject, 3, day="2026-11-01")
    assert not free_humanize.reserve(subject, 3, day="2026-11-01")
    assert free_humanize.remaining_today(subject, 3, day="2026-11-01") == 0
    assert free_humanize.remaining_today(subject, 3, day="2026-11-02") == 3
    assert free_humanize.reserve(subject, 3, day="2026-11-02")


def test_release_gives_the_run_back(economy):
    subject = free_humanize.user_subject(8)
    assert free_humanize.reserve(subject, 1, day="2026-11-01")
    free_humanize.release(subject, day="2026-11-01")
    assert free_humanize.remaining_today(subject, 1, day="2026-11-01") == 1
    free_humanize.release(subject, day="2026-11-01")
    assert free_humanize.used_today(subject, day="2026-11-01") == 0


def test_zero_daily_limit_never_reserves(economy):
    assert not free_humanize.reserve("user:1", 0)


def test_old_days_are_pruned(economy):
    subject = free_humanize.user_subject(9)
    free_humanize.reserve(subject, 5, day="2026-10-01")
    free_humanize.reserve(subject, 5, day="2026-11-01")
    assert free_humanize.used_today(subject, day="2026-10-01") == 0


def test_guest_subject_depends_on_ip_and_session_and_hides_the_ip():
    a = free_humanize.guest_subject("1.2.3.4", "sid-a", "salt")
    assert a.startswith("guest:") and "1.2.3.4" not in a
    assert a != free_humanize.guest_subject("1.2.3.5", "sid-a", "salt")
    assert a != free_humanize.guest_subject("1.2.3.4", "sid-b", "salt")
    assert a == free_humanize.guest_subject("1.2.3.4", "sid-a", "salt")


_NGINX = {"REMOTE_ADDR": "127.0.0.1"}


def test_client_ip_prefers_proxy_headers(monkeypatch):
    from flask import request

    from app import app

    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    with app.test_request_context(
        "/", headers={"X-Real-IP": "9.9.9.9", "X-Forwarded-For": "1.1.1.1"}, environ_base=_NGINX
    ):
        assert free_humanize.client_ip(request) == "9.9.9.9"
    with app.test_request_context("/", headers={"X-Forwarded-For": "6.6.6.6, 2.2.2.2"}, environ_base=_NGINX):
        assert free_humanize.client_ip(request) == "2.2.2.2"
    with app.test_request_context(
        "/", headers={"X-Real-IP": "9.9.9.9", "X-Forwarded-For": "1.1.1.1"}, environ_base={"REMOTE_ADDR": "8.8.4.4"}
    ):
        assert free_humanize.client_ip(request) == "8.8.4.4"


def test_client_ip_trusts_cf_connecting_ip_only_from_cloudflare(monkeypatch):
    from flask import request

    from app import app

    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    with app.test_request_context(
        "/", headers={"X-Real-IP": "172.70.1.2", "CF-Connecting-IP": "5.5.5.5"}, environ_base=_NGINX
    ):
        assert free_humanize.client_ip(request) == "5.5.5.5"
    with app.test_request_context(
        "/", headers={"X-Real-IP": "2606:4700::1", "CF-Connecting-IP": "5.5.5.6"}, environ_base=_NGINX
    ):
        assert free_humanize.client_ip(request) == "5.5.5.6"
    with app.test_request_context(
        "/", headers={"X-Real-IP": "9.9.9.9", "CF-Connecting-IP": "5.5.5.5"}, environ_base=_NGINX
    ):
        assert free_humanize.client_ip(request) == "9.9.9.9"
    with app.test_request_context("/", headers={"CF-Connecting-IP": "5.5.5.5"}, environ_base={"REMOTE_ADDR": "8.8.4.4"}):
        assert free_humanize.client_ip(request) == "8.8.4.4"


def test_rate_limiter_sliding_window():
    now = [0.0]
    limiter = free_humanize.RateLimiter(clock=lambda: now[0])
    assert limiter.allow("ip", 2)
    assert limiter.allow("ip", 2)
    assert not limiter.allow("ip", 2)
    assert limiter.allow("other", 2)
    now[0] = 61.0
    assert limiter.allow("ip", 2)
    assert limiter.allow("ip", 0)


# --- server word cap ---------------------------------------------------------


def test_server_word_cap_on_every_humanizer_endpoint(economy, engine, monkeypatch):
    from services.veil_tokens import issue_token

    monkeypatch.setenv("HUMANIZE_MAX_WORDS", "10")
    client, user = _user_client("cap@example.com")
    for url in (URL, "/api/humanizer/run"):
        res = client.post(url, json={"text": _words(11)})
        assert res.status_code == 400, url
        body = res.get_json()
        assert body["error"] == "TOO_MANY_WORDS"
        assert body["max_words"] == 10
    res = _client().post("/api/extension/humanize", json={"text": _words(11), "key": issue_token(user["id"])})
    assert res.status_code == 400
    assert res.get_json()["error"] == "TOO_MANY_WORDS"
    assert WalletService().get_balance(user["id"]) == 500
    assert engine["calls"] == []


# --- guests ------------------------------------------------------------------


def test_guest_gets_three_free_student_runs_then_signup(economy, engine):
    client = _client()
    for left in (2, 1, 0):
        res = client.post(URL, json={"text": EN})
        body = res.get_json()
        assert res.status_code == 200, body
        assert body["free_run"] is True
        assert body["coins_charged"] == 0
        assert body["humanized_text"] == "Rewritten by our model."
        assert body["free_runs_left"] == left
    assert engine["calls"] == [True, True, True]

    res = client.post(URL, json={"text": EN})
    assert res.status_code == 403
    body = res.get_json()
    assert body["error"] == "REGISTER_REQUIRED"
    assert body["reason"] == "FREE_LIMIT_REACHED"
    assert "10" in body["message"]
    assert len(engine["calls"]) == 3


def test_guest_daily_counter_resets_next_day(economy, engine, monkeypatch):
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_DAILY", "1")
    monkeypatch.setattr(free_humanize, "today", lambda now=None: "2026-11-01")
    client = _client()
    assert client.post(URL, json={"text": EN}).status_code == 200
    assert client.post(URL, json={"text": EN}).status_code == 403
    monkeypatch.setattr(free_humanize, "today", lambda now=None: "2026-11-02")
    assert client.post(URL, json={"text": EN}).status_code == 200


def test_guest_word_limit(economy, engine):
    res = _client().post(URL, json={"text": _words(1001)})
    assert res.status_code == 403
    body = res.get_json()
    assert body["error"] == "FREE_WORD_LIMIT"
    assert body["max_words"] == 1000
    assert engine["calls"] == []
    assert _client().post(URL, json={"text": _words(1000)}).status_code == 200


def test_guest_free_run_failure_is_not_counted(economy, engine, monkeypatch):
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_DAILY", "1")
    client = _client()
    engine["state"]["result"] = None
    res = client.post(URL, json={"text": EN})
    assert res.status_code == 503
    body = res.get_json()
    assert body["error"] == "FREE_ENGINE_UNAVAILABLE"
    assert "Try again" in body["message"]
    engine["state"]["result"] = STUDENT
    assert client.post(URL, json={"text": EN}).status_code == 200


def test_guest_rate_limit(economy, engine, monkeypatch):
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_RATE_PER_MIN", "2")
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_DAILY", "100")
    client = _client()
    assert client.post(URL, json={"text": EN}).status_code == 200
    assert client.post(URL, json={"text": EN}).status_code == 200
    res = client.post(URL, json={"text": EN})
    assert res.status_code == 429
    assert res.get_json()["error"] == "RATE_LIMITED"
    assert res.headers["Retry-After"] == "60"


def test_guest_non_english_text_is_not_a_free_run(economy, engine):
    res = _client().post(URL, json={"text": "Это русский текст для проверки хуманайзера."})
    assert res.status_code == 422
    assert res.get_json()["error"] == "FREE_ENGLISH_ONLY"
    assert engine["calls"] == []


def test_new_sessions_on_one_ip_share_the_ip_cap(economy, engine, monkeypatch):
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_IP_DAILY", "2")
    assert _client().post(URL, json={"text": EN}).status_code == 200
    assert _client().post(URL, json={"text": EN}).status_code == 200
    res = _client().post(URL, json={"text": EN})
    assert res.status_code == 403
    assert res.get_json()["error"] == "REGISTER_REQUIRED"
    other_ip = _client().post(URL, json={"text": EN}, environ_base={"REMOTE_ADDR": "10.0.0.9"})
    assert other_ip.status_code == 200
    assert len(engine["calls"]) == 3


def test_failed_guest_run_gives_back_the_ip_run_too(economy, engine, monkeypatch):
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_IP_DAILY", "1")
    engine["state"]["result"] = None
    assert _client().post(URL, json={"text": EN}).status_code == 503
    engine["state"]["result"] = STUDENT
    assert _client().post(URL, json={"text": EN}).status_code == 200


# --- signed-in users ---------------------------------------------------------


def test_user_free_run_is_free_and_uses_student(economy, engine):
    client, user = _user_client("free-user@example.com")
    res = client.post(URL, json={"text": EN})
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["free_run"] is True
    assert body["coins_charged"] == 0
    assert body["free_runs_left"] == 9
    assert body["guest_trial"] is False
    assert engine["calls"] == [True]
    assert WalletService().get_balance(user["id"]) == 500


def test_user_over_daily_limit_pays_with_the_usual_routing(economy, engine, monkeypatch):
    monkeypatch.setenv("FREE_HUMANIZE_USER_DAILY", "1")
    client, user = _user_client("paid-user@example.com")
    assert client.post(URL, json={"text": EN}).get_json()["free_run"] is True
    res = client.post(URL, json={"text": EN})
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["free_run"] is False
    assert body["coins_charged"] > 0
    assert WalletService().get_balance(user["id"]) == 500 - body["coins_charged"]
    assert engine["calls"] == [True, False]


def test_user_over_word_limit_pays(economy, engine):
    client, user = _user_client("long-user@example.com")
    res = client.post(URL, json={"text": _words(1501)})
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["free_run"] is False
    assert body["coins_charged"] > 0
    assert free_humanize.used_today(free_humanize.user_subject(user["id"])) == 0


def test_user_free_run_failure_is_not_charged_or_counted(economy, engine):
    client, user = _user_client("fail-user@example.com")
    engine["state"]["result"] = None
    res = client.post(URL, json={"text": EN})
    assert res.status_code == 503
    assert res.get_json()["error"] == "FREE_ENGINE_UNAVAILABLE"
    assert WalletService().get_balance(user["id"]) == 500
    assert free_humanize.used_today(free_humanize.user_subject(user["id"])) == 0


def test_default_engine_routes_free_runs_like_paid_ones(economy, engine, monkeypatch):
    monkeypatch.setenv("FREE_HUMANIZE_ENGINE", "default")
    client, user = _user_client("default-engine@example.com")
    body = client.post(URL, json={"text": EN}).get_json()
    assert body["free_run"] is True
    assert body["coins_charged"] == 0
    assert engine["calls"] == [False]
    assert WalletService().get_balance(user["id"]) == 500


def test_user_with_an_active_plan_keeps_the_paid_routing(economy, engine, monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod, "_has_active_plan", lambda _user: True)
    client, user = _user_client("plan-user@example.com")
    body = client.post(URL, json={"text": EN}).get_json()
    assert body["free_run"] is False
    assert engine["calls"] == [False]
    assert free_humanize.used_today(free_humanize.user_subject(user["id"])) == 0


def test_unverified_user_still_hits_the_email_gate(economy, engine):
    user = economy_auth.create_user("unverified@example.com", "secret123")
    client = _client()
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    res = client.post(URL, json={"text": EN})
    assert res.status_code in (401, 403)
    assert engine["calls"] == []


# --- app boot ------------------------------------------------------------------


def test_app_boot_reports_free_allowance(economy, monkeypatch):
    import app as app_mod

    monkeypatch.delenv("LEGACY_UI", raising=False)
    with app_mod.app.test_request_context("/app"):
        boot = app_mod._app_v2_boot()
    assert boot["freeHumanize"] == {
        "guestWords": 1000,
        "guestDaily": 3,
        "userWords": 1500,
        "userDaily": 10,
        "maxWords": 5000,
        "runsLeft": 3,
    }
    assert boot["guestHumanizeUsed"] is False
