"""Humanizer Engine service — one paragraph at a time."""

from __future__ import annotations

import uuid
from typing import Any

from services.assignment_pipeline.models import utc_now
from services.humanizer_engine.constants import MIN_HUMANIZE_CHARS
from services.humanizer_engine.merge import merge_session_to_humanized_draft
from services.humanizer_engine.mock_humanizer import MockTextHumanizer, TextHumanizer
from services.humanizer_engine.mock_validator import (
    MockParagraphValidator,
    ParagraphValidator,
    ZeroGPTParagraphValidator,
)
from services.humanizer_engine.models import (
    MAX_PARAGRAPH_ATTEMPTS,
    HumanizedDraft,
    HumanizerEngineInput,
    HumanizerParagraphStatus,
    HumanizerSession,
    HumanizerSessionStatus,
    count_words,
)
from services.humanizer_engine.paragraph_parser import split_draft_into_paragraphs
from services.humanizer_engine.store import HumanizedDraftStore, HumanizerSessionStore


class HumanizerEngineService:
    def __init__(
        self,
        session_store: HumanizerSessionStore | None = None,
        draft_store: HumanizedDraftStore | None = None,
        humanizer: TextHumanizer | None = None,
        validator: ParagraphValidator | None = None,
    ) -> None:
        self.sessions = session_store or HumanizerSessionStore()
        self.drafts = draft_store or HumanizedDraftStore()
        self.humanizer = humanizer or MockTextHumanizer()
        self.validator = validator or MockParagraphValidator()

    def create_session(
        self,
        *,
        draft: dict[str, Any],
        requirement_json: dict[str, Any],
        blueprint: dict[str, Any],
        project_id: str | None = None,
    ) -> HumanizerSession:
        if not draft or not requirement_json or not blueprint:
            raise ValueError("draft, requirement_json, and blueprint are required")

        paragraphs = split_draft_into_paragraphs(str(draft.get("content") or ""), blueprint)
        if not paragraphs:
            raise ValueError("Draft has no paragraphs to humanize")

        now = utc_now()
        session = HumanizerSession(
            id=str(uuid.uuid4()),
            project_id=project_id,
            source_draft_id=str(draft.get("id") or ""),
            source_draft_version=int(draft.get("version") or 1),
            paragraphs=paragraphs,
            current_paragraph_id=paragraphs[0].paragraph_id,
            completed_paragraph_ids=[],
            remaining_paragraph_ids=[paragraph.paragraph_id for paragraph in paragraphs],
            progress=0,
            paragraphs_processed=0,
            average_ai_reduction=0.0,
            estimated_remaining_time=_estimate_remaining(paragraphs),
            status=HumanizerSessionStatus.ACTIVE,
            engine_version=getattr(self.humanizer, "VERSION", "mock-1.0"),
            requirement_json=dict(requirement_json),
            blueprint=dict(blueprint),
            created_at=now,
            updated_at=now,
        )
        return self.sessions.save(session)

    def get_session(self, session_id: str) -> HumanizerSession:
        return self.sessions.require(session_id)

    def get_session_by_project(self, project_id: str) -> HumanizerSession:
        return self.sessions.require_by_project(project_id)

    def get_humanized_draft(self, draft_id: str) -> HumanizedDraft:
        return self.drafts.require(draft_id)

    def get_humanized_draft_by_project(self, project_id: str) -> HumanizedDraft:
        return self.drafts.require_by_project(project_id)

    def advance_paragraph(self, session_id: str) -> HumanizerSession:
        """Humanize and validate exactly one paragraph cycle."""
        session = self.sessions.require(session_id)
        if session.status != HumanizerSessionStatus.ACTIVE:
            return session

        paragraph = _active_paragraph(session)
        if paragraph is None:
            session.status = HumanizerSessionStatus.COMPLETED
            session.current_paragraph_id = None
            session.progress = 100
            session.estimated_remaining_time = "0 minutes"
            session.updated_at = utc_now()
            return self.sessions.save(session)

        tone = str(
            session.requirement_json.get("writing_tone")
            or session.blueprint.get("academic_tone")
            or "Formal academic prose"
        )

        if paragraph.status in {HumanizerParagraphStatus.PENDING, HumanizerParagraphStatus.REVISION}:
            try:
                paragraph = self._humanize_paragraph(paragraph, academic_tone=tone)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Humanizer failed: {exc}") from exc

        if paragraph.status == HumanizerParagraphStatus.VALIDATING:
            paragraph = self._validate_paragraph(paragraph)

        if paragraph.status == HumanizerParagraphStatus.FAILED:
            paragraph.humanized_text = paragraph.humanized_text or paragraph.original_text
            paragraph.status = HumanizerParagraphStatus.COMPLETED

        if paragraph.status == HumanizerParagraphStatus.COMPLETED:
            _complete_paragraph_in_session(session, paragraph)

        session.updated_at = utc_now()
        _refresh_session_metrics(session)
        return self.sessions.save(session)

    def merge_humanized_draft(self, session_id: str, *, title: str | None = None) -> HumanizedDraft:
        session = self.sessions.require(session_id)
        incomplete = [p for p in session.paragraphs if p.status != HumanizerParagraphStatus.COMPLETED]
        if incomplete:
            raise ValueError("All paragraphs must be completed before merge")

        draft = merge_session_to_humanized_draft(session, title=title)
        session.status = HumanizerSessionStatus.MERGED
        session.humanized_draft_id = draft.id
        session.updated_at = utc_now()
        self.sessions.save(session)
        return self.drafts.save(draft)

    def rehumanize_paragraph_for_detection(self, session_id: str, paragraph_id: str) -> str:
        """Re-humanize a single paragraph when AI detection fails. Updates merged draft if present."""
        session = self.sessions.require(session_id)
        paragraph = session.paragraph_by_id(paragraph_id)
        tone = str(
            session.requirement_json.get("writing_tone")
            or session.blueprint.get("academic_tone")
            or "Formal academic prose"
        )
        source = paragraph.humanized_text or paragraph.original_text
        paragraph.humanized_text = self.humanizer.humanize(source, academic_tone=tone)
        paragraph.ai_score_after = self.humanizer.estimate_ai_score(paragraph.humanized_text)
        paragraph.status = HumanizerParagraphStatus.COMPLETED
        session.updated_at = utc_now()
        self.sessions.save(session)

        if session.humanized_draft_id:
            draft = self.drafts.require(session.humanized_draft_id)
            updated = merge_session_to_humanized_draft(session, title=draft.title)
            updated.id = draft.id
            updated.version = draft.version
            self.drafts.save(updated)

        return paragraph.humanized_text

    def refresh_revised_sections(
        self,
        session_id: str,
        *,
        draft_content: str,
        blueprint: dict[str, Any],
        section_names: list[str],
    ) -> HumanizerSession:
        """Re-queue only paragraphs whose sections were revised in the writer draft."""
        session = self.sessions.require(session_id)
        if not section_names:
            return session

        new_paragraphs = split_draft_into_paragraphs(str(draft_content), blueprint)
        targets = {name.strip().lower() for name in section_names if name}

        def section_matches(section: str) -> bool:
            normalized = section.strip().lower()
            return any(target in normalized or normalized in target for target in targets)

        for paragraph in session.paragraphs:
            if not section_matches(paragraph.section):
                continue
            source = _source_text_for_section(new_paragraphs, paragraph.section)
            if source:
                paragraph.original_text = source
            paragraph.humanized_text = ""
            paragraph.status = HumanizerParagraphStatus.PENDING
            paragraph.attempts = 0
            paragraph.last_validation = None
            session.completed_paragraph_ids = [
                pid for pid in session.completed_paragraph_ids if pid != paragraph.paragraph_id
            ]
            if paragraph.paragraph_id not in session.remaining_paragraph_ids:
                session.remaining_paragraph_ids.append(paragraph.paragraph_id)

        session.status = HumanizerSessionStatus.ACTIVE
        next_paragraph = _active_paragraph(session)
        session.current_paragraph_id = next_paragraph.paragraph_id if next_paragraph else None
        session.updated_at = utc_now()
        _refresh_session_metrics(session)
        return self.sessions.save(session)

    def _humanize_paragraph(self, paragraph, *, academic_tone: str):
        if paragraph.status == HumanizerParagraphStatus.REVISION:
            paragraph.attempts += 1
        else:
            paragraph.attempts = max(paragraph.attempts, 0) + 1

        paragraph.status = HumanizerParagraphStatus.HUMANIZING
        source = (paragraph.original_text or "").strip()
        if paragraph.ai_score_before is None:
            paragraph.ai_score_before = self._quick_ai_score(source)

        if _should_passthrough_humanization(source):
            paragraph.humanized_text = source
            paragraph.ai_score_after = paragraph.ai_score_before
            paragraph.status = HumanizerParagraphStatus.VALIDATING
            return paragraph

        paragraph.humanized_text = self.humanizer.humanize(
            source,
            academic_tone=academic_tone,
        )
        paragraph.ai_score_after = self._quick_ai_score(paragraph.humanized_text)
        paragraph.status = HumanizerParagraphStatus.VALIDATING
        return paragraph

    def _quick_ai_score(self, text: str) -> int:
        """Fast heuristic score for pipeline metrics (skip slow detect API per batch)."""
        if hasattr(self.humanizer, "_fallback_scorer"):
            return int(self.humanizer._fallback_scorer.estimate_ai_score(text))
        return int(self.humanizer.estimate_ai_score(text))

    def _validate_paragraph(self, paragraph):
        validation = self.validator.validate(
            original_text=paragraph.original_text,
            humanized_text=paragraph.humanized_text,
            section=paragraph.section,
            attempt=paragraph.attempts,
        )
        paragraph.last_validation = validation
        if validation.passed:
            paragraph.status = HumanizerParagraphStatus.COMPLETED
        elif paragraph.attempts >= MAX_PARAGRAPH_ATTEMPTS:
            paragraph.status = HumanizerParagraphStatus.COMPLETED
            paragraph.humanized_text = paragraph.humanized_text or paragraph.original_text
        else:
            paragraph.status = HumanizerParagraphStatus.REVISION
        return paragraph


def _should_passthrough_humanization(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if stripped.startswith("## "):
        return True
    return len(stripped) < MIN_HUMANIZE_CHARS


def _active_paragraph(session: HumanizerSession):
    for paragraph in session.paragraphs:
        if paragraph.status in {
            HumanizerParagraphStatus.FAILED,
            HumanizerParagraphStatus.COMPLETED,
        }:
            continue
        return paragraph
    return None


def _complete_paragraph_in_session(session: HumanizerSession, paragraph) -> None:
    if paragraph.paragraph_id not in session.completed_paragraph_ids:
        session.completed_paragraph_ids.append(paragraph.paragraph_id)
    if paragraph.paragraph_id in session.remaining_paragraph_ids:
        session.remaining_paragraph_ids.remove(paragraph.paragraph_id)

    next_paragraph = _active_paragraph(session)
    session.current_paragraph_id = next_paragraph.paragraph_id if next_paragraph else None
    if next_paragraph is None:
        session.status = HumanizerSessionStatus.COMPLETED


def _refresh_session_metrics(session: HumanizerSession) -> None:
    completed = [p for p in session.paragraphs if p.status == HumanizerParagraphStatus.COMPLETED]
    total = len(session.paragraphs)
    session.paragraphs_processed = len(completed)
    session.progress = int(round(100 * len(completed) / total)) if total else 0

    reductions: list[float] = []
    for paragraph in completed:
        if paragraph.ai_score_before is not None and paragraph.ai_score_after is not None:
            reductions.append(max(0.0, paragraph.ai_score_before - paragraph.ai_score_after))
    session.average_ai_reduction = sum(reductions) / len(reductions) if reductions else 0.0

    remaining = [p for p in session.paragraphs if p.status != HumanizerParagraphStatus.COMPLETED]
    session.estimated_remaining_time = _estimate_remaining(remaining)


def _estimate_remaining(paragraphs) -> str:
    if not paragraphs:
        return "0 minutes"
    minutes = max(2, len(paragraphs) * 4)
    return f"{minutes} minutes"


def _source_text_for_section(paragraphs, section_name: str) -> str | None:
    target = section_name.strip().lower()
    for paragraph in paragraphs:
        section = str(paragraph.section or "").strip().lower()
        if target in section or section in target:
            return str(paragraph.original_text or "")
    return None
