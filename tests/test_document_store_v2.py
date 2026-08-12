"""Tests for Formatter V2 temporary document storage."""

from __future__ import annotations

from pathlib import Path

from formatter_v2.document_store import FormatV2DocumentStore


def test_document_store_save_and_resolve(tmp_path: Path) -> None:
    store = FormatV2DocumentStore(tmp_path, ttl_seconds=3600)
    doc_id = store.save(b"PK\x03\x04test")
    path = store.resolve(doc_id)
    assert path is not None
    assert path.read_bytes() == b"PK\x03\x04test"


def test_document_store_expires_and_cleans_up(tmp_path: Path, monkeypatch) -> None:
    now = [1_000.0]
    monkeypatch.setattr("formatter_v2.document_store.time.time", lambda: now[0])
    store = FormatV2DocumentStore(tmp_path, ttl_seconds=1)
    doc_id = store.save(b"PK\x03\x04test")
    assert store.resolve(doc_id) is not None
    now[0] += 1.1
    assert store.resolve(doc_id) is None
    assert not list(tmp_path.glob("*.docx"))
