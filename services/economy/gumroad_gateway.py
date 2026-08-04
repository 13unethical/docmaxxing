"""Gumroad Ping webhook — form-urlencoded sale notifications → credit top-ups.

Docs: https://gumroad.com/ping
Gumroad POSTs ``application/x-www-form-urlencoded`` with sale fields.
Custom checkout URL params (e.g. ``?user_id=42``) arrive as ``url_params[user_id]``.

Fulfillment is idempotent on ``sale_id``. The HTTP route always acknowledges
with ``200 OK`` so Gumroad does not retry forever.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Mapping

from .db import connect
from .ledger import classify_transaction, signed_credits
from .pricing import TOPUP_PACKAGES, package as get_package

logger = logging.getLogger(__name__)

STATUS_PAID = "Paid"
STATUS_IGNORED = "Ignored"


class GumroadGatewayError(Exception):
    """Ping processing failure (logged; route still returns 200)."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def gumroad_ping_secret() -> str:
    """Shared secret compared to Gumroad ping ``seller_id`` (or ``token``)."""
    return _env("GUMROAD_PING_SECRET")


def gumroad_product_map() -> dict[str, str]:
    """Map Gumroad short_product_id / permalink → internal package id.

    Built from ``GUMROAD_PRODUCT_CREDITS_1000`` / ``_2200`` (or legacy ``_2500``)
    env vars and any ``gumroad_product_id`` fields on TOPUP_PACKAGES.
    """
    mapping: dict[str, str] = {}
    for pkg_id, pkg in TOPUP_PACKAGES.items():
        gum_id = str(pkg.get("gumroad_product_id") or "").strip()
        if gum_id:
            mapping[gum_id.lower()] = pkg_id
    # Explicit env keys (also already loaded into packages via pricing.py)
    for env_key, pkg_id in (
        ("GUMROAD_PRODUCT_CREDITS_1000", "credits_1000"),
        ("GUMROAD_PRODUCT_CREDITS_2200", "credits_2500"),
        ("GUMROAD_PRODUCT_CREDITS_2500", "credits_2500"),
    ):
        gum_id = _env(env_key)
        if gum_id:
            mapping[gum_id.lower()] = pkg_id
    return mapping


def gumroad_configured() -> bool:
    """True when at least one package has a Gumroad product id mapped."""
    return bool(gumroad_product_map()) or bool(gumroad_ping_secret())


def ensure_gumroad_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gumroad_payments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id         TEXT NOT NULL UNIQUE,
            user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
            email           TEXT,
            product_id      TEXT,
            short_product_id TEXT,
            package_id      TEXT,
            price_cents     INTEGER NOT NULL DEFAULT 0,
            credits         INTEGER NOT NULL DEFAULT 0,
            currency        TEXT NOT NULL DEFAULT 'usd',
            status          TEXT NOT NULL DEFAULT 'Paid',
            payload_json    TEXT,
            paid_at         TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_gumroad_payments_user
            ON gumroad_payments(user_id, created_at DESC);
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_gumroad_topup_ref "
        "ON transactions(ref_id) "
        "WHERE reference_type = 'Gumroad' AND feature = 'topup' "
        "AND ref_id IS NOT NULL"
    )


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in ("1", "true", "yes", "y")


def _form_get(form: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        if key in form and form.get(key) is not None:
            val = form.get(key)
            if isinstance(val, (list, tuple)):
                val = val[0] if val else ""
            text = str(val).strip()
            if text:
                return text
    return ""


def extract_url_params(form: Mapping[str, Any]) -> dict[str, str]:
    """Parse Gumroad ``url_params[key]`` / ``custom_fields[key]`` form keys."""
    out: dict[str, str] = {}
    for raw_key in form.keys():
        key = str(raw_key)
        for prefix in ("url_params[", "custom_fields[", "custom_field["):
            if key.startswith(prefix) and key.endswith("]"):
                name = key[len(prefix) : -1].strip().lower()
                if not name:
                    continue
                val = _form_get(form, key)
                if val:
                    out[name] = val
    # Flat aliases Gumroad sometimes flattens
    for alias in ("user_id", "userid", "uid", "account_id"):
        if alias not in out:
            flat = _form_get(form, alias, f"url_params.{alias}")
            if flat:
                out[alias] = flat
    return out


def extract_user_id(form: Mapping[str, Any]) -> int | None:
    params = extract_url_params(form)
    for key in ("user_id", "userid", "uid", "account_id", "docmaxxing_user_id"):
        raw = params.get(key) or _form_get(form, key)
        if not raw:
            continue
        try:
            uid = int(str(raw).strip())
        except (TypeError, ValueError):
            continue
        if uid > 0:
            return uid
    return None


def resolve_package_id(form: Mapping[str, Any]) -> str | None:
    """Map Gumroad ``short_product_id`` / permalink onto TOPUP_PACKAGES ids.

    Prefers exact match against ``GUMROAD_PRODUCT_CREDITS_*`` (e.g. ``1000``, ``2200``).
    """
    product_map = gumroad_product_map()
    candidates = [
        _form_get(form, "short_product_id"),
        _form_get(form, "permalink"),
        _form_get(form, "product_permalink"),
        _form_get(form, "product_id"),
        _form_get(form, "product_name"),
    ]
    for cand in candidates:
        c = cand.strip().lower()
        if not c:
            continue
        if c in product_map:
            return product_map[c]
        # Permalinks may be full URLs ending in /l/1000
        for gum_id, pkg_id in product_map.items():
            if c.endswith("/" + gum_id) or c.endswith("/l/" + gum_id) or c == gum_id:
                return pkg_id
    # Fallback: internal package ids (credits_1000) if Gumroad sends those
    for cand in candidates:
        c = cand.strip().lower()
        if c in TOPUP_PACKAGES:
            return c
    return None


def resolve_credits(*, package_id: str | None, price_cents: int) -> tuple[int, str | None]:
    """Return (credits, package_id). Prefer catalog coins; else price cents → credits."""
    if package_id:
        pkg = get_package(package_id)
        if pkg and int(pkg.get("coins") or 0) > 0:
            return int(pkg["coins"]), str(pkg["id"])
    # Fallback: 1 cent ≈ 1 credit ($0.01 / credit matches USD_TO_COINS=100)
    cents = max(0, int(price_cents))
    return cents, package_id


def verify_ping_token(form: Mapping[str, Any]) -> None:
    """Require ping ``seller_id`` (or ``token``) to match ``GUMROAD_PING_SECRET``."""
    secret = gumroad_ping_secret() or os.environ.get("GUMROAD_PING_SECRET", "").strip()
    if not secret:
        return
    provided = _form_get(form, "seller_id", "token", "ping_secret", "secret")
    if not provided or provided != secret:
        raise GumroadGatewayError("Invalid or missing Gumroad seller_id / ping secret")


def _lookup_user_id(*, user_id: int | None, email: str) -> int | None:
    with connect() as conn:
        ensure_gumroad_schema(conn)
        if user_id is not None:
            row = conn.execute(
                "SELECT id FROM users WHERE id = ?", (int(user_id),)
            ).fetchone()
            if row is not None:
                return int(row["id"])
        if email:
            row = conn.execute(
                "SELECT id FROM users WHERE lower(email) = lower(?)", (email,)
            ).fetchone()
            if row is not None:
                return int(row["id"])
    return None


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
        raise GumroadGatewayError("credits must be positive")

    existing = conn.execute(
        "SELECT id FROM transactions "
        "WHERE ref_id = ? AND feature = 'topup' AND reference_type = 'Gumroad' "
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
    reference_type = "Gumroad"

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


def handle_ping(form: Mapping[str, Any]) -> dict[str, Any]:
    """Validate + fulfill a Gumroad Ping. Raises GumroadGatewayError on hard failures."""
    verify_ping_token(form)

    if _as_bool(form.get("refunded")) or _as_bool(form.get("chargebacked")):
        return {
            "handled": False,
            "ignored": True,
            "reason": "refunded_or_chargeback",
        }

    email = _form_get(form, "email")
    sale_id = _form_get(form, "sale_id", "id", "order_number")
    if not sale_id:
        # Stable-ish fallback so duplicates still collide
        sale_id = f"gumroad:{email}:{_form_get(form, 'sale_timestamp')}:{_form_get(form, 'price')}"
    if not sale_id or sale_id == "gumroad:::":
        raise GumroadGatewayError("Ping missing sale_id")

    try:
        price_cents = int(float(_form_get(form, "price") or "0"))
    except (TypeError, ValueError):
        price_cents = 0

    product_id = _form_get(form, "product_id")
    short_product_id = _form_get(form, "short_product_id")
    currency = (_form_get(form, "currency") or "usd").lower()
    package_id = resolve_package_id(form)
    credits, package_id = resolve_credits(package_id=package_id, price_cents=price_cents)
    if credits <= 0:
        raise GumroadGatewayError("Could not resolve positive credit amount")

    raw_user_id = extract_user_id(form)
    user_id = _lookup_user_id(user_id=raw_user_id, email=email)
    if user_id is None:
        raise GumroadGatewayError(
            f"No DocMaxxing user for user_id={raw_user_id!r} email={email!r}"
        )

    payload_snapshot = {str(k): str(form.get(k)) for k in list(form.keys())[:80]}

    with connect() as conn:
        ensure_gumroad_schema(conn)
        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute(
            "SELECT * FROM gumroad_payments WHERE sale_id = ?", (sale_id,)
        ).fetchone()
        if existing is not None and existing["status"] == STATUS_PAID:
            return {
                "handled": True,
                "already_credited": True,
                "sale_id": sale_id,
                "user_id": int(existing["user_id"]) if existing["user_id"] else user_id,
                "credits_added": 0,
                "package_id": existing["package_id"],
            }

        meta = {
            "package": package_id,
            "price_cents": price_cents,
            "currency": currency,
            "email": email,
            "product_id": product_id or None,
            "short_product_id": short_product_id or None,
            "gumroad_sale_id": sale_id,
            "provider": "gumroad",
        }
        credit_result = _credit_on_conn(
            conn,
            user_id,
            credits,
            ref_id=sale_id,
            meta=meta,
        )

        if existing is None:
            conn.execute(
                "INSERT INTO gumroad_payments "
                "(sale_id, user_id, email, product_id, short_product_id, package_id, "
                " price_cents, credits, currency, status, payload_json, paid_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                (
                    sale_id,
                    user_id,
                    email or None,
                    product_id or None,
                    short_product_id or None,
                    package_id,
                    price_cents,
                    credits,
                    currency,
                    STATUS_PAID,
                    json.dumps(payload_snapshot),
                ),
            )
        else:
            conn.execute(
                "UPDATE gumroad_payments SET status = ?, user_id = ?, credits = ?, "
                "package_id = COALESCE(?, package_id), paid_at = datetime('now') "
                "WHERE sale_id = ?",
                (STATUS_PAID, user_id, credits, package_id, sale_id),
            )

    amount_usd = price_cents / 100.0
    try:
        from .referral import on_successful_deposit

        on_successful_deposit(
            user_id,
            float(amount_usd),
            payment_ref=f"gumroad:{sale_id}",
        )
    except Exception:
        logger.exception(
            "referral on_successful_deposit failed user_id=%s sale_id=%s",
            user_id,
            sale_id,
        )

    logger.info(
        "gumroad paid sale_id=%s user_id=%s credits=%s package=%s price_cents=%s",
        sale_id,
        user_id,
        credit_result.get("credits") or 0,
        package_id,
        price_cents,
    )
    return {
        "handled": True,
        "already_credited": bool(credit_result.get("already_credited")),
        "sale_id": sale_id,
        "user_id": user_id,
        "credits_added": int(credit_result.get("credits") or 0),
        "balance": credit_result.get("balance"),
        "package_id": package_id,
        "price_cents": price_cents,
    }
