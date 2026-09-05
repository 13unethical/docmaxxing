"""Tests for real-user export + workspace exclusion (no browser / no production writes)."""

from __future__ import annotations

import json
from pathlib import Path

from services.humanizer_training.config import BLOCKED_TRAINING_SURFACES
from services.humanizer_training.loader import _raw_from_payload, load_raw_examples
from services.humanizer_training.config import DatasetBuildConfig
from services.humanizer_training.real_user_export import (
    assert_safe_for_legacy51_sft,
    evaluate_real_user_row,
    export_real_user_training_data,
    has_reliable_consent_mechanism,
    provider_metadata_for_surface,
    strip_pii,
)


def _row(
    *,
    source: str,
    original: str = "Academic source prose with enough distinct tokens for a pair.",
    humanized: str = "Academic rewritten prose with enough distinct tokens for a pair.",
    training_eligible: int | bool | None = 1,
    row_id: int = 1,
) -> dict:
    payload = {
        "id": row_id,
        "source": source,
        "original_text": original,
        "humanized_text": humanized,
        "created_at": "2026-01-01T00:00:00",
        "user_id": 999,  # must never appear in export
        "email": "secret@example.com",
    }
    if training_eligible is not None:
        payload["training_eligible"] = training_eligible
    return payload


def test_consent_mechanism_requires_column():
    assert has_reliable_consent_mechanism(columns=set()) is False
    assert has_reliable_consent_mechanism(columns={"training_eligible"}) is True


def test_missing_consent_rows_not_exported_when_mechanism_ready(tmp_path: Path):
    rows = [
        _row(source="standalone", row_id=1, training_eligible=0),
        _row(source="assignment", row_id=2, original="A " * 20, humanized="B " * 20, training_eligible=0),
        _row(source="workspace_partial", row_id=3, training_eligible=1),
    ]
    result = export_real_user_training_data(
        output_dir=tmp_path / "out",
        rows=rows,
        require_reliable_consent=True,
    )
    assert result.blocked is False
    assert result.counts.eligible_standalone == 0
    assert result.counts.eligible_assignment == 0
    assert result.counts.excluded_workspace == 1
    assert result.counts.excluded_missing_consent == 2
    assert (tmp_path / "out" / "records.jsonl").read_text() == ""
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert manifest["legacy51_sft_auto_ingest"] is False


def test_workspace_exclusion(tmp_path: Path):
    result = export_real_user_training_data(
        output_dir=tmp_path / "ws",
        rows=[_row(source="workspace_partial", training_eligible=1)],
        require_reliable_consent=False,
    )
    assert result.counts.eligible_standalone == 0
    assert result.counts.excluded_workspace == 1
    assert "workspace_partial" in BLOCKED_TRAINING_SURFACES


def test_standalone_and_assignment_inclusion(tmp_path: Path):
    rows = [
        _row(source="standalone", row_id=1),
        _row(
            source="assignment",
            row_id=2,
            original="Assignment source text with unique wording alpha.",
            humanized="Assignment humanized text with unique wording beta.",
        ),
    ]
    result = export_real_user_training_data(
        output_dir=tmp_path / "ok",
        rows=rows,
        require_reliable_consent=False,
    )
    assert result.blocked is False
    assert result.counts.eligible_standalone == 1
    assert result.counts.eligible_assignment == 1
    records = [
        json.loads(line)
        for line in (tmp_path / "ok" / "records.jsonl").read_text().splitlines()
        if line.strip()
    ]
    surfaces = {r["source_surface"] for r in records}
    assert surfaces == {"standalone", "assignment"}
    for r in records:
        assert r["legacy51_sft_eligible"] is False
        assert "user_id" not in r
        assert "email" not in r


def test_missing_consent_excluded(tmp_path: Path):
    result = export_real_user_training_data(
        output_dir=tmp_path / "nc",
        rows=[_row(source="standalone", training_eligible=0)],
        require_reliable_consent=False,
    )
    assert result.counts.eligible_standalone == 0
    assert result.counts.excluded_missing_consent == 1


def test_pii_stripped_from_export_records(tmp_path: Path):
    result = export_real_user_training_data(
        output_dir=tmp_path / "pii",
        rows=[_row(source="standalone")],
        require_reliable_consent=False,
    )
    raw = (tmp_path / "pii" / "records.jsonl").read_text()
    assert "user_id" not in raw
    assert "secret@example.com" not in raw
    assert "999" not in raw
    cleaned = strip_pii({"user_id": 1, "email": "a@b.c", "sample_id": "x", "nested": {"ip": "1.1.1.1"}})
    assert "user_id" not in cleaned
    assert "email" not in cleaned
    assert cleaned["sample_id"] == "x"
    assert "ip" not in cleaned["nested"]


def test_duplicate_and_unchanged_empty(tmp_path: Path):
    src = "Unique academic source sentence for duplicate detection checks."
    tgt = "Unique academic target sentence for duplicate detection checks."
    rows = [
        _row(source="standalone", original=src, humanized=tgt, row_id=1),
        _row(source="standalone", original=src, humanized=tgt, row_id=2),  # exact dup
        _row(source="standalone", original=src, humanized=tgt.upper(), row_id=3),  # norm dup-ish via normalize in pair hash of normalized?
        _row(source="assignment", original="", humanized="x", row_id=4),
        _row(
            source="assignment",
            original="Same text value used as both sides of the pair here.",
            humanized="Same text value used as both sides of the pair here.",
            row_id=5,
        ),
    ]
    result = export_real_user_training_data(
        output_dir=tmp_path / "dup",
        rows=rows,
        require_reliable_consent=False,
    )
    assert result.counts.eligible_standalone == 1
    assert result.counts.excluded_duplicate >= 1
    assert result.counts.excluded_invalid_output >= 2


def test_assignment_level_preserved():
    meta = provider_metadata_for_surface("assignment")
    assert meta["level"] == 10
    assert meta["legacy51_sft_eligible"] is False
    assert meta["level_recorded_in_db"] is False
    status, record, _ = evaluate_real_user_row(
        _row(source="assignment", training_eligible=1),
        require_consent=True,
        seen_exact=set(),
        seen_norm=set(),
    )
    assert status == "accepted"
    assert record is not None
    assert record["level"] == 10
    assert record["legacy51_sft_eligible"] is False
    assert record["consent_status"] == "auto_eligible"


def test_assignment_legacy51_when_level_8_recorded():
    meta = provider_metadata_for_surface(
        "assignment",
        verified_model="Legacy 5.1",
        verified_level=8,
    )
    assert meta["legacy51_sft_eligible"] is True
    status, record, _ = evaluate_real_user_row(
        {
            **_row(source="assignment", training_eligible=1),
            "verified_model": "Legacy 5.1",
            "verified_level": 8,
        },
        require_consent=True,
        seen_exact=set(),
        seen_norm=set(),
    )
    assert status == "accepted"
    assert record is not None
    assert record["legacy51_sft_eligible"] is True
    assert record["level"] == 8


def test_loader_rejects_workspace_payload():
    blocked = _raw_from_payload(
        {
            "source_type": "opted_in",
            "training_eligible": True,
            "source_surface": "workspace_partial",
            "original_text": "hello world " * 5,
            "humanized_text": "hello there " * 5,
        },
        origin="test",
    )
    assert blocked is None

    ok = _raw_from_payload(
        {
            "source_type": "opted_in",
            "training_eligible": True,
            "source_surface": "standalone",
            "original_text": "hello world " * 5,
            "humanized_text": "hello there " * 5,
        },
        origin="test",
    )
    assert ok is not None
    assert ok.metadata["origin_source"] == "standalone"


def test_loader_file_workspace_never_enters(tmp_path: Path):
    path = tmp_path / "mix.jsonl"
    path.write_text(
        json.dumps(
            {
                "source_type": "opted_in",
                "source_surface": "workspace_partial",
                "original_text": "workspace source text with enough words here",
                "humanized_text": "workspace target text with enough words here",
            }
        )
        + "\n"
        + json.dumps(
            {
                "source_type": "synthetic",
                "source_text": "synthetic source text with enough words here yes",
                "target_text": "synthetic target text with enough words here yes",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rows = load_raw_examples(
        DatasetBuildConfig(input_path=path, include_database=False, output_dir=tmp_path / "o")
    )
    assert len(rows) == 1
    assert rows[0].source_type == "synthetic"


def test_legacy51_cannot_consume_workspace_or_unmarked_real_user():
    assert assert_safe_for_legacy51_sft({"source_surface": "workspace_partial"}) is False
    assert assert_safe_for_legacy51_sft({"source_surface": "assignment"}) is False
    assert assert_safe_for_legacy51_sft({"source_surface": "standalone"}) is False
    assert (
        assert_safe_for_legacy51_sft(
            {"source_surface": "assignment", "legacy51_sft_eligible": True}
        )
        is True
    )
