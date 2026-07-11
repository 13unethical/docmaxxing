"""Configurable AI detection score thresholds."""

from __future__ import annotations

from services.ai_detection_engine.models import DetectionThresholds

DEFAULT_THRESHOLDS = DetectionThresholds(
    excellent_max=5.0,
    good_max=10.0,
    acceptable_max=15.0,
    needs_revision_max=25.0,
)


def classify_score(score: float, thresholds: DetectionThresholds | None = None) -> str:
    limits = thresholds or DEFAULT_THRESHOLDS
    if score <= limits.excellent_max:
        return "excellent"
    if score <= limits.good_max:
        return "good"
    if score <= limits.acceptable_max:
        return "acceptable"
    if score <= limits.needs_revision_max:
        return "needs_revision"
    return "high_ai_probability"


def score_passes(score: float, thresholds: DetectionThresholds | None = None) -> bool:
    limits = thresholds or DEFAULT_THRESHOLDS
    return score <= limits.acceptable_max
