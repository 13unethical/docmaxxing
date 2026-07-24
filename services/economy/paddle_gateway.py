"""Paddle Billing checkout + idempotent webhook fulfillment.

Purchase flow
-------------
1. User clicks Buy → POST /api/economy/checkout {package}
2. Backend resolves package → price_id, creates a Paddle transaction
3. Returns checkout_url (+ transaction_id for Overlay)

Webhook flow (transaction.completed)
------------------------------------
1. Verify Paddle-Signature (HMAC-SHA256 over ``ts:raw_body``)
2. If txn already Paid → 200 (idempotent)
3. Re-fetch transaction from Paddle API; verify status + price_id
4. Map price_id → credits from server catalog (never custom_data.credits)
5. BEGIN IMMEDIATE → Purchase Paid + wallet + ledger → COMMIT → 200
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from typing import Any

import requests

from .db import connect
from .ledger import classify_transaction, signed_credits
from .paddle_purchases import STATUS_FAILED, STATUS_PAID, STATUS_PENDING, _row_to_purchase
from .pricing import package as get_package

logger = logging.getLogger(__name__)

PADDLE_API_BASE_LIVE = "https://api.paddle.com"
PADDLE_API_BASE_SANDBOX = "https://sandbox-api.paddle.com"

# Reject webhook signatures older than this (replay protection).
_SIGNATURE_MAX_AGE_SEC = 300

# Statuses that mean payment succeeded and credits may be granted.
_PAID_STATUSES = frozenset({"completed"})


class PaddleGatewayError(Exception):
    """Raised when checkout / webhook processing fails."""


class PaddleSignatureError(PaddleGatewayError):
    """Invalid or missing webhook signature."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def paddle_configured() -> bool:
    return bool(_env("PADDLE_API_KEY"))


def paddle_environment() -> str:
    env = _env("PADDLE_ENVIRONMENT", "sandbox").lower()
    return "production" if env in ("live", "production", "prod") else "sandbox"


def paddle_api_base() -> str:
    if paddle_environment() == "production":
        return PADDLE_API_BASE_LIVE
    return PADDLE_API_BASE_SANDBOX


def paddle_client_token() -> str:
    return _env("PADDLE_CLIENT_TOKEN")


def paddle_webhook_secret() -> str:
    return _env("PADDLE_WEBHOOK_SECRET")


def mock_topup_allowed() -> bool:
    """Mock top-up never in live/production; sandbox only with explicit flag."""
    if paddle_environment() == "production":
        return False
    return _env("PADDLE_ALLOW_MOCK_TOPUP", "0") in ("1", "true", "yes")


def package_for_price_id(price_id: str) -> dict[str, Any] | None:
    """Map a Paddle ``pri_…`` id back to a TOPUP package."""
    price_id = (price_id or "").strip()
    if not price_id:
        return None
    from .pricing import TOPUP_PACKAGES

    for pkg in TOPUP_PACKAGES.values():
        if (pkg.get("price_id") or "").strip() == price_id:
            return pkg
    return None


def verify_paddle_signature(
    raw_body: bytes | str,
    signature_header: str | None,
    *,
    secret: str | None = None,
    max_age_sec: int = _SIGNATURE_MAX_AGE_SEC,
    now: float | None = None,
) -> None:
    """Verify ``Paddle-Signature: ts=…;h1=…`` (HMAC-SHA256 of ``ts:body``)."""
    secret = (secret if secret is not None else paddle_webhook_secret()).strip()
    if not secret:
        raise PaddleSignatureError("PADDLE_WEBHOOK_SECRET is not configured")
    if not signature_header:
        raise PaddleSignatureError("Missing Paddle-Signature header")

    parts: dict[str, str] = {}
    for chunk in signature_header.split(";"):
        chunk = chunk.strip()
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        parts[key.strip()] = value.strip()

    ts = parts.get("ts")
    h1 = parts.get("h1")
    if not ts or not h1:
        raise PaddleSignatureError("Malformed Paddle-Signature header")

    try:
        ts_int = int(ts)
    except ValueError as exc:
        raise PaddleSignatureError("Invalid signature timestamp") from exc

    age = abs((now if now is not None else time.time()) - ts_int)
    if max_age_sec > 0 and age > max_age_sec:
        raise PaddleSignatureError("Signature timestamp too old")

    if isinstance(raw_body, bytes):
        body_str = raw_body.decode("utf-8")
    else:
        body_str = raw_body

    signed_payload = f"{ts}:{body_str}".encode("utf-8")
    expected = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, h1):
        raise PaddleSignatureError("Invalid webhook signature")


def create_checkout(
    *,
    user_id: int,
    package_id: str,
    customer_email: str | None = None,
) -> dict[str, Any]:
    """Create a Paddle transaction for a credit package and return checkout info."""
    if not paddle_configured():
        raise PaddleGatewayError("Paddle is not configured (missing PADDLE_API_KEY)")

    pkg = get_package(package_id)
    if pkg is None:
        raise PaddleGatewayError(f"Unknown package: {package_id}")

    price_id = (pkg.get("price_id") or "").strip()
    if not price_id:
        raise PaddleGatewayError(
            f"Package {pkg['id']!r} has no Paddle price_id "
            f"(set PADDLE_PRICE_{pkg['id'].upper()} in env)"
        )

    body: dict[str, Any] = {
        "items": [{"price_id": price_id, "quantity": 1}],
        "custom_data": {
            "user_id": str(int(user_id)),
            "package_id": str(pkg["id"]),
            "credits": str(int(pkg["coins"])),
        },
    }
    if customer_email:
        body["customer"] = {"email": customer_email}

    api_key = _env("PADDLE_API_KEY")
    try:
        res = requests.post(
            f"{paddle_api_base()}/transactions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise PaddleGatewayError(f"Paddle API request failed: {exc}") from exc

    if res.status_code >= 400:
        detail = res.text[:500]
        try:
            detail = json.dumps(res.json())[:500]
        except (ValueError, TypeError):
            pass
        raise PaddleGatewayError(f"Paddle API error {res.status_code}: {detail}")

    payload = res.json()
    data = payload.get("data") or {}
    transaction_id = (data.get("id") or "").strip()
    checkout = data.get("checkout") or {}
    checkout_url = (checkout.get("url") or "").strip() or None

    if not transaction_id:
        raise PaddleGatewayError("Paddle response missing transaction id")

    # Record Pending purchase so admin can see open checkouts; webhook flips to Paid.
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM paddle_purchases WHERE paddle_transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        if existing is None:
            try:
                conn.execute(
                    "INSERT INTO paddle_purchases "
                    "(user_id, paddle_transaction_id, product_id, price_id, "
                    " credits, amount, currency, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        int(user_id),
                        transaction_id,
                        str(pkg["id"]),
                        price_id,
                        int(pkg["coins"]),
                        float(pkg["usd"]),
                        "USD",
                        STATUS_PENDING,
                    ),
                )
            except sqlite3.IntegrityError:
                pass  # concurrent create — fine

    return {
        "transaction_id": transaction_id,
        "checkout_url": checkout_url,
        "price_id": price_id,
        "package": pkg,
        "client_token": paddle_client_token() or None,
        "environment": paddle_environment(),
    }


def fetch_paddle_transaction(transaction_id: str) -> dict[str, Any]:
    """GET /transactions/{id} — authoritative status and line items."""
    transaction_id = (transaction_id or "").strip()
    if not transaction_id:
        raise PaddleGatewayError("transaction_id is required")
    if not paddle_configured():
        raise PaddleGatewayError("Paddle is not configured (missing PADDLE_API_KEY)")

    api_key = _env("PADDLE_API_KEY")
    try:
        res = requests.get(
            f"{paddle_api_base()}/transactions/{transaction_id}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise PaddleGatewayError(f"Paddle API request failed: {exc}") from exc

    if res.status_code >= 400:
        detail = res.text[:500]
        try:
            detail = json.dumps(res.json())[:500]
        except (ValueError, TypeError):
            pass
        raise PaddleGatewayError(f"Paddle API error {res.status_code}: {detail}")

    payload = res.json()
    data = payload.get("data")
    if not isinstance(data, dict) or not data.get("id"):
        raise PaddleGatewayError("Paddle transaction response missing data")
    return data


def _price_id_from_transaction(data: dict[str, Any]) -> str:
    items = data.get("items") or []
    if items and isinstance(items[0], dict):
        price = items[0].get("price") or {}
        if isinstance(price, dict):
            pid = str(price.get("id") or "").strip()
            if pid:
                return pid
        pid = str(items[0].get("price_id") or "").strip()
        if pid:
            return pid
    return ""


def _credit_on_conn(
    conn: sqlite3.Connection,
    user_id: int,
    amount: int,
    *,
    ref_id: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Credit wallet + ledger on an already-open connection (same DB txn)."""
    amount = int(amount)
    if amount <= 0:
        raise PaddleGatewayError("credits must be positive")
    delta = signed_credits(kind="credit", amount=amount)
    tx_type, reference_type = classify_transaction(kind="credit", feature="topup")

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
    return {
        "id": cur.lastrowid,
        "balance": balance_after,
        "credits": amount,
    }


def apply_paid_purchase_atomic(
    *,
    user_id: int,
    paddle_transaction_id: str,
    product_id: str,
    price_id: str,
    credits: int,
    amount: float,
    currency: str = "USD",
    country: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert/update Paid purchase + wallet credit + ledger in one SQLite txn."""
    paddle_transaction_id = (paddle_transaction_id or "").strip()
    if not paddle_transaction_id:
        raise PaddleGatewayError("paddle_transaction_id is required")
    user_id = int(user_id)
    credits = int(credits)
    if user_id <= 0:
        raise PaddleGatewayError("user_id is required")
    if credits <= 0:
        raise PaddleGatewayError("credits must be positive")
    country_code = (country or "").strip().upper() or None

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute(
            "SELECT * FROM paddle_purchases WHERE paddle_transaction_id = ?",
            (paddle_transaction_id,),
        ).fetchone()

        if existing is not None and existing["status"] == STATUS_PAID:
            return {
                "already_credited": True,
                "purchase": _row_to_purchase(existing),
                "balance": None,
                "credits_added": 0,
            }

        purchase_id: int
        if existing is None:
            try:
                cur = conn.execute(
                    "INSERT INTO paddle_purchases "
                    "(user_id, paddle_transaction_id, product_id, price_id, "
                    " credits, amount, currency, status, country) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        user_id,
                        paddle_transaction_id,
                        (product_id or "").strip() or None,
                        (price_id or "").strip() or None,
                        credits,
                        float(amount),
                        (currency or "USD").strip().upper() or "USD",
                        STATUS_PAID,
                        country_code,
                    ),
                )
                purchase_id = int(cur.lastrowid)
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT * FROM paddle_purchases WHERE paddle_transaction_id = ?",
                    (paddle_transaction_id,),
                ).fetchone()
                if row is not None and row["status"] == STATUS_PAID:
                    return {
                        "already_credited": True,
                        "purchase": _row_to_purchase(row),
                        "balance": None,
                        "credits_added": 0,
                    }
                raise PaddleGatewayError(
                    f"Purchase race for {paddle_transaction_id}; retry"
                )
        else:
            if int(existing["user_id"]) != user_id:
                raise PaddleGatewayError("Purchase user_id mismatch")
            conn.execute(
                "UPDATE paddle_purchases SET status = ?, product_id = ?, price_id = ?, "
                "credits = ?, amount = ?, currency = ?, "
                "country = COALESCE(?, country) WHERE id = ?",
                (
                    STATUS_PAID,
                    (product_id or "").strip() or None,
                    (price_id or "").strip() or None,
                    credits,
                    float(amount),
                    (currency or "USD").strip().upper() or "USD",
                    country_code,
                    int(existing["id"]),
                ),
            )
            purchase_id = int(existing["id"])

        credit_meta = {
            "package": product_id,
            "price_id": price_id,
            "usd": float(amount),
            "currency": (currency or "USD").strip().upper() or "USD",
            "paddle_purchase_id": purchase_id,
            "paddle_transaction_id": paddle_transaction_id,
            **(meta or {}),
        }
        credit_result = _credit_on_conn(
            conn,
            user_id,
            credits,
            ref_id=paddle_transaction_id,
            meta=credit_meta,
        )

        row = conn.execute(
            "SELECT * FROM paddle_purchases WHERE id = ?", (purchase_id,)
        ).fetchone()

    return {
        "already_credited": False,
        "purchase": _row_to_purchase(row),
        "balance": credit_result["balance"],
        "credits_added": credits,
    }


def _extract_country(data: dict[str, Any]) -> str | None:
    """Best-effort ISO country from a Paddle transaction payload."""
    for key in ("address", "billing_details"):
        block = data.get(key)
        if isinstance(block, dict):
            code = (block.get("country_code") or block.get("country") or "").strip()
            if code:
                return code.upper()
    customer = data.get("customer")
    if isinstance(customer, dict):
        code = (customer.get("country_code") or "").strip()
        if code:
            return code.upper()
    return None


def fulfill_transaction_completed(data: dict[str, Any]) -> dict[str, Any]:
    """Idempotently grant credits after API re-fetch + catalog price_id mapping."""
    transaction_id = str(data.get("id") or "").strip()
    if not transaction_id:
        raise PaddleGatewayError("Webhook data missing transaction id")

    # Fast idempotent path — no API call if already Paid.
    existing = None
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM paddle_purchases WHERE paddle_transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        if existing is not None and existing["status"] == STATUS_PAID:
            return {
                "already_credited": True,
                "purchase": _row_to_purchase(existing),
                "balance": None,
                "credits_added": 0,
            }
        # Materialize fields we need after the connection closes.
        existing_user_id = int(existing["user_id"]) if existing is not None else 0

    verified = fetch_paddle_transaction(transaction_id)
    status = str(verified.get("status") or "").strip().lower()
    if status not in _PAID_STATUSES:
        raise PaddleGatewayError(
            f"Transaction {transaction_id} status is {status!r}, expected completed"
        )

    price_id = _price_id_from_transaction(verified)
    if not price_id:
        raise PaddleGatewayError(
            f"Transaction {transaction_id} has no price_id on line items"
        )

    pkg = package_for_price_id(price_id)
    if pkg is None:
        raise PaddleGatewayError(f"Unknown Paddle price_id: {price_id}")

    credits = int(pkg["coins"])
    package_id = str(pkg["id"])
    amount_usd = float(pkg["usd"])
    currency = str(verified.get("currency_code") or "USD").upper() or "USD"

    totals = verified.get("details") or {}
    if isinstance(totals, dict):
        totals = totals.get("totals") or {}
    if isinstance(totals, dict) and totals.get("grand_total") is not None:
        try:
            amount_usd = int(totals["grand_total"]) / 100.0
        except (TypeError, ValueError):
            amount_usd = float(pkg["usd"])

    custom = verified.get("custom_data") or data.get("custom_data") or {}
    if not isinstance(custom, dict):
        custom = {}

    user_id = existing_user_id
    if user_id <= 0:
        try:
            user_id = int(custom.get("user_id") or 0)
        except (TypeError, ValueError):
            user_id = 0

    if user_id <= 0:
        raise PaddleGatewayError(
            "Cannot fulfill: missing user_id (custom_data / pending purchase)"
        )

    country = _extract_country(verified) or _extract_country(data)

    return apply_paid_purchase_atomic(
        user_id=user_id,
        paddle_transaction_id=transaction_id,
        product_id=package_id,
        price_id=price_id,
        credits=credits,
        amount=amount_usd,
        currency=currency,
        country=country,
    )


def handle_webhook_event(event: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a verified Paddle webhook event."""
    event_type = str(event.get("event_type") or event.get("eventType") or "").strip()
    data = event.get("data") or {}

    if event_type == "transaction.completed":
        result = fulfill_transaction_completed(data)
        logger.info(
            "paddle webhook fulfilled txn=%s already=%s",
            (data.get("id") if isinstance(data, dict) else None),
            result.get("already_credited"),
        )
        return {"handled": True, "event_type": event_type, **result}

    if event_type in (
        "transaction.payment_failed",
        "transaction.canceled",
    ):
        txn_id = str((data or {}).get("id") or "").strip()
        if txn_id:
            with connect() as conn:
                conn.execute(
                    "UPDATE paddle_purchases SET status = ? "
                    "WHERE paddle_transaction_id = ? AND status = ?",
                    (STATUS_FAILED, txn_id, STATUS_PENDING),
                )
        return {"handled": True, "event_type": event_type, "ignored_credits": True}

    return {"handled": False, "event_type": event_type}
