"""Revision Engine service — section-level fixes from Review Reports only."""

from __future__ import annotations

from typing import Any

from services.assignment_pipeline.models import utc_now
from services.revision_engine.mock_reviser import MockSectionReviser, SectionReviser
from services.revision_engine.models import MAX_REVISION_ATTEMPTS, RevisionEngineInput, RevisionHistory, RevisionResult
from services.revision_engine.store import RevisionHistoryStore
from services.writer_engine.models import Draft
from services.writer_engine.store import DraftStore


class RevisionEngineService:
    def __init__(
        self,
        history_store: RevisionHistoryStore | None = None,
        draft_store: DraftStore | None = None,
        reviser: SectionReviser | None = None,
    ) -> None:
        self.history = history_store or RevisionHistoryStore()
        self.drafts = draft_store or DraftStore()
        self.reviser = reviser or MockSectionReviser()

    def register_initial_draft(self, draft: Draft) -> RevisionHistory:
        return self.history.register_initial_draft(draft)

    def revise_draft(
        self,
        *,
        requirement_json: dict[str, Any],
        research_plan: dict[str, Any],
        blueprint: dict[str, Any],
        draft: dict[str, Any],
        review_report: dict[str, Any],
        project_id: str | None = None,
    ) -> RevisionResult:
        if project_id and not self.history.can_revise(project_id):
            raise ValueError("Maximum automatic revision attempts reached")

        for key, value in {
            "requirement_json": requirement_json,
            "research_plan": research_plan,
            "blueprint": blueprint,
            "draft": draft,
            "review_report": review_report,
        }.items():
            if not value:
                raise ValueError(f"{key} is required")

        if review_report.get("passed"):
            raise ValueError("Review report passed — revision is not required")

        if project_id:
            history = self.history.get(project_id)
            if history is None or not history.versions:
                self.history.register_initial_draft(self._save_draft(dict(draft)))

        payload = RevisionEngineInput(
            requirement_json=dict(requirement_json),
            research_plan=dict(research_plan),
            blueprint=dict(blueprint),
            draft=dict(draft),
            review_report=dict(review_report),
            project_id=project_id,
        )
        result = self.reviser.revise(payload)

        if project_id:
            history = self.history.get(project_id)
            attempt_number = (history.revision_attempts if history else 0) + 1
        else:
            attempt_number = 1
        result.attempt_number = attempt_number

        saved_draft = self._save_draft(result.draft)
        if project_id:
            self.history.append_revision(
                project_id,
                draft=saved_draft,
                changes=result.changes,
                attempt_number=attempt_number,
            )
        result.draft = saved_draft.to_dict()
        return result

    def get_history(self, project_id: str) -> RevisionHistory:
        return self.history.require(project_id)

    def get_history_or_empty(self, project_id: str) -> RevisionHistory:
        return self.history.ensure(project_id)

    def update_review_score(self, project_id: str, *, version: int, review_score: int) -> RevisionHistory:
        return self.history.update_review_score(project_id, version=version, review_score=review_score)

    def mark_needs_manual_review(self, project_id: str) -> RevisionHistory:
        return self.history.mark_needs_manual_review(project_id)

    def restore_version(self, project_id: str, version: int) -> Draft:
        record = self.history.restore_version(project_id, version)
        session_id = ""
        current = self.drafts.get_by_project(project_id)
        if current:
            session_id = current.session_id

        restored = Draft(
            id=record.draft_id,
            project_id=project_id,
            session_id=session_id,
            title=record.title,
            content=record.content,
            total_words=record.total_words,
            version=record.version,
            created_at=record.created_at or utc_now(),
        )
        return self.drafts.save(restored)

    def _save_draft(self, draft_data: dict[str, Any]) -> Draft:
        created_at = None
        if draft_data.get("created_at"):
            created_at = utc_now()
        draft = Draft(
            id=str(draft_data["id"]),
            project_id=draft_data.get("project_id"),
            session_id=str(draft_data.get("session_id") or ""),
            title=str(draft_data.get("title") or "Assignment Draft"),
            content=str(draft_data.get("content") or ""),
            total_words=int(draft_data.get("total_words") or 0),
            version=int(draft_data.get("version") or 1),
            created_at=created_at,
        )
        if draft.project_id:
            existing = self.drafts.get_by_project(draft.project_id)
            if existing and not draft.session_id:
                draft.session_id = existing.session_id
        return self.drafts.save(draft)
