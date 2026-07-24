"""Tests for Usage (AI launch) records."""

from __future__ import annotations

import pytest

from services.economy import auth
from services.economy import db as economy_db
from services.economy.admin import AdminService
from services.economy.paddle_purchases import PaddlePurchaseService
from services.economy.usage import (
    FEATURE_DETECTION,
    FEATURE_HUMANIZER,
    FEATURE_TURNITIN,
    UsageService,
)
from services.economy.wallet import WalletService


@pytest.fixture()
def usage_db(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    with economy_db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("user@example.com", "hash"),
        )
        user_id = int(cur.lastrowid)
    return UsageService(), user_id


def test_record_and_list_usage(usage_db):
    svc, uid = usage_db
    row = svc.record(
        user_id=uid,
        feature=FEATURE_HUMANIZER,
        credits_used=10,
        provider="StealthWriter",
        latency=1234,
        request_id="job_abc",
    )
    assert row["feature"] == "Humanizer"
    assert row["credits_used"] == 10
    assert row["latency"] == 1234

    listed = svc.list_for_user(uid)
    assert listed["total"] == 1
    assert listed["usage"][0]["provider"] == "StealthWriter"


def test_multiple_features(usage_db):
    svc, uid = usage_db
    svc.record(user_id=uid, feature=FEATURE_DETECTION, credits_used=10, provider="ZeroGPT")
    svc.record(user_id=uid, feature=FEATURE_TURNITIN, credits_used=25, provider="PlagDetect")
    listed = svc.list_for_user(uid)
    assert listed["total"] == 2
    features = {u["feature"] for u in listed["usage"]}
    assert features == {"Detection", "Turnitin"}


def test_admin_get_usage(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    user = auth.create_user("u@example.com", "secret123")
    admin = AdminService(WalletService(), PaddlePurchaseService(), UsageService())
    admin.usage.record(
        user_id=user["id"],
        feature=FEATURE_HUMANIZER,
        credits_used=10,
        provider="StealthWriter",
        request_id="r1",
    )
    payload = admin.get_usage(user["id"])
    assert payload["user"]["email"] == "u@example.com"
    assert payload["total"] == 1
