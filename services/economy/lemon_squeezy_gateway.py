"""Lemon Squeezy webhooks → credit top-ups.

Docs: https://docs.lemonsqueezy.com/help/webhooks

Signing: HMAC-SHA256 of the raw request body with ``LEMON_SQUEEZY_WEBHOOK_SECRET``,
compared to the ``X-Signature`` header.

Fulfillment is idempotent on Lemon order ``data.id`` (and ledger ``ref_id``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sqlite3
from typing import Any

from .db import connect
from .ledger import classify_transaction, signed_credits
from .pricing import TOPUP_PACKAGES

logger = logging.getLogger(__name__)

STATUS_PAID = "Paid"
STATUS_IGNORED = "Ignored"


class LemonSqueezyGatewayError(Exception):
    """Processing / config failure."""


class LemonSqueezySignatureError(LemonSqueezyGatewayError):
    """Invalid or missing X-Signature."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def lemon_squeezy_webhook_secret() -> str:
    return _env("LEMON_SQUEEZY_WEBHOOK_SECRET")


def lemon_variant_coin_map() -> dict[str, int]:
    """Map Lemon Squeezy ``variant_id`` → coin amount.

    Prefer package env keys; fall back to a placeholder map you can edit.
    """
    mapping: dict[str, int] = {}

    # From TOPUP_PACKAGES when lemon_variant_id is set on the package.
    for pkg in TOPUP_PACKAGES.values():
        vid = str(pkg.get("lemon_variant_id") or "").strip()
        coins = int(pkg.get("coins") or 0)
        if vid and coins > 0:
            mapping[vid] = coins

    # Explicit env overrides (update these with real Lemon variant IDs).
    for env_key, coins in (
        ("LEMON_VARIANT_CREDITS_1000", 1000),
        ("LEMON_VARIANT_CREDITS_2200", 2200),
        ("LEMON_VARIANT_CREDITS_2500", 2200),
    ):
        vid = _env(env_key)
        if vid:
            mapping[vid] = int(coins)

    # Dummy placeholders so the webhook path is testable before real IDs exist.
    # Replace / override via LEMON_VARIANT_* env vars in production.
    mapping.setdefault("variant_1_id", 1000)
    mapping.setdefault("variant_2_id", 2200)
    return mapping


def ensure_lemon_squeezy_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS lemon_squeezy_payments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        TEXT NOT NULL UNIQUE,
            user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
            email           TEXT,
            variant_id      TEXT,
            package_id      TEXT,
            credits         INTEGER NOT NULL DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'Pending',
            payload_json    TEXT,
            paid_at         TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_lemon_squeezy_payments_user
            ON lemon_squeezy_payments(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_lemon_squeezy_payments_status
            ON lemon_squeezy_payments(status);
        """
    )


def verify_lemon_squeezy_signature(raw_body: bytes, signature_header: str | None) -> None:
    """Verify ``X-Signature`` = HMAC-SHA256(raw_body, webhook_secret)."""
    secret = lemon_squeezy_webhook_secret()
    if not secret:
        raise LemonSqueezySignatureError(
            "LEMON_SQUEEZY_WEBHOOK_SECRET is not configured"
        )
    provided = (signature_header or "").strip()
    if not provided:
        raise LemonSqueezySignatureError("Missing X-Signature header")

    digest = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(digest, provided):
        raise LemonSqueezySignatureError("Invalid Lemon Squeezy webhook signature")


def _dig(obj: Any, *path: str, default: Any = None) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def _parse_user_id(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        uid = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return uid if uid > 0 else None


def _lookup_user(user_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, email, name FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
    if not row:
        return None
    return {"id": int(row["id"]), "email": row["email"], "name": row["name"]}


def _credit_idempotent(
    conn: sqlite3.Connection,
    user_id: int,
    amount: int,
    *,
    ref_id: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Credit coins once per Lemon order id (ledger + unique index protection)."""
    amount = int(amount)
    if amount <= 0:
        raise LemonSqueezyGatewayError("credits must be positive")

    existing = conn.execute(
        "SELECT id FROM transactions "
        "WHERE ref_id = ? AND feature = 'topup' AND reference_type = 'LemonSqueezy' "
        "LIMIT 1",
        (ref_id,),
    ).fetchone()
    if existing is not None:
        row = conn.execute(
            "SELECT balance FROM wallets WHERE user_id = ?", (user_id,)
        ).fetchone()
        return {
            "id": int(existing["id"]),
            "balance": int(row["balance"]) if row else 0,
            "credits": 0,
            "already_credited": True,
        }

    delta = signed_credits(kind="credit", amount=amount)
    tx_type, _ = classify_transaction(kind="credit", feature="topup")
    reference_type = "LemonSqueezy"

    conn.execute(
        "INSERT OR IGNORE INTO wallets (user_id, balance) VALUES (?, 0)",
        (user_id,),
    )
    row = conn.execute(
        "SELECT balance FROM wallets WHERE user_id = ?", (user_id,)
    ).fetchone()
    balance_before = int(row["balance"]) if row else 0
    balance_after = balance_before + delta
    conn.execute(
        "UPDATE wallets SET balance = ?, updated_at = datetime('now') WHERE user_id = ?",
        (balance_after, user_id),
    )
    try:
        cur = conn.execute(
            "INSERT INTO transactions "
            "(user_id, kind, feature, amount, balance_before, balance_after, "
            " type, reference_type, status, ref_id, meta_json) "
            "VALUES (?, 'credit', 'topup', ?, ?, ?, ?, ?, 'completed', ?, ?)",
            (
                user_id,
                amount,
                balance_before,
                balance_after,
                tx_type,
                reference_type,
                ref_id,
                json.dumps(meta),
            ),
        )
    except sqlite3.IntegrityError:
        row = conn.execute(
            "SELECT balance FROM wallets WHERE user_id = ?", (user_id,)
        ).fetchone()
        return {
            "id": None,
            "balance": int(row["balance"]) if row else balance_before,
            "credits": 0,
            "already_credited": True,
        }

    return {
        "id": int(cur.lastrowid),
        "balance": balance_after,
        "credits": amount,
        "already_credited": False,
    }


def handle_webhook_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Fulfill a verified Lemon Squeezy webhook payload."""
    if not isinstance(payload, dict):
        raise LemonSqueezyGatewayError("payload must be a JSON object")

    event_name = str(_dig(payload, "meta", "event_name") or "").strip()
    if event_name != "order_created":
        logger.info("lemon-squeezy webhook ignored event=%s", event_name or "(empty)")
        return {
            "status": "ignored",
            "reason": "not_order_created",
            "event_name": event_name or None,
        }

    user_id = _parse_user_id(_dig(payload, "meta", "custom_data", "user_id"))
    if user_id is None:
        raise LemonSqueezyGatewayError("meta.custom_data.user_id is required")

    user = _lookup_user(user_id)
    if user is None:
        raise LemonSqueezyGatewayError(f"user_id={user_id} not found")

    variant_raw = _dig(
        payload, "data", "attributes", "first_order_item", "variant_id"
    )
    variant_id = str(variant_raw).strip() if variant_raw is not None else ""
    if not variant_id:
        raise LemonSqueezyGatewayError("first_order_item.variant_id is missing")

    coin_map = lemon_variant_coin_map()
    credits = coin_map.get(variant_id)
    if credits is None:
        # Also try int-as-str / str-as-int variants in map keys.
        credits = coin_map.get(str(int(variant_id))) if str(variant_id).isdigit() else None
    if credits is None or int(credits) <= 0:
        raise LemonSqueezyGatewayError(
            f"Unknown Lemon Squeezy variant_id={variant_id!r} "
            f"(known={sorted(coin_map.keys())})"
        )
    credits = int(credits)

    order_id = str(_dig(payload, "data", "id") or "").strip()
    if not order_id:
        # Fallback: attribute identifier / order_number for older payloads.
        order_id = str(
            _dig(payload, "data", "attributes", "identifier")
            or _dig(payload, "data", "attributes", "order_number")
            or ""
        ).strip()
    if not order_id:
        raise LemonSqueezyGatewayError("data.id (order id) is missing")

    ref_id = f"lemon:{order_id}"
    email = str(
        _dig(payload, "data", "attributes", "user_email")
        or user.get("email")
        or ""
    ).strip()

    with connect() as conn:
        ensure_lemon_squeezy_schema(conn)
        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute(
            "SELECT id, status, credits FROM lemon_squeezy_payments WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if existing is not None and str(existing["status"]) == STATUS_PAID:
            row = conn.execute(
                "SELECT balance FROM wallets WHERE user_id = ?", (user_id,)
            ).fetchone()
            return {
                "status": "success",
                "already_credited": True,
                "user_id": user_id,
                "order_id": order_id,
                "variant_id": variant_id,
                "credits": int(existing["credits"] or 0),
                "balance": int(row["balance"]) if row else 0,
            }

        credit_result = _credit_idempotent(
            conn,
            user_id,
            credits,
            ref_id=ref_id,
            meta={
                "provider": "lemon_squeezy",
                "order_id": order_id,
                "variant_id": variant_id,
                "event_name": event_name,
            },
        )

        conn.execute(
            """
            INSERT INTO lemon_squeezy_payments
                (order_id, user_id, email, variant_id, package_id, credits,
                 status, payload_json, paid_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(order_id) DO UPDATE SET
                user_id = excluded.user_id,
                email = excluded.email,
                variant_id = excluded.variant_id,
                credits = excluded.credits,
                status = excluded.status,
                payload_json = excluded.payload_json,
                paid_at = COALESCE(lemon_squeezy_payments.paid_at, excluded.paid_at)
            """,
            (
                order_id,
                user_id,
                email or None,
                variant_id,
                None,
                credits,
                STATUS_PAID,
                json.dumps(payload)[:100_000],
            ),
        )

    logger.info(
        "lemon-squeezy credited user_id=%s order_id=%s variant_id=%s credits=%s already=%s",
        user_id,
        order_id,
        variant_id,
        credits,
        credit_result.get("already_credited"),
    )
    return {
        "status": "success",
        "already_credited": bool(credit_result.get("already_credited")),
        "user_id": user_id,
        "order_id": order_id,
        "variant_id": variant_id,
        "credits": credits if not credit_result.get("already_credited") else 0,
        "balance": credit_result.get("balance"),
    }
