"""Temporary DOCX storage for Formatter V2 JSON API responses (disk-backed)."""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

DEFAULT_TTL_SECONDS = 3600
_DOCUMENT_ID_BYTES = 32
_DOCUMENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

_store: FormatV2DocumentStore | None = None
_store_lock = threading.Lock()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_valid_document_id(document_id: str) -> bool:
    if not document_id:
        return False
    if "/" in document_id or "\\" in document_id or "." in document_id:
        return False
    return bool(_DOCUMENT_ID_RE.fullmatch(document_id))


def _generate_document_id() -> str:
    for _ in range(8):
        document_id = secrets.token_urlsafe(_DOCUMENT_ID_BYTES)
        if _is_valid_document_id(document_id):
            return document_id
    raise RuntimeError("failed to generate a safe document id")


def _sanitize_filename(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = Path(name).name.strip()
    return cleaned or None


class FormatV2DocumentStore:
    """Save formatted DOCX bytes; retrieve by opaque id until TTL expires."""

    def __init__(self, root: Path, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.root = root.expanduser().resolve()
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, docx_bytes: bytes, *, original_filename: str | None = None) -> str:
        if not docx_bytes:
            raise ValueError("docx_bytes must not be empty")
        self.cleanup_expired()
        document_id = _generate_document_id()
        doc_path = self._docx_path(document_id)
        meta_path = self._meta_path(document_id)
        if doc_path is None or meta_path is None:
            raise RuntimeError("failed to allocate document path")

        created_at = time.time()
        meta = {
            "created_at": created_at,
            "ttl_seconds": self.ttl_seconds,
            "expires_at": created_at + self.ttl_seconds,
            "original_filename": _sanitize_filename(original_filename),
        }
        doc_path.write_bytes(docx_bytes)
        meta_path.write_text(json.dumps(meta, separators=(",", ":")), encoding="utf-8")
        return document_id

    def resolve(self, document_id: str) -> Path | None:
        if not _is_valid_document_id(document_id):
            return None

        meta_path = self._meta_path(document_id)
        doc_path = self._docx_path(document_id)
        if meta_path is None or doc_path is None:
            return None
        if not meta_path.is_file() or not doc_path.is_file():
            return None

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        expires_at = float(meta.get("expires_at") or 0)
        if time.time() > expires_at:
            self._remove_document(document_id)
            return None
        return doc_path

    def cleanup_expired(self) -> int:
        now = time.time()
        removed = 0
        for meta_path in self.root.glob("*.json"):
            document_id = meta_path.stem
            if not _is_valid_document_id(document_id):
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                expires_at = float(meta.get("expires_at") or 0)
            except (json.JSONDecodeError, OSError):
                expires_at = 0
            if now > expires_at and self._remove_document(document_id):
                removed += 1
        return removed

    def _remove_document(self, document_id: str) -> bool:
        if not _is_valid_document_id(document_id):
            return False
        removed_any = False
        for path in (self._docx_path(document_id), self._meta_path(document_id)):
            if path is not None and path.is_file():
                path.unlink(missing_ok=True)
                removed_any = True
        return removed_any

    def _safe_child_path(self, document_id: str, suffix: str) -> Path | None:
        if not _is_valid_document_id(document_id):
            return None
        candidate = (self.root / f"{document_id}{suffix}").resolve()
        root = self.root.resolve()
        try:
            if not candidate.is_relative_to(root):
                return None
        except AttributeError:
            if os.path.commonpath([str(root), str(candidate)]) != str(root):
                return None
        return candidate

    def _docx_path(self, document_id: str) -> Path | None:
        return self._safe_child_path(document_id, ".docx")

    def _meta_path(self, document_id: str) -> Path | None:
        return self._safe_child_path(document_id, ".json")


def _store_root() -> Path:
    override = (os.environ.get("FORMAT_V2_DOCUMENT_DIR") or "").strip()
    if override:
        return Path(override).expanduser()
    return _repo_root() / "data" / "tmp" / "format_v2_documents"


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
    global _store
    with _store_lock:
        _store = FormatV2DocumentStore(
            root or (_store_root() / "test"),
            ttl_seconds=ttl_seconds or DEFAULT_TTL_SECONDS,
        )
        return _store


def ensure_store_started(*, testing: bool = False) -> None:
    """Ensure the store directory exists. ``testing`` is accepted for API compatibility."""
    del testing
    get_document_store()
