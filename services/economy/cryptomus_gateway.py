"""Cryptomus payment gateway — invoice create + signed webhook fulfillment.

Aligned with official docs: https://doc.cryptomus.com
-----------------------------------------------------
Creating invoice (POST /v1/payment):
  Headers: ``merchant`` (merchant UUID) + ``sign`` + ``Content-Type: application/json``
  Body: amount (string), currency, order_id (alpha_dash), optional url_*, additional_data
  Sign: MD5( base64( json_body ) + PAYMENT_API_KEY )
  json_body matches PHP json_encode (no spaces; escaped ``/``)

Webhook (POST to url_callback):
  Body JSON includes ``sign``; verify by unset(sign) then
  MD5( base64( json_encode(data, JSON_UNESCAPED_UNICODE) ) + API_KEY )
  with PHP-compatible slash escaping
  Source IP allowlist (docs): 91.227.144.54
  Successful payment: status in {paid, paid_over} AND is_final == true
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
from typing import Any

import requests

from .db import connect
from .ledger import classify_transaction, signed_credits
from .pricing import package as get_package

logger = logging.getLogger(__name__)

CRYPTOMUS_API_BASE = "https://api.cryptomus.com/v1"

STATUS_PENDING = "Pending"
STATUS_PAID = "Paid"
STATUS_FAILED = "Failed"
STATUS_EXPIRED = "Expired"

# Official successful payment statuses (docs webhook status list).
_SUCCESS_STATUSES = frozenset({"paid", "paid_over"})

# Cryptomus documents webhook source IP; override via CRYPTOMUS_WEBHOOK_IPS.
_DEFAULT_WEBHOOK_IPS = frozenset({"91.227.144.54"})

_ORDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class CryptomusGatewayError(Exception):
    """Checkout / webhook processing failure."""


class CryptomusSignatureError(CryptomusGatewayError):
    """Invalid or missing webhook / request signature."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def cryptomus_api_key() -> str:
    return _env("CRYPTOMUS_API_KEY")


def cryptomus_merchant_id() -> str:
    return _env("CRYPTOMUS_MERCHANT_ID")


def cryptomus_configured() -> bool:
    return bool(cryptomus_api_key() and cryptomus_merchant_id())


def webhook_ip_allowlist() -> frozenset[str] | None:
    """Return allowed webhook source IPs, or None to disable IP checks.

    Set ``CRYPTOMUS_WEBHOOK_IP_CHECK=0`` to disable.
    Set ``CRYPTOMUS_WEBHOOK_IPS=a,b,c`` to override the default allowlist.
    """
    flag = _env("CRYPTOMUS_WEBHOOK_IP_CHECK", "1").lower()
    if flag in ("0", "false", "no", "off"):
        return None
    raw = _env("CRYPTOMUS_WEBHOOK_IPS")
    if raw:
        return frozenset(p.strip() for p in raw.split(",") if p.strip())
    return _DEFAULT_WEBHOOK_IPS


def cryptomus_json_dumps(data: Any) -> str:
    """Match PHP ``json_encode($data, JSON_UNESCAPED_UNICODE)`` used in Cryptomus docs.

    - no spaces after separators (PHP default)
    - unescaped unicode
    - escaped forward slashes (PHP default; required for sign match)
    """
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("/", "\\/")


def cryptomus_sign(body: str | bytes, *, api_key: str | None = None) -> str:
    """MD5(base64(body) + api_key) — official Cryptomus request/webhook algorithm."""
    key = (api_key if api_key is not None else cryptomus_api_key()).strip()
    if not key:
        raise CryptomusSignatureError("CRYPTOMUS_API_KEY is not configured")
    if isinstance(body, bytes):
        body_bytes = body
    else:
        body_bytes = body.encode("utf-8")
    encoded = base64.b64encode(body_bytes).decode("ascii")
    return hashlib.md5((encoded + key).encode("utf-8")).hexdigest()


def parse_webhook_payload(raw_body: bytes | str) -> dict[str, Any]:
    """Decode webhook body like PHP ``json_decode(file_get_contents('php://input'), true)``."""
    if isinstance(raw_body, bytes):
        text = raw_body.decode("utf-8")
    else:
        text = raw_body
    try:
        payload = json.loads(text)
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise CryptomusGatewayError("invalid_json") from exc
    if not isinstance(payload, dict):
        raise CryptomusGatewayError("invalid_json")
    return payload


def verify_cryptomus_webhook(
    payload: dict[str, Any],
    *,
    api_key: str | None = None,
) -> None:
    """Verify webhook ``sign`` exactly per Cryptomus docs."""
    if not isinstance(payload, dict):
        raise CryptomusSignatureError("Webhook payload must be a JSON object")
    received = str(payload.get("sign") or "").strip()
    if not received:
        raise CryptomusSignatureError("Missing webhook sign")

    # Preserve insertion order from json.loads (Python 3.7+), drop sign.
    data = {k: v for k, v in payload.items() if k != "sign"}
    body = cryptomus_json_dumps(data)
    expected = cryptomus_sign(body, api_key=api_key)
    try:
        ok = hmac.compare_digest(expected, received)
    except (TypeError, ValueError):
        ok = False
    if not ok:
        raise CryptomusSignatureError("Invalid webhook signature")


def assert_webhook_source_ip(remote_addr: str | None) -> None:
    """Enforce Cryptomus webhook IP allowlist (docs: 91.227.144.54)."""
    allow = webhook_ip_allowlist()
    if allow is None:
        return
    ip = (remote_addr or "").strip()
    if not ip or ip not in allow:
        raise CryptomusSignatureError(f"Webhook source IP not allowed: {ip or 'unknown'}")


def _row_to_payment(row: sqlite3.Row) -> dict[str, Any]:
    keys = set(row.keys())
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "order_id": row["order_id"],
        "cryptomus_uuid": row["cryptomus_uuid"],
        "amount": float(row["amount"]),
        "currency": row["currency"] or "USD",
        "credits": int(row["credits"]),
        "package_id": row["package_id"],
        "status": row["status"],
        "txid": row["txid"] if "txid" in keys else None,
        "created_at": row["created_at"],
        "paid_at": row["paid_at"] if "paid_at" in keys else None,
    }


def _safe_package_public(pkg: dict[str, Any]) -> dict[str, Any]:
    """Public subset — never expose provider secrets/price ids unnecessarily."""
    return {
        "id": pkg["id"],
        "name": pkg.get("name"),
        "usd": float(pkg["usd"]),
        "coins": int(pkg["coins"]),
        "featured": bool(pkg.get("featured")),
    }


def _new_order_id(user_id: int) -> str:
    # Docs: alpha_dash, min 1, max 128.
    order_id = f"dm_{int(user_id)}_{secrets.token_hex(16)}"
    if not _ORDER_ID_RE.match(order_id):
        raise CryptomusGatewayError("Generated order_id failed Cryptomus alpha_dash rules")
    return order_id


def _clamp_url(value: str, *, field: str) -> str | None:
    """Docs: url_* min 6, max 255."""
    url = (value or "").strip()
    if not url:
        return None
    if len(url) < 6 or len(url) > 255:
        raise CryptomusGatewayError(f"{field} must be 6–255 characters per Cryptomus docs")
    if not (url.startswith("https://") or url.startswith("http://")):
        raise CryptomusGatewayError(f"{field} must be a valid http(s) URL")
    return url


def _callback_urls() -> dict[str, str]:
    """Callback URLs from env only — never from the client request."""
    base = _env("PUBLIC_BASE_URL", "https://docmaxxing.com").rstrip("/")
    out: dict[str, str] = {}
    cb = _clamp_url(
        _env("CRYPTOMUS_URL_CALLBACK") or f"{base}/api/payments/cryptomus/webhook",
        field="url_callback",
    )
    ret = _clamp_url(
        _env("CRYPTOMUS_URL_RETURN") or f"{base}/pricing",
        field="url_return",
    )
    ok = _clamp_url(
        _env("CRYPTOMUS_URL_SUCCESS") or f"{base}/pricing?paid=1",
        field="url_success",
    )
    if cb:
        out["url_callback"] = cb
    if ret:
        out["url_return"] = ret
    if ok:
        out["url_success"] = ok
    return out


def _invoice_lifetime() -> int | None:
    """Optional lifetime (docs: 300–43200, default 3600 if omitted)."""
    raw = _env("CRYPTOMUS_INVOICE_LIFETIME")
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise CryptomusGatewayError("CRYPTOMUS_INVOICE_LIFETIME must be an integer") from exc
    if value < 300 or value > 43200:
        raise CryptomusGatewayError("CRYPTOMUS_INVOICE_LIFETIME must be 300–43200")
    return value


def create_invoice(*, user_id: int, package_id: str) -> dict[str, Any]:
    """Create a Cryptomus invoice (POST /v1/payment) for a TOPUP package.

    Amount and credits are taken exclusively from the server package catalog.
    """
    if not cryptomus_configured():
        raise CryptomusGatewayError(
            "Cryptomus is not configured (set CRYPTOMUS_API_KEY and CRYPTOMUS_MERCHANT_ID)"
        )

    pkg = get_package(package_id)
    if pkg is None:
        raise CryptomusGatewayError(f"Unknown package: {package_id}")

    user_id = int(user_id)
    if user_id <= 0:
        raise CryptomusGatewayError("user_id is required")

    order_id = _new_order_id(user_id)
    amount_usd = float(pkg["usd"])
    if amount_usd <= 0:
        raise CryptomusGatewayError("Package amount must be positive")
    credits = int(pkg["coins"])
    if credits <= 0:
        raise CryptomusGatewayError("Package credits must be positive")

    # Docs: amount is a string; pennies use '.' (example: 10.28).
    amount = f"{amount_usd:.2f}"
    currency = "USD"

    # Docs: additional_data string max 255 — informational only.
    additional_data = f"user:{user_id};package:{pkg['id']}"[:255]

    payload: dict[str, Any] = {
        "amount": amount,
        "currency": currency,
        "order_id": order_id,
        "additional_data": additional_data,
    }
    payload.update(_callback_urls())
    lifetime = _invoice_lifetime()
    if lifetime is not None:
        payload["lifetime"] = lifetime

    body = cryptomus_json_dumps(payload)
    sign = cryptomus_sign(body)
    merchant = cryptomus_merchant_id()

    try:
        res = requests.post(
            f"{CRYPTOMUS_API_BASE}/payment",
            headers={
                # Payment API uses ``merchant`` (not userId) — creating-invoice docs.
                "merchant": merchant,
                "sign": sign,
                "Content-Type": "application/json",
            },
            data=body.encode("utf-8"),
            timeout=30,
        )
    except requests.RequestException as exc:
        raise CryptomusGatewayError(f"Cryptomus API request failed: {exc}") from exc

    if res.status_code >= 400:
        detail = res.text[:500]
        try:
            detail = json.dumps(res.json())[:500]
        except (ValueError, TypeError):
            pass
        raise CryptomusGatewayError(f"Cryptomus API error {res.status_code}: {detail}")

    try:
        response = res.json()
    except (ValueError, TypeError) as exc:
        raise CryptomusGatewayError(
            f"Cryptomus API returned non-JSON: {res.text[:300]}"
        ) from exc

    # Success envelope: {"state": 0, "result": {...}}
    if response.get("state") not in (0, "0"):
        detail = response.get("message") or response.get("errors") or response
        raise CryptomusGatewayError(f"Cryptomus API error: {detail}")

    result = response.get("result") or {}
    if not isinstance(result, dict):
        raise CryptomusGatewayError("Cryptomus response missing result")

    payment_url = str(result.get("url") or "").strip() or None
    cryptomus_uuid = str(result.get("uuid") or "").strip() or None
    if not payment_url:
        raise CryptomusGatewayError("Cryptomus response missing payment url")

    with connect() as conn:
        try:
            conn.execute(
                "INSERT INTO cryptomus_payments "
                "(user_id, order_id, cryptomus_uuid, amount, currency, credits, "
                " package_id, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    order_id,
                    cryptomus_uuid,
                    amount_usd,
                    currency,
                    credits,
                    str(pkg["id"]),
                    STATUS_PENDING,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise CryptomusGatewayError(f"Duplicate order_id: {order_id}") from exc

        row = conn.execute(
            "SELECT * FROM cryptomus_payments WHERE order_id = ?", (order_id,)
        ).fetchone()

    logger.info(
        "cryptomus invoice created order_id=%s uuid=%s user_id=%s package=%s credits=%s",
        order_id,
        cryptomus_uuid,
        user_id,
        pkg["id"],
        credits,
    )

    return {
        "order_id": order_id,
        "payment_url": payment_url,
        "cryptomus_uuid": cryptomus_uuid,
        "amount": amount_usd,
        "currency": currency,
        "credits": credits,
        "package": _safe_package_public(pkg),
        "payment": _row_to_payment(row),
    }


def _credit_on_conn(
    conn: sqlite3.Connection,
    user_id: int,
    amount: int,
    *,
    ref_id: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    amount = int(amount)
    if amount <= 0:
        raise CryptomusGatewayError("credits must be positive")

    existing = conn.execute(
        "SELECT id FROM transactions "
        "WHERE ref_id = ? AND feature = 'topup' AND reference_type = 'Cryptomus' "
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
    tx_type, _legacy_ref = classify_transaction(kind="credit", feature="topup")
    reference_type = "Cryptomus"

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
        "id": cur.lastrowid,
        "balance": balance_after,
        "credits": amount,
        "already_credited": False,
    }


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in ("1", "true", "yes", "y")


def fulfill_paid_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Idempotently mark payment Paid and credit the wallet.

    Credits come from the Pending payment row (server catalog snapshot).
    Webhook amount fields are never used for credit amounts.
    """
    order_id = str(payload.get("order_id") or "").strip()
    if not order_id:
        raise CryptomusGatewayError("Webhook missing order_id")

    status = str(payload.get("status") or "").strip().lower()
    is_final = _as_bool(payload.get("is_final"))

    # Docs: is_final means invoice cannot be paid further (paid or expired).
    # Successful money-received statuses: paid, paid_over.
    if status not in _SUCCESS_STATUSES or not is_final:
        logger.info(
            "cryptomus webhook ignored order_id=%s status=%s is_final=%s",
            order_id,
            status,
            is_final,
        )
        return {
            "handled": False,
            "ignored": True,
            "order_id": order_id,
            "status": status,
            "is_final": is_final,
        }

    cryptomus_uuid = str(payload.get("uuid") or "").strip() or None
    txid = str(payload.get("txid") or "").strip() or None

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM cryptomus_payments WHERE order_id = ?", (order_id,)
        ).fetchone()
        if row is None:
            raise CryptomusGatewayError(f"Unknown order_id: {order_id}")

        if row["status"] == STATUS_PAID:
            return {
                "handled": True,
                "already_credited": True,
                "order_id": order_id,
                "payment": _row_to_payment(row),
                "credits_added": 0,
                "balance": None,
            }

        if row["status"] != STATUS_PENDING:
            logger.warning(
                "cryptomus webhook refused order_id=%s status=%s (expected Pending)",
                order_id,
                row["status"],
            )
            return {
                "handled": False,
                "ignored": True,
                "order_id": order_id,
                "payment": _row_to_payment(row),
                "credits_added": 0,
                "balance": None,
            }

        user_id = int(row["user_id"])
        credits = int(row["credits"])
        package_id = row["package_id"]
        amount = float(row["amount"])
        if credits <= 0:
            raise CryptomusGatewayError("Payment row has invalid credits")

        cur = conn.execute(
            "UPDATE cryptomus_payments SET status = ?, "
            "cryptomus_uuid = COALESCE(?, cryptomus_uuid), "
            "txid = COALESCE(?, txid), paid_at = datetime('now') "
            "WHERE id = ? AND status = ?",
            (
                STATUS_PAID,
                cryptomus_uuid,
                txid,
                int(row["id"]),
                STATUS_PENDING,
            ),
        )
        if cur.rowcount != 1:
            fresh = conn.execute(
                "SELECT * FROM cryptomus_payments WHERE order_id = ?", (order_id,)
            ).fetchone()
            return {
                "handled": True,
                "already_credited": True,
                "order_id": order_id,
                "payment": _row_to_payment(fresh) if fresh else _row_to_payment(row),
                "credits_added": 0,
                "balance": None,
            }

        credit_meta = {
            "package": package_id,
            "usd": amount,
            "currency": row["currency"] or "USD",
            "cryptomus_order_id": order_id,
            "cryptomus_uuid": cryptomus_uuid,
            "txid": txid,
            "cryptomus_status": status,
            "cryptomus_payment_id": int(row["id"]),
        }
        credit_result = _credit_on_conn(
            conn,
            user_id,
            credits,
            ref_id=order_id,
            meta=credit_meta,
        )
        if credit_result.get("already_credited"):
            fresh = conn.execute(
                "SELECT * FROM cryptomus_payments WHERE id = ?", (int(row["id"]),)
            ).fetchone()
            return {
                "handled": True,
                "already_credited": True,
                "order_id": order_id,
                "payment": _row_to_payment(fresh) if fresh else _row_to_payment(row),
                "credits_added": 0,
                "balance": credit_result.get("balance"),
            }

        fresh = conn.execute(
            "SELECT * FROM cryptomus_payments WHERE id = ?", (int(row["id"]),)
        ).fetchone()
        payment = _row_to_payment(fresh)

    logger.info(
        "cryptomus paid order_id=%s user_id=%s credits=%s uuid=%s status=%s",
        order_id,
        user_id,
        credits,
        cryptomus_uuid,
        status,
    )
    try:
        from .referral import on_successful_deposit

        on_successful_deposit(
            user_id,
            float(amount),
            payment_ref=f"cryptomus:{order_id}",
        )
    except Exception:
        logger.exception(
            "referral on_successful_deposit failed user_id=%s order_id=%s",
            user_id,
            order_id,
        )
    return {
        "handled": True,
        "already_credited": False,
        "order_id": order_id,
        "payment": payment,
        "credits_added": credits,
        "balance": credit_result["balance"],
    }


def handle_webhook(
    payload: dict[str, Any],
    *,
    remote_addr: str | None = None,
) -> dict[str, Any]:
    """Verify source IP (optional) + signature, then fulfill."""
    assert_webhook_source_ip(remote_addr)
    verify_cryptomus_webhook(payload)
    return fulfill_paid_webhook(payload)


def get_payment_by_order_id(order_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM cryptomus_payments WHERE order_id = ?",
            ((order_id or "").strip(),),
        ).fetchone()
    return _row_to_payment(row) if row else None
