"""Lemon Squeezy subscriptions for the Basic / Pro / Max plans."""

from __future__ import annotations

import pytest

from services.economy import lemon_api
from services.economy.db import connect, init_db
from services.economy.lemon_plans import (
    active_subscription,
    billing_subscription,
    payg_checkout,
    plan_checkout,
    plan_checkout_url,
    plan_for_variant,
)
from services.economy.lemon_squeezy_gateway import LemonSqueezyGatewayError, handle_webhook_event
from services.economy.plans import active_plan, payment_history
from services.economy.wallet import WalletService


@pytest.fixture()
def uid(tmp_path, monkeypatch):
    import os

    for key in [k for k in os.environ if k.startswith("LEMON_")]:
        monkeypatch.delenv(key)
    monkeypatch.setattr(lemon_api, "_store_id_cache", None)
    db_path = tmp_path / "economy.db"
    monkeypatch.setenv("ECONOMY_DB_PATH", str(db_path))
    monkeypatch.setenv("LEMON_CHECKOUT_PLAN_BASIC", "https://docmaxxing.lemonsqueezy.com/buy/basic-uuid")
    monkeypatch.setenv("LEMON_CHECKOUT_PLAN_PRO", "pro-uuid")
    monkeypatch.setenv("LEMON_VARIANT_ID_PLAN_BASIC", "501")
    monkeypatch.setenv("LEMON_VARIANT_ID_PLAN_PRO", "502")
    monkeypatch.setenv("LEMON_VARIANT_ID_PLAN_MAX", "503")
    import services.economy.db as db_mod

    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    init_db()
    with connect() as conn:
        conn.execute("INSERT INTO users (email, name, password_hash) VALUES ('b@example.com', 'B', 'x')")
        user_id = int(conn.execute("SELECT id FROM users").fetchone()["id"])
    WalletService().ensure_wallet(user_id)
    return user_id


def _balance(user_id):
    with connect() as conn:
        return int(conn.execute("SELECT balance FROM wallets WHERE user_id = ?", (user_id,)).fetchone()["balance"])


def _order(user_id, variant, order_id="ord_1", cents=1900):
    return {
        "meta": {"event_name": "order_created", "custom_data": {"user_id": str(user_id)}},
        "data": {"id": order_id, "attributes": {"user_email": "b@example.com", "total_usd": cents,
                                                "first_order_item": {"variant_id": variant}}},
    }


def _subscription(user_id, sub_id="sub_1", variant=502, status="active", event="subscription_created"):
    return {
        "meta": {"event_name": event, "custom_data": {"user_id": str(user_id)}},
        "data": {"id": sub_id, "attributes": {"variant_id": variant, "status": status,
                                              "renews_at": "2026-11-27T00:00:00Z",
                                              "urls": {"customer_portal": "https://portal.example/sub_1"}}},
    }


def _invoice(invoice_id="inv_2", sub_id="sub_1", reason="renewal", custom_user=None):
    meta = {"event_name": "subscription_payment_success"}
    if custom_user:
        meta["custom_data"] = {"user_id": str(custom_user)}
    return {"meta": meta, "data": {"id": invoice_id, "attributes": {
        "subscription_id": sub_id, "billing_reason": reason, "total_usd": 1900, "status": "paid"}}}


def test_checkout_url_carries_user_and_email(uid):
    assert plan_checkout_url("basic", user_id=uid, email="b@example.com") == (
        "https://docmaxxing.lemonsqueezy.com/buy/basic-uuid"
        f"?checkout%5Bcustom%5D%5Buser_id%5D={uid}&checkout%5Bemail%5D=b%40example.com"
    )
    assert plan_checkout_url("pro", user_id=uid).startswith(
        "https://docmaxxing.lemonsqueezy.com/checkout/buy/pro-uuid?"
    )
    assert plan_checkout_url("max", user_id=uid) is None
    assert plan_for_variant(503) == "max" and plan_for_variant("999") is None


def test_first_payment_grants_plan_and_credits_once(uid):
    before = _balance(uid)
    result = handle_webhook_event(_order(uid, 502))
    assert result["plan_id"] == "pro" and result["credits"] == 1000
    assert _balance(uid) == before + 1000
    assert active_plan(uid)["plan_id"] == "pro"
    again = handle_webhook_event(_order(uid, 502))
    assert again["already_credited"] is True
    assert _balance(uid) == before + 1000
    history = payment_history(uid)
    assert history[0]["item"] == "Pro plan · 30 days" and history[0]["amount"] == 19.0


def test_renewal_extends_plan_and_adds_credits(uid):
    handle_webhook_event(_order(uid, 502))
    first_end = active_plan(uid)["expires_at"]
    handle_webhook_event(_subscription(uid))
    assert active_subscription(uid)["portal_url"] == "https://portal.example/sub_1"

    assert handle_webhook_event(_invoice(reason="initial"))["status"] == "ignored"
    before = _balance(uid)
    result = handle_webhook_event(_invoice())
    assert result["credits"] == 1000 and _balance(uid) == before + 1000
    assert active_plan(uid)["expires_at"] > first_end
    assert handle_webhook_event(_invoice())["already_credited"] is True
    assert _balance(uid) == before + 1000


def test_cancelled_subscription_is_no_longer_active(uid):
    handle_webhook_event(_subscription(uid))
    handle_webhook_event(_subscription(uid, status="cancelled", event="subscription_cancelled"))
    assert active_subscription(uid) is None


def test_unmatched_renewal_is_rejected(uid):
    with pytest.raises(LemonSqueezyGatewayError):
        handle_webhook_event(_invoice(sub_id="unknown"))


def _payg_order(user_id, credits, subtotal, order_id="ord_p", discount=0):
    return {
        "meta": {"event_name": "order_created", "custom_data": {"user_id": str(user_id), "credits": str(credits)}},
        "data": {"id": order_id, "attributes": {"subtotal": subtotal, "discount_total": discount,
                                                "total_usd": subtotal, "first_order_item": {"variant_id": 777}}},
    }


def test_payg_order_credits_what_was_paid_for(uid, monkeypatch):
    monkeypatch.setenv("LEMON_VARIANT_ID_PAYG", "777")
    before = _balance(uid)
    assert handle_webhook_event(_payg_order(uid, 2000, 2200))["credits"] == 2000
    assert _balance(uid) == before + 2000
    assert payment_history(uid)[0]["item"] == "2,000 credits · one-time"
    # A store discount code lowers the subtotal but is still a valid purchase.
    assert handle_webhook_event(_payg_order(uid, 500, 500, order_id="ord_d", discount=200))["credits"] == 500


@pytest.mark.parametrize(("credits", "subtotal"), [(10000, 2200), (750, 2200), ("lots", 2200)])
def test_payg_order_with_wrong_amount_or_credits_is_rejected(uid, monkeypatch, credits, subtotal):
    monkeypatch.setenv("LEMON_VARIANT_ID_PAYG", "777")
    before = _balance(uid)
    with pytest.raises(LemonSqueezyGatewayError):
        handle_webhook_event(_payg_order(uid, credits, subtotal))
    assert _balance(uid) == before


def test_refund_marks_payment_and_stops_the_plan(uid):
    handle_webhook_event(_order(uid, 502, order_id="ord_r"))
    refund = _order(uid, 502, order_id="ord_r")
    refund["meta"]["event_name"] = "order_refunded"
    refund["data"]["attributes"]["status"] = "refunded"
    result = handle_webhook_event(refund)
    assert result["plan_stopped"] is True
    assert active_plan(uid) is None
    assert payment_history(uid)[0]["status"] == "Refunded"


def test_partial_refund_keeps_the_plan(uid):
    handle_webhook_event(_order(uid, 502, order_id="ord_pr"))
    refund = _order(uid, 502, order_id="ord_pr")
    refund["meta"]["event_name"] = "order_refunded"
    refund["data"]["attributes"]["status"] = "partial_refund"
    assert handle_webhook_event(refund)["plan_stopped"] is False
    assert active_plan(uid)["plan_id"] == "pro"


class _FakeApi:
    def __init__(self, monkeypatch, *, fail=False):
        self.calls = []
        self.fail = fail
        monkeypatch.setenv("LEMON_SQUEEZY_API_KEY", "key")
        monkeypatch.setenv("LEMON_STORE_ID", "42")
        monkeypatch.setattr(lemon_api.requests, "request", self)

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs.get("json")))

        class Res:
            ok = not self.fail
            status_code = 500 if self.fail else 201
            text = "boom"

            @staticmethod
            def json():
                if self.fail:
                    return {"errors": [{"detail": "boom"}]}
                return {"data": {"attributes": {"url": "https://docmaxxing.lemonsqueezy.com/checkout/custom/abc"}}}

        return Res()


def test_payg_checkout_sets_server_price_and_custom_data(uid, monkeypatch):
    api = _FakeApi(monkeypatch)
    monkeypatch.setenv("LEMON_VARIANT_ID_PAYG", "777")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://docmaxxing.com")
    url = payg_checkout(2000, user_id=uid, email="b@example.com")
    assert url.endswith("/checkout/custom/abc")
    method, endpoint, body = api.calls[0]
    assert (method, endpoint) == ("POST", "https://api.lemonsqueezy.com/v1/checkouts")
    attrs = body["data"]["attributes"]
    assert attrs["custom_price"] == 2200
    assert attrs["checkout_data"] == {"custom": {"user_id": str(uid), "credits": "2000"}, "email": "b@example.com"}
    assert attrs["product_options"]["redirect_url"] == "https://docmaxxing.com/app?paid=1#/billing"
    assert body["data"]["relationships"]["store"]["data"]["id"] == "42"
    assert body["data"]["relationships"]["variant"]["data"]["id"] == "777"


def test_plan_checkout_prefers_api_and_falls_back_to_buy_link(uid, monkeypatch):
    api = _FakeApi(monkeypatch)
    assert plan_checkout("pro", user_id=uid).endswith("/checkout/custom/abc")
    assert "custom_price" not in api.calls[0][2]["data"]["attributes"]
    _FakeApi(monkeypatch, fail=True)
    assert plan_checkout("pro", user_id=uid).startswith("https://docmaxxing.lemonsqueezy.com/checkout/buy/pro-uuid?")


def test_billing_shows_cancelled_subscription_until_it_expires(uid):
    handle_webhook_event(_subscription(uid, status="cancelled", event="subscription_cancelled"))
    assert billing_subscription(uid)["status"] == "cancelled"
    handle_webhook_event(_subscription(uid, status="expired", event="subscription_expired"))
    assert billing_subscription(uid) is None


def test_credit_packs_still_use_their_own_variants(uid, monkeypatch):
    monkeypatch.setenv("LEMON_VARIANT_ID_CREDITS_1000", "1111111")
    before = _balance(uid)
    result = handle_webhook_event(_order(uid, "1111111", order_id="ord_c"))
    assert result["credits"] == 1000 and "plan_id" not in result
    assert active_plan(uid) is None
    assert _balance(uid) == before + 1000
