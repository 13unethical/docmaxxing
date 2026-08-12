"""Strict Gemini adapter for post-format chat edits (single model, no retries)."""

from __future__ import annotations

from typing import Any

from services.gemini_client import gemini_enabled, gemini_model, generate_json


class GeminiChatClient:
    """Chat-specific Gemini calls: one model, no retries, strict timeout."""

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
        del response_mime_type, response_schema
        if not gemini_enabled():
            raise ValueError("GOOGLE_API_KEY is not set")

        limit = max(5, int(timeout_s))
        payload, diag = generate_json(
            system_prompt=system_instruction,
            user_prompt=user_message,
            temperature=temperature,
            timeout_s=limit,
            max_retries=0,
            models=[gemini_model()],
        )
        if payload is None:
            if diag.get("failure_reason") == "timeout":
                raise TimeoutError(diag.get("error_message") or "Gemini request timed out")
            raise ValueError(diag.get("error_message") or "Gemini request failed")
        if not isinstance(payload, dict):
            raise ValueError("Gemini response is not a JSON object")
        return payload
