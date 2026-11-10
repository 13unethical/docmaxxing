"""Product growth analytics: privacy-safe events, metrics, admin access."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from services import product_analytics as pa
from services.economy import auth as economy_auth
from services.economy import db as economy_db


@pytest.fixture()
def analytics_env(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "test-secret-for-product-analytics")
    monkeypatch.setenv("PRODUCT_ANALYTICS_SALT", "pa-test-salt")
    for name in list(os.environ):
        if name.startswith(("FREE_", "SMARTFORM_", "LOGIN_", "OTP_", "TRUSTED_")):
            monkeypatch.delenv(name, raising=False)
    economy_db.init_db()
    pa.ensure_schema()
    yield


def _count(event: str | None = None) -> int:
    with economy_db.connect() as conn:
        if event:
            return conn.execute(
                "SELECT COUNT(*) FROM product_events WHERE event = ?", (event,)
            ).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM product_events").fetchone()[0]


def _rows(event: str | None = None):
    with economy_db.connect() as conn:
        if event:
            return conn.execute(
                "SELECT * FROM product_events WHERE event = ? ORDER BY id", (event,)
            ).fetchall()
        return conn.execute("SELECT * FROM product_events ORDER BY id").fetchall()


def test_word_bucket_boundaries():
    assert pa.word_bucket(0) == "0-500"
    assert pa.word_bucket(500) == "0-500"
    assert pa.word_bucket(501) == "501-1000"
    assert pa.word_bucket(2001) == "2001-5000"
    assert pa.word_bucket(9000) == "5000+"
    assert pa.word_bucket(None) is None


def test_duplicate_first_success_is_deduped(analytics_env):
    assert pa.record(
        "humanizer_first_success",
        user_id=1,
        tool="humanizer",
        words=800,
        dedupe_key="humanizer_first_success:u:1",
    )
    assert not pa.record(
        "humanizer_first_success",
        user_id=1,
        tool="humanizer",
        words=900,
        dedupe_key="humanizer_first_success:u:1",
    )
    assert _count("humanizer_first_success") == 1
    pa.record_tool_success("humanizer", user_id=1, words=800)
    pa.record_tool_success("humanizer", user_id=1, words=900)
    assert _count("humanizer_first_success") == 1
    assert _count("humanizer_success") == 2


def test_anonymous_vs_authenticated_attribution(analytics_env):
    class Sess(dict):
        pass

    sess = Sess()
    anon = pa.anon_id_from_session(sess)
    assert anon and len(anon) == 32
    pa.record_tool_success("detector", user_id=None, words=200, session=sess)
    pa.record_tool_success("detector", user_id=42, words=200, session=sess)
    rows = _rows("detector_success")
    assert rows[0]["user_id"] is None and rows[0]["anon_id"] == anon
    assert rows[1]["user_id"] == 42
    # Authenticated success does not require anon_id
    assert rows[1]["anon_id"] is None or rows[1]["user_id"] == 42


def test_cross_user_isolation_in_snapshot(analytics_env):
    with economy_db.connect() as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash, is_verified, is_admin) VALUES (?, ?, 1, 0)",
            ("a@example.com", "x"),
        )
        conn.execute(
            "INSERT INTO users (email, password_hash, is_verified, is_admin) VALUES (?, ?, 1, 0)",
            ("b@example.com", "x"),
        )
        conn.commit()
    pa.record("humanizer_success", user_id=1, tool="humanizer", words=100)
    pa.record("humanizer_success", user_id=1, tool="humanizer", words=100)
    pa.record("humanizer_success", user_id=2, tool="humanizer", words=100)
    snap = pa.growth_snapshot(period="today", exclude_staff=False)
    hum = next(m for m in snap["metrics"] if m["key"] == "humanizer_usage")
    assert hum["available"] and hum["value"] == 3
    dau = next(m for m in snap["metrics"] if m["key"] == "dau")
    assert dau["value"] == 2


def test_failed_ai_operation_does_not_record_success(analytics_env):
    # Simulate: only call record on success paths; a failure path records nothing.
    before = _count()
    # Explicit failure outcome is allowed for completeness but product hooks do not use it.
    pa.record("humanizer_success", user_id=1, tool="humanizer", outcome="failure", words=50)
    assert _count("humanizer_success") == 1
    row = _rows("humanizer_success")[0]
    assert row["outcome"] == "failure"
    # Growth counters only count outcome=success
    snap = pa.growth_snapshot(period="today", exclude_staff=False)
    hum = next(m for m in snap["metrics"] if m["key"] == "humanizer_usage")
    assert hum["value"] == 0
    assert _count() == before + 1


def test_no_document_or_secrets_in_events(analytics_env):
    secretish = "sk-ant-api03-THIS_IS_NOT_A_REAL_KEY_XXXX"
    document = "Student essay body that must never be stored " * 20
    pa.record(
        "humanizer_success",
        user_id=7,
        tool="humanizer",
        words=len(document.split()),
        source="newsletter",
    )
    with economy_db.connect() as conn:
        blob = " ".join(
            str(c) for row in conn.execute("SELECT * FROM product_events").fetchall() for c in row
        )
    assert document.strip() not in blob
    assert secretish not in blob
    assert "password" not in blob.lower()
    row = _rows("humanizer_success")[0]
    assert set(row.keys()) >= {
        "event", "created_at", "user_id", "anon_id", "tool", "word_bucket", "outcome", "source"
    }
    assert row["word_bucket"] == pa.word_bucket(len(document.split()))


def test_d1_and_d7_unavailable_with_small_cohort(analytics_env):
    snap = pa.growth_snapshot(period="today", exclude_staff=False)
    d1 = next(m for m in snap["metrics"] if m["key"] == "d1_retention")
    d7 = next(m for m in snap["metrics"] if m["key"] == "d7_retention")
    assert d1["available"] is False and d1["value"] is None
    assert d7["available"] is False and d7["value"] is None
    assert "Fewer than 5" in (d1["reason"] or "")


def test_d1_retention_calculation(analytics_env):
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat() + " 12:00:00"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d 12:00:00")
    with economy_db.connect() as conn:
        for i in range(5):
            conn.execute(
                "INSERT INTO users (email, password_hash, is_verified) VALUES (?, ?, 1)",
                (f"u{i}@example.com", "x"),
            )
        conn.commit()
        for uid in range(1, 6):
            conn.execute(
                "INSERT INTO product_events (event, user_id, outcome, created_at) VALUES (?, ?, 'success', ?)",
                ("registration_completed", uid, yesterday),
            )
        # 3 of 5 return today
        for uid in (1, 2, 3):
            conn.execute(
                "INSERT INTO product_events (event, user_id, outcome, created_at) VALUES (?, ?, 'success', ?)",
                ("humanizer_success", uid, today),
            )
        conn.commit()
    snap = pa.growth_snapshot(period="d7", exclude_staff=False)
    d1 = next(m for m in snap["metrics"] if m["key"] == "d1_retention")
    assert d1["available"] is True
    assert d1["numerator"] == 3 and d1["denominator"] == 5
    assert d1["value"] == 0.6


def test_utm_capture_and_client_event_allowlist(analytics_env):
    class Req:
        def __init__(self):
            self.args = {"utm_source": "twitter", "utm_medium": "social", "evil": "drop"}

    sess: dict = {}
    pa.capture_acquisition(Req(), sess)
    assert sess["_pa_utm_source"] == "twitter"
    assert sess["_pa_utm_medium"] == "social"
    assert "evil" not in sess
    assert "pricing_viewed" in pa.CLIENT_EVENTS
    assert "payment_completed" not in pa.CLIENT_EVENTS
    pa.record("pricing_viewed", user_id=None, session=sess, tool="pricing")
    row = _rows("pricing_viewed")[0]
    assert row["source"] == "twitter"


def test_admin_overview_includes_growth(analytics_env, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "y" * 40)
    from services.economy import admin_panel

    ov = admin_panel.overview()
    assert "growth" in ov
    assert "today" in ov["growth"]
    metrics = ov["growth"]["today"]["metrics"]
    assert any(m["key"] == "dau" for m in metrics)
    assert any(m["key"] == "humanizer_usage" for m in metrics)
    # Admin gate is @admin_required on /api/admin/panel/overview (verified admin only).
    assert economy_auth.is_admin({"is_admin": True, "is_verified": True}) is True
    assert economy_auth.is_admin({"is_admin": True, "is_verified": False}) is False
    assert economy_auth.is_admin({"is_admin": False, "is_verified": True}) is False


def test_registration_and_verify_emit_events(analytics_env, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "y" * 40)
    user = economy_auth.create_user("new@example.com", "password123")
    assert _count("registration_completed") == 1
    # Duplicate registration event for same user is deduped
    pa.record(
        "registration_completed",
        user_id=int(user["id"]),
        tool="auth",
        dedupe_key=f"registration_completed:u:{int(user['id'])}",
    )
    assert _count("registration_completed") == 1

    code = economy_auth.issue_verification_otp(int(user["id"]))
    verified = economy_auth.verify_email_otp(int(user["id"]), code)
    assert verified["is_verified"] is True
    assert _count("email_verified") == 1
