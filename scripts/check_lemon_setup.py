#!/usr/bin/env python3
"""Check the Lemon Squeezy setup before (and after) a deploy. Read-only.

    python scripts/check_lemon_setup.py

Reads ``.env``. Verifies the plan and pay-as-you-go variants (price, subscription
or one-time, published), the plan buy links, and that the store webhook points at
this site with every event the app handles. Exits 1 when something is wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env")

from services.economy import lemon_api  # noqa: E402
from services.economy.lemon_plans import (  # noqa: E402
    payg_variant_id,
    plan_checkout_link,
    plan_variant_id,
)
from services.economy.lemon_squeezy_gateway import lemon_squeezy_webhook_secret  # noqa: E402
from services.economy.plans import PLANS  # noqa: E402

WEBHOOK_EVENTS = {
    "order_created",
    "order_refunded",
    "subscription_created",
    "subscription_updated",
    "subscription_cancelled",
    "subscription_resumed",
    "subscription_expired",
    "subscription_payment_success",
    "subscription_payment_refunded",
}

problems: list[str] = []


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def bad(msg: str) -> None:
    print(f"  ❌ {msg}")
    problems.append(msg)


def check_variant(label: str, variant_id: str, *, price_cents: int | None, subscription: bool) -> None:
    try:
        data = lemon_api.request("GET", f"/variants/{variant_id}", params={"include": "product"})
        attrs = data["data"]["attributes"]
    except (lemon_api.LemonApiError, KeyError) as exc:
        bad(f"{label}: variant {variant_id} not readable ({exc})")
        return
    product = next((i.get("attributes", {}) for i in data.get("included", []) if i.get("type") == "products"), {})
    issues = []
    # "pending" is the status of the default variant of a product without extra variants.
    if attrs.get("status") not in ("published", "pending"):
        issues.append(f"variant status={attrs.get('status')}")
    if product.get("status") != "published":
        issues.append(f"product status={product.get('status')}")
    if bool(attrs.get("is_subscription")) != subscription:
        issues.append("should be a subscription" if subscription else "should be a one-time payment")
    if subscription and (attrs.get("interval"), int(attrs.get("interval_count") or 1)) != ("month", 1):
        issues.append(f"billing every {attrs.get('interval_count')} {attrs.get('interval')}")
    if price_cents is not None and int(attrs.get("price") or 0) != price_cents:
        issues.append(f"price ${int(attrs.get('price') or 0) / 100:.2f}, expected ${price_cents / 100:.2f}")
    if issues:
        bad(f"{label} (variant {variant_id}): " + "; ".join(issues))
    else:
        ok(f"{label}: variant {variant_id} of '{product.get('name')}' published"
           + (f", ${int(attrs.get('price') or 0) / 100:.2f}/month" if subscription else ", one-time"))


def main() -> int:
    print("Environment")
    ok("LEMON_SQUEEZY_WEBHOOK_SECRET set") if lemon_squeezy_webhook_secret() else bad(
        "LEMON_SQUEEZY_WEBHOOK_SECRET missing (webhooks will be rejected)"
    )
    api = lemon_api.api_configured()
    ok("LEMON_SQUEEZY_API_KEY set") if api else bad(
        "LEMON_SQUEEZY_API_KEY missing (pay-as-you-go stays on Cryptomus; checks below are limited)"
    )
    for plan_id in PLANS:
        link, variant = plan_checkout_link(plan_id), plan_variant_id(plan_id)
        if link and variant:
            ok(f"{plan_id}: buy link and variant id set")
        else:
            bad(f"{plan_id}: LEMON_CHECKOUT_PLAN_{plan_id.upper()} / LEMON_VARIANT_ID_PLAN_{plan_id.upper()} missing")
    ok("LEMON_VARIANT_ID_PAYG set") if payg_variant_id() else bad(
        "LEMON_VARIANT_ID_PAYG missing (pay-as-you-go stays on Cryptomus)"
    )

    print("Buy links")
    for plan_id in PLANS:
        link = plan_checkout_link(plan_id)
        if not link:
            continue
        try:
            res = requests.get(link, timeout=15, allow_redirects=True)
            ok(f"{plan_id}: checkout page opens") if res.ok else bad(f"{plan_id}: buy link returned {res.status_code}")
        except requests.RequestException as exc:
            bad(f"{plan_id}: buy link unreachable ({exc})")

    if not api:
        print("\nSkipped API checks (no API key).")
        return report()

    print("Store")
    try:
        store = lemon_api.store_id()
        attrs = lemon_api.request("GET", f"/stores/{store}")["data"]["attributes"]
        ok(f"store {store} '{attrs.get('name')}' ({attrs.get('currency')})")
        if attrs.get("currency") != "USD":
            bad(f"store currency is {attrs.get('currency')}; prices are set in USD")
    except (lemon_api.LemonApiError, KeyError) as exc:
        bad(f"store not readable ({exc})")
        return report()

    print("Products")
    for plan_id, plan in PLANS.items():
        if plan_variant_id(plan_id):
            check_variant(plan["name"], plan_variant_id(plan_id), price_cents=int(plan["usd"]) * 100, subscription=True)
    if payg_variant_id():
        check_variant("Pay as you go", payg_variant_id(), price_cents=None, subscription=False)

    print("Webhook")
    expected_url = f"{lemon_api.public_base_url()}/api/webhooks/lemon-squeezy"
    try:
        hooks = lemon_api.request("GET", "/webhooks", params={"filter[store_id]": store})["data"]
    except (lemon_api.LemonApiError, KeyError) as exc:
        bad(f"webhooks not readable ({exc})")
        return report()
    live = [h for h in hooks if h["attributes"].get("url") == expected_url and not h["attributes"].get("test_mode")]
    if not live:
        bad(f"no live webhook for {expected_url} (found: {[h['attributes'].get('url') for h in hooks]})")
    else:
        events = set(live[0]["attributes"].get("events") or [])
        missing = sorted(WEBHOOK_EVENTS - events)
        ok(f"webhook {expected_url}")
        bad(f"webhook is missing events: {', '.join(missing)}") if missing else ok("all events enabled")
    return report()


def report() -> int:
    print()
    if problems:
        print(f"{len(problems)} problem(s) to fix.")
        return 1
    print("Lemon Squeezy setup looks good.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
