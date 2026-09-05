"""Tests for auto training eligibility (no user opt-in) + real-user export gates."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from services.dataset_logger import ensure_dataset_schema, log_humanization_event
from services.economy import db as economy_db
from services.humanizer_training.consent import (
    ensure_training_consent_schema,
    training_eligible_for_new_log,
)
from services.humanizer_training.real_user_export import (
    export_real_user_training_data,
    has_reliable_consent_mechanism,
    provider_metadata_for_surface,
)


@pytest.fixture()
def economy(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "economy.db"
    monkeypatch.setattr(economy_db, "DB_PATH", db_path)
    economy_db.init_db()
    ensure_training_consent_schema()
    ensure_dataset_schema()
    with economy_db.connect() as conn:
        conn.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
            ("a@example.com", "A", "x"),
        )
        uid = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()["id"])
    return uid


def test_auto_eligible_standalone_and_assignment(economy):
    uid = economy
    assert training_eligible_for_new_log(uid, source="standalone") == 1
    assert training_eligible_for_new_log(uid, source="assignment") == 1
    assert training_eligible_for_new_log(uid, source="workspace_partial") == 0
    assert training_eligible_for_new_log(None, source="standalone") == 1
    assert has_reliable_consent_mechanism(columns={"training_eligible"}) is True


def test_users_table_has_no_opt_in_requirement(economy):
    """Opt-in columns are obsolete; eligibility is source-based only."""
    with economy_db.connect() as conn:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    # New DBs must not create training_data_opt_in*. Existing DBs may still have them.
    # Eligibility must not depend on them either way.
    assert training_eligible_for_new_log(economy, source="standalone") == 1
    assert training_eligible_for_new_log(economy, source="workspace_partial") == 0
    # Fresh init_db from this codebase should not add the obsolete columns.
    assert "training_data_opt_in" not in cols
    assert "training_data_opt_in_at" not in cols


def test_new_logs_auto_eligible_old_rows_stay_ineligible(economy, tmp_path: Path):
    uid = economy
    with economy_db.connect() as conn:
        conn.execute(
            "INSERT INTO humanizer_dataset_logs "
            "(user_id, source, original_text, humanized_text, training_eligible) "
            "VALUES (?, ?, ?, ?, 0)",
            (
                uid,
                "standalone",
                "Old source text with enough words for a pair here.",
                "Old humanized text with enough words for a pair here.",
            ),
        )

    log_humanization_event(
        uid,
        "standalone",
        "New source text with enough words for a pair here.",
        "New humanized text with enough words for a pair here.",
    )
    log_humanization_event(
        uid,
        "assignment",
        "Assignment source text with enough words for a pair here.",
        "Assignment humanized text with enough words for a pair here.",
    )

    for _ in range(50):
        with economy_db.connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM humanizer_dataset_logs WHERE training_eligible = 1"
            ).fetchone()["c"]
        if int(n) >= 2:
            break
        time.sleep(0.05)

    result = export_real_user_training_data(
        output_dir=tmp_path / "exp",
        require_reliable_consent=True,
    )
    assert result.blocked is False
    assert result.counts.eligible_standalone == 1
    assert result.counts.eligible_assignment == 1
    assert result.counts.excluded_missing_consent >= 1
    records = [
        json.loads(line)
        for line in (tmp_path / "exp" / "records.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(records) == 2
    for rec in records:
        assert "user_id" not in rec
        assert "email" not in rec
        assert rec["consent_status"] == "auto_eligible"
    by_surface = {r["source_surface"]: r for r in records}
    assert by_surface["standalone"]["legacy51_sft_eligible"] is False
    assert by_surface["assignment"]["legacy51_sft_eligible"] is False
    assert by_surface["assignment"]["level"] == 10


def test_workspace_always_excluded_even_if_stamped(economy, tmp_path: Path):
    uid = economy
    with economy_db.connect() as conn:
        conn.execute(
            "INSERT INTO humanizer_dataset_logs "
            "(user_id, source, original_text, humanized_text, training_eligible) "
            "VALUES (?, 'workspace_partial', ?, ?, 1)",
            (uid, "WS source " * 10, "WS target " * 10),
        )
    result = export_real_user_training_data(
        output_dir=tmp_path / "ws",
        require_reliable_consent=True,
    )
    assert result.counts.eligible_standalone == 0
    assert result.counts.eligible_assignment == 0
    assert result.counts.excluded_workspace == 1


def test_assignment_legacy51_only_when_model_level_match():
    default = provider_metadata_for_surface("assignment")
    assert default["level"] == 10
    assert default["legacy51_sft_eligible"] is False

    matched = provider_metadata_for_surface(
        "assignment",
        verified_model="Legacy 5.1",
        verified_level=8,
    )
    assert matched["level"] == 8
    assert matched["legacy51_sft_eligible"] is True
