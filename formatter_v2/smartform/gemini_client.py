"""Gemini adapter implementing ``SmartformLLMClient`` for production routes."""

from __future__ import annotations

from typing import Any

from services.gemini_client import generate_json, gemini_enabled

_META_FIELDS = {"evidence", "unsupported", "warnings"}


def gemini_response_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Wire schema for Gemini: every value field becomes ``{value, evidence}``.

    Gemini's responseSchema rejects ``additionalProperties`` (the flat ``evidence`` map), and
    with a separate optional map it fills values but skips their quotes, so post-processing
    clears them. Pairing each value with its quote keeps both in one place.
    """
    props: dict[str, Any] = {}
    for key, spec in (schema.get("properties") or {}).items():
        if key == "evidence":
            continue
        if key in _META_FIELDS:
            props[key] = spec
            continue
        value = {k: v for k, v in spec.items() if k != "nullable"}
        props[key] = {
            "type": "object",
            "nullable": True,
            "properties": {"value": value, "evidence": {"type": "string"}},
            "required": ["value", "evidence"],
        }
    return {"type": "object", "properties": props}


def flatten_gemini_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Inverse of :func:`gemini_response_schema`: back to flat fields + ``evidence`` map."""
    out: dict[str, Any] = {}
    evidence: dict[str, str] = {}
    for key, item in payload.items():
        if key in _META_FIELDS:
            out[key] = item
        elif isinstance(item, dict) and "value" in item:
            out[key] = item.get("value")
            if item.get("value") is not None and item.get("evidence"):
                evidence[key] = str(item["evidence"])
        elif item is not None:
            out[key] = item
    out["evidence"] = {**evidence, **dict(payload.get("evidence") or {})}
    return out


class GeminiSmartformClient:
    """Thin adapter: smartform Protocol → ``services.gemini_client.generate_json``."""

    def generate(
        self,
        *,
        system_instruction: str,
        user_message: str,
        temperature: float,
        response_mime_type: str,
        response_schema: dict[str, Any],
        timeout_s: float,
    ) -> dict[str, Any]:
        del response_mime_type  # generate_json always requests JSON
        if not gemini_enabled():
            raise ValueError("GOOGLE_API_KEY is not set")
        payload, diag = generate_json(
            system_prompt=system_instruction,
            user_prompt=user_message,
            temperature=temperature,
            timeout_s=max(10, int(timeout_s)),
            response_schema=gemini_response_schema(response_schema) if response_schema else None,
        )
        if payload is None:
            raise ValueError(diag.get("error_message") or "Gemini request failed")
        if not isinstance(payload, dict):
            raise ValueError("Gemini response is not a JSON object")
        return flatten_gemini_response(payload) if response_schema else payload
