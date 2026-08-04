"""Single source of truth for coin prices.

Every paid feature reads its cost from here. Values are intentionally simple
integers so they are easy to tune. Assignment projects reuse the existing USD
calculator and convert to coins at a fixed rate.
"""

from __future__ import annotations

import os
from typing import Any

from services.assignment_project.pricing import calculate_project_price


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


# Coins granted to a brand-new account.
WELCOME_BONUS: int = _env_int("COINS_WELCOME_BONUS", 50)

# 1 coin == $0.01  ->  $1 == 100 coins. Used to price assignments and top-ups.
USD_TO_COINS: int = _env_int("USD_TO_COINS", 100)

# Flat / base costs in coins, keyed by feature id.
FEATURE_COSTS: dict[str, int] = {
    "humanize": _env_int("COST_HUMANIZE", 200),
    "detect": _env_int("COST_DETECT", 10),
    "check": _env_int("COST_CHECK", 20),
    "cite": _env_int("COST_CITE", 2),
    "turnitin": _env_int("COST_TURNITIN", 300),
}

# Human-readable labels for ledger/UI.
FEATURE_LABELS: dict[str, str] = {
    "humanize": "Humanize",
    "detect": "AI Detect",
    "check": "Academic Check",
    "cite": "Citation search",
    "turnitin": "Turnitin check",
    "assignment": "Assignment project",
    "topup": "Top-up",
    "welcome_bonus": "Welcome bonus",
    "admin_adjustment": "Admin adjustment",
    "referral_signup_bonus": "Referral signup bonus",
    "referral_milestone": "Referral milestone",
    "referral_convert": "Referral → credits",
}

# Top-up packages — Pricing UI + Paddle price_id → credits (Starter / Pro only).
TOPUP_PACKAGES: dict[str, dict[str, Any]] = {
    "credits_1000": {
        "id": "credits_1000",
        "name": "Starter",
        "usd": 9.0,
        "coins": 1000,
        "featured": False,
        "price_id": _env_str("PADDLE_PRICE_CREDITS_1000"),
        "gumroad_product_id": _env_str("GUMROAD_PRODUCT_CREDITS_1000"),
    },
    "credits_2500": {
        "id": "credits_2500",
        "name": "Pro",
        "usd": 20.0,
        "coins": 2500,
        "featured": True,
        "badge": "MOST POPULAR",
        "price_id": _env_str("PADDLE_PRICE_CREDITS_2500"),
        "gumroad_product_id": _env_str("GUMROAD_PRODUCT_CREDITS_2500"),
    },
}


def feature_cost(feature: str, **params: Any) -> int:
    """Return the coin cost for a feature call.

    ``params`` is accepted for features that scale with input size in the
    future (e.g. word count). Today all micro-features are flat.
    """
    feature = (feature or "").strip().lower()
    if feature == "assignment":
        return assignment_cost_coins(
            params.get("requirement") or {},
            priority=str(params.get("priority") or "standard"),
        )
    if feature not in FEATURE_COSTS:
        raise KeyError(f"Unknown paid feature: {feature!r}")
    cost = int(FEATURE_COSTS[feature])
    if feature == "humanize":
        from .site_settings import apply_humanizer_site_discount

        cost = apply_humanizer_site_discount(cost)
    return int(cost)


def assignment_cost_coins(
    requirement: dict[str, Any],
    *,
    priority: str = "standard",
) -> int:
    """Price an assignment project in coins (USD calculator x fixed rate)."""
    pricing = calculate_project_price(requirement, priority=priority)
    amount_usd = float(pricing.get("amount_usd") or 0.0)
    return int(round(amount_usd * USD_TO_COINS))


def package(package_id: str) -> dict[str, Any] | None:
    """Return a top-up package definition by id, or None."""
    return TOPUP_PACKAGES.get((package_id or "").strip().lower())
