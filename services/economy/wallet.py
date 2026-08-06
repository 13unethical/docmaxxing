"""Coin wallet with an append-only CreditTransaction ledger.

All balance movements go through :class:`WalletService`. Each movement is
atomic (single SQLite transaction with an immediate write lock) and records a
ledger row with type, signed credits, balance_before/after, and reference.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .db import connect
from .ledger import classify_transaction, row_to_credit_transaction, signed_credits


class WalletError(Exception):
    """Base class for wallet errors."""


class InsufficientCoins(WalletError):
    """Raised when a debit would take the balance below zero."""

    def __init__(self, *, required: int, balance: int) -> None:
        self.required = int(required)
        self.balance = int(balance)
        super().__init__(
            f"Insufficient credits: need {self.required}, have {self.balance}"
        )


def _row_to_tx(row: sqlite3.Row) -> dict[str, Any]:
    """Legacy + CreditTransaction shape for API consumers."""
    base = row_to_credit_transaction(row)
    meta = None
    if row["meta_json"]:
        try:
            meta = json.loads(row["meta_json"])
        except (ValueError, TypeError):
            meta = None
    base["meta"] = meta
    return base


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
        delta = signed_credits(kind=kind, amount=amount)
        tx_type, reference_type = classify_transaction(kind=kind, feature=feature)
        with connect() as conn:
            # Immediate write lock — concurrent debit/credit cannot race.
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_wallet(conn, user_id)
            row = conn.execute(
                "SELECT balance FROM wallets WHERE user_id = ?", (user_id,)
            ).fetchone()
            balance_before = int(row["balance"]) if row else 0

            if kind == "debit":
                # Atomic conditional debit — prevents TOCTOU under concurrency.
                cur = conn.execute(
                    "UPDATE wallets SET balance = balance - ?, "
                    "updated_at = datetime('now') "
                    "WHERE user_id = ? AND balance >= ?",
                    (amount, user_id, amount),
                )
                if cur.rowcount != 1:
                    raise InsufficientCoins(required=amount, balance=balance_before)
                balance_after = balance_before - amount
            else:
                balance_after = balance_before + delta
                if balance_after < 0:
                    raise InsufficientCoins(required=amount, balance=balance_before)
                conn.execute(
                    "UPDATE wallets SET balance = ?, updated_at = datetime('now') "
                    "WHERE user_id = ?",
                    (balance_after, user_id),
                )

            cur = conn.execute(
                "INSERT INTO transactions "
                "(user_id, kind, feature, amount, balance_before, balance_after, "
                " type, reference_type, status, ref_id, meta_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?)",
                (
                    user_id,
                    kind,
                    feature,
                    amount,
                    balance_before,
                    balance_after,
                    tx_type,
                    reference_type,
                    ref_id,
                    json.dumps(meta) if meta else None,
                ),
            )
            tx_id = cur.lastrowid
        return {
            "id": tx_id,
            "user_id": user_id,
            "type": tx_type,
            "credits": delta,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "reference_type": reference_type,
            "reference_id": ref_id,
            "status": "completed",
            "kind": kind,
            "feature": feature,
            "amount": amount,
            "balance": balance_after,
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
        limit = max(1, min(int(limit), 500))
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE user_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [_row_to_tx(r) for r in rows]

    def ledger(
        self,
        user_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Admin-facing CreditTransaction journal for one user."""
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        with connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM transactions WHERE user_id = ?",
                (user_id,),
            ).fetchone()["c"]
            rows = conn.execute(
                "SELECT * FROM transactions WHERE user_id = ? "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
        entries = [_row_to_tx(r) for r in rows]
        return {
            "user_id": user_id,
            "balance": self.get_balance(user_id),
            "total": int(total),
            "limit": limit,
            "offset": offset,
            "entries": entries,
        }
