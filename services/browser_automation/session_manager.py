"""Session lifecycle management for browser automation providers."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.browser_automation.models import BrowserProviderType, BrowserSession
from services.browser_automation.storage import InMemoryStorage


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_profile_root() -> Path:
    return Path(os.environ.get("BROWSER_PROFILE_DIR", "browser_profiles/default"))


class SessionManager:
    """Create, restore, expire, and track session metadata. No login implementation."""

    def __init__(self, storage: InMemoryStorage | None = None) -> None:
        self._storage = storage or InMemoryStorage()

    def create_session(
        self,
        *,
        provider_type: BrowserProviderType,
        profile_path: str | None = None,
    ) -> BrowserSession:
        now = _utc_now()
        resolved_profile = profile_path or str(_default_profile_root() / provider_type.value)
        session = BrowserSession(
            session_id=str(uuid.uuid4()),
            provider=provider_type,
            created_at=now,
            last_used=now,
            profile_path=resolved_profile,
            is_active=True,
        )
        self._storage.save_session(session)
        return session

    def restore_session(self, session_id: str) -> BrowserSession | None:
        session = self._storage.get_session(session_id)
        if session is None or not session.is_active:
            return None
        session.last_used = _utc_now()
        self._storage.save_session(session)
        return session

    def expire_session(self, session_id: str) -> None:
        session = self._storage.get_session(session_id)
        if session is None:
            return
        session.is_active = False
        session.last_used = _utc_now()
        self._storage.save_session(session)

    def get_session_metadata(self, session_id: str) -> dict[str, Any] | None:
        session = self._storage.get_session(session_id)
        if session is None:
            return None
        return {
            "session_id": session.session_id,
            "provider": session.provider.value,
            "created_at": session.created_at.isoformat(),
            "last_used": session.last_used.isoformat(),
            "profile_path": session.profile_path,
            "is_active": session.is_active,
        }

    def update_session_metadata(self, session_id: str, metadata: dict[str, Any]) -> None:
        session = self._storage.get_session(session_id)
        if session is None:
            return
        if "profile_path" in metadata and metadata["profile_path"]:
            session.profile_path = str(metadata["profile_path"])
        if "is_active" in metadata:
            session.is_active = bool(metadata["is_active"])
        session.last_used = _utc_now()
        self._storage.save_session(session)

    def list_active_sessions(
        self,
        *,
        provider_type: BrowserProviderType | None = None,
    ) -> list[BrowserSession]:
        sessions = [s for s in self._storage.list_sessions() if s.is_active]
        if provider_type is not None:
            sessions = [s for s in sessions if s.provider == provider_type]
        return sessions
