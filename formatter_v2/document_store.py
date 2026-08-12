"""Temporary DOCX storage for Formatter V2 JSON API responses."""

from __future__ import annotations

import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

DEFAULT_TTL_SECONDS = 3600
CLEANUP_INTERVAL_SECONDS = 300
_DOCUMENT_ID_RE = re.compile(r"^[0-9a-f]{32}$")

_store: FormatV2DocumentStore | None = None
_store_lock = threading.Lock()
_scheduler_started = False


class FormatV2DocumentStore:
    """Save formatted DOCX bytes; retrieve by opaque id until TTL expires."""

    def __init__(self, root: Path, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.root = root
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.root.mkdir(parents=True, exist_ok=True)
        self._expires_at: dict[str, float] = {}
        self._meta_lock = threading.Lock()

    def save(self, docx_bytes: bytes) -> str:
        if not docx_bytes:
            raise ValueError("docx_bytes must not be empty")
        self.cleanup_expired()
        document_id = uuid.uuid4().hex
        path = self._path(document_id)
        path.write_bytes(docx_bytes)
        expires_at = time.time() + self.ttl_seconds
        with self._meta_lock:
            self._expires_at[document_id] = expires_at
        return document_id

    def resolve(self, document_id: str) -> Path | None:
        if not document_id or not _DOCUMENT_ID_RE.fullmatch(document_id):
            return None
        self.cleanup_expired()
        with self._meta_lock:
            expires_at = self._expires_at.get(document_id)
        if expires_at is None or time.time() > expires_at:
            return None
        path = self._path(document_id)
        return path if path.is_file() else None

    def cleanup_expired(self) -> int:
        now = time.time()
        removed = 0
        with self._meta_lock:
            expired_ids = [doc_id for doc_id, ts in self._expires_at.items() if ts <= now]
            for doc_id in expired_ids:
                self._expires_at.pop(doc_id, None)
                path = self._path(doc_id)
                if path.is_file():
                    path.unlink(missing_ok=True)
                    removed += 1
        return removed

    def _path(self, document_id: str) -> Path:
        return self.root / f"{document_id}.docx"


def _store_root() -> Path:
    override = (os.environ.get("FORMAT_V2_DOCUMENT_DIR") or "").strip()
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "format_v2_documents"


def _store_ttl_seconds() -> int:
    raw = (os.environ.get("FORMAT_V2_DOCUMENT_TTL_S") or "").strip()
    if raw.isdigit():
        return max(60, int(raw))
    return DEFAULT_TTL_SECONDS


def get_document_store() -> FormatV2DocumentStore:
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is None:
            _store = FormatV2DocumentStore(_store_root(), ttl_seconds=_store_ttl_seconds())
        return _store


def reset_document_store(*, root: Path | None = None, ttl_seconds: int | None = None) -> FormatV2DocumentStore:
    """Replace the singleton (tests)."""
    global _store, _scheduler_started
    with _store_lock:
        if _store is not None:
            _store.cleanup_expired()
        _store = FormatV2DocumentStore(
            root or (_store_root() / "test"),
            ttl_seconds=ttl_seconds or DEFAULT_TTL_SECONDS,
        )
        _scheduler_started = False
        return _store


def start_cleanup_scheduler(*, interval_seconds: int = CLEANUP_INTERVAL_SECONDS) -> None:
    global _scheduler_started
    with _store_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    def _loop() -> None:
        while True:
            time.sleep(max(30, interval_seconds))
            try:
                get_document_store().cleanup_expired()
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=_loop, name="format-v2-doc-cleanup", daemon=True).start()


def ensure_store_started(*, testing: bool = False) -> None:
    get_document_store()
    if not testing:
        start_cleanup_scheduler()
