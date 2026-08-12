"""Gemini adapter implementing ``SmartformLLMClient`` for production routes."""

from __future__ import annotations

from typing import Any

from services.gemini_client import generate_json, gemini_enabled


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
        del response_mime_type, response_schema  # generate_json always requests JSON
        if not gemini_enabled():
            raise ValueError("GOOGLE_API_KEY is not set")
        payload, diag = generate_json(
            system_prompt=system_instruction,
            user_prompt=user_message,
            temperature=temperature,
            timeout_s=max(10, int(timeout_s)),
        )
        if payload is None:
            raise ValueError(diag.get("error_message") or "Gemini request failed")
        if not isinstance(payload, dict):
            raise ValueError("Gemini response is not a JSON object")
        return payload
