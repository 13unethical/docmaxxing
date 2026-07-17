"""Base provider interface for browser-based external services."""

from __future__ import annotations

from typing import Any, Protocol

from services.browser_automation.models import BrowserTask, ProviderHealth, TaskResult


class BrowserProvider(Protocol):
    """Contract for browser automation providers (StealthWriter, Turnitin, etc.)."""

    provider_type: str

    def initialize(self) -> None: ...

    def login(self, *, credentials: dict[str, Any] | None = None) -> None: ...

    def health_check(self) -> ProviderHealth: ...

    def execute(self, task: BrowserTask) -> TaskResult: ...

    def logout(self) -> None: ...

    def shutdown(self) -> None: ...
