"""ZeroGPT Business adapter for the AIDetectionEngine AIDetector protocol."""

from __future__ import annotations


class ZeroGPTAIDetector:
    """Maps ZeroGPT Business detection scores into 0–100 floats."""

    VERSION = "zerogpt-business-1.0"

    def __init__(self, client=None) -> None:
        from services.zerogpt_business.client import ZeroGPTClient
        from services.zerogpt_business.providers import ZeroGPTDetectionProvider

        self._provider = ZeroGPTDetectionProvider(client=client or ZeroGPTClient())

    def detect(self, text: str) -> float:
        from services.humanizer_engine.heading_utils import is_heading_only

        if not text or not text.strip():
            return 0.0
        if is_heading_only(text):
            return 2.0
        try:
            result = self._provider.detect(text)
            return float(max(0.0, min(100.0, result.ai_score)))
        except Exception as exc:  # noqa: BLE001 — provider network/parse errors
            raise RuntimeError(f"ZeroGPT detection failed: {exc}") from exc
