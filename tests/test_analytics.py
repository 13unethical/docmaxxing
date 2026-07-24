"""Admin analytics aggregates."""

from __future__ import annotations

import pytest

from services.economy import auth
from services.economy import db as economy_db
from services.economy.admin import AdminService
from services.economy.analytics import AnalyticsService
from services.economy.paddle_purchases import STATUS_PAID, PaddlePurchaseService
from services.economy.usage import FEATURE_HUMANIZER, FEATURE_TURNITIN, UsageService
from services.economy.wallet import WalletService


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    a = auth.create_user("a@example.com", "secret123")
    b = auth.create_user("b@example.com", "secret123")
    return a, b


def test_analytics_snapshot(tmp_path, monkeypatch):
    a, b = _setup(tmp_path, monkeypatch)
    purchases = PaddlePurchaseService()
    usage = UsageService()
    wallet = WalletService()

    purchases.create(
        user_id=a["id"],
        paddle_transaction_id="txn_a1",
        product_id="starter",
        price_id="pri_a",
        credits=500,
        amount=5.0,
        status=STATUS_PAID,
        country="US",
    )
    purchases.create(
        user_id=a["id"],
        paddle_transaction_id="txn_a2",
        product_id="student",
        price_id="pri_b",
        credits=1500,
        amount=15.0,
        status=STATUS_PAID,
        country="US",
    )
    purchases.create(
        user_id=b["id"],
        paddle_transaction_id="txn_b1",
        product_id="cram",
        price_id="pri_c",
        credits=2900,
        amount=29.0,
        status=STATUS_PAID,
        country="GB",
    )
    wallet.credit(a["id"], 500, "topup", ref_id="txn_a1")
    wallet.credit(a["id"], 1500, "topup", ref_id="txn_a2")
    wallet.credit(b["id"], 2900, "topup", ref_id="txn_b1")

    usage.record(user_id=a["id"], feature=FEATURE_HUMANIZER, credits_used=10)
    usage.record(user_id=a["id"], feature=FEATURE_HUMANIZER, credits_used=10)
    usage.record(user_id=b["id"], feature=FEATURE_TURNITIN, credits_used=300)

    snap = AnalyticsService().snapshot(top_limit=5)
    assert snap["total_credits_sold"] == 4900
    assert snap["total_credits_used"] == 320
    assert snap["revenue"] == 49.0
    assert snap["most_used_feature"]["feature"] == FEATURE_HUMANIZER
    assert snap["most_used_feature"]["launches"] == 2
    assert snap["user_count"] == 2
    assert snap["average_credits_per_user"] == 2450.0
    assert snap["average_purchase"]["amount"] == pytest.approx(16.33, abs=0.01)
    assert snap["top_customers"][0]["email"] == "b@example.com"
    assert snap["top_countries"][0]["country"] == "GB"
    assert snap["top_countries"][0]["revenue"] == 29.0

    admin = AdminService(wallet, purchases, usage)
    via_admin = admin.get_analytics()
    assert via_admin["total_credits_sold"] == 4900
