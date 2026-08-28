"""Tests for Formatter V2 temporary document storage."""

from __future__ import annotations

import json
import re
from pathlib import Path

from formatter_v2.document_store import (
    FormatV2DocumentStore,
    _generate_document_id,
    _is_valid_document_id,
)


def test_document_store_save_and_resolve(tmp_path: Path) -> None:
    store = FormatV2DocumentStore(tmp_path, ttl_seconds=3600)
    doc_id = store.save(b"PK\x03\x04test", original_filename="essay.docx")
    path = store.resolve(doc_id)
    assert path is not None
    assert path.read_bytes() == b"PK\x03\x04test"
    meta = json.loads((tmp_path / f"{doc_id}.json").read_text(encoding="utf-8"))
    assert meta["original_filename"] == "essay.docx"
    assert meta["ttl_seconds"] == 3600


def test_download_works_from_a_different_process(tmp_path: Path) -> None:
    store_a = FormatV2DocumentStore(tmp_path, ttl_seconds=3600)
    doc_id = store_a.save(b"PK\x03\x04worker-test")
    store_b = FormatV2DocumentStore(tmp_path, ttl_seconds=3600)
    path = store_b.resolve(doc_id)
    assert path is not None
    assert path.read_bytes() == b"PK\x03\x04worker-test"


def test_expired_document_returns_404(tmp_path: Path, monkeypatch) -> None:
    now = [1_000.0]
    monkeypatch.setattr("formatter_v2.document_store.time.time", lambda: now[0])
    store = FormatV2DocumentStore(tmp_path, ttl_seconds=1)
    doc_id = store.save(b"PK\x03\x04test")
    assert store.resolve(doc_id) is not None
    now[0] += 1.1
    assert store.resolve(doc_id) is None
    assert not (tmp_path / f"{doc_id}.docx").exists()
    assert not (tmp_path / f"{doc_id}.json").exists()


def test_document_store_expires_and_cleans_up(tmp_path: Path, monkeypatch) -> None:
    now = [1_000.0]
    monkeypatch.setattr("formatter_v2.document_store.time.time", lambda: now[0])
    store = FormatV2DocumentStore(tmp_path, ttl_seconds=1)
    doc_id = store.save(b"PK\x03\x04test")
    assert store.resolve(doc_id) is not None
    now[0] += 1.1
    assert store.cleanup_expired() >= 1
    assert not list(tmp_path.glob("*.docx"))
    assert not list(tmp_path.glob("*.json"))


def test_document_id_is_not_guessable(tmp_path: Path) -> None:
    store = FormatV2DocumentStore(tmp_path, ttl_seconds=3600)
    ids = {store.save(b"PK\x03\x04x") for _ in range(50)}
    assert len(ids) == 50
    for doc_id in ids:
        assert _is_valid_document_id(doc_id)
        assert len(doc_id) >= 32
        assert not re.fullmatch(r"[0-9a-f]{32}", doc_id)
    generated = {_generate_document_id() for _ in range(20)}
    assert len(generated) == 20
    assert all(_is_valid_document_id(doc_id) for doc_id in generated)


def test_path_traversal_in_document_id_is_rejected(tmp_path: Path) -> None:
    store = FormatV2DocumentStore(tmp_path, ttl_seconds=3600)
    store.save(b"PK\x03\x04safe")
    for bad_id in (
        "../../etc/passwd",
        "..\\etc\\passwd",
        "foo/bar",
        "foo.docx",
        "../secret",
        "a..b",
        "",
        "spaces not allowed",
    ):
        assert store.resolve(bad_id) is None


def test_old_files_are_cleaned_up(tmp_path: Path, monkeypatch) -> None:
    now = [1_000.0]
    monkeypatch.setattr("formatter_v2.document_store.time.time", lambda: now[0])
    store = FormatV2DocumentStore(tmp_path, ttl_seconds=60)
    old_id = store.save(b"PK\x03\x04old")
    now[0] += 120
    fresh_id = store.save(b"PK\x03\x04fresh")
    assert store.resolve(old_id) is None
    assert store.resolve(fresh_id) is not None
    assert not (tmp_path / f"{old_id}.docx").exists()
    assert (tmp_path / f"{fresh_id}.docx").exists()
