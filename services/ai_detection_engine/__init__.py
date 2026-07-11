"""AI Detection Engine — paragraph-by-paragraph analysis for the assignment pipeline."""

from services.ai_detection_engine.models import (
    AIDetectionEngineInput,
    DetectionReport,
    DetectionSession,
    DetectionThresholds,
    ParagraphDetection,
    ParagraphDetectionStatus,
)
from services.ai_detection_engine.mock_detector import AIDetector, MockAIDetector
from services.ai_detection_engine.service import AIDetectionEngineService
from services.ai_detection_engine.store import DetectionReportStore, DetectionSessionStore
from services.ai_detection_engine.thresholds import DEFAULT_THRESHOLDS, classify_score, score_passes

__all__ = [
    "AIDetectionEngineInput",
    "AIDetectionEngineService",
    "AIDetector",
    "DEFAULT_THRESHOLDS",
    "DetectionReport",
    "DetectionReportStore",
    "DetectionSession",
    "DetectionSessionStore",
    "DetectionThresholds",
    "MockAIDetector",
    "ParagraphDetection",
    "ParagraphDetectionStatus",
    "classify_score",
    "score_passes",
]
