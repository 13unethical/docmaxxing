"""PageManager — one persistent tab per provider inside a browser context.

Each provider (stealthwriter, turnitin, gptzero, ...) reuses its own tab. Tabs
are never duplicated; requesting a provider's page returns the existing tab or
creates one. After a reconnect the manager restores a tab for every known
provider so providers never observe the disruption.
"""

from __future__ import annotations

from typing import Any

_DEFAULT_NAME = "default"


class PageManager:
    def __init__(self, context: Any | None = None) -> None:
        self._context = context
        self._pages: dict[str, Any] = {}
        self._known_names: set[str] = set()

    def bind_context(self, context: Any, *, restore: bool = True) -> None:
        """Attach a (possibly new) context and rebuild provider tabs."""
        self._context = context
        self._pages = {}
        if restore and self._known_names:
            for name in sorted(self._known_names):
                self.get_or_create_page(name)

    def get_or_create_page(self, name: str | None = None) -> Any:
        name = name or _DEFAULT_NAME
        self._known_names.add(name)
        if self._context is None:
            raise RuntimeError("PageManager has no browser context bound")

        existing = self._pages.get(name)
        if existing is not None and self._alive(existing):
            return existing

        # Drop dead cached handle before creating a replacement.
        self._pages.pop(name, None)
        page = self._adopt_unassigned_page() or self._context.new_page()
        self._pages[name] = page
        return page

    def peek(self, name: str) -> Any | None:
        return self._pages.get(name)

    def invalidate(self, name: str) -> None:
        self._pages.pop(name, None)

    def new_page(self) -> Any:
        """Create an anonymous (unnamed) tab."""
        if self._context is None:
            raise RuntimeError("PageManager has no browser context bound")
        return self._context.new_page()

    def _adopt_unassigned_page(self) -> Any | None:
        """Reuse a stray blank tab (e.g. Chrome's initial about:blank) if free."""
        try:
            assigned = set(id(p) for p in self._pages.values())
            for page in self._context.pages:
                if id(page) in assigned:
                    continue
                if not self._alive(page):
                    continue
                url = ""
                try:
                    url = page.url or ""
                except Exception:  # noqa: BLE001
                    url = ""
                if url in ("", "about:blank", "chrome://newtab/"):
                    return page
        except Exception:  # noqa: BLE001
            return None
        return None

    def names(self) -> list[str]:
        return sorted(self._known_names)

    def live_pages(self) -> list[Any]:
        return [p for p in self._pages.values() if self._alive(p)]

    def count(self) -> int:
        return len(self.live_pages())

    @staticmethod
    def _alive(page: Any) -> bool:
        try:
            if page.is_closed():
                return False
            # Zombie handles can report not-closed while CDP is dead.
            _ = page.evaluate("() => 1")
            return True
        except Exception:  # noqa: BLE001
            return False
