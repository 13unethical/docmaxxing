"""Tests for dataset loggers: store-raw humanize + detector corpus."""

from __future__ import annotations

import json
import time

import pytest

from services.dataset_logger import (
    clean_text_for_ml,
    get_dataset_stats,
    log_detection_event,
    log_humanization_event,
)
from services.economy import auth
from services.economy import db as economy_db
from services.economy.db import connect


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    economy_db.init_db()
    return tmp_path


def _wait_until(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_clean_text_strips_html_and_ws_markers():
    raw = (
        "<p>Hello <b>world</b></p>\n"
        "IMPORTANT: Keep every marker line like ⟦WS:0⟧ exactly unchanged on its own line. "
        "Only rewrite the prose under each marker. Do not merge sections.\n\n"
        "⟦WS:0⟧\n"
        "First chunk.\n\n"
        "⟦WS:1⟧\n"
        "Second chunk."
    )
    cleaned = clean_text_for_ml(raw)
    assert "<" not in cleaned
    assert "⟦WS:" not in cleaned
    assert "IMPORTANT" not in cleaned
    assert "First chunk" in cleaned
    assert "Second chunk" in cleaned


def test_log_humanization_stores_raw(economy):
    user = auth.create_user("ds@example.com", "secret12")
    original = "<p>Original AI prose here with enough words.</p>\n⟦WS:0⟧\nChunk."
    humanized = "<p>Humanized prose here with enough words.</p>\n⟦WS:0⟧\nChunk."
    log_humanization_event(user["id"], "standalone", original, humanized)
    assert _wait_until(lambda: get_dataset_stats()["total"] >= 1)

    stats = get_dataset_stats()
    assert stats["total"] == 1
    assert stats["standalone"] == 1
    assert stats["assignment"] == 0
    assert stats["workspace_partial"] == 0

    with connect() as conn:
        row = conn.execute(
            "SELECT original_text, humanized_text FROM humanizer_dataset_logs LIMIT 1"
        ).fetchone()
    assert row["original_text"] == original
    assert row["humanized_text"] == humanized
    assert "<p>" in row["original_text"]
    assert "⟦WS:0⟧" in row["original_text"]


def test_log_skips_empty(economy):
    user = auth.create_user("skip@example.com", "secret12")
    log_humanization_event(user["id"], "standalone", "", "output")
    log_humanization_event(user["id"], "standalone", "input", "")
    time.sleep(0.2)
    assert get_dataset_stats()["total"] == 0


def test_log_detection_event_and_stats(economy):
    user = auth.create_user("det@example.com", "secret12")
    full = "Sentence one is human. Sentence two is AI generated fluff."
    ai_segs = ["Sentence two is AI generated fluff."]
    log_detection_event(
        user["id"],
        full,
        42.5,
        ai_segs,
        None,
        "auto_report_over_20",
    )
    log_detection_event(
        user["id"],
        full,
        12.0,
        ["Sentence two is AI generated fluff."],
        ["Sentence one is human."],
        "manual_highlights",
    )
    assert _wait_until(lambda: get_dataset_stats()["detector_total"] >= 2)

    stats = get_dataset_stats()
    assert stats["detector_total"] == 2
    assert stats["auto_report_over_20"] == 1
    assert stats["manual_highlights"] == 1

    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM detector_dataset_logs WHERE capture_type = ?",
            ("auto_report_over_20",),
        ).fetchone()
    assert row["full_text"] == full
    assert float(row["ai_percentage"]) == 42.5
    assert json.loads(row["ai_segments"]) == ai_segs
    assert "Sentence one is human." in json.loads(row["human_segments"])
