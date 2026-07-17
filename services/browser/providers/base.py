"""Provider base class for the Browser Automation Platform.

Providers contain ONLY domain knowledge: page, selectors, buttons, workflow.
They contain no browser lifecycle code — Chrome, CDP, contexts, tabs, cookies,
and recovery are all owned by BrowserService.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from services.browser.browser_service import BrowserService


class Provider(ABC):
    """Contract every provider (StealthWriter, Turnitin, GPTZero, ...) implements."""

    #: Unique provider key; also names the provider's persistent tab.
    name: str = "provider"

    @property
    def service(self) -> BrowserService:
        return BrowserService.instance()

    def page(self) -> Any:
        """The provider's own persistent tab, created on demand by BrowserService."""
        return self.service.get_or_create_page(self.name)

    @abstractmethod
    def initialize(self) -> None:
        """Prepare the provider (e.g. ensure its tab exists). No browser launching."""

    @abstractmethod
    def login(self, *, credentials: dict[str, Any] | None = None) -> Any:
        """Perform or guide login. Manual providers may raise NotImplementedError."""

    @abstractmethod
    def is_logged_in(self) -> bool:
        """Return whether the provider session is currently authenticated."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Cheap, non-navigating status snapshot for the health endpoint."""

    @abstractmethod
    def execute(self, task: Any) -> Any:
        """Run a provider operation described by ``task``."""
