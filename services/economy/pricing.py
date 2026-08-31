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

def _lemon_checkout_uuid(package_key: str, *, legacy_env: str, default: str = "") -> str:
    """Checkout buy-link UUID (path segment). Prefer LEMON_CHECKOUT_UUID_*."""
    return (
        _env_str(f"LEMON_CHECKOUT_UUID_CREDITS_{package_key}")
        or _env_str(legacy_env)
        or default
    )


def _lemon_numeric_variant_id(package_key: str, *legacy_envs: str) -> str:
    """Numeric Lemon API variant_id used in webhooks.

    Prefer ``LEMON_VARIANT_ID_CREDITS_*``. Fall back to legacy
    ``LEMON_VARIANT_CREDITS_*`` only when the value looks numeric (so UUID
    leftovers in the old keys do not pollute webhook matching).
    """
    primary = _env_str(f"LEMON_VARIANT_ID_CREDITS_{package_key}")
    if primary:
        return primary
    for env_name in legacy_envs:
        raw = _env_str(env_name)
        if raw and raw.isdigit():
            return raw
    return ""


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
        # Checkout URL path uses Lemon's share/buy UUID.
        "lemon_checkout_uuid": _lemon_checkout_uuid(
            "1000",
            legacy_env="LEMON_VARIANT_CREDITS_1000",
            default="5074ed4e-a06f-4860-acb0-d6044357d549",
        ),
        # Webhook ``first_order_item.variant_id`` is a numeric API id.
        "lemon_variant_id": _lemon_numeric_variant_id(
            "1000", "LEMON_VARIANT_CREDITS_1000"
        ),
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
        "lemon_checkout_uuid": _lemon_checkout_uuid(
            "2200",
            legacy_env="LEMON_VARIANT_CREDITS_2200",
            default="8bd0501d-302f-4054-a905-302112b8e267",
        )
        or _lemon_checkout_uuid(
            "2500",
            legacy_env="LEMON_VARIANT_CREDITS_2500",
        ),
        "lemon_variant_id": _lemon_numeric_variant_id(
            "2200",
            "LEMON_VARIANT_CREDITS_2200",
            "LEMON_VARIANT_CREDITS_2500",
        )
        or _lemon_numeric_variant_id("2500"),
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
    checkout_uuid = str(pkg.get("lemon_checkout_uuid") or "").strip()
    if explicit:
        url = explicit
    elif checkout_uuid:
        url = f"{lemon_store_checkout_base()}/{checkout_uuid}"
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


def package_credits_per_usd(coins: int, usd: float) -> float:
    """Credits granted per USD spent (e.g. 1000 coins / $10 → 100)."""
    amount = float(usd or 0)
    if amount <= 0:
        return 0.0
    return int(coins) / amount


def package_usage_floor(coins: int, unit_cost: int) -> int:
    """How many times a feature can run with ``coins`` (round down)."""
    cost = int(unit_cost or 0)
    if cost <= 0:
        return 0
    return int(coins) // cost


def pro_savings_pct_vs_starter() -> int | None:
    """Pro % more credits per dollar vs Starter; None if not better."""
    starter = TOPUP_PACKAGES.get("credits_1000")
    pro = TOPUP_PACKAGES.get("credits_2500")
    if not starter or not pro:
        return None
    starter_rate = package_credits_per_usd(int(starter["coins"]), float(starter["usd"]))
    pro_rate = package_credits_per_usd(int(pro["coins"]), float(pro["usd"]))
    if starter_rate <= 0 or pro_rate <= starter_rate:
        return None
    return int(math.floor((pro_rate / starter_rate - 1) * 100))


def _format_usd(usd: float) -> str:
    if float(usd) == int(usd):
        return str(int(usd))
    text = f"{float(usd):.2f}".rstrip("0").rstrip(".")
    return text


def _format_rate_number(value: float) -> str:
    if float(value) == int(value):
        return str(int(value))
    return f"{float(value):.1f}".rstrip("0").rstrip(".")


def _credit_word(n: int) -> str:
    return "credit" if int(n) == 1 else "credits"


def pricing_page_packages(*, user_id: int | None = None) -> list[dict[str, Any]]:
    """Enriched Starter/Pro rows for ``/pricing`` (all amounts derived from catalog)."""
    humanize_cost = feature_cost("humanize")
    turnitin_cost = feature_cost("turnitin")
    savings_pct = pro_savings_pct_vs_starter()
    rows: list[dict[str, Any]] = []
    for pkg_id in ("credits_1000", "credits_2500"):
        raw = TOPUP_PACKAGES[pkg_id]
        coins = int(raw["coins"])
        usd = float(raw["usd"])
        credits_per_usd = package_credits_per_usd(coins, usd)
        rows.append(
            {
                **raw,
                "usd_display": _format_usd(usd),
                "coins_formatted": f"{coins:,}",
                "humanize_passes": package_usage_floor(coins, humanize_cost),
                "turnitin_checks": package_usage_floor(coins, turnitin_cost),
                "credits_per_usd_display": _format_rate_number(credits_per_usd),
                "lemon_checkout_url": lemon_checkout_url_for_package(
                    pkg_id, user_id=user_id
                ),
                "savings_pct": savings_pct if raw.get("featured") else None,
            }
        )
    return rows


def pricing_cost_rows() -> list[dict[str, str]]:
    """Credit cost table for the pricing explainer."""
    humanize = feature_cost("humanize")
    cite = int(FEATURE_COSTS["cite"])
    turnitin = int(FEATURE_COSTS["turnitin"])
    detect_per_100 = detect_cost_credits(100)
    return [
        {"label": "Home Format & Academic Check", "value": "Free"},
        {
            "label": "Humanize marked selections",
            "value": f"{humanize} {_credit_word(humanize)} / call",
        },
        {
            "label": "AI detect in editor",
            "value": f"{detect_per_100} {_credit_word(detect_per_100)} / 100 words",
        },
        {
            "label": "Citation insert",
            "value": f"{cite} {_credit_word(cite)}",
        },
        {
            "label": "Turnitin similarity check",
            "value": f"{turnitin} credits",
        },
        {"label": "Failed paid action", "value": "Refunded"},
    ]
