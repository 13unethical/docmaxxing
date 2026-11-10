"""Per-network limits: rotating addresses inside one IPv6 /64 must not reset a limit.

Guest humanizer runs, guest free-AI pools, sign-in and code-guess limits, code issuing and
anonymous reference lookups are keyed by ``rate_limit.source_id`` (IPv4 address or IPv6 /64).
Each request below comes from a fresh session, as if the client cleared cookies.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from services import free_humanize
from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy import login_throttle

_KNOB_PREFIXES = (
    "FREE_HUMANIZE_", "FREE_DOC_AI_", "SMARTFORM_", "LOGIN_", "OTP_", "VERIFY_EMAIL_",
    "REFERENCE_LOOKUPS_",
)


@pytest.fixture()
def app_mod(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    for name in list(os.environ):
        if name.startswith(_KNOB_PREFIXES) or name == "TRUSTED_PROXIES":
            monkeypatch.delenv(name, raising=False)
    economy_db.init_db()
    free_humanize.guest_rate_limiter.reset()
    import app as module

    yield module
    free_humanize.guest_rate_limiter.reset()


def _in_64(i: int, net: str = "2001:db8:1:2") -> str:
    return f"{net}::{i + 1:x}"


def _ctx(module, ip: str, path: str = "/"):
    return module.app.test_request_context(path, method="POST", environ_base={"REMOTE_ADDR": ip})


def _humanize_runs(module, ips) -> int:
    granted = 0
    for ip in ips:
        with _ctx(module, ip, "/api/browser/providers/stealthwriter/humanize"):
            subject, refusal = module._free_humanize_gate(None, "word " * 50, english_only=False)
            granted += subject is not None and refusal is None
    return granted


def _free_ai_units(module, pool: str, ips) -> int:
    granted = 0
    for ip in ips:
        with _ctx(module, ip, "/api/structure-recovery"):
            grant = module._free_ai_grant(pool)
            if grant.acquire():
                granted += 1
                grant.note_provider_call()
                grant.finish()
    return granted


def _events(key: str) -> int:
    with economy_db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM rate_limit_events WHERE key = ?", (key,)).fetchone()[0]


def test_guest_humanizer_daily_pool_covers_the_whole_ipv6_64(app_mod):
    daily = free_humanize.limits().guest_ip_daily
    assert _humanize_runs(app_mod, [_in_64(i) for i in range(12)]) == daily
    assert _humanize_runs(app_mod, [_in_64(i, "2001:db8:1:3") for i in range(12)]) == daily
    assert _humanize_runs(app_mod, ["198.51.100.7"] * 12) == daily


def test_guest_humanizer_minute_limit_covers_the_whole_ipv6_64(app_mod, monkeypatch):
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_DAILY", "100")
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_IP_DAILY", "100")
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_RATE_PER_MIN", "10")
    assert _humanize_runs(app_mod, [_in_64(i) for i in range(15)]) == 10


def test_ipv4_and_mapped_guest_pools_keep_their_existing_subject(app_mod):
    salt = "s" * 40
    legacy = "guest-ip:" + hashlib.sha256(f"{salt}|198.51.100.7".encode()).hexdigest()
    assert free_humanize.guest_ip_subject("198.51.100.7", salt) == legacy
    assert free_humanize.guest_ip_subject("::ffff:198.51.100.7", salt) == legacy
    assert free_humanize.guest_ip_subject(None, salt) is None


@pytest.mark.parametrize(("pool", "bound"), [("document", 3), ("brief", 5)])
def test_guest_free_ai_pools_cover_the_whole_ipv6_64(app_mod, pool, bound):
    # document: 3 guest units a day per network; brief: 5 per minute per network.
    assert _free_ai_units(app_mod, pool, [_in_64(100 + i) for i in range(15)]) == bound


def test_sign_in_ip_limit_covers_the_whole_ipv6_64_and_account_limit_still_holds(app_mod):
    spray = [login_throttle.begin("login", f"r{i}@example.com", _in_64(300 + i)) for i in range(40)]
    assert sum(not isinstance(g, int) for g in spray) == 30
    victim = [
        login_throttle.begin("login", "victim@example.com", _in_64(0, f"2001:db8:{9 + i:x}:1"))
        for i in range(8)
    ]
    assert sum(not isinstance(g, int) for g in victim) == 5


def test_code_guess_ip_limit_covers_the_whole_ipv6_64(app_mod):
    allowed = 0
    for i in range(40):
        with _ctx(app_mod, _in_64(400 + i)):
            allowed += app_mod._otp_verify_wait() is None
    assert allowed == 30
    assert _events("otp_verify:ip:2001:db8:1:2::/64") == 30


def test_code_issue_ip_key_is_the_network(app_mod):
    user = economy_auth.create_user("issue@example.com", "password123")
    for i in range(3):
        with _ctx(app_mod, _in_64(500 + i)):
            assert app_mod._otp_resend_wait(int(user["id"])) is None
    assert _events("otp_issue:ip:2001:db8:1:2::/64") == 3


def test_reference_lookup_limit_covers_the_whole_ipv6_64(app_mod):
    allowed = 0
    for i in range(25):
        with _ctx(app_mod, _in_64(600 + i), "/api/reference"):
            allowed += app_mod._reference_fetch_wait() is None
    assert allowed == 20
