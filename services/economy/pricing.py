"""Single source of truth for credit prices.

Every paid feature reads its cost from here. Values are intentionally simple
integers so they are easy to tune. Assignment projects reuse the existing USD
calculator and convert to credits at a fixed rate.
"""

from __future__ import annotations

import math
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


# Credits granted to a brand-new account.
WELCOME_BONUS: int = _env_int("COINS_WELCOME_BONUS", 50)

# 1 credit == $0.01  ->  $1 == 100 credits. Used to price assignments and top-ups.
USD_TO_COINS: int = _env_int("USD_TO_COINS", 100)

# Flat / base costs in credits, keyed by feature id.
# ``detect`` is overridden dynamically via word_count (1 credit / 100 words, min 1).
FEATURE_COSTS: dict[str, int] = {
    "humanize": _env_int("COST_HUMANIZE", 200),
    "detect": _env_int("COST_DETECT", 1),
    "check": _env_int("COST_CHECK", 20),
    "cite": _env_int("COST_CITE", 2),
    "turnitin": _env_int("COST_TURNITIN", 300),
}

# Human-readable labels for ledger/UI.
FEATURE_LABELS: dict[str, str] = {
    "humanize": "Humanize",
    "detect": "AI Detect",
    "check": "Academic Check",
    "cite": "Citation",
    "turnitin": "Turnitin check",
    "assignment": "Assignment project",
    "topup": "Top-up",
    "welcome_bonus": "Welcome bonus",
    "admin_adjustment": "Admin adjustment",
    "referral_signup_bonus": "Referral signup bonus",
    "referral_milestone": "Referral milestone",
    "referral_convert": "Referral → credits",
}

# Top-up packages — Pricing UI + Gumroad / Cryptomus / Paddle (Starter / Pro only).
TOPUP_PACKAGES: dict[str, dict[str, Any]] = {
    "credits_1000": {
        "id": "credits_1000",
        "name": "Starter",
        "usd": 10.0,
        "coins": 1000,
        "featured": False,
        "price_id": _env_str("PADDLE_PRICE_CREDITS_1000"),
        "gumroad_product_id": _env_str("GUMROAD_PRODUCT_CREDITS_1000"),
        "lemon_variant_id": _env_str("LEMON_VARIANT_CREDITS_1000"),
        "lemon_checkout_url": _env_str("LEMON_CHECKOUT_CREDITS_1000"),
    },
    "credits_2500": {
        "id": "credits_2500",
        "name": "Pro",
        "usd": 20.0,
        "coins": 2200,
        "featured": True,
        "badge": "MOST POPULAR",
        "price_id": _env_str("PADDLE_PRICE_CREDITS_2500"),
        # Prefer new env key; fall back to legacy _2500 product id mapping.
        "gumroad_product_id": _env_str("GUMROAD_PRODUCT_CREDITS_2200")
        or _env_str("GUMROAD_PRODUCT_CREDITS_2500"),
        "lemon_variant_id": _env_str("LEMON_VARIANT_CREDITS_2200")
        or _env_str("LEMON_VARIANT_CREDITS_2500"),
        "lemon_checkout_url": _env_str("LEMON_CHECKOUT_CREDITS_2200")
        or _env_str("LEMON_CHECKOUT_CREDITS_2500"),
    },
}


def lemon_store_checkout_base() -> str:
    """Base for Lemon buy links, e.g. https://docmaxxing.lemonsqueezy.com/checkout/buy"""
    return (
        _env_str("LEMON_CHECKOUT_BASE")
        or "https://docmaxxing.lemonsqueezy.com/checkout/buy"
    ).rstrip("/")


def lemon_checkout_url_for_package(
    package_id: str,
    *,
    user_id: int | None = None,
) -> str | None:
    """Build a Lemon Squeezy checkout URL that embeds ``custom_data.user_id``."""
    pkg = package(package_id)
    if not pkg:
        return None
    explicit = str(pkg.get("lemon_checkout_url") or "").strip()
    variant = str(pkg.get("lemon_variant_id") or "").strip()
    if explicit:
        url = explicit
    elif variant:
        url = f"{lemon_store_checkout_base()}/{variant}"
    else:
        return None
    if user_id is not None and int(user_id) > 0:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}checkout[custom][user_id]={int(user_id)}"
    return url


def detect_cost_credits(word_count: int) -> int:
    """1 credit per 100 words, minimum 1 credit."""
    words = max(0, int(word_count or 0))
    return max(1, math.ceil(words / 100)) if words else 1


def feature_cost(feature: str, **params: Any) -> int:
    """Return the credit cost for a feature call.

    ``params`` may include ``word_count`` for size-based features (detect).
    """
    feature = (feature or "").strip().lower()
    if feature == "assignment":
        return assignment_cost_coins(
            params.get("requirement") or {},
            priority=str(params.get("priority") or "standard"),
        )
    if feature == "detect":
        if "word_count" in params:
            return detect_cost_credits(int(params.get("word_count") or 0))
        return detect_cost_credits(0)
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
    """Price an assignment project in credits (USD calculator x fixed rate)."""
    pricing = calculate_project_price(requirement, priority=priority)
    amount_usd = float(pricing.get("amount_usd") or 0.0)
    return int(round(amount_usd * USD_TO_COINS))


def package(package_id: str) -> dict[str, Any] | None:
    """Return a top-up package definition by id, or None."""
    return TOPUP_PACKAGES.get((package_id or "").strip().lower())
