"""Admin operations: user listing, balance adjustments, admin role management."""

from __future__ import annotations

import os
from typing import Any

from .analytics import AnalyticsService
from .auth import normalize_email
from .db import connect
from .paddle_purchases import PaddlePurchaseService
from .usage import UsageService
from .wallet import WalletError, WalletService


class AdminError(Exception):
    """Raised when an admin action is rejected."""


class AdminService:
    def __init__(
        self,
        wallet: WalletService | None = None,
        purchases: PaddlePurchaseService | None = None,
        usage: UsageService | None = None,
        analytics: AnalyticsService | None = None,
    ) -> None:
        self.wallet = wallet or WalletService()
        self.purchases = purchases or PaddlePurchaseService()
        self.usage = usage or UsageService()
        self.analytics = analytics or AnalyticsService()

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
        # Absolute assign — never treat new_balance as an increment.
        if isinstance(new_balance, bool) or not isinstance(new_balance, int):
            raise AdminError("Balance must be an integer.")
        if new_balance < 0:
            raise AdminError("Balance cannot be negative.")

        current = self.wallet.get_balance(user_id)
        current_str = str(int(current))
        new_str = str(int(new_balance))
        if (
            new_balance != current
            and len(new_str) > len(current_str)
            and new_str.startswith(current_str)
        ):
            raise AdminError(
                f"Balance looks like digits appended to the current balance ({current}). "
                "Send the exact new total only."
            )

        meta = {
            "admin_id": int(admin_id),
            "reason": reason or "Admin set balance",
            "previous_balance": current,
            "new_balance": new_balance,
        }
        try:
            tx = self.wallet.set_balance(
                user_id,
                new_balance,
                feature="admin_set",
                meta=meta,
            )
        except WalletError as exc:
            raise AdminError(str(exc)) from exc

        balance_after = int(tx.get("balance_after", tx.get("balance", new_balance)))
        return {
            "userId": user_id,
            "balance": balance_after,
            "previousBalance": current,
            "delta": balance_after - current,
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

    def delete_user(self, user_id: int, *, actor_id: int) -> dict[str, Any]:
        """Permanently delete a user and cascaded economy rows."""
        user_id = int(user_id)
        actor_id = int(actor_id)
        if user_id == actor_id:
            raise AdminError("You cannot delete your own account from the admin panel.")

        with connect() as conn:
            row = conn.execute(
                "SELECT id, email, is_admin, avatar_file FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                raise AdminError("User not found.")

            if int(row["is_admin"]):
                admin_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE is_admin = 1"
                ).fetchone()["c"]
                if int(admin_count) <= 1:
                    raise AdminError("You cannot delete the last admin account.")

            # Referral links are soft FKs (added via ALTER) — clear them first.
            conn.execute(
                "UPDATE users SET referrer_id = NULL WHERE referrer_id = ?",
                (user_id,),
            )
            avatar_file = row["avatar_file"] if "avatar_file" in row.keys() else None
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

        self._cleanup_avatar_file(avatar_file)
        self._cleanup_turnitin_for_user(user_id)

        return {
            "userId": user_id,
            "email": row["email"],
            "deleted": True,
        }

    @staticmethod
    def _cleanup_avatar_file(avatar_file: str | None) -> None:
        if not avatar_file:
            return
        try:
            from pathlib import Path

            repo_root = Path(__file__).resolve().parents[2]
            # Stored as relative path under static/ (e.g. uploads/avatars/…)
            path = (repo_root / "static" / str(avatar_file)).resolve()
            avatars_root = (repo_root / "static" / "uploads" / "avatars").resolve()
            if path.is_file() and str(path).startswith(str(avatars_root)):
                path.unlink()
        except OSError:
            pass

    @staticmethod
    def _cleanup_turnitin_for_user(user_id: int) -> None:
        """Best-effort cleanup of Turnitin rows (separate SQLite DB)."""
        try:
            from services.turnitin_service.store import TurnitinStore

            store = TurnitinStore()
            rows = store.list_for_user(int(user_id), limit=500)
            for row in rows:
                sid = row.get("id")
                if sid:
                    store.delete_for_user(str(sid), int(user_id))
        except Exception:  # noqa: BLE001
            pass

    def get_ledger(
        self,
        user_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        with connect() as conn:
            row = conn.execute(
                "SELECT id, email, name FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None:
                raise AdminError("User not found.")
        payload = self.wallet.ledger(user_id, limit=limit, offset=offset)
        return {
            "user": {
                "id": int(row["id"]),
                "email": row["email"],
                "name": row["name"],
            },
            **payload,
        }

    def get_purchases(
        self,
        user_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        with connect() as conn:
            row = conn.execute(
                "SELECT id, email, name FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None:
                raise AdminError("User not found.")
        payload = self.purchases.list_for_user(user_id, limit=limit, offset=offset)
        return {
            "user": {
                "id": int(row["id"]),
                "email": row["email"],
                "name": row["name"],
            },
            **payload,
        }

    def list_purchases(
        self,
        *,
        search: str = "",
        status: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        try:
            return self.purchases.list_all(
                search=search, status=status, limit=limit, offset=offset
            )
        except Exception as exc:  # noqa: BLE001
            from .paddle_purchases import PaddlePurchaseError

            if isinstance(exc, PaddlePurchaseError):
                raise AdminError(str(exc)) from exc
            raise

    def get_usage(
        self,
        user_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        with connect() as conn:
            row = conn.execute(
                "SELECT id, email, name FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None:
                raise AdminError("User not found.")
        payload = self.usage.list_for_user(user_id, limit=limit, offset=offset)
        return {
            "user": {
                "id": int(row["id"]),
                "email": row["email"],
                "name": row["name"],
            },
            **payload,
        }

    def list_usage(
        self,
        *,
        search: str = "",
        feature: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self.usage.list_all(
            search=search, feature=feature, limit=limit, offset=offset
        )

    def get_analytics(self, *, top_limit: int = 10) -> dict[str, Any]:
        return self.analytics.snapshot(top_limit=top_limit)


def bootstrap_admin_from_env() -> None:
    """Promote ADMIN_EMAIL to admin on startup (if the account exists)."""
    email = normalize_email(os.environ.get("ADMIN_EMAIL") or "")
    if not email:
        return
    with connect() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
