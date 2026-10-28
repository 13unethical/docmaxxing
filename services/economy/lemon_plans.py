"""Pricing page purchases through Lemon Squeezy: monthly plans and pay-as-you-go credits.

Per plan, ``.env`` holds the product's share link (or just its UUID) and the numeric
variant id that webhooks report:

    LEMON_CHECKOUT_PLAN_BASIC=https://docmaxxing.lemonsqueezy.com/buy/<uuid>
    LEMON_VARIANT_ID_PLAN_BASIC=123456

Pay-as-you-go uses one one-time product (``LEMON_VARIANT_ID_PAYG``) whose price is
set per checkout through the API, so it needs ``LEMON_SQUEEZY_API_KEY``.

The first plan payment arrives as ``order_created``; every later charge arrives as
``subscription_payment_success`` with ``billing_reason == "renewal"``.
``subscription_created`` / ``subscription_updated`` keep the subscription → user/plan
link used for renewals and the customer portal link used to manage the subscription.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any
from urllib.parse import urlencode

from . import lemon_api
from .db import connect
from .plans import PLANS, payg_usd

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("on_trial", "active", "past_due")


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _checkout_base() -> str:
    return (_env("LEMON_CHECKOUT_BASE") or "https://docmaxxing.lemonsqueezy.com/checkout/buy").rstrip("/")


def plan_checkout_link(plan_id: str) -> str | None:
    raw = _env(f"LEMON_CHECKOUT_PLAN_{plan_id.upper()}")
    if not raw:
        return None
    return raw if raw.startswith("http") else f"{_checkout_base()}/{raw}"


def plan_checkout_url(plan_id: str, *, user_id: int, email: str | None = None) -> str | None:
    """Buy link that carries ``custom_data.user_id`` so the webhook finds the account."""
    link = plan_checkout_link(plan_id)
    if not link:
        return None
    params = {"checkout[custom][user_id]": str(int(user_id))}
    if email:
        params["checkout[email]"] = email
    return f"{link}{'&' if '?' in link else '?'}{urlencode(params)}"


def plan_variant_id(plan_id: str) -> str:
    return _env(f"LEMON_VARIANT_ID_PLAN_{plan_id.upper()}")


def plan_checkout(plan_id: str, *, user_id: int, email: str | None = None) -> str | None:
    """Checkout for a plan: API-created (returns to /app) when possible, else the buy link."""
    variant = plan_variant_id(plan_id)
    if lemon_api.api_configured() and variant:
        try:
            return lemon_api.create_checkout(
                variant_id=variant, custom={"user_id": int(user_id), "plan": plan_id}, email=email
            )
        except lemon_api.LemonApiError:
            logger.exception("lemon plan checkout via API failed; using the buy link")
    return plan_checkout_url(plan_id, user_id=user_id, email=email)


def payg_variant_id() -> str:
    return _env("LEMON_VARIANT_ID_PAYG")


def payg_configured() -> bool:
    return bool(payg_variant_id()) and lemon_api.api_configured()


def payg_checkout(credits: int, *, user_id: int, email: str | None = None) -> str:
    """Checkout for one-time credits priced by ``payg_usd``."""
    return lemon_api.create_checkout(
        variant_id=payg_variant_id(),
        custom={"user_id": int(user_id), "credits": int(credits)},
        email=email,
        custom_price_cents=payg_usd(int(credits)) * 100,
    )


def plan_for_variant(variant_id: Any) -> str | None:
    raw = str(variant_id or "").strip()
    if not raw:
        return None
    for plan_id in PLANS:
        if _env(f"LEMON_VARIANT_ID_PLAN_{plan_id.upper()}") == raw:
            return plan_id
    return None


def ensure_subscription_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lemon_subscriptions (
            subscription_id TEXT PRIMARY KEY,
            user_id         INTEGER,
            plan_id         TEXT,
            status          TEXT,
            portal_url      TEXT,
            renews_at       TEXT,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def save_subscription(
    subscription_id: str,
    *,
    user_id: int | None,
    plan_id: str | None,
    status: str | None,
    portal_url: str | None,
    renews_at: str | None,
) -> None:
    with connect() as conn:
        ensure_subscription_schema(conn)
        conn.execute(
            "INSERT INTO lemon_subscriptions (subscription_id, user_id, plan_id, status, portal_url, renews_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(subscription_id) DO UPDATE SET "
            "user_id = COALESCE(excluded.user_id, lemon_subscriptions.user_id), "
            "plan_id = COALESCE(excluded.plan_id, lemon_subscriptions.plan_id), "
            "status = COALESCE(excluded.status, lemon_subscriptions.status), "
            "portal_url = COALESCE(excluded.portal_url, lemon_subscriptions.portal_url), "
            "renews_at = COALESCE(excluded.renews_at, lemon_subscriptions.renews_at), "
            "updated_at = datetime('now')",
            (str(subscription_id), user_id, plan_id, status, portal_url, renews_at),
        )


def get_subscription(subscription_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        ensure_subscription_schema(conn)
        row = conn.execute(
            "SELECT * FROM lemon_subscriptions WHERE subscription_id = ?", (str(subscription_id),)
        ).fetchone()
    return dict(row) if row else None


def lemon_checkout_enabled() -> bool:
    return any(plan_checkout_link(p) for p in PLANS) or payg_configured()


def billing_subscription(user_id: int) -> dict[str, Any] | None:
    """Latest subscription for the Billing page (cancelled ones still show until they end)."""
    with connect() as conn:
        ensure_subscription_schema(conn)
        row = conn.execute(
            "SELECT plan_id, status, portal_url, renews_at FROM lemon_subscriptions "
            "WHERE user_id = ? AND status NOT IN ('expired') ORDER BY updated_at DESC LIMIT 1",
            (int(user_id),),
        ).fetchone()
    return dict(row) if row else None


def active_subscription(user_id: int) -> dict[str, Any] | None:
    """The user's running subscription, if any (one per account)."""
    marks = ",".join("?" for _ in ACTIVE_STATUSES)
    with connect() as conn:
        ensure_subscription_schema(conn)
        row = conn.execute(
            f"SELECT * FROM lemon_subscriptions WHERE user_id = ? AND status IN ({marks}) "
            "ORDER BY updated_at DESC LIMIT 1",
            (int(user_id), *ACTIVE_STATUSES),
        ).fetchone()
    return dict(row) if row else None
