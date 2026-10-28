"""Lemon Squeezy REST API: server-created checkouts.

Buy links cannot carry a server price or a return URL, so when
``LEMON_SQUEEZY_API_KEY`` is set every Pricing page checkout is created here:
the price comes from our catalog (``custom_price``), ``custom_data`` names the
account and what was bought, and the buyer returns to ``/app`` after paying.
"""

from __future__ import annotations

import os
from typing import Any

import requests

API_BASE = "https://api.lemonsqueezy.com/v1"
_TIMEOUT_S = 15
_store_id_cache: str | None = None


class LemonApiError(RuntimeError):
    pass


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def api_configured() -> bool:
    return bool(_env("LEMON_SQUEEZY_API_KEY"))


def request(method: str, path: str, *, json: dict[str, Any] | None = None, params: dict | None = None) -> dict:
    key = _env("LEMON_SQUEEZY_API_KEY")
    if not key:
        raise LemonApiError("LEMON_SQUEEZY_API_KEY is not configured")
    try:
        res = requests.request(
            method,
            f"{API_BASE}{path}",
            json=json,
            params=params,
            timeout=_TIMEOUT_S,
            headers={
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
                "Authorization": f"Bearer {key}",
            },
        )
    except requests.RequestException as exc:
        raise LemonApiError(f"Lemon Squeezy API request failed: {exc}") from exc
    if not res.ok:
        detail = ""
        try:
            errors = res.json().get("errors") or []
            detail = "; ".join(str(e.get("detail") or e.get("title") or e) for e in errors)
        except ValueError:
            detail = res.text[:200]
        raise LemonApiError(f"Lemon Squeezy API {res.status_code}: {detail}")
    return res.json()


def store_id() -> str:
    """``LEMON_STORE_ID``, or the account's only store."""
    global _store_id_cache
    configured = _env("LEMON_STORE_ID")
    if configured:
        return configured
    if _store_id_cache:
        return _store_id_cache
    stores = request("GET", "/stores").get("data") or []
    if len(stores) != 1:
        raise LemonApiError(f"Set LEMON_STORE_ID: the API key sees {len(stores)} stores")
    _store_id_cache = str(stores[0]["id"])
    return _store_id_cache


def public_base_url() -> str:
    return (_env("PUBLIC_BASE_URL") or "https://docmaxxing.com").rstrip("/")


def create_checkout(
    *,
    variant_id: str,
    custom: dict[str, Any],
    email: str | None = None,
    custom_price_cents: int | None = None,
    redirect_path: str = "/app?paid=1#/billing",
) -> str:
    """Create a one-off checkout and return its URL."""
    attributes: dict[str, Any] = {
        "product_options": {
            "enabled_variants": [int(variant_id)],
            "redirect_url": f"{public_base_url()}{redirect_path}",
        },
        "checkout_data": {"custom": {k: str(v) for k, v in custom.items()}},
    }
    if email:
        attributes["checkout_data"]["email"] = email
    if custom_price_cents is not None:
        attributes["custom_price"] = int(custom_price_cents)
    body = {
        "data": {
            "type": "checkouts",
            "attributes": attributes,
            "relationships": {
                "store": {"data": {"type": "stores", "id": store_id()}},
                "variant": {"data": {"type": "variants", "id": str(variant_id)}},
            },
        }
    }
    url = ((request("POST", "/checkouts", json=body).get("data") or {}).get("attributes") or {}).get("url")
    if not url:
        raise LemonApiError("Lemon Squeezy did not return a checkout URL")
    return str(url)
