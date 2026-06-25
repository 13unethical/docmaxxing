"""Gemini REST client with retries, model fallback, and structured diagnostics."""

from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash"
_DEFAULT_TIMEOUT_S = 30
_DEFAULT_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 1.0
_MAX_BACKOFF_S = 32.0

# Primary → lighter fallbacks when the primary model is overloaded or unavailable.
DEFAULT_MODEL_FALLBACK_CHAIN = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
)

_RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})
_NETWORK_EXCEPTIONS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
)


def gemini_model() -> str:
    return (os.environ.get("GEMINI_MODEL") or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL


def gemini_model_chain() -> list[str]:
    """Ordered model list: env override first, then default fallbacks (deduped)."""
    primary = gemini_model()
    chain: list[str] = []
    for model in (primary, *DEFAULT_MODEL_FALLBACK_CHAIN):
        model = model.strip()
        if model and model not in chain:
            chain.append(model)
    return chain


def gemini_api_key() -> str:
    return (os.environ.get("GOOGLE_API_KEY") or "").strip()


def gemini_enabled() -> bool:
    return bool(gemini_api_key())


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text or "") / 4))


def _extract_text_from_response(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    content = first.get("content") if isinstance(first, dict) else {}
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            chunks.append(part["text"])
    return "\n".join(chunks).strip()


def _classify_failure(
    *,
    http_status: int | None,
    error_message: str,
    exc: Exception | None,
) -> str:
    msg = (error_message or "").lower()
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if http_status == 429 or "quota" in msg or "rate limit" in msg or "resource_exhausted" in msg:
        return "quota"
    if http_status in {503, 502, 504} or "unavailable" in msg or "high demand" in msg:
        return "unavailable"
    if http_status == 400 or "invalid" in msg or "validation" in msg:
        return "validation_error"
    if http_status == 404:
        return "validation_error"
    if exc is not None:
        return "unavailable"
    return "parse_error"


def _base_diagnostics(
    *,
    model: str,
    request_chars: int,
    token_usage_estimate: int,
) -> dict[str, Any]:
    return {
        "enabled": gemini_enabled(),
        "model": model,
        "models_attempted": [model],
        "fallback_activated": False,
        "api_call_success": False,
        "failure_reason": None,
        "http_status": None,
        "retry_count": 0,
        "latency_ms": 0,
        "request_chars": request_chars,
        "token_usage_estimate": token_usage_estimate,
        "error_message": None,
    }


def generate_json(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    model: str | None = None,
    models: list[str] | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """
    Call Gemini and parse a JSON object from the response.

    Retries transient failures (503, 429, 5xx, network) with exponential backoff.
    Tries fallback models when the primary model keeps failing.
  """
    prompt_text = f"{system_prompt}\n\n{user_prompt}"
    request_chars = len(prompt_text)
    token_est = estimate_tokens(prompt_text)
    chain = [model] if model else (models or gemini_model_chain())
    chain = [m.strip() for m in chain if m and m.strip()]

    if not gemini_enabled():
        diag = _base_diagnostics(model=chain[0] if chain else _DEFAULT_MODEL, request_chars=request_chars, token_usage_estimate=token_est)
        diag["enabled"] = False
        diag["failure_reason"] = "validation_error"
        diag["error_message"] = "GOOGLE_API_KEY is not set"
        return None, diag

    total_retries = 0
    total_latency_ms = 0
    models_attempted: list[str] = []
    last_http_status: int | None = None
    last_error_message = ""
    last_exc: Exception | None = None
    primary_model = chain[0]

    for model_idx, active_model in enumerate(chain):
        models_attempted.append(active_model)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }

        for attempt in range(max_retries + 1):
            started = time.monotonic()
            try:
                res = requests.post(
                    url,
                    params={"key": gemini_api_key()},
                    json=body,
                    timeout=timeout_s,
                )
                elapsed_ms = int((time.monotonic() - started) * 1000)
                total_latency_ms += elapsed_ms
                last_http_status = res.status_code

                if res.status_code in _RETRYABLE_HTTP_STATUS and attempt < max_retries:
                    total_retries += 1
                    try:
                        err_body = res.json()
                        last_error_message = str((err_body.get("error") or {}).get("message") or res.text[:500])
                    except Exception:  # noqa: BLE001
                        last_error_message = res.text[:500]
                    backoff = min(_MAX_BACKOFF_S, _INITIAL_BACKOFF_S * (2**attempt))
                    backoff += random.uniform(0, 0.35)
                    logger.warning(
                        "Gemini retry model=%s attempt=%s status=%s backoff=%.2fs",
                        active_model,
                        attempt + 1,
                        res.status_code,
                        backoff,
                    )
                    time.sleep(backoff)
                    continue

                if not res.ok:
                    try:
                        err_body = res.json()
                        last_error_message = str((err_body.get("error") or {}).get("message") or res.text[:800])
                    except Exception:  # noqa: BLE001
                        last_error_message = res.text[:800]
                    # Try next fallback model on non-retryable client errors (e.g. 404 model not found)
                    if res.status_code == 404 and model_idx < len(chain) - 1:
                        logger.warning("Gemini model %s not found; trying fallback", active_model)
                        break
                    failure = _classify_failure(
                        http_status=res.status_code,
                        error_message=last_error_message,
                        exc=None,
                    )
                    diag = _base_diagnostics(
                        model=active_model,
                        request_chars=request_chars,
                        token_usage_estimate=token_est,
                    )
                    diag.update(
                        {
                            "models_attempted": list(models_attempted),
                            "fallback_activated": active_model != primary_model,
                            "failure_reason": failure,
                            "http_status": res.status_code,
                            "retry_count": total_retries,
                            "latency_ms": total_latency_ms,
                            "error_message": last_error_message[:500] if last_error_message else None,
                        }
                    )
                    return None, diag

                payload = res.json()
                text = _extract_text_from_response(payload)
                if not text:
                    if attempt < max_retries:
                        total_retries += 1
                        time.sleep(min(_MAX_BACKOFF_S, _INITIAL_BACKOFF_S * (2**attempt)))
                        continue
                    diag = _base_diagnostics(
                        model=active_model,
                        request_chars=request_chars,
                        token_usage_estimate=token_est,
                    )
                    diag.update(
                        {
                            "models_attempted": list(models_attempted),
                            "fallback_activated": active_model != primary_model,
                            "failure_reason": "parse_error",
                            "http_status": res.status_code,
                            "retry_count": total_retries,
                            "latency_ms": total_latency_ms,
                            "error_message": "Empty model response text",
                        }
                    )
                    return None, diag

                try:
                    data = json.loads(text)
                except json.JSONDecodeError as exc:
                    last_exc = exc
                    last_error_message = f"JSON decode error: {exc}"
                    if attempt < max_retries:
                        total_retries += 1
                        time.sleep(min(_MAX_BACKOFF_S, _INITIAL_BACKOFF_S * (2**attempt)))
                        continue
                    diag = _base_diagnostics(
                        model=active_model,
                        request_chars=request_chars,
                        token_usage_estimate=token_est,
                    )
                    diag.update(
                        {
                            "models_attempted": list(models_attempted),
                            "fallback_activated": active_model != primary_model,
                            "failure_reason": "parse_error",
                            "http_status": res.status_code,
                            "retry_count": total_retries,
                            "latency_ms": total_latency_ms,
                            "error_message": last_error_message,
                        }
                    )
                    return None, diag

                usage = payload.get("usageMetadata") if isinstance(payload, dict) else None
                if isinstance(usage, dict):
                    total = usage.get("totalTokenCount")
                    if isinstance(total, int):
                        token_est = total

                diag = _base_diagnostics(
                    model=active_model,
                    request_chars=request_chars,
                    token_usage_estimate=token_est,
                )
                diag.update(
                    {
                        "models_attempted": list(models_attempted),
                        "fallback_activated": active_model != primary_model,
                        "api_call_success": True,
                        "retry_count": total_retries,
                        "latency_ms": total_latency_ms,
                        "http_status": res.status_code,
                    }
                )
                return data if isinstance(data, dict) else None, diag

            except _NETWORK_EXCEPTIONS as exc:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                total_latency_ms += elapsed_ms
                last_exc = exc
                last_error_message = repr(exc)
                if attempt < max_retries:
                    total_retries += 1
                    backoff = min(_MAX_BACKOFF_S, _INITIAL_BACKOFF_S * (2**attempt))
                    backoff += random.uniform(0, 0.35)
                    logger.warning(
                        "Gemini network retry model=%s attempt=%s err=%s",
                        active_model,
                        attempt + 1,
                        exc,
                    )
                    time.sleep(backoff)
                    continue
                break
            except Exception as exc:  # noqa: BLE001
                elapsed_ms = int((time.monotonic() - started) * 1000)
                total_latency_ms += elapsed_ms
                last_exc = exc
                last_error_message = repr(exc)
                break

        # try next model in fallback chain
        if model_idx < len(chain) - 1:
            logger.warning("Gemini switching fallback from %s", active_model)
            continue

    failure = _classify_failure(
        http_status=last_http_status,
        error_message=last_error_message,
        exc=last_exc,
    )
    diag = _base_diagnostics(
        model=models_attempted[-1] if models_attempted else primary_model,
        request_chars=request_chars,
        token_usage_estimate=token_est,
    )
    diag.update(
        {
            "models_attempted": list(models_attempted),
            "fallback_activated": len(models_attempted) > 1,
            "failure_reason": failure,
            "http_status": last_http_status,
            "retry_count": total_retries,
            "latency_ms": total_latency_ms,
            "error_message": (last_error_message or str(last_exc) or "Unknown Gemini failure")[:500],
        }
    )
    return None, diag
