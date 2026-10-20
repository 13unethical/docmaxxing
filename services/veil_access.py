"""A paid 30-day pass that unlocks Veil. Questions during the pass are not charged again."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from services.economy.db import connect
from services.economy.pricing import VEIL_PASS_DAYS, feature_cost
from services.economy.wallet import WalletService

_FMT = "%Y-%m-%d %H:%M:%S"


def pass_cost() -> int:
    return feature_cost("veil")


def pass_days() -> int:
    return VEIL_PASS_DAYS


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse(value: str) -> datetime:
    return datetime.strptime(value, _FMT).replace(tzinfo=timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(_FMT)


def pass_status(user_id: int) -> dict[str, Any]:
    """Whether this account can use Veil right now."""
    with connect() as conn:
        row = conn.execute("SELECT expires_at FROM veil_passes WHERE user_id = ?", (int(user_id),)).fetchone()
    if row is None:
        return {"active": False, "expires_at": None, "expires_label": "", "days_left": 0}
    expires = _parse(row["expires_at"])
    active = expires > _now()
    days_left = max(0, (expires - _now()).days) if active else 0
    return {
        "active": active,
        "expires_at": expires.isoformat(),
        "expires_label": expires.strftime("%d %b %Y"),
        "days_left": days_left,
    }


def purchase_pass(user_id: int) -> dict[str, Any]:
    """Debit the pass price and extend access by 30 days from today, or from the current end if it is still active."""
    cost = pass_cost()
    now = _now()
    with connect() as conn:
        row = conn.execute("SELECT expires_at FROM veil_passes WHERE user_id = ?", (int(user_id),)).fetchone()
    current_end = _parse(row["expires_at"]) if row is not None else None
    base = current_end if current_end is not None and current_end > now else now
    expires = base + timedelta(days=pass_days())
    WalletService().debit(
        int(user_id),
        cost,
        "veil",
        meta={"pass_days": pass_days(), "expires_at": _stamp(expires)},
    )
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO veil_passes (user_id, expires_at, updated_at) VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(user_id) DO UPDATE SET expires_at = excluded.expires_at, updated_at = datetime('now')",
                (int(user_id), _stamp(expires)),
            )
    except Exception:
        WalletService().refund(int(user_id), cost, "veil", meta={"reason": "pass-save-failed"})
        raise
    status = pass_status(user_id)
    status["credits"] = cost
    status["balance"] = WalletService().get_balance(int(user_id))
    return status
