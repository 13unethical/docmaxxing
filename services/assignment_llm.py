"""LLM routing for the assignment pipeline (temporary Claude-first switch)."""

from __future__ import annotations

import os
from typing import Any

from services.claude_client import claude_enabled, claude_model, generate_json as claude_generate_json
from services.gemini_client import gemini_enabled, gemini_model, generate_json as gemini_generate_json


def assignment_llm_provider() -> str:
    """Return ``claude`` or ``gemini`` for assignment-stage JSON calls."""
    explicit = (os.environ.get("ASSIGNMENT_LLM") or "").strip().lower()
    if explicit in {"claude", "gemini"}:
        return explicit
    # Temporary default while Gemini billing is unavailable for assignment work.
    if claude_enabled():
        return "claude"
    return "gemini"


def assignment_uses_claude() -> bool:
    return assignment_llm_provider() == "claude"


def assignment_llm_model() -> str:
    if assignment_uses_claude():
        return claude_model()
    return gemini_model()


def assignment_generate_json(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_retries: int = 2,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if assignment_uses_claude():
        return claude_generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_retries=max_retries,
        )
    return gemini_generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_retries=max_retries,
    )


def assignment_llm_configured() -> bool:
    if assignment_uses_claude():
        return claude_enabled()
    return gemini_enabled()
