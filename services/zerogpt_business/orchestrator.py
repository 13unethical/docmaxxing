"""Orchestrator review flow aligned with src/services/ai/AIOrchestrator.ts."""

from __future__ import annotations

from typing import Any

from services.zerogpt_business.client import ZeroGPTClient, ZeroGPTError
from services.zerogpt_business.providers import (
    ZeroGPTDetectionProvider,
    ZeroGPTHumanizerProvider,
    ZeroGPTProviderError,
)


def orchestrator_review(text: str, client: ZeroGPTClient | None = None) -> dict[str, Any]:
    """Run detect -> humanize -> detect and return AIOrchestrator-compatible payload."""
    active_client = client or ZeroGPTClient()
    provider = "zerogpt"
    trimmed = text.strip()
    if not trimmed:
        return _failure(
            provider=provider,
            message="Input text is empty",
            step="detection",
        )

    detection_provider = ZeroGPTDetectionProvider(active_client)
    humanizer_provider = ZeroGPTHumanizerProvider(active_client)

    try:
        original_detection = detection_provider.detect(trimmed)
    except (ZeroGPTError, ZeroGPTProviderError) as exc:
        return _failure(provider=provider, message=f"Detection failed: {exc}", step="detection")

    try:
        humanized = humanizer_provider.humanize(trimmed)
    except (ZeroGPTError, ZeroGPTProviderError) as exc:
        return _failure(
            provider=provider,
            message=f"Humanizer is unavailable or failed: {exc}",
            step="humanizer",
        )

    humanized_text = humanized.text.strip()
    if not humanized_text:
        return _failure(
            provider=provider,
            message="Humanizer returned empty text",
            step="humanizer",
        )

    try:
        final_detection = detection_provider.detect(humanized_text)
    except (ZeroGPTError, ZeroGPTProviderError) as exc:
        return _failure(
            provider=provider,
            message=f"Final detection failed: {exc}",
            step="final-detection",
        )

    improved = final_detection.ai_score < original_detection.ai_score
    pipeline = {
        "originalDetection": _serialize_detection(original_detection),
        "humanizedText": humanized_text,
        "finalDetection": _serialize_detection(final_detection),
        "improved": improved,
    }
    message = (
        "AI score improved after humanization"
        if improved
        else "AI score did not improve after humanization"
    )

    return {
        "success": True,
        "provider": provider,
        "pipeline": pipeline,
        "review": {
            "improved": improved,
            "originalAiScore": original_detection.ai_score,
            "finalAiScore": final_detection.ai_score,
            "humanizedText": humanized_text,
            "message": message,
        },
    }


def _serialize_detection(result) -> dict[str, Any]:
    return {
        "provider": result.provider,
        "aiScore": result.ai_score,
        "passed": result.passed,
        "paragraphs": result.paragraphs,
        "raw": result.raw,
    }


def _failure(*, provider: str, message: str, step: str) -> dict[str, Any]:
    return {
        "success": False,
        "provider": provider,
        "pipeline": None,
        "review": {
            "improved": False,
            "originalAiScore": None,
            "finalAiScore": None,
            "humanizedText": None,
            "message": message,
            "error": {"step": step, "message": message},
        },
    }
