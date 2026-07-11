"""In-memory writer session and draft storage."""

from __future__ import annotations

from threading import RLock

from services.writer_engine.models import Draft, WriterSession


class WriterSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, WriterSession] = {}
        self._by_project: dict[str, str] = {}
        self._lock = RLock()

    def save(self, session: WriterSession) -> WriterSession:
        with self._lock:
            self._sessions[session.id] = session
            if session.project_id:
                self._by_project[session.project_id] = session.id
            return session

    def get(self, session_id: str) -> WriterSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def get_by_project(self, project_id: str) -> WriterSession | None:
        with self._lock:
            session_id = self._by_project.get(project_id)
            if not session_id:
                return None
            return self._sessions.get(session_id)

    def require(self, session_id: str) -> WriterSession:
        session = self.get(session_id)
        if session is None:
            raise KeyError(f"Writer session not found: {session_id}")
        return session

    def require_by_project(self, project_id: str) -> WriterSession:
        session = self.get_by_project(project_id)
        if session is None:
            raise KeyError(f"Writer session not found for project: {project_id}")
        return session


class DraftStore:
    def __init__(self) -> None:
        self._drafts: dict[str, Draft] = {}
        self._by_project: dict[str, str] = {}
        self._lock = RLock()

    def save(self, draft: Draft) -> Draft:
        with self._lock:
            self._drafts[draft.id] = draft
            if draft.project_id:
                self._by_project[draft.project_id] = draft.id
            return draft

    def get(self, draft_id: str) -> Draft | None:
        with self._lock:
            return self._drafts.get(draft_id)

    def get_by_project(self, project_id: str) -> Draft | None:
        with self._lock:
            draft_id = self._by_project.get(project_id)
            if not draft_id:
                return None
            return self._drafts.get(draft_id)

    def require(self, draft_id: str) -> Draft:
        draft = self.get(draft_id)
        if draft is None:
            raise KeyError(f"Draft not found: {draft_id}")
        return draft

    def require_by_project(self, project_id: str) -> Draft:
        draft = self.get_by_project(project_id)
        if draft is None:
            raise KeyError(f"Draft not found for project: {project_id}")
        return draft
