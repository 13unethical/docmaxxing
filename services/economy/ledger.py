"""Credit ledger types and mapping for audit-friendly CreditTransaction rows.

Balance = current wallet state.
Ledger = append-only history of every credit movement.
"""

from __future__ import annotations

from typing import Any

# Transaction type (what happened)
TYPE_PURCHASE = "PURCHASE"
TYPE_USAGE = "USAGE"
TYPE_REFUND = "REFUND"
TYPE_ADMIN_ADD = "ADMIN_ADD"
TYPE_ADMIN_REMOVE = "ADMIN_REMOVE"
TYPE_BONUS = "BONUS"

# Reference type (which product / channel)
REF_PADDLE = "Paddle"
REF_HUMANIZER = "Humanizer"
REF_TURNITIN = "Turnitin"
REF_ASSIGNMENT = "Assignment"
REF_ADMIN = "Admin"
REF_DETECT = "Detect"
REF_CITE = "Cite"
REF_CHECK = "Check"
REF_SYSTEM = "System"

FEATURE_TO_REFERENCE: dict[str, str] = {
    "humanize": REF_HUMANIZER,
    "turnitin": REF_TURNITIN,
    "assignment": REF_ASSIGNMENT,
    "detect": REF_DETECT,
    "cite": REF_CITE,
    "check": REF_CHECK,
    "topup": REF_PADDLE,
    "welcome_bonus": REF_SYSTEM,
    "admin_adjustment": REF_ADMIN,
}


def classify_transaction(*, kind: str, feature: str) -> tuple[str, str]:
    """Return (type, reference_type) from legacy kind + feature."""
    kind = (kind or "").strip().lower()
    feature = (feature or "").strip().lower()
    ref = FEATURE_TO_REFERENCE.get(feature, REF_SYSTEM)

    if feature == "admin_adjustment":
        if kind == "debit":
            return TYPE_ADMIN_REMOVE, REF_ADMIN
        return TYPE_ADMIN_ADD, REF_ADMIN

    if feature == "welcome_bonus":
        return TYPE_BONUS, REF_SYSTEM

    if kind == "refund":
        return TYPE_REFUND, ref

    if kind == "debit":
        return TYPE_USAGE, ref

    # credit
    if feature == "topup":
        return TYPE_PURCHASE, REF_PADDLE
    return TYPE_BONUS, ref


def signed_credits(*, kind: str, amount: int) -> int:
    """Positive for money/coins in, negative for usage out."""
    amount = abs(int(amount))
    kind = (kind or "").strip().lower()
    if kind in ("credit", "refund"):
        return amount
    return -amount


def row_to_credit_transaction(row: Any) -> dict[str, Any]:
    """Normalize a SQLite transactions row into CreditTransaction shape."""
    kind = row["kind"] if "kind" in row.keys() else ""
    feature = row["feature"] if "feature" in row.keys() else ""
    amount = int(row["amount"])

    # Prefer persisted columns when present (new writes).
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    tx_type = None
    reference_type = None
    balance_before = None
    if "type" in keys and row["type"]:
        tx_type = str(row["type"])
    if "reference_type" in keys and row["reference_type"]:
        reference_type = str(row["reference_type"])
    if "balance_before" in keys and row["balance_before"] is not None:
        balance_before = int(row["balance_before"])

    if not tx_type or not reference_type:
        mapped_type, mapped_ref = classify_transaction(kind=kind, feature=feature)
        tx_type = tx_type or mapped_type
        reference_type = reference_type or mapped_ref

    balance_after = int(row["balance_after"])
    if balance_before is None:
        # Reconstruct for legacy rows.
        credits = signed_credits(kind=kind, amount=amount)
        balance_before = balance_after - credits
    else:
        credits = signed_credits(kind=kind, amount=amount)

    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "type": tx_type,
        "credits": credits,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "reference_type": reference_type,
        "reference_id": row["ref_id"] if "ref_id" in keys else None,
        "status": (row["status"] if "status" in keys and row["status"] else "completed"),
        "created_at": row["created_at"] if "created_at" in keys else None,
        # Legacy fields kept for existing /api/economy/transactions consumers.
        "kind": kind,
        "feature": feature,
        "amount": amount,
        "ref_id": row["ref_id"] if "ref_id" in keys else None,
    }
