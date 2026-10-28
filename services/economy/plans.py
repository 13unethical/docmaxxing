"""Monthly plans and pay-as-you-go credits sold on the Pricing page.

A plan is a 30-day pass: one payment adds the plan's credits and opens its free
generations until the pass ends. Paying again for the same plan extends it by
30 days and starts a fresh allowance.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from services.economy.db import connect

PLAN_DAYS = 30
_FMT = "%Y-%m-%d %H:%M:%S"

# free: feature -> (window, uses). "day" resets at 00:00 UTC, "period" lasts the whole pass.
# unlimited: features that cost nothing while the pass is active.
PLANS: dict[str, dict[str, Any]] = {
    "basic": {
        "id": "basic",
        "name": "Basic",
        "usd": 9,
        "credits": 300,
        "free": {"assignment": ("period", 1), "presentation": ("period", 1)},
        "unlimited": ("cite", "detect"),
        "veil": False,
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "usd": 19,
        "credits": 1000,
        "free": {"humanize": ("day", 15), "assignment": ("period", 3), "presentation": ("period", 5)},
        "unlimited": ("cite", "detect", "check"),
        "veil": True,
    },
    "max": {
        "id": "max",
        "name": "Max",
        "usd": 39,
        "credits": 2500,
        "free": {
            "humanize": ("day", 40),
            "assignment": ("period", 8),
            "presentation": ("period", 15),
            "turnitin": ("period", 1),
        },
        "unlimited": ("cite", "detect", "check"),
        "veil": True,
    },
}

PAYG: dict[str, Any] = {"min": 500, "max": 10000, "step": 500, "base_usd": 2, "usd_per_step": 5}

PLAN_ITEM_PREFIX = "plan_"
PAYG_ITEM_PREFIX = "payg_"


class PlanError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse(value: str) -> datetime:
    return datetime.strptime(value, _FMT).replace(tzinfo=timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(_FMT)


def get_plan(plan_id: str) -> dict[str, Any] | None:
    return PLANS.get((plan_id or "").strip().lower())


def payg_usd(credits: int) -> int:
    """$2 base plus $5 per 500-credit step: 500 → $7, 2,000 → $22, 10,000 → $102."""
    steps = int(credits) // PAYG["step"]
    return PAYG["base_usd"] + steps * PAYG["usd_per_step"]


def checkout_item(
    *, plan_id: str | None = None, credits: Any = None, quantity: Any = None
) -> dict[str, Any]:
    """Server-side price for a Pricing page purchase. The client only names what it wants."""
    if plan_id:
        plan = get_plan(plan_id)
        if plan is None:
            raise PlanError("Unknown plan.")
        return {
            "id": PLAN_ITEM_PREFIX + plan["id"],
            "name": f"{plan['name']} plan · {PLAN_DAYS} days",
            "usd": float(plan["usd"]),
            "coins": int(plan["credits"]),
        }
    try:
        amount = int(credits)
    except (TypeError, ValueError) as exc:
        raise PlanError("Choose how many credits to buy.") from exc
    if amount < PAYG["min"] or amount > PAYG["max"] or (amount - PAYG["min"]) % PAYG["step"]:
        raise PlanError(
            f"Credits must be between {PAYG['min']} and {PAYG['max']} in steps of {PAYG['step']}."
        )
    packs = amount // PAYG["step"]
    if quantity is not None and str(quantity).strip() != str(packs):
        raise PlanError("Credit pack quantity does not match the chosen amount.")
    return {
        "id": f"{PAYG_ITEM_PREFIX}{amount}",
        "name": f"{amount:,} credits · one-time",
        "usd": float(payg_usd(amount)),
        "coins": amount,
        "quantity": packs,
    }


def plan_id_from_item(item_id: str | None) -> str | None:
    item_id = str(item_id or "")
    if not item_id.startswith(PLAN_ITEM_PREFIX):
        return None
    plan_id = item_id[len(PLAN_ITEM_PREFIX):]
    return plan_id if plan_id in PLANS else None


def active_plan(user_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM user_plans WHERE user_id = ?", (int(user_id),)).fetchone()
    if row is None:
        return None
    plan = get_plan(row["plan_id"])
    expires = _parse(row["expires_at"])
    if plan is None or expires <= _now():
        return None
    return {
        "plan_id": plan["id"],
        "name": plan["name"],
        "started_at": row["started_at"],
        "expires_at": row["expires_at"],
        "days_left": max(0, (expires - _now()).days),
        "veil": bool(plan["veil"]),
    }


def activate_plan(user_id: int, plan_id: str, *, order_ref: str | None = None) -> dict[str, Any]:
    """Start the pass, or add 30 days when the same plan is still running."""
    plan = get_plan(plan_id)
    if plan is None:
        raise PlanError("Unknown plan.")
    now = _now()
    with connect() as conn:
        row = conn.execute("SELECT * FROM user_plans WHERE user_id = ?", (int(user_id),)).fetchone()
        base = now
        if row is not None and row["plan_id"] == plan["id"]:
            current_end = _parse(row["expires_at"])
            if current_end > now:
                base = current_end
        expires = base + timedelta(days=PLAN_DAYS)
        conn.execute(
            "INSERT INTO user_plans (user_id, plan_id, started_at, expires_at, order_ref, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET plan_id = excluded.plan_id, started_at = excluded.started_at, "
            "expires_at = excluded.expires_at, order_ref = excluded.order_ref, updated_at = datetime('now')",
            (int(user_id), plan["id"], _stamp(now), _stamp(expires), order_ref),
        )
    return active_plan(user_id) or {}


def _period_key(window: str, started_at: str) -> str:
    return "day:" + _now().strftime("%Y-%m-%d") if window == "day" else "pass:" + started_at


def consume_free_use(user_id: int, feature: str) -> str | None:
    """Spend one plan allowance for ``feature``. Returns "unlimited", "quota" or None (pay as usual)."""
    current = active_plan(user_id)
    if current is None:
        return None
    plan = PLANS[current["plan_id"]]
    if feature in plan["unlimited"]:
        return "unlimited"
    rule = plan["free"].get(feature)
    if rule is None:
        return None
    window, limit = rule
    key = _period_key(window, current["started_at"])
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT used FROM plan_usage WHERE user_id = ? AND feature = ? AND period_key = ?",
            (int(user_id), feature, key),
        ).fetchone()
        used = int(row["used"]) if row else 0
        if used >= limit:
            return None
        conn.execute(
            "INSERT INTO plan_usage (user_id, feature, period_key, used) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(user_id, feature, period_key) DO UPDATE SET used = used + 1",
            (int(user_id), feature, key),
        )
    return "quota"


def release_free_use(user_id: int, feature: str) -> None:
    """Give back an allowance when the run it paid for failed."""
    current = active_plan(user_id)
    if current is None:
        return
    rule = PLANS[current["plan_id"]]["free"].get(feature)
    if rule is None:
        return
    key = _period_key(rule[0], current["started_at"])
    with connect() as conn:
        conn.execute(
            "UPDATE plan_usage SET used = MAX(0, used - 1) "
            "WHERE user_id = ? AND feature = ? AND period_key = ?",
            (int(user_id), feature, key),
        )


def plan_summary(user_id: int) -> dict[str, Any] | None:
    """Active pass with what is left of each free allowance, for Billing."""
    current = active_plan(user_id)
    if current is None:
        return None
    plan = PLANS[current["plan_id"]]
    allowances = []
    with connect() as conn:
        for feature, (window, limit) in plan["free"].items():
            row = conn.execute(
                "SELECT used FROM plan_usage WHERE user_id = ? AND feature = ? AND period_key = ?",
                (int(user_id), feature, _period_key(window, current["started_at"])),
            ).fetchone()
            used = int(row["used"]) if row else 0
            allowances.append({"feature": feature, "window": window, "limit": limit, "used": min(used, limit)})
    return {**current, "usd": plan["usd"], "credits": plan["credits"], "allowances": allowances,
            "unlimited": list(plan["unlimited"])}


def _payment_label(package_id: str | None, credits: int) -> str:
    plan_id = plan_id_from_item(package_id)
    if plan_id:
        return f"{PLANS[plan_id]['name']} plan · {PLAN_DAYS} days"
    return f"{int(credits):,} credits · one-time"


def payment_history(user_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    """Paid and refunded purchases from every payment provider, newest first."""
    items: list[dict[str, Any]] = []
    with connect() as conn:
        for row in conn.execute(
            "SELECT package_id, credits, amount, status, COALESCE(paid_at, created_at) AS at "
            "FROM cryptomus_payments WHERE user_id = ? AND status != 'Pending' ORDER BY at DESC LIMIT ?",
            (int(user_id), limit),
        ):
            items.append({"date": row["at"], "item": _payment_label(row["package_id"], row["credits"]),
                          "amount": float(row["amount"]), "status": row["status"]})
        for row in conn.execute(
            "SELECT credits, amount, status, created_at FROM paddle_purchases "
            "WHERE user_id = ? AND status != 'Pending' ORDER BY created_at DESC LIMIT ?",
            (int(user_id), limit),
        ):
            items.append({"date": row["created_at"], "item": _payment_label(None, row["credits"]),
                          "amount": float(row["amount"]), "status": row["status"]})
        for row in conn.execute(
            "SELECT credits, price_cents, status, COALESCE(paid_at, created_at) AS at FROM gumroad_payments "
            "WHERE user_id = ? ORDER BY at DESC LIMIT ?",
            (int(user_id), limit),
        ):
            items.append({"date": row["at"], "item": _payment_label(None, row["credits"]),
                          "amount": round(int(row["price_cents"] or 0) / 100, 2), "status": row["status"]})
        has_lemon = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'lemon_squeezy_payments'"
        ).fetchone()
        if has_lemon:
            for row in conn.execute(
                "SELECT package_id, credits, status, COALESCE(paid_at, created_at) AS at, "
                "json_extract(payload_json, '$.data.attributes.total_usd') AS cents "
                "FROM lemon_squeezy_payments WHERE user_id = ? ORDER BY at DESC LIMIT ?",
                (int(user_id), limit),
            ):
                items.append({"date": row["at"], "item": _payment_label(row["package_id"], row["credits"]),
                              "amount": round(float(row["cents"] or 0) / 100, 2), "status": row["status"]})
    items.sort(key=lambda x: str(x["date"] or ""), reverse=True)
    return items[:limit]


def catalog() -> dict[str, Any]:
    return {
        "plan_days": PLAN_DAYS,
        "plans": [{"id": p["id"], "name": p["name"], "usd": p["usd"], "credits": p["credits"]} for p in PLANS.values()],
        "payg": dict(PAYG),
    }
