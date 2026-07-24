"""PaddlePurchase — payment records separate from the coin ledger.

Ledger tracks credit movements. This table tracks checkout / payment lifecycle
with Paddle (or mock top-up until real webhooks are wired).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .db import connect

STATUS_PENDING = "Pending"
STATUS_PAID = "Paid"
STATUS_REFUNDED = "Refunded"
STATUS_FAILED = "Failed"

VALID_STATUSES = frozenset(
    {STATUS_PENDING, STATUS_PAID, STATUS_REFUNDED, STATUS_FAILED}
)


class PaddlePurchaseError(Exception):
    """Raised when a purchase action is rejected."""


def _row_to_purchase(row: sqlite3.Row) -> dict[str, Any]:
    keys = set(row.keys())
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "paddle_transaction_id": row["paddle_transaction_id"],
        "product_id": row["product_id"],
        "price_id": row["price_id"],
        "credits": int(row["credits"]),
        "amount": float(row["amount"]),
        "currency": row["currency"] or "USD",
        "status": row["status"],
        "country": row["country"] if "country" in keys else None,
        "created_at": row["created_at"],
    }


class PaddlePurchaseService:
    def create(
        self,
        *,
        user_id: int,
        paddle_transaction_id: str,
        product_id: str,
        price_id: str,
        credits: int,
        amount: float,
        currency: str = "USD",
        status: str = STATUS_PENDING,
        country: str | None = None,
    ) -> dict[str, Any]:
        status = (status or STATUS_PENDING).strip()
        if status not in VALID_STATUSES:
            raise PaddlePurchaseError(f"Invalid status: {status}")
        paddle_transaction_id = (paddle_transaction_id or "").strip()
        if not paddle_transaction_id:
            raise PaddlePurchaseError("paddle_transaction_id is required")
        credits = int(credits)
        if credits <= 0:
            raise PaddlePurchaseError("credits must be positive")
        country_code = (country or "").strip().upper() or None

        with connect() as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO paddle_purchases "
                    "(user_id, paddle_transaction_id, product_id, price_id, "
                    " credits, amount, currency, status, country) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        int(user_id),
                        paddle_transaction_id,
                        (product_id or "").strip() or None,
                        (price_id or "").strip() or None,
                        credits,
                        float(amount),
                        (currency or "USD").strip().upper() or "USD",
                        status,
                        country_code,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise PaddlePurchaseError(
                    f"Duplicate paddle_transaction_id: {paddle_transaction_id}"
                ) from exc
            purchase_id = int(cur.lastrowid)
            row = conn.execute(
                "SELECT * FROM paddle_purchases WHERE id = ?", (purchase_id,)
            ).fetchone()
        return _row_to_purchase(row)

    def update_status(
        self,
        purchase_id: int,
        status: str,
    ) -> dict[str, Any]:
        status = (status or "").strip()
        if status not in VALID_STATUSES:
            raise PaddlePurchaseError(f"Invalid status: {status}")
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM paddle_purchases WHERE id = ?", (int(purchase_id),)
            ).fetchone()
            if row is None:
                raise PaddlePurchaseError("Purchase not found")
            conn.execute(
                "UPDATE paddle_purchases SET status = ? WHERE id = ?",
                (status, int(purchase_id)),
            )
            row = conn.execute(
                "SELECT * FROM paddle_purchases WHERE id = ?", (int(purchase_id),)
            ).fetchone()
        return _row_to_purchase(row)

    def get(self, purchase_id: int) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM paddle_purchases WHERE id = ?", (int(purchase_id),)
            ).fetchone()
        return _row_to_purchase(row) if row else None

    def get_by_paddle_transaction_id(
        self, paddle_transaction_id: str
    ) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM paddle_purchases WHERE paddle_transaction_id = ?",
                ((paddle_transaction_id or "").strip(),),
            ).fetchone()
        return _row_to_purchase(row) if row else None

    def list_for_user(
        self,
        user_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        with connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM paddle_purchases WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()["c"]
            rows = conn.execute(
                "SELECT * FROM paddle_purchases WHERE user_id = ? "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (int(user_id), limit, offset),
            ).fetchall()
        return {
            "user_id": int(user_id),
            "total": int(total),
            "limit": limit,
            "offset": offset,
            "purchases": [_row_to_purchase(r) for r in rows],
        }

    def list_all(
        self,
        *,
        search: str = "",
        status: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        clauses: list[str] = []
        params: list[Any] = []

        q = (search or "").strip().lower()
        if q:
            clauses.append(
                "(LOWER(COALESCE(p.paddle_transaction_id, '')) LIKE ? "
                "OR LOWER(COALESCE(p.product_id, '')) LIKE ? "
                "OR LOWER(COALESCE(u.email, '')) LIKE ? "
                "OR CAST(p.user_id AS TEXT) LIKE ?)"
            )
            like = f"%{q}%"
            params.extend([like, like, like, like])

        st = (status or "").strip()
        if st:
            if st not in VALID_STATUSES:
                raise PaddlePurchaseError(f"Invalid status filter: {st}")
            clauses.append("p.status = ?")
            params.append(st)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with connect() as conn:
            total = conn.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM paddle_purchases p
                LEFT JOIN users u ON u.id = p.user_id
                {where}
                """,
                params,
            ).fetchone()["c"]
            rows = conn.execute(
                f"""
                SELECT p.*, u.email AS user_email, u.name AS user_name
                FROM paddle_purchases p
                LEFT JOIN users u ON u.id = p.user_id
                {where}
                ORDER BY p.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        purchases = []
        for row in rows:
            item = _row_to_purchase(row)
            item["user_email"] = row["user_email"]
            item["user_name"] = row["user_name"]
            purchases.append(item)
        return {
            "total": int(total),
            "limit": limit,
            "offset": offset,
            "purchases": purchases,
        }
