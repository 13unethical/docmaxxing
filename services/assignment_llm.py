"""LLM routing for the assignment pipeline — per-stage provider selection."""

from __future__ import annotations

import os
from typing import Any

from services.claude_client import claude_enabled, claude_model, generate_json as claude_generate_json
from services.gemini_client import gemini_enabled, gemini_model, generate_json as gemini_generate_json

STAGE_REQUIREMENT_ANALYSIS = "requirement_analysis"
STAGE_RESEARCH = "research"
STAGE_BLUEPRINT = "blueprint"
STAGE_SECTION_REVIEW = "section_review"
STAGE_WRITER = "writer"
STAGE_ACADEMIC_REVIEW = "style_review"
STAGE_REVISION = "revision"
STAGE_CITATION_EXTRACT = "citation_generation"
STAGE_REQUIREMENT_VALIDATION = "requirement_validation"

# Planning / analysis / review stages use Gemini when GOOGLE_API_KEY is set.
_GEMINI_STAGES = frozenset({
    STAGE_REQUIREMENT_ANALYSIS,
    STAGE_RESEARCH,
    STAGE_BLUEPRINT,
    STAGE_SECTION_REVIEW,
    STAGE_ACADEMIC_REVIEW,
    STAGE_REVISION,
    STAGE_CITATION_EXTRACT,
    STAGE_REQUIREMENT_VALIDATION,
})


def assignment_llm_provider(stage: str | None = None) -> str:
    """Return ``claude`` or ``gemini`` for a pipeline stage."""
    normalized = (stage or STAGE_WRITER).strip().lower()

    if normalized in _GEMINI_STAGES:
        if gemini_enabled():
            return "gemini"
        if claude_enabled():
            return "claude"
        return "gemini"

    explicit = (os.environ.get("ASSIGNMENT_LLM") or "").strip().lower()
    if explicit in {"claude", "gemini"}:
        return explicit
    if claude_enabled():
        return "claude"
    return "gemini"


def assignment_uses_claude(stage: str | None = None) -> bool:
    return assignment_llm_provider(stage) == "claude"


def assignment_uses_gemini(stage: str | None = None) -> bool:
    return assignment_llm_provider(stage) == "gemini"


def assignment_llm_model(stage: str | None = None) -> str:
    if assignment_uses_claude(stage):
        return claude_model()
    return gemini_model()


def assignment_generate_json(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_retries: int = 2,
    stage: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if assignment_uses_claude(stage):
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


def assignment_llm_configured(stage: str | None = None) -> bool:
    if assignment_uses_claude(stage):
        return claude_enabled()
    return gemini_enabled()
