"""Admin analytics aggregates over purchases, ledger, and usage."""

from __future__ import annotations

from typing import Any

from .db import connect
from .paddle_purchases import STATUS_PAID


def _safe_div(num: float, den: float) -> float:
    if not den:
        return 0.0
    return float(num) / float(den)


class AnalyticsService:
    """Read-only KPIs for the admin Analytics panel."""

    def snapshot(self, *, top_limit: int = 10) -> dict[str, Any]:
        top_limit = max(1, min(int(top_limit), 50))

        with connect() as conn:
            user_count = int(
                conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
            )

            sold_row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(credits), 0) AS credits_sold,
                    COALESCE(SUM(amount), 0) AS revenue,
                    COUNT(*) AS purchase_count
                FROM paddle_purchases
                WHERE status = ?
                """,
                (STATUS_PAID,),
            ).fetchone()
            credits_sold = int(sold_row["credits_sold"] or 0)
            revenue = float(sold_row["revenue"] or 0.0)
            purchase_count = int(sold_row["purchase_count"] or 0)

            # Prefer usage_events; fall back to ledger debits if usage is empty.
            used_row = conn.execute(
                "SELECT COALESCE(SUM(credits_used), 0) AS used FROM usage_events"
            ).fetchone()
            credits_used = int(used_row["used"] or 0)
            if credits_used == 0:
                debit_row = conn.execute(
                    """
                    SELECT COALESCE(SUM(amount), 0) AS used
                    FROM transactions
                    WHERE kind = 'debit'
                    """
                ).fetchone()
                credits_used = int(debit_row["used"] or 0)

            feature_rows = conn.execute(
                """
                SELECT feature,
                       COUNT(*) AS launches,
                       COALESCE(SUM(credits_used), 0) AS credits
                FROM usage_events
                GROUP BY feature
                ORDER BY launches DESC, credits DESC
                """
            ).fetchall()
            if not feature_rows:
                feature_rows = conn.execute(
                    """
                    SELECT feature,
                           COUNT(*) AS launches,
                           COALESCE(SUM(amount), 0) AS credits
                    FROM transactions
                    WHERE kind = 'debit'
                    GROUP BY feature
                    ORDER BY launches DESC, credits DESC
                    """
                ).fetchall()

            features = [
                {
                    "feature": row["feature"],
                    "launches": int(row["launches"]),
                    "credits": int(row["credits"]),
                }
                for row in feature_rows
            ]
            most_used = features[0] if features else None

            avg_purchase_row = conn.execute(
                """
                SELECT
                    COALESCE(AVG(amount), 0) AS avg_amount,
                    COALESCE(AVG(credits), 0) AS avg_credits
                FROM paddle_purchases
                WHERE status = ?
                """,
                (STATUS_PAID,),
            ).fetchone()

            top_customers = conn.execute(
                """
                SELECT
                    u.id AS user_id,
                    u.email,
                    u.name,
                    COUNT(p.id) AS purchase_count,
                    COALESCE(SUM(p.credits), 0) AS credits_bought,
                    COALESCE(SUM(p.amount), 0) AS revenue
                FROM paddle_purchases p
                JOIN users u ON u.id = p.user_id
                WHERE p.status = ?
                GROUP BY u.id
                ORDER BY revenue DESC, credits_bought DESC
                LIMIT ?
                """,
                (STATUS_PAID, top_limit),
            ).fetchall()

            # Country column may be missing on very old DBs before migrate.
            countries: list[dict[str, Any]] = []
            try:
                country_rows = conn.execute(
                    """
                    SELECT
                        COALESCE(NULLIF(TRIM(country), ''), 'Unknown') AS country,
                        COUNT(*) AS purchase_count,
                        COALESCE(SUM(credits), 0) AS credits,
                        COALESCE(SUM(amount), 0) AS revenue
                    FROM paddle_purchases
                    WHERE status = ?
                    GROUP BY COALESCE(NULLIF(TRIM(country), ''), 'Unknown')
                    ORDER BY revenue DESC, purchase_count DESC
                    LIMIT ?
                    """,
                    (STATUS_PAID, top_limit),
                ).fetchall()
                countries = [
                    {
                        "country": row["country"],
                        "purchase_count": int(row["purchase_count"]),
                        "credits": int(row["credits"]),
                        "revenue": round(float(row["revenue"] or 0.0), 2),
                    }
                    for row in country_rows
                ]
            except Exception:  # noqa: BLE001
                countries = []

        return {
            "total_credits_sold": credits_sold,
            "total_credits_used": credits_used,
            "revenue": round(revenue, 2),
            "revenue_currency": "USD",
            "purchase_count": purchase_count,
            "user_count": user_count,
            "most_used_feature": most_used,
            "features": features,
            "average_credits_per_user": round(
                _safe_div(credits_sold, user_count), 2
            ),
            "average_purchase": {
                "amount": round(float(avg_purchase_row["avg_amount"] or 0.0), 2),
                "credits": round(float(avg_purchase_row["avg_credits"] or 0.0), 2),
                "currency": "USD",
            },
            "top_customers": [
                {
                    "user_id": int(row["user_id"]),
                    "email": row["email"],
                    "name": row["name"],
                    "purchase_count": int(row["purchase_count"]),
                    "credits_bought": int(row["credits_bought"]),
                    "revenue": round(float(row["revenue"] or 0.0), 2),
                }
                for row in top_customers
            ],
            "top_countries": countries,
        }
