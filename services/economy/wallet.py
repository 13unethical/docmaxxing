"""Coin wallet with an append-only ledger.

All balance movements go through :class:`WalletService`. Each movement is
atomic (single SQLite transaction with an immediate write lock) and records a
row in ``transactions`` capturing the resulting balance for auditability.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .db import connect


class WalletError(Exception):
    """Base class for wallet errors."""


class InsufficientCoins(WalletError):
    """Raised when a debit would take the balance below zero."""

    def __init__(self, *, required: int, balance: int) -> None:
        self.required = int(required)
        self.balance = int(balance)
        super().__init__(
            f"Insufficient coins: need {self.required}, have {self.balance}"
        )


def _row_to_tx(row: sqlite3.Row) -> dict[str, Any]:
    meta = None
    if row["meta_json"]:
        try:
            meta = json.loads(row["meta_json"])
        except (ValueError, TypeError):
            meta = None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "feature": row["feature"],
        "amount": row["amount"],
        "balance_after": row["balance_after"],
        "status": row["status"],
        "ref_id": row["ref_id"],
        "meta": meta,
        "created_at": row["created_at"],
    }


class WalletService:
    """Thin service over the economy DB. Stateless; safe to share."""

    def ensure_wallet(self, user_id: int) -> None:
        with connect() as conn:
            self._ensure_wallet(conn, user_id)

    @staticmethod
    def _ensure_wallet(conn: sqlite3.Connection, user_id: int) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO wallets (user_id, balance) VALUES (?, 0)",
            (user_id,),
        )

    def get_balance(self, user_id: int) -> int:
        with connect() as conn:
            row = conn.execute(
                "SELECT balance FROM wallets WHERE user_id = ?", (user_id,)
            ).fetchone()
            return int(row["balance"]) if row else 0

    def _apply(
        self,
        user_id: int,
        *,
        kind: str,
        feature: str,
        amount: int,
        ref_id: str | None,
        meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        amount = int(amount)
        if amount <= 0:
            raise WalletError("amount must be a positive integer")
        delta = amount if kind in ("credit", "refund") else -amount
        with connect() as conn:
            # Immediate lock so concurrent debits can't race the balance read.
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_wallet(conn, user_id)
            row = conn.execute(
                "SELECT balance FROM wallets WHERE user_id = ?", (user_id,)
            ).fetchone()
            balance = int(row["balance"]) if row else 0
            new_balance = balance + delta
            if new_balance < 0:
                raise InsufficientCoins(required=amount, balance=balance)
            conn.execute(
                "UPDATE wallets SET balance = ?, updated_at = datetime('now') "
                "WHERE user_id = ?",
                (new_balance, user_id),
            )
            cur = conn.execute(
                "INSERT INTO transactions "
                "(user_id, kind, feature, amount, balance_after, status, ref_id, meta_json) "
                "VALUES (?, ?, ?, ?, ?, 'completed', ?, ?)",
                (
                    user_id,
                    kind,
                    feature,
                    amount,
                    new_balance,
                    ref_id,
                    json.dumps(meta) if meta else None,
                ),
            )
            tx_id = cur.lastrowid
        return {
            "id": tx_id,
            "kind": kind,
            "feature": feature,
            "amount": amount,
            "balance_after": new_balance,
            "balance": new_balance,
            "ref_id": ref_id,
        }

    def credit(
        self,
        user_id: int,
        amount: int,
        feature: str,
        *,
        ref_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._apply(
            user_id, kind="credit", feature=feature, amount=amount,
            ref_id=ref_id, meta=meta,
        )

    def debit(
        self,
        user_id: int,
        amount: int,
        feature: str,
        *,
        ref_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._apply(
            user_id, kind="debit", feature=feature, amount=amount,
            ref_id=ref_id, meta=meta,
        )

    def refund(
        self,
        user_id: int,
        amount: int,
        feature: str,
        *,
        ref_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._apply(
            user_id, kind="refund", feature=feature, amount=amount,
            ref_id=ref_id, meta=meta,
        )

    def history(self, user_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE user_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [_row_to_tx(r) for r in rows]
