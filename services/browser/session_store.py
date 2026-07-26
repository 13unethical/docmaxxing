"""SessionStore — owns cookies, login state, and storage state per provider.

Providers must never manage cookies directly. The store snapshots and restores
Playwright storage state so sessions survive reconnects and cross-platform
deploys (macOS export → Linux VPS import).
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
        self._applied: set[str] = set()

    def _path(self, name: str) -> Path:
        safe = "".join(c for c in (name or "default") if c.isalnum() or c in ("-", "_")).lower()
        return self._dir / f"{safe or 'default'}.json"

    def _legacy_path(self, name: str) -> Path:
        safe = "".join(c for c in (name or "default") if c.isalnum() or c in ("-", "_")).lower()
        return self._dir.parent / f"{safe}_storage_state.json"

    def has(self, name: str) -> bool:
        return self._path(name).is_file() or self._legacy_path(name).is_file()

    def list(self) -> list[str]:
        names = {p.stem for p in self._dir.glob("*.json")}
        for legacy in self._dir.parent.glob("*_storage_state.json"):
            names.add(legacy.stem.replace("_storage_state", ""))
        return sorted(names)

    def load(self, name: str) -> dict[str, Any] | None:
        for path in (self._path(name), self._legacy_path(name)):
            if not path.is_file():
                continue
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
        return None

    def save(self, name: str, context: Any) -> bool:
        """Snapshot the context's Playwright storage state for a provider."""
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
        """Restore cookies only (used on context reconnect)."""
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

    def apply_to_page(self, name: str, page: Any) -> bool:
        """Restore full storageState (cookies + localStorage) once per process."""
        if name in self._applied:
            return True
        state = self.load(name)
        if not state:
            return False
        try:
            cookies = state.get("cookies") or []
            if cookies:
                page.context.add_cookies(cookies)
            for origin in state.get("origins") or []:
                origin_url = (origin.get("origin") or "").strip()
                if not origin_url:
                    continue
                try:
                    page.goto(origin_url, wait_until="domcontentloaded", timeout=20_000)
                    for entry in origin.get("localStorage") or []:
                        key = entry.get("name")
                        if key is None:
                            continue
                        page.evaluate(
                            "([k, v]) => { try { localStorage.setItem(k, v); } catch (_) {} }",
                            [key, entry.get("value") or ""],
                        )
                except Exception:  # noqa: BLE001
                    continue
            self._applied.add(name)
            print(f"[session-store] applied storageState for {name}", flush=True)
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[session-store] apply failed for {name}: {exc}", flush=True)
            return False

    def clear(self, name: str) -> None:
        try:
            self._path(name).unlink(missing_ok=True)
            self._legacy_path(name).unlink(missing_ok=True)
            self._applied.discard(name)
        except Exception:  # noqa: BLE001
            pass

    def mark_unapplied(self, name: str) -> None:
        """Allow apply_to_page to run again after a tab/browser recovery."""
        self._applied.discard(name)

    def clear_applied(self) -> None:
        self._applied.clear()
