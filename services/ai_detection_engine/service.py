"""AI Detection Engine service — one paragraph at a time."""

from __future__ import annotations

import re
import uuid
from typing import Any, Callable

from services.assignment_pipeline.models import utc_now
from services.ai_detection_engine.mock_detector import MockAIDetector, AIDetector
from services.ai_detection_engine.models import (
    MAX_DETECTION_ATTEMPTS,
    AIDetectionEngineInput,
    DetectionReport,
    DetectionSession,
    DetectionSessionStatus,
    DetectionThresholds,
    FinalDetectionStatus,
    ParagraphDetectionStatus,
)
from services.ai_detection_engine.paragraph_parser import split_humanized_draft_into_paragraphs
from services.ai_detection_engine.store import DetectionReportStore, DetectionSessionStore
from services.ai_detection_engine.thresholds import DEFAULT_THRESHOLDS, classify_score, score_passes


ParagraphRehumanizer = Callable[[str, str], str]

_REFERENCE_SECTION_RE = re.compile(
    r"reference|bibliograph|works\s+cited|citation\s+list|sources",
    re.I,
)
_CITATION_LINE_RE = re.compile(
    r"(https?://doi\.org|\bdoi:\s*\d|vol\.?\s*\d|\(\d{4}\)|\bpp?\.\s*\d)",
    re.I,
)


def _is_non_prose_paragraph(paragraph) -> bool:
    """Headings, reference list entries, and citation lines — skip ZeroGPT / auto-pass."""
    from services.humanizer_engine.heading_utils import is_heading_only

    text = (paragraph.text or "").strip()
    if not text or is_heading_only(text):
        return True
    section = str(paragraph.section or "")
    if _REFERENCE_SECTION_RE.search(section):
        return True
    words = len(text.split())
    if words <= 60 and _CITATION_LINE_RE.search(text):
        return True
    return False


class AIDetectionEngineService:
    def __init__(
        self,
        session_store: DetectionSessionStore | None = None,
        report_store: DetectionReportStore | None = None,
        detector: AIDetector | None = None,
    ) -> None:
        self.sessions = session_store or DetectionSessionStore()
        self.reports = report_store or DetectionReportStore()
        self.detector = detector or MockAIDetector()

    def create_session(
        self,
        *,
        humanized_draft: dict[str, Any],
        requirement_json: dict[str, Any],
        project_id: str | None = None,
        thresholds: DetectionThresholds | None = None,
        humanizer_paragraph_ids: list[str] | None = None,
    ) -> DetectionSession:
        if not humanized_draft or not requirement_json:
            raise ValueError("humanized_draft and requirement_json are required")

        paragraphs = split_humanized_draft_into_paragraphs(
            str(humanized_draft.get("content") or ""),
            humanizer_paragraph_ids=humanizer_paragraph_ids,
        )
        if not paragraphs:
            raise ValueError("Humanized draft has no paragraphs to analyze")

        now = utc_now()
        session = DetectionSession(
            id=str(uuid.uuid4()),
            project_id=project_id,
            humanized_draft_id=str(humanized_draft.get("id") or ""),
            paragraphs=paragraphs,
            current_paragraph_id=paragraphs[0].paragraph_id,
            completed_paragraph_ids=[],
            remaining_paragraph_ids=[paragraph.paragraph_id for paragraph in paragraphs],
            progress=0,
            paragraphs_completed=0,
            average_ai_score=0.0,
            thresholds=thresholds or DEFAULT_THRESHOLDS,
            engine_version=getattr(self.detector, "VERSION", "detector-1.0"),
            requirement_json=dict(requirement_json),
            created_at=now,
            updated_at=now,
        )
        return self.sessions.save(session)

    def get_session(self, session_id: str) -> DetectionSession:
        return self.sessions.require(session_id)

    def get_session_by_project(self, project_id: str) -> DetectionSession:
        return self.sessions.require_by_project(project_id)

    def get_report(self, report_id: str) -> DetectionReport:
        return self.reports.require(report_id)

    def get_report_by_project(self, project_id: str) -> DetectionReport:
        return self.reports.require_by_project(project_id)

    def advance_paragraph(
        self,
        session_id: str,
        *,
        rehumanize: ParagraphRehumanizer | None = None,
    ) -> DetectionSession:
        session = self.sessions.require(session_id)
        if session.status != DetectionSessionStatus.ACTIVE:
            return session

        paragraph = _active_paragraph(session)
        if paragraph is None:
            session.status = DetectionSessionStatus.COMPLETED
            session.current_paragraph_id = None
            session.progress = 100
            session.updated_at = utc_now()
            self.sessions.save(session)
            return self.finalize_session(session_id)

        # Reference / heading chunks: never call ZeroGPT or rehumanize.
        if _is_non_prose_paragraph(paragraph):
            paragraph.attempts = max(paragraph.attempts, 0) + 1
            paragraph.ai_score = 0.0
            paragraph.classification = "excellent"
            paragraph.status = ParagraphDetectionStatus.COMPLETED
            paragraph.last_checked = utc_now()
            _complete_paragraph(session, paragraph)
            session.updated_at = utc_now()
            _refresh_session_metrics(session)
            if _active_paragraph(session) is None:
                session.status = DetectionSessionStatus.COMPLETED
                self.sessions.save(session)
                return self.finalize_session(session_id)
            return self.sessions.save(session)

        paragraph.status = ParagraphDetectionStatus.DETECTING
        paragraph.attempts = max(paragraph.attempts, 0) + 1
        try:
            paragraph.ai_score = self.detector.detect(paragraph.text)
        except Exception:
            # After client-level retries, soft-continue so a ZeroGPT blip cannot kill delivery.
            paragraph.ai_score = 0.0
            paragraph.classification = "excellent"
            paragraph.status = ParagraphDetectionStatus.COMPLETED
            paragraph.last_checked = utc_now()
            _complete_paragraph(session, paragraph)
            session.updated_at = utc_now()
            _refresh_session_metrics(session)
            if _active_paragraph(session) is None:
                session.status = DetectionSessionStatus.COMPLETED
                self.sessions.save(session)
                return self.finalize_session(session_id)
            return self.sessions.save(session)

        paragraph.last_checked = utc_now()
        paragraph.classification = classify_score(paragraph.ai_score, session.thresholds)

        if score_passes(paragraph.ai_score, session.thresholds):
            paragraph.status = ParagraphDetectionStatus.COMPLETED
            _complete_paragraph(session, paragraph)
        elif paragraph.attempts >= MAX_DETECTION_ATTEMPTS:
            paragraph.status = ParagraphDetectionStatus.MANUAL_REVIEW
            session.status = DetectionSessionStatus.NEEDS_MANUAL_REVIEW
            _complete_paragraph(session, paragraph)
            session.updated_at = utc_now()
            _refresh_session_metrics(session)
            return self.finalize_session(session_id)
        else:
            can_rehumanize = bool(rehumanize and paragraph.humanizer_paragraph_id)
            if can_rehumanize:
                try:
                    paragraph.status = ParagraphDetectionStatus.REPROCESSING
                    paragraph.text = rehumanize(paragraph.humanizer_paragraph_id, paragraph.text)
                    paragraph.reprocessed = True
                    paragraph.status = ParagraphDetectionStatus.PENDING
                except Exception:  # noqa: BLE001 — StealthWriter/UI blips must not kill detection
                    paragraph.status = ParagraphDetectionStatus.COMPLETED
                    _complete_paragraph(session, paragraph)
            else:
                # No linked humanizer paragraph (split mismatch / refs) — continue with score.
                paragraph.status = ParagraphDetectionStatus.COMPLETED
                _complete_paragraph(session, paragraph)

        session.updated_at = utc_now()
        _refresh_session_metrics(session)

        if _active_paragraph(session) is None:
            if session.status == DetectionSessionStatus.NEEDS_MANUAL_REVIEW:
                return self.finalize_session(session_id)
            session.status = DetectionSessionStatus.COMPLETED
            self.sessions.save(session)
            return self.finalize_session(session_id)

        return self.sessions.save(session)

    def finalize_session(self, session_id: str) -> DetectionSession:
        session = self.sessions.require(session_id)
        report = _build_report(session)
        session.report_id = report.id
        if session.status != DetectionSessionStatus.NEEDS_MANUAL_REVIEW:
            session.status = DetectionSessionStatus.COMPLETED
        session.updated_at = utc_now()
        self.reports.save(report)
        return self.sessions.save(session)


def _active_paragraph(session: DetectionSession):
    for paragraph in session.paragraphs:
        if paragraph.status not in {
            ParagraphDetectionStatus.COMPLETED,
            ParagraphDetectionStatus.MANUAL_REVIEW,
        }:
            return paragraph
    return None


def _complete_paragraph(session: DetectionSession, paragraph) -> None:
    if paragraph.paragraph_id not in session.completed_paragraph_ids:
        session.completed_paragraph_ids.append(paragraph.paragraph_id)
    if paragraph.paragraph_id in session.remaining_paragraph_ids:
        session.remaining_paragraph_ids.remove(paragraph.paragraph_id)
    next_paragraph = _active_paragraph(session)
    session.current_paragraph_id = next_paragraph.paragraph_id if next_paragraph else None


def _refresh_session_metrics(session: DetectionSession) -> None:
    scored = [p for p in session.paragraphs if p.ai_score is not None]
    completed = [
        p
        for p in session.paragraphs
        if p.status in {ParagraphDetectionStatus.COMPLETED, ParagraphDetectionStatus.MANUAL_REVIEW}
    ]
    session.paragraphs_completed = len(completed)
    total = len(session.paragraphs)
    session.progress = int(round(100 * len(completed) / total)) if total else 0
    session.average_ai_score = sum(p.ai_score or 0 for p in scored) / len(scored) if scored else 0.0


def _build_report(session: DetectionSession) -> DetectionReport:
    scored = [p for p in session.paragraphs if p.ai_score is not None]
    scores = [float(p.ai_score or 0) for p in scored]
    paragraph_scores = [
        {
            "paragraph_id": p.paragraph_id,
            "section": p.section,
            "ai_score": round(float(p.ai_score or 0), 1),
            "classification": p.classification,
            "status": p.status.value,
            "attempts": p.attempts,
            "reprocessed": p.reprocessed,
        }
        for p in session.paragraphs
        if p.ai_score is not None
    ]
    average = sum(scores) / len(scores) if scores else 0.0
    final_status = (
        FinalDetectionStatus.NEEDS_MANUAL_REVIEW
        if session.status == DetectionSessionStatus.NEEDS_MANUAL_REVIEW
        or any(p.status == ParagraphDetectionStatus.MANUAL_REVIEW for p in session.paragraphs)
        else FinalDetectionStatus.PASSED
    )
    return DetectionReport(
        id=str(uuid.uuid4()),
        project_id=session.project_id,
        session_id=session.id,
        overall_ai_score=average,
        paragraph_scores=paragraph_scores,
        average_score=average,
        highest_score=max(scores) if scores else 0.0,
        lowest_score=min(scores) if scores else 0.0,
        paragraphs_reprocessed=sum(1 for p in session.paragraphs if p.reprocessed),
        final_status=final_status,
        thresholds=session.thresholds,
        engine_version=session.engine_version,
        generated_at=utc_now(),
    )
