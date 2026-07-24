"""Usage — one row per AI feature launch (admin cost / audit view).

Separate from the coin ledger: ledger is money movements; usage is each AI run
with provider, latency, and credits consumed.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .db import connect

FEATURE_HUMANIZER = "Humanizer"
FEATURE_TURNITIN = "Turnitin"
FEATURE_ASSIGNMENT = "Assignment"
FEATURE_AI_WRITER = "AI Writer"
FEATURE_DETECTION = "Detection"

VALID_FEATURES = frozenset(
    {
        FEATURE_HUMANIZER,
        FEATURE_TURNITIN,
        FEATURE_ASSIGNMENT,
        FEATURE_AI_WRITER,
        FEATURE_DETECTION,
    }
)

# Map wallet feature ids → Usage.feature labels
WALLET_FEATURE_TO_USAGE: dict[str, str] = {
    "humanize": FEATURE_HUMANIZER,
    "turnitin": FEATURE_TURNITIN,
    "assignment": FEATURE_ASSIGNMENT,
    "detect": FEATURE_DETECTION,
}


class UsageError(Exception):
    """Raised when a usage record is rejected."""


def _row_to_usage(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "feature": row["feature"],
        "credits_used": int(row["credits_used"]),
        "provider": row["provider"],
        "provider_cost": (
            float(row["provider_cost"]) if row["provider_cost"] is not None else None
        ),
        "latency": int(row["latency"]) if row["latency"] is not None else None,
        "request_id": row["request_id"],
        "created_at": row["created_at"],
    }


class UsageService:
    def record(
        self,
        *,
        user_id: int,
        feature: str,
        credits_used: int,
        provider: str | None = None,
        provider_cost: float | None = None,
        latency: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        feature = (feature or "").strip()
        if feature not in VALID_FEATURES:
            # Allow unknown labels but normalize empty
            if not feature:
                raise UsageError("feature is required")
        credits_used = max(0, int(credits_used))
        latency_ms = None if latency is None else max(0, int(latency))
        cost = None if provider_cost is None else float(provider_cost)

        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO usage_events "
                "(user_id, feature, credits_used, provider, provider_cost, latency, request_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    int(user_id),
                    feature,
                    credits_used,
                    (provider or "").strip() or None,
                    cost,
                    latency_ms,
                    (request_id or "").strip() or None,
                ),
            )
            usage_id = int(cur.lastrowid)
            row = conn.execute(
                "SELECT * FROM usage_events WHERE id = ?", (usage_id,)
            ).fetchone()
        return _row_to_usage(row)

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
                "SELECT COUNT(*) AS c FROM usage_events WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()["c"]
            rows = conn.execute(
                "SELECT * FROM usage_events WHERE user_id = ? "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (int(user_id), limit, offset),
            ).fetchall()
        return {
            "user_id": int(user_id),
            "total": int(total),
            "limit": limit,
            "offset": offset,
            "usage": [_row_to_usage(r) for r in rows],
        }

    def list_all(
        self,
        *,
        search: str = "",
        feature: str = "",
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
                "(LOWER(COALESCE(u.email, '')) LIKE ? "
                "OR LOWER(COALESCE(e.provider, '')) LIKE ? "
                "OR LOWER(COALESCE(e.request_id, '')) LIKE ? "
                "OR CAST(e.user_id AS TEXT) LIKE ?)"
            )
            like = f"%{q}%"
            params.extend([like, like, like, like])

        feat = (feature or "").strip()
        if feat:
            clauses.append("e.feature = ?")
            params.append(feat)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with connect() as conn:
            total = conn.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM usage_events e
                LEFT JOIN users u ON u.id = e.user_id
                {where}
                """,
                params,
            ).fetchone()["c"]
            rows = conn.execute(
                f"""
                SELECT e.*, u.email AS user_email, u.name AS user_name
                FROM usage_events e
                LEFT JOIN users u ON u.id = e.user_id
                {where}
                ORDER BY e.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        items = []
        for row in rows:
            item = _row_to_usage(row)
            item["user_email"] = row["user_email"]
            item["user_name"] = row["user_name"]
            items.append(item)
        return {
            "total": int(total),
            "limit": limit,
            "offset": offset,
            "usage": items,
        }
