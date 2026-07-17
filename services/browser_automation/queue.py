"""Task queue for browser automation jobs."""

from __future__ import annotations

from services.browser_automation.models import BrowserTask, BrowserTaskStatus


class TaskQueue:
    """Enqueue, dequeue, and track retry/status for browser tasks."""

    def enqueue(self, task: BrowserTask) -> None:
        raise NotImplementedError

    def dequeue(self) -> BrowserTask | None:
        raise NotImplementedError

    def get_status(self, task_id: str) -> BrowserTaskStatus | None:
        raise NotImplementedError

    def set_status(self, task_id: str, status: BrowserTaskStatus) -> None:
        raise NotImplementedError

    def increment_retry(self, task_id: str) -> int:
        raise NotImplementedError

    def get_retry_count(self, task_id: str) -> int:
        raise NotImplementedError

    def cancel(self, task_id: str) -> None:
        raise NotImplementedError

    def list_queued(self) -> list[BrowserTask]:
        raise NotImplementedError
