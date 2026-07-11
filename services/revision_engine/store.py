"""In-memory revision history and draft version storage."""

from __future__ import annotations

from threading import RLock

from services.assignment_pipeline.models import utc_now
from services.revision_engine.models import DraftVersionRecord, MAX_REVISION_ATTEMPTS, RevisionHistory
from services.writer_engine.models import Draft


class RevisionHistoryStore:
    def __init__(self) -> None:
        self._histories: dict[str, RevisionHistory] = {}
        self._lock = RLock()

    def get(self, project_id: str) -> RevisionHistory | None:
        with self._lock:
            return self._histories.get(project_id)

    def require(self, project_id: str) -> RevisionHistory:
        history = self.get(project_id)
        if history is None:
            raise KeyError(f"Revision history not found for project: {project_id}")
        return history

    def ensure(self, project_id: str) -> RevisionHistory:
        with self._lock:
            history = self._histories.get(project_id)
            if history is None:
                history = RevisionHistory(project_id=project_id)
                self._histories[project_id] = history
            return history

    def register_initial_draft(self, draft: Draft, *, changes: list[str] | None = None) -> RevisionHistory:
        if not draft.project_id:
            raise ValueError("Draft project_id is required")
        with self._lock:
            history = self.ensure(draft.project_id)
            if history.versions:
                return history
            history.versions.append(
                DraftVersionRecord(
                    version=draft.version,
                    draft_id=draft.id,
                    title=draft.title,
                    content=draft.content,
                    total_words=draft.total_words,
                    created_at=draft.created_at or utc_now(),
                    changes=list(changes or ["Initial draft from writer merge"]),
                    review_score=None,
                    source="merge",
                )
            )
            return history

    def append_revision(
        self,
        project_id: str,
        *,
        draft: Draft,
        changes: list[str],
        attempt_number: int,
    ) -> RevisionHistory:
        with self._lock:
            history = self.ensure(project_id)
            history.revision_attempts = attempt_number
            history.versions.append(
                DraftVersionRecord(
                    version=draft.version,
                    draft_id=draft.id,
                    title=draft.title,
                    content=draft.content,
                    total_words=draft.total_words,
                    created_at=draft.created_at or utc_now(),
                    changes=list(changes),
                    review_score=None,
                    source="revision",
                )
            )
            return history

    def update_review_score(self, project_id: str, *, version: int, review_score: int) -> RevisionHistory:
        with self._lock:
            history = self.require(project_id)
            for record in history.versions:
                if record.version == version:
                    record.review_score = review_score
                    break
            return history

    def mark_needs_manual_review(self, project_id: str) -> RevisionHistory:
        with self._lock:
            history = self.require(project_id)
            history.needs_manual_review = True
            return history

    def restore_version(self, project_id: str, version: int) -> DraftVersionRecord:
        with self._lock:
            history = self.require(project_id)
            for record in history.versions:
                if record.version == version:
                    return record
            raise KeyError(f"Draft version not found: {version}")

    def can_revise(self, project_id: str) -> bool:
        with self._lock:
            history = self._histories.get(project_id)
            if history is None:
                return True
            return history.revision_attempts < MAX_REVISION_ATTEMPTS and not history.needs_manual_review
