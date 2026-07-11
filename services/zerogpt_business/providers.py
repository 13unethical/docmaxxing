"""ZeroGPT provider adapters for backend interfaces."""

from __future__ import annotations

from typing import Any

from services.ai_provider_interfaces import (
    DetectionProvider,
    DetectionResult,
    HumanizedResult,
    HumanizerProvider,
)
from services.humanizer_engine.constants import normalize_humanizer_mode
from services.zerogpt_business.client import ZeroGPTClient, ZeroGPTError


class ZeroGPTProviderError(RuntimeError):
    """Raised when ZeroGPT payload cannot be mapped safely."""


class ZeroGPTDetectionProvider(DetectionProvider):
    def __init__(self, client: ZeroGPTClient | None = None) -> None:
        self.client = client or ZeroGPTClient()

    def detect(self, text: str) -> DetectionResult:
        raw = self.client.detect(text)
        ai_score = _extract_detection_score(raw)
        return DetectionResult(
            provider="zerogpt-business",
            ai_score=ai_score,
            passed=ai_score < 50.0,
            paragraphs=[],
            raw=raw,
        )


class ZeroGPTHumanizerProvider(HumanizerProvider):
    def __init__(self, client: ZeroGPTClient | None = None) -> None:
        self.client = client or ZeroGPTClient()

    def humanize(
        self,
        text: str,
        *,
        tone: str = "Academic",
        mode: str | None = None,
    ) -> HumanizedResult:
        selected_mode = normalize_humanizer_mode(mode)
        if selected_mode == "advanced_paraphrase":
            raw = self.client.advanced_paraphrase(text, tone=tone)
            provider_name = "zerogpt-advanced-paraphrase"
        elif selected_mode == "paraphrase":
            raw = self.client.paraphrase(text, tone=tone)
            provider_name = "zerogpt-paraphrase"
        else:
            try:
                raw = self.client.humanize(text, tone=tone)
            except ZeroGPTError:
                raw = self.client.paraphrase(text, tone=tone)
            provider_name = "zerogpt-humanize"
        output_text = _extract_humanized_text(raw)
        return HumanizedResult(
            provider=provider_name,
            text=output_text,
            original_words=_count_words(text),
            humanized_words=_count_words(output_text),
            processing_time=0.0,
            raw=raw,
        )


def _extract_detection_score(raw: dict[str, Any]) -> float:
    data = raw.get("data")
    if isinstance(data, dict):
        for key in ("fakePercentage", "aiPercentage", "ai_percentage", "score"):
            if key in data and isinstance(data[key], (int, float)):
                return float(data[key])
    for key in ("ai_percentage", "aiPercentage", "score"):
        if key in raw and isinstance(raw[key], (int, float)):
            return float(raw[key])
    raise ZeroGPTProviderError(f"Unexpected detection payload: {raw}")


def _extract_humanized_text(raw: dict[str, Any]) -> str:
    if raw.get("success") is False:
        message = str(raw.get("message") or "ZeroGPT humanize failed")
        raise ZeroGPTProviderError(message)

    data = raw.get("data")
    if isinstance(data, dict):
        for key in (
            "output",
            "message",
            "output_text",
            "outputText",
            "newString",
            "new_string",
            "text",
            "result",
            "humanized_text",
            "humanizedText",
            "humanized",
        ):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
        nested = data.get("raw")
        if isinstance(nested, dict):
            for key in ("output", "message", "output_text", "outputText", "text", "result"):
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value
    if isinstance(data, str) and data.strip():
        return data
    for key in ("humanized_text", "humanizedText", "text", "result", "output_text"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value
    if isinstance(raw.get("message"), str) and isinstance(data, str):
        return data
    raise ZeroGPTProviderError(f"Unexpected humanize payload: {raw}")


def _count_words(text: str) -> int:
    return len([part for part in text.split() if part.strip()])
