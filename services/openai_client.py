"""Minimal OpenAI Chat Completions client for training-data generation.

Same call shape as ``gemini_client.generate_text``. Used only by offline/background jobs
(source pool, detector corpus), never in a user request path.
"""

from __future__ import annotations

import os
import random
import time
from typing import Any

import requests

_URL = "https://api.openai.com/v1/chat/completions"
_DEFAULT_MODEL = "gpt-4o"
_RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})
_NETWORK_EXCEPTIONS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
)
# Reasoning models accept only the default temperature.
_FIXED_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3", "o4")
# USD per 1M tokens (input, output), for spend reports only.
PRICES = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
}


def openai_api_key() -> str:
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def openai_enabled() -> bool:
    return bool(openai_api_key())


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    price = PRICES.get(model)
    if price is None:
        base = max((m for m in PRICES if model.startswith(m)), key=len, default=None)
        price = PRICES.get(base) if base else None
    if price is None:
        return None
    return (prompt_tokens * price[0] + completion_tokens * price[1]) / 1_000_000


def build_body(*, system_prompt: str, content: str, temperature: float, model: str, max_tokens: int) -> dict[str, Any]:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": content})
    body: dict[str, Any] = {"model": model, "messages": messages, "max_completion_tokens": int(max_tokens)}
    if not model.startswith(_FIXED_TEMPERATURE_PREFIXES):
        body["temperature"] = temperature
    return body


def generate_text(
    *,
    system_prompt: str,
    content: str,
    temperature: float = 0.7,
    model: str | None = None,
    max_retries: int = 3,
    timeout_s: int = 300,
    max_tokens: int = 8192,
) -> tuple[str | None, dict[str, Any]]:
    active_model = (model or os.environ.get("OPENAI_MODEL") or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    diag: dict[str, Any] = {"provider": "openai", "model": active_model, "api_call_success": False}
    key = openai_api_key()
    if not key:
        diag["error_message"] = "OPENAI_API_KEY is not set"
        return None, diag
    body = build_body(
        system_prompt=system_prompt, content=content, temperature=temperature, model=active_model, max_tokens=max_tokens
    )
    headers = {"Authorization": f"Bearer {key}"}
    started = time.monotonic()
    error = ""
    for attempt in range(max_retries + 1):
        try:
            res = requests.post(_URL, headers=headers, json=body, timeout=timeout_s)
            diag["http_status"] = res.status_code
            if res.ok:
                payload = res.json()
                choice = (payload.get("choices") or [{}])[0] or {}
                text = ((choice.get("message") or {}).get("content") or "").strip()
                usage = payload.get("usage") or {}
                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                completion_tokens = int(usage.get("completion_tokens") or 0)
                diag.update(
                    {
                        "model": payload.get("model") or active_model,
                        "retry_count": attempt,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "cost_usd": estimate_cost_usd(active_model, prompt_tokens, completion_tokens),
                        "finish_reason": "MAX_TOKENS" if choice.get("finish_reason") == "length" else choice.get("finish_reason"),
                    }
                )
                if text:
                    diag["api_call_success"] = True
                    return text, diag
                error = "Empty model response text"
                break
            error = res.text[:500]
            if res.status_code not in _RETRYABLE_HTTP_STATUS:
                break
        except _NETWORK_EXCEPTIONS as exc:
            error = repr(exc)
        if attempt < max_retries:
            time.sleep(min(30.0, 2.0 * (2**attempt)) + random.uniform(0, 0.5))
    diag["error_message"] = error
    diag["latency_ms"] = int((time.monotonic() - started) * 1000)
    return None, diag
