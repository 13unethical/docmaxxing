"""Referral & cashback business logic."""

from __future__ import annotations

import json
import secrets
import string
import sqlite3
from typing import Any

from .db import connect
from .pricing import USD_TO_COINS
from .wallet import WalletService

_wallet = WalletService()

REFERRAL_SIGNUP_BONUS = 100
CASHBACK_RATE = 0.40
QUALIFYING_DEPOSIT_USD = 10.0
CONVERT_MULTIPLIER = 1.2
MIN_WITHDRAW_USD = 50.0
PRO_DISCOUNT = 0.10  # 10% off paid features

MILESTONE_THRESHOLDS = (1, 3, 5, 10)


class ReferralError(Exception):
    """User-facing referral error."""


def _generate_code(conn: sqlite3.Connection) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(40):
        code = "DM" + "".join(secrets.choice(alphabet) for _ in range(8))
        exists = conn.execute(
            "SELECT 1 FROM users WHERE referral_code = ?", (code,)
        ).fetchone()
        if not exists:
            return code
    raise ReferralError("Could not allocate a referral code.")


def ensure_referral_code(user_id: int) -> str:
    with connect() as conn:
        row = conn.execute(
            "SELECT referral_code FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise ReferralError("User not found.")
        if row["referral_code"]:
            return str(row["referral_code"])
        code = _generate_code(conn)
        conn.execute(
            "UPDATE users SET referral_code = ? WHERE id = ? AND referral_code IS NULL",
            (code, user_id),
        )
        return code


def lookup_referrer_id(referral_code: str | None) -> int | None:
    code = (referral_code or "").strip().upper()
    if not code:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE upper(referral_code) = ?", (code,)
        ).fetchone()
    return int(row["id"]) if row else None


def _claimed_list(raw: str | None) -> list[int]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [int(x) for x in data]
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return []


def list_referred_users(referrer_id: int) -> list[dict[str, Any]]:
    """Referrals for the Earn dashboard: id only (no email), deposits + history."""
    with connect() as conn:
        people = conn.execute(
            """
            SELECT id, created_at,
                   COALESCE(has_qualified_deposit, 0) AS has_qualified_deposit
            FROM users
            WHERE referrer_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (referrer_id,),
        ).fetchall()
        if not people:
            return []

        ids = [int(p["id"]) for p in people]
        placeholders = ",".join("?" * len(ids))

        deposits: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}

        paddle_rows = conn.execute(
            f"""
            SELECT user_id, amount, credits, currency, paddle_transaction_id, created_at
            FROM paddle_purchases
            WHERE user_id IN ({placeholders}) AND status = 'Paid'
            ORDER BY created_at DESC, id DESC
            """,
            ids,
        ).fetchall()
        for r in paddle_rows:
            uid = int(r["user_id"])
            amount = round(float(r["amount"] or 0), 2)
            deposits[uid].append(
                {
                    "amount_usd": amount,
                    "credits": int(r["credits"] or 0),
                    "source": "paddle",
                    "created_at": r["created_at"],
                    "cashback_usd": round(amount * CASHBACK_RATE, 2),
                }
            )

        crypto_rows = conn.execute(
            f"""
            SELECT user_id, amount, credits, currency, order_id, paid_at, created_at
            FROM cryptomus_payments
            WHERE user_id IN ({placeholders}) AND status = 'Paid'
            ORDER BY COALESCE(paid_at, created_at) DESC, id DESC
            """,
            ids,
        ).fetchall()
        for r in crypto_rows:
            uid = int(r["user_id"])
            amount = round(float(r["amount"] or 0), 2)
            deposits[uid].append(
                {
                    "amount_usd": amount,
                    "credits": int(r["credits"] or 0),
                    "source": "cryptomus",
                    "created_at": r["paid_at"] or r["created_at"],
                    "cashback_usd": round(amount * CASHBACK_RATE, 2),
                }
            )

    items: list[dict[str, Any]] = []
    for p in people:
        uid = int(p["id"])
        history = sorted(
            deposits.get(uid, []),
            key=lambda x: x.get("created_at") or "",
            reverse=True,
        )
        total = round(sum(h["amount_usd"] for h in history), 2)
        cashback = round(sum(h["cashback_usd"] for h in history), 2)
        items.append(
            {
                "id": uid,
                "joined_at": p["created_at"],
                "qualified": bool(p["has_qualified_deposit"]),
                "total_deposited_usd": total,
                "your_cashback_usd": cashback,
                "deposit_count": len(history),
                "history": history,
            }
        )
    return items


def get_referral_profile(user_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise ReferralError("User not found.")
        code = row["referral_code"]
        if not code:
            code = _generate_code(conn)
            conn.execute(
                "UPDATE users SET referral_code = ? WHERE id = ?", (code, user_id)
            )
        referred = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE referrer_id = ?", (user_id,)
        ).fetchone()
        pending_withdrawals = conn.execute(
            "SELECT COUNT(*) AS n FROM withdrawal_requests "
            "WHERE user_id = ? AND status = 'pending'",
            (user_id,),
        ).fetchone()
    qualifying = int(row["qualifying_referrals_count"] or 0)
    claimed = _claimed_list(row["milestones_claimed"] if "milestones_claimed" in row.keys() else "[]")
    referrals = list_referred_users(user_id)
    return {
        "user_id": user_id,
        "referral_code": code,
        "referral_balance_usd": float(row["referral_balance_usd"] or 0),
        "qualifying_referrals_count": qualifying,
        "total_referrals": int(referred["n"] if referred else 0),
        "is_pro": bool(row["is_pro"]),
        "free_turnitin_reports": int(row["free_turnitin_reports"] or 0),
        "milestones_claimed": claimed,
        "referrals": referrals,
        "milestones": [
            {
                "threshold": 1,
                "label": "1 friend",
                "reward": "+1 Free Detailed Turnitin Report",
                "unlocked": qualifying >= 1,
                "claimed": 1 in claimed,
            },
            {
                "threshold": 3,
                "label": "3 friends",
                "reward": "+1,000 credits",
                "unlocked": qualifying >= 3,
                "claimed": 3 in claimed,
            },
            {
                "threshold": 5,
                "label": "5 friends",
                "reward": "+3,000 credits",
                "unlocked": qualifying >= 5,
                "claimed": 5 in claimed,
            },
            {
                "threshold": 10,
                "label": "10 friends",
                "reward": "Pro status (10% off checks)",
                "unlocked": qualifying >= 10,
                "claimed": 10 in claimed,
            },
        ],
        "min_withdraw_usd": MIN_WITHDRAW_USD,
        "can_withdraw": float(row["referral_balance_usd"] or 0) >= MIN_WITHDRAW_USD,
        "convert_multiplier": CONVERT_MULTIPLIER,
        "usd_to_coins": USD_TO_COINS,
        "pending_withdrawals": int(pending_withdrawals["n"] if pending_withdrawals else 0),
    }


def apply_milestones(conn: sqlite3.Connection, referrer_id: int) -> list[dict[str, Any]]:
    """Award any newly reached milestones. Returns list of awards granted now."""
    row = conn.execute("SELECT * FROM users WHERE id = ?", (referrer_id,)).fetchone()
    if row is None:
        return []
    count = int(row["qualifying_referrals_count"] or 0)
    claimed = _claimed_list(row["milestones_claimed"] if "milestones_claimed" in row.keys() else "[]")
    awards: list[dict[str, Any]] = []

    if count >= 1 and 1 not in claimed:
        conn.execute(
            "UPDATE users SET free_turnitin_reports = COALESCE(free_turnitin_reports, 0) + 1 "
            "WHERE id = ?",
            (referrer_id,),
        )
        claimed.append(1)
        awards.append({"threshold": 1, "type": "free_turnitin", "amount": 1})

    if count >= 3 and 3 not in claimed:
        claimed.append(3)
        awards.append({"threshold": 3, "type": "credits", "amount": 1000})

    if count >= 5 and 5 not in claimed:
        claimed.append(5)
        awards.append({"threshold": 5, "type": "credits", "amount": 3000})

    if count >= 10 and 10 not in claimed:
        conn.execute("UPDATE users SET is_pro = 1 WHERE id = ?", (referrer_id,))
        claimed.append(10)
        awards.append({"threshold": 10, "type": "pro", "amount": 1})

    conn.execute(
        "UPDATE users SET milestones_claimed = ? WHERE id = ?",
        (json.dumps(sorted(set(claimed))), referrer_id),
    )
    return awards


def on_successful_deposit(
    user_id: int,
    amount_usd: float,
    *,
    payment_ref: str | None = None,
) -> dict[str, Any]:
    """Cashback loop after a paid top-up. Safe to call outside payment txn."""
    amount_usd = float(amount_usd or 0)
    if amount_usd <= 0:
        return {"handled": False, "reason": "zero_amount"}

    credit_awards: list[dict[str, Any]] = []
    with connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            return {"handled": False, "reason": "user_missing"}
        referrer_id = user["referrer_id"]
        if not referrer_id:
            return {"handled": False, "reason": "no_referrer"}
        referrer_id = int(referrer_id)
        if referrer_id == int(user_id):
            return {"handled": False, "reason": "self_referral"}

        cashback = round(amount_usd * CASHBACK_RATE, 2)
        conn.execute(
            "UPDATE users SET referral_balance_usd = "
            "COALESCE(referral_balance_usd, 0) + ? WHERE id = ?",
            (cashback, referrer_id),
        )

        qualified_now = False
        if amount_usd >= QUALIFYING_DEPOSIT_USD:
            cur = conn.execute(
                "UPDATE users SET has_qualified_deposit = 1 "
                "WHERE id = ? AND COALESCE(has_qualified_deposit, 0) = 0",
                (user_id,),
            )
            if cur.rowcount == 1:
                qualified_now = True
                conn.execute(
                    "UPDATE users SET qualifying_referrals_count = "
                    "COALESCE(qualifying_referrals_count, 0) + 1 WHERE id = ?",
                    (referrer_id,),
                )
                credit_awards = apply_milestones(conn, referrer_id)

        result = {
            "handled": True,
            "cashback_usd": cashback,
            "referrer_id": referrer_id,
            "qualified_now": qualified_now,
            "milestone_awards": credit_awards,
            "payment_ref": payment_ref,
        }

    for award in credit_awards:
        if award["type"] == "credits":
            _wallet.credit(
                referrer_id,
                int(award["amount"]),
                "referral_milestone",
                ref_id=f"milestone_{award['threshold']}_{referrer_id}",
                meta={"threshold": award["threshold"], "from_user_id": user_id},
            )
    return result


def convert_balance_to_credits(user_id: int, amount_usd: float) -> dict[str, Any]:
    amount_usd = round(float(amount_usd), 2)
    if amount_usd <= 0:
        raise ReferralError("Amount must be positive.")
    credits = int(round(amount_usd * USD_TO_COINS * CONVERT_MULTIPLIER))
    if credits < 1:
        raise ReferralError("Converted amount is too small.")
    with connect() as conn:
        row = conn.execute(
            "SELECT referral_balance_usd FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise ReferralError("User not found.")
        balance = float(row["referral_balance_usd"] or 0)
        if amount_usd > balance + 1e-9:
            raise ReferralError(
                f"Insufficient referral balance. You have ${balance:.2f}."
            )
        cur = conn.execute(
            "UPDATE users SET referral_balance_usd = referral_balance_usd - ? "
            "WHERE id = ? AND referral_balance_usd >= ?",
            (amount_usd, user_id, amount_usd),
        )
        if cur.rowcount != 1:
            raise ReferralError("Could not deduct referral balance. Try again.")
        new_balance = round(balance - amount_usd, 2)
    tx = _wallet.credit(
        user_id,
        credits,
        "referral_convert",
        ref_id=f"convert_{user_id}_{int(amount_usd * 100)}_{credits}",
        meta={"usd": amount_usd, "multiplier": CONVERT_MULTIPLIER},
    )
    return {
        "converted_usd": amount_usd,
        "credits": credits,
        "referral_balance_usd": new_balance,
        "balance": tx.get("balance_after") if isinstance(tx, dict) else None,
    }


def create_withdrawal(
    user_id: int,
    *,
    amount_usd: float,
    wallet_details: str,
) -> dict[str, Any]:
    amount_usd = round(float(amount_usd), 2)
    details = (wallet_details or "").strip()
    if amount_usd < MIN_WITHDRAW_USD:
        raise ReferralError(f"Minimum withdrawal is ${MIN_WITHDRAW_USD:.0f}.")
    if not details or len(details) < 4:
        raise ReferralError("Please provide wallet / payment details.")
    with connect() as conn:
        row = conn.execute(
            "SELECT referral_balance_usd FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise ReferralError("User not found.")
        balance = float(row["referral_balance_usd"] or 0)
        if amount_usd > balance + 1e-9:
            raise ReferralError(
                f"Insufficient referral balance. You have ${balance:.2f}."
            )
        cur = conn.execute(
            "UPDATE users SET referral_balance_usd = referral_balance_usd - ? "
            "WHERE id = ? AND referral_balance_usd >= ?",
            (amount_usd, user_id, amount_usd),
        )
        if cur.rowcount != 1:
            raise ReferralError("Could not reserve withdrawal amount. Try again.")
        ins = conn.execute(
            "INSERT INTO withdrawal_requests "
            "(user_id, amount_usd, wallet_details, status) VALUES (?, ?, ?, 'pending')",
            (user_id, amount_usd, details),
        )
        req_id = int(ins.lastrowid)
        new_balance = round(balance - amount_usd, 2)
    return {
        "id": req_id,
        "amount_usd": amount_usd,
        "status": "pending",
        "referral_balance_usd": new_balance,
    }


def list_withdrawals(
    *,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("w.status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM withdrawal_requests w {where}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT w.*, u.email, u.name
            FROM withdrawal_requests w
            JOIN users u ON u.id = w.user_id
            {where}
            ORDER BY w.created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    items = [
        {
            "id": int(r["id"]),
            "user_id": int(r["user_id"]),
            "email": r["email"],
            "name": r["name"],
            "amount_usd": float(r["amount_usd"]),
            "wallet_details": r["wallet_details"],
            "status": r["status"],
            "created_at": r["created_at"],
            "resolved_at": r["resolved_at"],
            "admin_note": r["admin_note"],
        }
        for r in rows
    ]
    return {"items": items, "total": int(total)}


def resolve_withdrawal(
    request_id: int,
    *,
    approve: bool,
    admin_id: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM withdrawal_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if row is None:
            raise ReferralError("Withdrawal request not found.")
        if row["status"] != "pending":
            raise ReferralError(f"Request is already {row['status']}.")
        new_status = "approved" if approve else "rejected"
        if not approve:
            conn.execute(
                "UPDATE users SET referral_balance_usd = "
                "COALESCE(referral_balance_usd, 0) + ? WHERE id = ?",
                (float(row["amount_usd"]), int(row["user_id"])),
            )
        conn.execute(
            "UPDATE withdrawal_requests SET status = ?, resolved_at = datetime('now'), "
            "admin_note = ? WHERE id = ?",
            (new_status, (note or "").strip() or None, request_id),
        )
    return {"id": request_id, "status": new_status, "admin_id": admin_id}


def consume_free_turnitin_report(user_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE users SET free_turnitin_reports = free_turnitin_reports - 1 "
            "WHERE id = ? AND COALESCE(free_turnitin_reports, 0) > 0",
            (user_id,),
        )
        return cur.rowcount == 1


def user_has_pro(user_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT is_pro FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return bool(row and row["is_pro"])


def apply_pro_discount(user: dict[str, Any] | None, cost: int) -> int:
    if not user or not user.get("is_pro"):
        return int(cost)
    return max(1, int(round(int(cost) * (1.0 - PRO_DISCOUNT))))
