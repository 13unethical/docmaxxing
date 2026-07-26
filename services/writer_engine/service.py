"""Writer Engine service — one section at a time."""

from __future__ import annotations

import uuid
from typing import Any

from services.assignment_pipeline.models import utc_now
from services.writer_engine.llm_writer import LLMSectionWriter
from services.writer_engine.merge import merge_session_to_draft
from services.writer_engine.mock_writer import SectionWriter
from services.writer_engine.section_review_engine import GeminiSectionReviewer, SectionReviewer
from services.writer_engine.models import (
    Draft,
    WriterEngineInput,
    WriterSection,
    WriterSectionStatus,
    WriterSession,
    WriterSessionStatus,
    count_words,
)
from services.writer_engine.store import DraftStore, WriterSessionStore


class WriterEngineService:
    def __init__(
        self,
        session_store: WriterSessionStore | None = None,
        draft_store: DraftStore | None = None,
        writer: SectionWriter | None = None,
        reviewer: SectionReviewer | None = None,
    ) -> None:
        self.sessions = session_store or WriterSessionStore()
        self.drafts = draft_store or DraftStore()
        self.writer = writer or LLMSectionWriter()
        self.reviewer = reviewer or GeminiSectionReviewer()

    def create_session(
        self,
        *,
        requirement_json: dict[str, Any],
        research_plan: dict[str, Any],
        blueprint: dict[str, Any],
        project_id: str | None = None,
    ) -> WriterSession:
        if not requirement_json or not research_plan or not blueprint:
            raise ValueError("requirement_json, research_plan, and blueprint are required")

        queue_ids = list(blueprint.get("writing_order") or [])
        blueprint_sections = {
            str(item.get("id")): item for item in (blueprint.get("sections") or []) if item.get("id")
        }
        if not queue_ids:
            queue_ids = [
                str(item.get("id"))
                for item in (blueprint.get("sections") or [])
                if int(item.get("estimated_words") or 0) > 0
                and "reference" not in str(item.get("title", "")).lower()
                and "cover" not in str(item.get("title", "")).lower()
            ]

        sections: list[WriterSection] = []
        # Prefer AssignmentSpec word targets when present in requirement_json artifact-compatible form.
        from services.assignment_spec import build_assignment_spec

        try:
            spec = build_assignment_spec(requirement_json, project_id=project_id)
            spec_targets = {s.title.strip().lower(): s.target_words for s in spec.writable_sections}
        except Exception:  # noqa: BLE001
            spec_targets = {}

        for section_id in queue_ids:
            item = blueprint_sections.get(section_id, {})
            title = str(item.get("title") or section_id)
            estimated = int(item.get("estimated_words") or 0)
            if title.strip().lower() in spec_targets:
                estimated = int(spec_targets[title.strip().lower()])
            sections.append(
                WriterSection(
                    id=section_id,
                    title=title,
                    objective=str(item.get("objective") or ""),
                    estimated_words=estimated,
                )
            )

        if not sections:
            raise ValueError("Blueprint writing queue is empty")

        now = utc_now()
        session = WriterSession(
            id=str(uuid.uuid4()),
            project_id=project_id,
            sections=sections,
            current_section_id=sections[0].id,
            completed_section_ids=[],
            remaining_section_ids=[section.id for section in sections],
            progress=0,
            total_words_written=0,
            estimated_remaining_time=_estimate_remaining(sections),
            status=WriterSessionStatus.ACTIVE,
            engine_version=getattr(self.writer, "VERSION", "llm-writer-1.0"),
            requirement_json=dict(requirement_json),
            research_plan=dict(research_plan),
            blueprint=dict(blueprint),
            created_at=now,
            updated_at=now,
        )
        return self.sessions.save(session)

    def get_session(self, session_id: str) -> WriterSession:
        return self.sessions.require(session_id)

    def get_session_by_project(self, project_id: str) -> WriterSession:
        return self.sessions.require_by_project(project_id)

    def get_draft(self, draft_id: str) -> Draft:
        return self.drafts.require(draft_id)

    def get_draft_by_project(self, project_id: str) -> Draft:
        return self.drafts.require_by_project(project_id)

    def advance_section(self, session_id: str) -> WriterSession:
        """Write and review exactly one section cycle. Never processes multiple sections."""
        session = self.sessions.require(session_id)
        if session.status != WriterSessionStatus.ACTIVE:
            return session

        section = _active_section(session)
        if section is None:
            session.status = WriterSessionStatus.COMPLETED
            session.current_section_id = None
            session.progress = 100
            session.estimated_remaining_time = "0 minutes"
            session.updated_at = utc_now()
            return self.sessions.save(session)

        payload = WriterEngineInput(
            requirement_json=session.requirement_json,
            research_plan=session.research_plan,
            blueprint=session.blueprint,
            project_id=session.project_id,
        )

        # WRITING means a previous attempt died mid-call — rewrite instead of no-op.
        if section.status in {
            WriterSectionStatus.PENDING,
            WriterSectionStatus.REVISION,
            WriterSectionStatus.WRITING,
        }:
            section = self._write_section(
                session,
                section,
                payload,
                revision=section.status == WriterSectionStatus.REVISION,
            )

        if section.status == WriterSectionStatus.SECTION_REVIEW:
            section = self._review_section(session, section, payload)
            if section.status == WriterSectionStatus.REVISION:
                # Automatic one-time regeneration only for this section.
                section = self._write_section(session, section, payload, revision=True)
                section = self._review_section(session, section, payload)
                if section.status == WriterSectionStatus.REVISION:
                    if section.last_review:
                        section.last_review.needs_manual_review = True
                        section.last_review.review_message = (
                            (section.last_review.review_message + " ").strip()
                            + "Section still below threshold after one automatic regeneration."
                        ).strip()
                        section.last_review.warnings = list(section.last_review.warnings) + [
                            "needs_manual_review=true"
                        ]
                    section.status = WriterSectionStatus.COMPLETED
                    section.completed_at = utc_now()

        if section.status == WriterSectionStatus.COMPLETED:
            _complete_section_in_session(session, section)
        elif session.status == WriterSessionStatus.ACTIVE:
            # Never leave an active section in a silent no-op state.
            section.status = WriterSectionStatus.COMPLETED
            section.completed_at = section.completed_at or utc_now()
            section.warnings = list(section.warnings) + [
                "Forced section completion after unexpected writer state"
            ]
            _complete_section_in_session(session, section)

        session.updated_at = utc_now()
        _refresh_session_metrics(session)
        return self.sessions.save(session)

    def revise_section(self, session_id: str, section_id: str | None = None) -> WriterSession:
        """Regenerate only the requested section."""
        session = self.sessions.require(session_id)
        target_id = section_id or session.current_section_id
        if not target_id:
            raise ValueError("No section available for revision")
        section = session.section_by_id(target_id)
        if section.status != WriterSectionStatus.REVISION:
            raise ValueError("Section is not awaiting revision")
        session.current_section_id = section.id
        session.updated_at = utc_now()
        self.sessions.save(session)
        return self.advance_section(session_id)

    def merge_draft(self, session_id: str, *, title: str | None = None) -> Draft:
        from services.assignment_spec import (
            build_assignment_spec,
            needs_expansion,
            section_bounds,
            validate_draft_against_spec,
        )

        session = self.sessions.require(session_id)
        incomplete = [s for s in session.sections if s.status != WriterSectionStatus.COMPLETED]
        if incomplete:
            raise ValueError("All sections must be completed before merge")

        # Auto-clamp each section into its ±10% band before merge (trim overages; flag shorts).
        short = []
        for section in session.sections:
            target = int(section.estimated_words or 0)
            if target <= 0:
                continue
            actual = count_words(section.generated_text)
            if needs_expansion(actual, target):
                short.append(f"{section.title}: {actual}/{target}")
                continue
            _lo, hi = section_bounds(target)
            if actual > hi:
                words = section.generated_text.split()
                trimmed = " ".join(words[:hi]).rstrip(" ,;:")
                if trimmed and trimmed[-1] not in ".!?":
                    trimmed += "."
                section.generated_text = trimmed
                section.warnings = list(section.warnings) + [
                    f"Auto-trimmed from {actual} to {count_words(trimmed)} words for ±10% budget"
                ]
        if short:
            raise ValueError(
                "Cannot merge: sections below hard word budget — "
                + "; ".join(short)
            )

        draft = merge_session_to_draft(session, title=title)
        try:
            spec = build_assignment_spec(session.requirement_json, project_id=session.project_id)
            session_target = sum(int(s.estimated_words or 0) for s in session.sections)
            if session_target > 0:
                spec.total_word_target = session_target
            result = validate_draft_against_spec(content=draft.content, spec=spec)
            if spec.total_word_target and not result.total_passed:
                # Final proportional trim across writable sections, then re-merge.
                if result.total_words > spec.max_total_words:
                    # Reserve words consumed by markdown ## headings in the merged draft.
                    heading_overhead = sum(
                        count_words(s.title) for s in session.sections if int(s.estimated_words or 0) > 0
                    )
                    # Small safety margin so rounding / tokenizer drift does not leave us 1–20 over.
                    body_cap = max(1, spec.max_total_words - heading_overhead - 8)
                    _clamp_session_to_total(session, body_cap)
                    draft = merge_session_to_draft(session, title=title)
                    result = validate_draft_against_spec(content=draft.content, spec=spec)

                # If still over: Gemini deletes the minimum safe excess (logic/rubric-preserving).
                if result.total_words > spec.max_total_words:
                    from services.writer_engine.gemini_trim import (
                        apply_trimmed_markdown_to_session,
                        gemini_trim_markdown_to_budget,
                    )

                    trimmed = gemini_trim_markdown_to_budget(
                        draft.content,
                        spec=spec,
                        current_words=result.total_words,
                    )
                    if trimmed and apply_trimmed_markdown_to_session(session, trimmed):
                        draft = merge_session_to_draft(session, title=title)
                        result = validate_draft_against_spec(content=draft.content, spec=spec)
                        # One more hard clamp if Gemini landed just slightly over max.
                        if result.total_words > spec.max_total_words:
                            heading_overhead = sum(
                                count_words(s.title)
                                for s in session.sections
                                if int(s.estimated_words or 0) > 0
                            )
                            body_cap = max(1, spec.max_total_words - heading_overhead - 4)
                            _clamp_session_to_total(session, body_cap)
                            draft = merge_session_to_draft(session, title=title)
                            result = validate_draft_against_spec(content=draft.content, spec=spec)

                if not result.total_passed:
                    raise ValueError(
                        f"Cannot merge: total words {result.total_words} outside "
                        f"{spec.min_total_words}-{spec.max_total_words} "
                        f"(target {spec.total_word_target})"
                    )
        except ValueError:
            raise
        except Exception:  # noqa: BLE001
            pass

        session.status = WriterSessionStatus.MERGED
        session.draft_id = draft.id
        session.updated_at = utc_now()
        self.sessions.save(session)
        return self.drafts.save(draft)

    def _write_section(
        self,
        session: WriterSession,
        section: WriterSection,
        payload: WriterEngineInput,
        *,
        revision: bool,
    ) -> WriterSection:
        if revision:
            section.revision_count += 1
        section.status = WriterSectionStatus.WRITING
        section.started_at = section.started_at or utc_now()
        text = self.writer.write_section(section=section, payload=payload, revision=revision)
        section.generated_text = text
        section.status = WriterSectionStatus.SECTION_REVIEW
        session.current_section_id = section.id
        return section

    def _review_section(
        self,
        session: WriterSession,
        section: WriterSection,
        payload: WriterEngineInput,
    ) -> WriterSection:
        from services.assignment_spec import needs_expansion

        review = self.reviewer.review_section(section=section, payload=payload)
        section.last_review = review
        section.review_score = review.score
        under_budget = needs_expansion(count_words(section.generated_text), int(section.estimated_words or 0))
        if under_budget:
            review.needs_revision = True
            review.passed = False
            review.warnings = list(review.warnings) + [
                f"HARD_WORD_BUDGET_FAIL: {count_words(section.generated_text)}/"
                f"{section.estimated_words} words"
            ]
            section.warnings = list(section.warnings) + review.warnings[-1:]
        if not review.needs_revision:
            section.status = WriterSectionStatus.COMPLETED
            section.completed_at = utc_now()
        else:
            section.status = WriterSectionStatus.REVISION
        return section


def _active_section(session: WriterSession) -> WriterSection | None:
    for section in session.sections:
        if section.status != WriterSectionStatus.COMPLETED:
            return section
    return None


def _complete_section_in_session(session: WriterSession, section: WriterSection) -> None:
    if section.id not in session.completed_section_ids:
        session.completed_section_ids.append(section.id)
    if section.id in session.remaining_section_ids:
        session.remaining_section_ids.remove(section.id)

    next_section = _active_section(session)
    session.current_section_id = next_section.id if next_section else None
    if next_section is None:
        session.status = WriterSessionStatus.COMPLETED


def _refresh_session_metrics(session: WriterSession) -> None:
    completed_by_status = [
        section for section in session.sections if section.status == WriterSectionStatus.COMPLETED
    ]
    # Keep completed_section_ids aligned with real section statuses.
    session.completed_section_ids = [section.id for section in completed_by_status]
    session.remaining_section_ids = [
        section.id for section in session.sections if section.status != WriterSectionStatus.COMPLETED
    ]
    completed = len(session.completed_section_ids)
    total = len(session.sections)
    session.progress = int(round(100 * completed / total)) if total else 0
    if completed and session.progress == 0:
        session.progress = 1
    if completed == total and total > 0:
        session.progress = 100
        if session.status == WriterSessionStatus.ACTIVE:
            session.status = WriterSessionStatus.COMPLETED
            session.current_section_id = None
    elif session.status == WriterSessionStatus.COMPLETED and completed < total:
        # Repair inconsistent snapshots that claim completed too early.
        session.status = WriterSessionStatus.ACTIVE
        if session.current_section_id is None and session.remaining_section_ids:
            session.current_section_id = session.remaining_section_ids[0]
    session.total_words_written = sum(count_words(section.generated_text) for section in session.sections)
    remaining = [section for section in session.sections if section.status != WriterSectionStatus.COMPLETED]
    session.estimated_remaining_time = _estimate_remaining(remaining)


def _estimate_remaining(sections: list[WriterSection]) -> str:
    if not sections:
        return "0 minutes"
    minutes = max(5, sum(max(section.estimated_words, 120) for section in sections) // 45)
    return f"{minutes} minutes"


def _clamp_session_to_total(session: WriterSession, max_total: int) -> None:
    """Proportionally trim writable sections so merged body fits max_total words."""
    writable = [s for s in session.sections if int(s.estimated_words or 0) > 0 and s.generated_text.strip()]
    if not writable or max_total <= 0:
        return
    current = sum(count_words(s.generated_text) for s in writable)
    if current <= max_total:
        return
    # Allocate by section targets, then trim each to its share.
    target_sum = sum(int(s.estimated_words or 0) for s in writable) or current
    remaining_budget = max_total
    for index, section in enumerate(writable):
        share = int(round(max_total * (int(section.estimated_words or 0) / target_sum)))
        if index == len(writable) - 1:
            share = remaining_budget
        share = max(1, share)
        remaining_budget = max(0, remaining_budget - share)
        words = section.generated_text.split()
        if len(words) <= share:
            continue
        trimmed = " ".join(words[:share]).rstrip(" ,;:")
        if trimmed and trimmed[-1] not in ".!?":
            trimmed += "."
        section.generated_text = trimmed
        section.warnings = list(section.warnings) + [
            f"Auto-trimmed to fit total word budget (cap {max_total})"
        ]
