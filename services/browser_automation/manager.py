"""Central registry for providers, sessions, and workers."""

from __future__ import annotations

from services.browser_automation.models import BrowserProviderType, BrowserSession
from services.browser_automation.providers.provider import BrowserProvider
from services.browser_automation.runtime import BrowserRuntime, get_shared_runtime
from services.browser_automation.worker import TaskWorker


class BrowserAutomationManager:
    """Provider, session, and worker registry. Owns exactly one browser runtime."""

    def __init__(self, runtime: BrowserRuntime | None = None) -> None:
        self._runtime = runtime or get_shared_runtime()
        self._providers: dict[BrowserProviderType, BrowserProvider] = {}
        self._sessions: dict[str, BrowserSession] = {}
        self._workers: dict[str, TaskWorker] = {}

    @property
    def runtime(self) -> BrowserRuntime:
        return self._runtime

    def register_provider(self, provider_type: BrowserProviderType, provider: BrowserProvider) -> None:
        raise NotImplementedError

    def unregister_provider(self, provider_type: BrowserProviderType) -> None:
        raise NotImplementedError

    def get_provider(self, provider_type: BrowserProviderType) -> BrowserProvider | None:
        raise NotImplementedError

    def list_providers(self) -> list[BrowserProviderType]:
        raise NotImplementedError

    def register_session(self, session: BrowserSession) -> None:
        raise NotImplementedError

    def unregister_session(self, session_id: str) -> None:
        raise NotImplementedError

    def get_session(self, session_id: str) -> BrowserSession | None:
        raise NotImplementedError

    def list_sessions(self) -> list[BrowserSession]:
        raise NotImplementedError

    def register_worker(self, worker_id: str, worker: TaskWorker) -> None:
        raise NotImplementedError

    def unregister_worker(self, worker_id: str) -> None:
        raise NotImplementedError

    def get_worker(self, worker_id: str) -> TaskWorker | None:
        raise NotImplementedError

    def list_workers(self) -> list[str]:
        raise NotImplementedError
