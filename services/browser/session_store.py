"""SessionStore — owns cookies, login state, and storage state per provider.

Providers must never manage cookies directly. The store snapshots and restores
Playwright storage state so sessions survive reconnects and process restarts.

Note: with a persistent Chrome user-data-dir, cookies/localStorage already live
on disk. SessionStore adds an explicit, provider-scoped snapshot layer on top so
the platform can restore state after recovery and support multiple accounts later.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_DIR = Path("browser_profiles/sessions")


class SessionStore:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self._dir = Path(base_dir or _DEFAULT_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        safe = "".join(c for c in (name or "default") if c.isalnum() or c in ("-", "_")).lower()
        return self._dir / f"{safe or 'default'}.json"

    def has(self, name: str) -> bool:
        return self._path(name).is_file()

    def list(self) -> list[str]:
        return [p.stem for p in self._dir.glob("*.json")]

    def load(self, name: str) -> dict[str, Any] | None:
        path = self._path(name)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def save(self, name: str, context: Any) -> bool:
        """Snapshot the context's storage state (cookies + origins) for a provider."""
        try:
            state = context.storage_state()
        except Exception:  # noqa: BLE001
            return False
        try:
            self._path(name).write_text(json.dumps(state), encoding="utf-8")
            return True
        except Exception:  # noqa: BLE001
            return False

    def apply(self, name: str, context: Any) -> bool:
        """Best-effort restore of saved cookies into a live context.

        localStorage is bound to a page/origin and is already persisted by the
        Chrome profile; only cookies are re-applied here.
        """
        state = self.load(name)
        if not state:
            return False
        cookies = state.get("cookies") or []
        if not cookies:
            return False
        try:
            context.add_cookies(cookies)
            return True
        except Exception:  # noqa: BLE001
            return False

    def clear(self, name: str) -> None:
        try:
            self._path(name).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
