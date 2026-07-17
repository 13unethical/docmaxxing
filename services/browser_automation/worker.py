"""Task worker for browser automation execution."""

from __future__ import annotations

from services.browser_automation.models import BrowserTask, TaskResult


class TaskWorker:
    """Execute browser automation tasks. No browser implementation."""

    def execute(self, task: BrowserTask) -> TaskResult:
        raise NotImplementedError

    def cancel(self, task_id: str) -> None:
        raise NotImplementedError

    def is_running(self, task_id: str) -> bool:
        raise NotImplementedError
