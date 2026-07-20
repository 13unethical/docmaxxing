"""Admin operations: user listing, balance adjustments, admin role management."""

from __future__ import annotations

import os
from typing import Any

from .auth import normalize_email
from .db import connect
from .wallet import InsufficientCoins, WalletService


class AdminError(Exception):
    """Raised when an admin action is rejected."""


class AdminService:
    def __init__(self, wallet: WalletService | None = None) -> None:
        self.wallet = wallet or WalletService()

    def list_users(
        self,
        *,
        search: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        q = (search or "").strip().lower()
        params: list[Any] = []
        where = ""
        if q:
            where = (
                "WHERE LOWER(u.email) LIKE ? OR LOWER(COALESCE(u.name, '')) LIKE ? "
                "OR CAST(u.id AS TEXT) LIKE ?"
            )
            like = f"%{q}%"
            params.extend([like, like, like])

        with connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS c FROM users u {where}",
                params,
            ).fetchone()["c"]
            rows = conn.execute(
                f"""
                SELECT u.id, u.email, u.name, u.is_admin, u.created_at,
                       COALESCE(w.balance, 0) AS balance
                FROM users u
                LEFT JOIN wallets w ON w.user_id = u.id
                {where}
                ORDER BY u.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        users = [
            {
                "id": row["id"],
                "email": row["email"],
                "name": row["name"],
                "isAdmin": bool(row["is_admin"]),
                "balance": int(row["balance"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]
        return {"users": users, "total": int(total), "limit": limit, "offset": offset}

    def set_balance(
        self,
        user_id: int,
        new_balance: int,
        *,
        admin_id: int,
        reason: str | None = None,
    ) -> dict[str, Any]:
        new_balance = int(new_balance)
        if new_balance < 0:
            raise AdminError("Balance cannot be negative.")

        current = self.wallet.get_balance(user_id)
        delta = new_balance - current
        meta = {"admin_id": admin_id, "reason": reason or "Admin adjustment"}
        if delta > 0:
            tx = self.wallet.credit(user_id, delta, "admin_adjustment", meta=meta)
        elif delta < 0:
            try:
                tx = self.wallet.debit(user_id, -delta, "admin_adjustment", meta=meta)
            except InsufficientCoins as exc:
                raise AdminError(
                    f"Cannot set balance to {new_balance}: user has {exc.balance} coins."
                ) from exc
        else:
            tx = {"balance": current, "balance_after": current, "amount": 0}

        return {
            "userId": user_id,
            "balance": int(tx.get("balance_after", tx.get("balance", new_balance))),
            "previousBalance": current,
            "delta": delta,
        }

    def count_admins(self) -> int:
        with connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE is_admin = 1"
            ).fetchone()
        return int(row["c"]) if row else 0

    def set_admin(
        self,
        user_id: int,
        *,
        is_admin: bool,
        actor_id: int,
    ) -> dict[str, Any]:
        with connect() as conn:
            row = conn.execute(
                "SELECT id, email, is_admin FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None:
                raise AdminError("User not found.")

            if not is_admin and int(row["is_admin"]) and user_id == actor_id:
                if self.count_admins() <= 1:
                    raise AdminError("You cannot remove admin access from the last admin.")

            conn.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?",
                (1 if is_admin else 0, user_id),
            )

        return {
            "userId": user_id,
            "email": row["email"],
            "isAdmin": bool(is_admin),
        }


def bootstrap_admin_from_env() -> None:
    """Promote ADMIN_EMAIL to admin on startup (if the account exists)."""
    email = normalize_email(os.environ.get("ADMIN_EMAIL") or "")
    if not email:
        return
    with connect() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
