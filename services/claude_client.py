"""Anthropic Claude REST client for structured JSON generation."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_API_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_TIMEOUT_S = 120
_DEFAULT_MAX_RETRIES = 2
_RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})
_NETWORK_EXCEPTIONS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
)


def claude_model() -> str:
    return (os.environ.get("ANTHROPIC_MODEL") or os.environ.get("CLAUDE_MODEL") or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL


def claude_api_key() -> str:
    return (
        (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        or (os.environ.get("Claude_API_Key") or "").strip()
    )


def claude_enabled() -> bool:
    return bool(claude_api_key())


def _base_diagnostics(*, model: str, request_chars: int) -> dict[str, Any]:
    return {
        "enabled": claude_enabled(),
        "model": model,
        "models_attempted": [model],
        "api_call_success": False,
        "failure_reason": None,
        "http_status": None,
        "retry_count": 0,
        "latency_ms": 0,
        "request_chars": request_chars,
        "error_message": None,
    }


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty model response text")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model response is not valid JSON") from None
        data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Model response JSON is not an object")
    return data


def generate_json(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    model: str | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Call Claude and parse a JSON object from the response."""
    active_model = (model or claude_model()).strip() or claude_model()
    prompt_text = f"{system_prompt}\n\n{user_prompt}"
    request_chars = len(prompt_text)

    if not claude_enabled():
        diag = _base_diagnostics(model=active_model, request_chars=request_chars)
        diag["failure_reason"] = "validation_error"
        diag["error_message"] = "ANTHROPIC_API_KEY is not set"
        return None, diag

    body = {
        "model": active_model,
        "max_tokens": 4096,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    headers = {
        "x-api-key": claude_api_key(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    total_retries = 0
    total_latency_ms = 0
    last_http_status: int | None = None
    last_error_message = ""

    for attempt in range(max_retries + 1):
        started = time.monotonic()
        try:
            response = requests.post(
                _API_URL,
                json=body,
                headers=headers,
                timeout=timeout_s,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            total_latency_ms += elapsed_ms
            last_http_status = response.status_code

            if response.status_code in _RETRYABLE_HTTP_STATUS and attempt < max_retries:
                total_retries += 1
                last_error_message = response.text[:500]
                logger.warning(
                    "Claude retry model=%s attempt=%s status=%s",
                    active_model,
                    attempt + 1,
                    response.status_code,
                )
                time.sleep(min(8.0, 1.0 * (2**attempt)))
                continue

            if not response.ok:
                last_error_message = response.text[:800]
                diag = _base_diagnostics(model=active_model, request_chars=request_chars)
                diag.update(
                    {
                        "failure_reason": "unavailable",
                        "http_status": response.status_code,
                        "retry_count": total_retries,
                        "latency_ms": total_latency_ms,
                        "error_message": last_error_message,
                    }
                )
                return None, diag

            payload = response.json()
            content = payload.get("content") or []
            text_chunks = [
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            raw_text = "\n".join(text_chunks).strip()
            try:
                data = _parse_json_object(raw_text)
            except ValueError as exc:
                last_error_message = str(exc)
                if attempt < max_retries:
                    total_retries += 1
                    continue
                diag = _base_diagnostics(model=active_model, request_chars=request_chars)
                diag.update(
                    {
                        "failure_reason": "parse_error",
                        "http_status": response.status_code,
                        "retry_count": total_retries,
                        "latency_ms": total_latency_ms,
                        "error_message": last_error_message,
                    }
                )
                return None, diag

            diag = _base_diagnostics(model=active_model, request_chars=request_chars)
            diag.update(
                {
                    "api_call_success": True,
                    "retry_count": total_retries,
                    "latency_ms": total_latency_ms,
                    "http_status": response.status_code,
                }
            )
            return data, diag

        except _NETWORK_EXCEPTIONS as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            total_latency_ms += elapsed_ms
            last_error_message = repr(exc)
            if attempt < max_retries:
                total_retries += 1
                time.sleep(min(8.0, 1.0 * (2**attempt)))
                continue
            break

    diag = _base_diagnostics(model=active_model, request_chars=request_chars)
    diag.update(
        {
            "failure_reason": "unavailable",
            "http_status": last_http_status,
            "retry_count": total_retries,
            "latency_ms": total_latency_ms,
            "error_message": (last_error_message or "Unknown Claude failure")[:500],
        }
    )
    return None, diag
