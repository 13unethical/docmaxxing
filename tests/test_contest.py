"""The $2,500 Challenge — scoring, phases, flags, prizes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.economy import auth as economy_auth
from services.economy import contest as C
from services.economy import db as economy_db


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    db_path = tmp_path / "contest.db"
    monkeypatch.setattr(economy_db, "DB_PATH", db_path)
    economy_db.init_db()
    monkeypatch.delenv("CONTEST_PHASE_OVERRIDE", raising=False)
    return db_path


def _user(email: str, *, referrer_code: str | None = None, verified: bool = True):
    user = economy_auth.create_user(email, "secret123", referral_code=referrer_code or "")
    if verified:
        economy_auth.mark_email_verified(user["id"], user["email"])
    return user


def test_phase_boundaries(monkeypatch, economy):
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "before")
    assert C.contest_phase() == "before"
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "live")
    assert C.contest_phase() == "live"
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "results")
    assert C.contest_phase() == "results"


def test_friend_humanize_awards_once(monkeypatch, economy):
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "live")
    host = _user("host@example.com")
    from services.economy.referral import ensure_referral_code

    code = ensure_referral_code(host["id"])
    C.mark_eligible(host["id"])
    friend = _user("friend@example.com", referrer_code=code)
    first = C.on_humanize_success(friend["id"], email_verified=True)
    second = C.on_humanize_success(friend["id"], email_verified=True)
    assert first["friend_point"] is True
    assert second["friend_point"] is False
    board = C.leaderboard(limit=10)
    assert board[0]["user_id"] == host["id"]
    assert board[0]["pts"] == 1


def test_pre_contest_referral_still_counts(monkeypatch, economy):
    """Friends who signed up before Nov 20 still award +1 when they humanize."""
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "live")
    host = _user("oldhost@example.com")
    from services.economy.referral import ensure_referral_code

    code = ensure_referral_code(host["id"])
    C.mark_eligible(host["id"])
    friend = _user("oldfriend@example.com", referrer_code=code)
    with economy_db.connect() as conn:
        conn.execute(
            "UPDATE users SET created_at = ? WHERE id = ?",
            ("2026-01-15 12:00:00", friend["id"]),
        )
    out = C.on_humanize_success(friend["id"], email_verified=True)
    assert out["friend_point"] is True
    assert C.leaderboard(limit=5)[0]["pts"] == 1


def test_backfill_historical_humanized_friends(monkeypatch, economy):
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "live")
    host = _user("backhost@example.com")
    from services.economy.referral import ensure_referral_code

    code = ensure_referral_code(host["id"])
    # Host never humanized after the race started — backfill must still open eligibility.
    friend = _user("backfriend@example.com", referrer_code=code)
    # Friend already humanized before the race (eligible row), but host never got a point.
    C.mark_eligible(friend["id"])
    with economy_db.connect() as conn:
        conn.execute(
            "UPDATE users SET created_at = ? WHERE id = ?",
            ("2025-06-01 00:00:00", friend["id"]),
        )
    n = C.backfill_friend_humanize_points(force=True)
    assert n == 1
    assert C.backfill_friend_humanize_points(force=True) == 0  # idempotent
    board = C.leaderboard(limit=5)
    assert board[0]["user_id"] == host["id"]
    assert board[0]["pts"] == 1
    prof = C.profile_for_user(host, public_origin="")
    assert prof["state"] != "need_humanize"


def test_backfill_marks_host_eligible_from_wallet_debit(monkeypatch, economy):
    """Friends who only left a humanize debit still count; host appears on the board."""
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "live")
    host = _user("txhost@example.com")
    from services.economy.referral import ensure_referral_code

    code = ensure_referral_code(host["id"])
    friend = _user("txfriend@example.com", referrer_code=code)
    with economy_db.connect() as conn:
        conn.execute(
            "INSERT INTO transactions "
            "(user_id, kind, feature, amount, balance_after, type, status) "
            "VALUES (?, 'debit', 'humanize', 25, 0, 'USAGE', 'completed')",
            (friend["id"],),
        )
    assert C.backfill_friend_humanize_points(force=True) == 1
    board = C.leaderboard(limit=5)
    assert board[0]["user_id"] == host["id"]
    assert board[0]["pts"] == 1


def test_backfill_detects_usage_feature_humanizer_label(monkeypatch, economy):
    """usage_events store FEATURE_HUMANIZER='Humanizer', not lowercase humanize."""
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "live")
    host = _user("humlabel@example.com")
    friend = _user("humfriend@example.com")
    with economy_db.connect() as conn:
        conn.execute(
            "INSERT INTO usage_events (user_id, feature, credits_used) VALUES (?, 'Humanizer', 0)",
            (host["id"],),
        )
        conn.execute(
            "INSERT INTO plan_usage (user_id, feature, period_key, used) "
            "VALUES (?, 'humanize', 'day:2026-11-20', 3)",
            (friend["id"],),
        )
    C.backfill_friend_humanize_points(force=True)
    assert C.profile_for_user(host, public_origin="")["state"] != "need_humanize"
    assert C.profile_for_user(friend, public_origin="")["state"] != "need_humanize"


def test_deposit_pending_then_confirm(monkeypatch, economy):
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "live")
    user = _user("spender@example.com")
    C.mark_eligible(user["id"])
    out = C.on_contest_deposit(user["id"], 19.9, payment_ref="pay_1")
    assert out["self"] is True
    assert out["points"] == 19
    prof = C.profile_for_user(user, public_origin="https://docmaxxing.com")
    assert prof["me"]["pts"] == 0
    assert prof["me"]["pending"] == 19
    # Confirm early
    with economy_db.connect() as conn:
        conn.execute(
            "UPDATE contest_ledger SET pending_until = ? WHERE payment_ref = ?",
            ("2000-01-01 00:00:00", "pay_1"),
        )
    assert C.confirm_pending_points() >= 1
    prof2 = C.profile_for_user(user, public_origin="https://docmaxxing.com")
    assert prof2["me"]["pts"] == 19


def test_deposit_also_awards_referrer(monkeypatch, economy):
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "live")
    host = _user("host2@example.com")
    from services.economy.referral import ensure_referral_code

    code = ensure_referral_code(host["id"])
    C.mark_eligible(host["id"])
    friend = _user("friend2@example.com", referrer_code=code)
    C.mark_eligible(friend["id"])
    C.on_contest_deposit(friend["id"], 10, payment_ref="pay_ref")
    with economy_db.connect() as conn:
        conn.execute(
            "UPDATE contest_ledger SET pending_until = '2000-01-01 00:00:00' WHERE payment_ref = ?",
            ("pay_ref",),
        )
    C.confirm_pending_points()
    board = {r["user_id"]: r["pts"] for r in C.leaderboard(limit=10)}
    assert board[friend["id"]] == 10
    # 10 from friend's spend + 1 from friend_humanize backfill (friend is already eligible)
    assert board[host["id"]] == 11


def test_dq_removes_from_leaderboard(monkeypatch, economy):
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "live")
    user = _user("dq@example.com")
    C.mark_eligible(user["id"])
    C.on_contest_deposit(user["id"], 50, payment_ref="pay_dq")
    with economy_db.connect() as conn:
        conn.execute(
            "UPDATE contest_ledger SET status = 'confirmed', pending_until = NULL WHERE payment_ref = ?",
            ("pay_dq",),
        )
    assert C.leaderboard()[0]["user_id"] == user["id"]
    C.set_flag(user["id"], C.FLAG_DQ, reason="abuse")
    assert C.leaderboard() == []
    prof = C.profile_for_user(user, public_origin="")
    assert prof["state"] == "excluded"


def test_prize_tiers_and_mins():
    assert C.resolve_prize(1, 500)["label"] == "$700"
    assert C.resolve_prize(1, 200)["label"] == "$100"  # below $200 min → next cash tier met
    assert C.resolve_prize(4, 50)["plan"] == "max"
    assert C.resolve_prize(25, 10)["plan"] == "basic"
    assert C.resolve_prize(40, 3)["kind"] == "credits"
    assert C.resolve_prize(40, 2)["kind"] == "none"


def test_reverse_deposit(monkeypatch, economy):
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "live")
    user = _user("refund@example.com")
    C.mark_eligible(user["id"])
    C.on_contest_deposit(user["id"], 12, payment_ref="pay_x")
    assert C.reverse_contest_deposit("pay_x") >= 1
    with economy_db.connect() as conn:
        conn.execute(
            "UPDATE contest_ledger SET pending_until = '2000-01-01 00:00:00' WHERE payment_ref = ?",
            ("pay_x",),
        )
    C.confirm_pending_points()
    assert C.leaderboard() == []


def test_api_contest_me(economy, monkeypatch):
    monkeypatch.setenv("CONTEST_PHASE_OVERRIDE", "live")
    from app import app

    app.config["TESTING"] = True
    client = app.test_client()
    res = client.get("/api/contest/me")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["phase"] == "live"
    assert body["state"] == "guest"
    assert "top" in body
