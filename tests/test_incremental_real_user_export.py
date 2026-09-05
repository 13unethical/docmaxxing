"""Tests for incremental real-user export (checkpoint + idempotency)."""

from __future__ import annotations

import json
from pathlib import Path

from services.humanizer_training.real_user_export import (
    assert_safe_for_legacy51_sft,
    export_real_user_training_data_incremental,
    load_export_checkpoint,
    provider_metadata_for_surface,
)


def _row(
    *,
    row_id: int,
    source: str,
    original: str,
    humanized: str,
    training_eligible: int = 1,
    created_at: str = "2026-01-01T00:00:00",
    **extra,
) -> dict:
    payload = {
        "id": row_id,
        "source": source,
        "original_text": original,
        "humanized_text": humanized,
        "created_at": created_at,
        "training_eligible": training_eligible,
        "user_id": 42,
        "email": "hidden@example.com",
        "session_id": "sess-1",
        "ip": "1.2.3.4",
    }
    payload.update(extra)
    return payload


def _lines(path: Path) -> list[dict]:
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_incremental_export_checkpoint_and_idempotency(tmp_path: Path):
    out = tmp_path / "real_user_raw"
    rows = [
        _row(
            row_id=1,
            source="standalone",
            original="Standalone source text with enough distinct tokens one.",
            humanized="Standalone humanized text with enough distinct tokens one.",
            created_at="2026-01-01T10:00:00",
        ),
        _row(
            row_id=2,
            source="assignment",
            original="Assignment source text with enough distinct tokens two.",
            humanized="Assignment humanized text with enough distinct tokens two.",
            created_at="2026-01-01T11:00:00",
        ),
        _row(
            row_id=3,
            source="workspace_partial",
            original="Workspace source text with enough distinct tokens three.",
            humanized="Workspace humanized text with enough distinct tokens three.",
            created_at="2026-01-01T12:00:00",
            training_eligible=0,
        ),
        _row(
            row_id=4,
            source="standalone",
            original="",
            humanized="",
            created_at="2026-01-01T13:00:00",
        ),
    ]

    dry = export_real_user_training_data_incremental(
        output_dir=out,
        rows=rows,
        dry_run=True,
        require_reliable_consent=True,
    )
    assert dry.dry_run is True
    assert dry.exported == 2
    assert dry.workspace_excluded == 1
    assert dry.skipped >= 1
    assert not (out / "records.jsonl").exists() or (out / "records.jsonl").read_text() == ""
    assert load_export_checkpoint(out)["last_id"] == 0

    first = export_real_user_training_data_incremental(
        output_dir=out,
        rows=rows,
        dry_run=False,
        require_reliable_consent=True,
    )
    assert first.new_eligible_records == 3  # includes empty eligible standalone
    assert first.exported == 2
    assert first.exported_standalone == 1
    assert first.exported_assignment == 1
    assert first.workspace_excluded == 1
    assert first.skipped >= 1
    assert first.checkpoint_after["last_id"] == 4
    records = _lines(out / "records.jsonl")
    assert len(records) == 2
    for rec in records:
        assert "user_id" not in rec
        assert "email" not in rec
        assert "session_id" not in rec
        assert "ip" not in rec
        assert set(rec.keys()) >= {
            "sample_id",
            "source_surface",
            "original_text",
            "humanized_text",
            "timestamp",
        }
    by_surface = {r["source_surface"]: r for r in records}
    assert by_surface["assignment"]["legacy51_sft_eligible"] is False
    assert by_surface["assignment"]["level"] == 10
    assert by_surface["standalone"]["legacy51_sft_eligible"] is False

    # Rerun with same rows: checkpoint skips all → no duplicates.
    second = export_real_user_training_data_incremental(
        output_dir=out,
        rows=rows,
        dry_run=False,
        require_reliable_consent=True,
    )
    assert second.exported == 0
    assert second.new_eligible_records == 0
    assert len(_lines(out / "records.jsonl")) == 2

    # New eligible row after checkpoint.
    more = rows + [
        _row(
            row_id=5,
            source="standalone",
            original="Brand new standalone source with enough distinct tokens five.",
            humanized="Brand new standalone humanized with enough distinct tokens five.",
            created_at="2026-01-02T09:00:00",
            verified_model="Legacy 5.1",
            ui_model_label="Ghost 5.1 Legacy",
            verified_level=8,
            selection_verified=True,
        )
    ]
    third = export_real_user_training_data_incremental(
        output_dir=out,
        rows=more,
        dry_run=False,
        require_reliable_consent=True,
    )
    assert third.exported == 1
    assert third.exported_standalone == 1
    assert third.legacy51_sft_eligible_exported == 1
    assert third.checkpoint_after["last_id"] == 5
    records = _lines(out / "records.jsonl")
    assert len(records) == 3
    legacy = [r for r in records if r.get("legacy51_sft_eligible") is True]
    assert len(legacy) == 1
    assert legacy[0]["source_surface"] == "standalone"
    assert assert_safe_for_legacy51_sft(legacy[0]) is True
    assert assert_safe_for_legacy51_sft(by_surface["assignment"]) is False


def test_incremental_limit_and_duplicate_content(tmp_path: Path):
    out = tmp_path / "raw"
    src = "Duplicate content source sentence for incremental checks here."
    tgt = "Duplicate content target sentence for incremental checks here."
    rows = [
        _row(row_id=10, source="standalone", original=src, humanized=tgt, created_at="2026-02-01T00:00:00"),
        _row(row_id=11, source="standalone", original=src, humanized=tgt, created_at="2026-02-01T01:00:00"),
        _row(
            row_id=12,
            source="assignment",
            original="Different assignment source with enough tokens here aa.",
            humanized="Different assignment humanized with enough tokens here bb.",
            created_at="2026-02-01T02:00:00",
        ),
    ]
    limited = export_real_user_training_data_incremental(
        output_dir=out,
        rows=rows,
        limit=1,
        require_reliable_consent=True,
    )
    assert limited.exported == 1
    assert limited.checkpoint_after["last_id"] == 10

    rest = export_real_user_training_data_incremental(
        output_dir=out,
        rows=rows,
        require_reliable_consent=True,
    )
    assert rest.duplicates >= 1
    assert rest.exported_assignment == 1
    assert len(_lines(out / "records.jsonl")) == 2


def test_assignment_not_auto_legacy_without_match():
    meta = provider_metadata_for_surface("assignment")
    assert meta["legacy51_sft_eligible"] is False
    matched = provider_metadata_for_surface(
        "assignment",
        verified_model="Legacy 5.1",
        verified_level=8,
    )
    assert matched["legacy51_sft_eligible"] is True
