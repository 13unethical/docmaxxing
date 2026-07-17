"""Temporary in-memory storage for browser automation state."""

from __future__ import annotations

from services.browser_automation.models import BrowserSession, BrowserTask


class InMemoryStorage:
    """In-memory store for tasks and sessions. No database."""

    def __init__(self) -> None:
        self._tasks: dict[str, BrowserTask] = {}
        self._sessions: dict[str, BrowserSession] = {}

    def save_task(self, task: BrowserTask) -> None:
        self._tasks[task.id] = task

    def get_task(self, task_id: str) -> BrowserTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[BrowserTask]:
        return list(self._tasks.values())

    def save_session(self, session: BrowserSession) -> None:
        self._sessions[session.session_id] = session

    def get_session(self, session_id: str) -> BrowserSession | None:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[BrowserSession]:
        return list(self._sessions.values())

    def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
