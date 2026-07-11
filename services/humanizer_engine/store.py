"""In-memory humanizer session and humanized draft storage."""

from __future__ import annotations

from threading import RLock

from services.humanizer_engine.models import HumanizedDraft, HumanizerSession


class HumanizerSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, HumanizerSession] = {}
        self._by_project: dict[str, str] = {}
        self._lock = RLock()

    def save(self, session: HumanizerSession) -> HumanizerSession:
        with self._lock:
            self._sessions[session.id] = session
            if session.project_id:
                self._by_project[session.project_id] = session.id
            return session

    def get(self, session_id: str) -> HumanizerSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def get_by_project(self, project_id: str) -> HumanizerSession | None:
        with self._lock:
            session_id = self._by_project.get(project_id)
            if not session_id:
                return None
            return self._sessions.get(session_id)

    def require(self, session_id: str) -> HumanizerSession:
        session = self.get(session_id)
        if session is None:
            raise KeyError(f"Humanizer session not found: {session_id}")
        return session

    def require_by_project(self, project_id: str) -> HumanizerSession:
        session = self.get_by_project(project_id)
        if session is None:
            raise KeyError(f"Humanizer session not found for project: {project_id}")
        return session


class HumanizedDraftStore:
    def __init__(self) -> None:
        self._drafts: dict[str, HumanizedDraft] = {}
        self._by_project: dict[str, str] = {}
        self._lock = RLock()

    def save(self, draft: HumanizedDraft) -> HumanizedDraft:
        with self._lock:
            self._drafts[draft.id] = draft
            if draft.project_id:
                self._by_project[draft.project_id] = draft.id
            return draft

    def get(self, draft_id: str) -> HumanizedDraft | None:
        with self._lock:
            return self._drafts.get(draft_id)

    def get_by_project(self, project_id: str) -> HumanizedDraft | None:
        with self._lock:
            draft_id = self._by_project.get(project_id)
            if not draft_id:
                return None
            return self._drafts.get(draft_id)

    def require(self, draft_id: str) -> HumanizedDraft:
        draft = self.get(draft_id)
        if draft is None:
            raise KeyError(f"Humanized draft not found: {draft_id}")
        return draft

    def require_by_project(self, project_id: str) -> HumanizedDraft:
        draft = self.get_by_project(project_id)
        if draft is None:
            raise KeyError(f"Humanized draft not found for project: {project_id}")
        return draft
