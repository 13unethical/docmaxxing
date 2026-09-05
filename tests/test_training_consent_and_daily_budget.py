"""Tests for training consent, daily budget, and synthetic backfill planning."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from services.dataset_logger import ensure_dataset_schema
from services.economy import db as economy_db
from services.economy.site_settings import (
    ensure_schema,
    ensure_today_row,
    update_site_settings,
)
from services.humanizer_training.consent import (
    ensure_training_consent_schema,
)
from services.humanizer_training.daily_budget import (
    get_humanizer_daily_budget,
    next_reset_at,
    release_humanizer_slots,
    reserve_humanizer_slots,
    within_reset_window,
)
from services.humanizer_training.real_user_export import (
    provider_metadata_for_surface,
)
from services.humanizer_training.synthetic_daily import plan_daily_backfill, run_daily_backfill


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
        ensure_schema(conn)
        ensure_today_row(conn)
    update_site_settings(humanizer_daily_limit=10)
    return uid


def test_assignment_metadata_level_10(tmp_path: Path):
    meta = provider_metadata_for_surface("assignment")
    assert meta["level"] == 10
    assert meta["legacy51_sft_eligible"] is False
    rows = [
        {
            "id": 1,
            "source": "assignment",
            "original_text": "Assignment source text with enough distinct tokens aaa.",
            "humanized_text": "Assignment humanized text with enough distinct tokens bbb.",
            "training_eligible": 1,
            "created_at": "2026-01-02T00:00:00",
        }
    ]
    from services.humanizer_training.real_user_export import export_real_user_training_data

    result = export_real_user_training_data(
        output_dir=tmp_path / "asg",
        rows=rows,
        require_reliable_consent=False,
    )
    assert result.counts.eligible_assignment == 1
    rec = json.loads((tmp_path / "asg" / "records.jsonl").read_text().splitlines()[0])
    assert rec["level"] == 10
    assert rec["legacy51_sft_eligible"] is False
    assert rec["consent_status"] == "auto_eligible"


def test_standalone_legacy51_only_with_proven_meta(tmp_path: Path):
    plain = provider_metadata_for_surface("standalone")
    assert plain["legacy51_sft_eligible"] is False
    proven = provider_metadata_for_surface(
        "standalone",
        verified_model="Legacy 5.1",
        ui_model_label="Ghost 5.1 Legacy",
        verified_level=8,
        selection_verified=True,
    )
    assert proven["legacy51_sft_eligible"] is True


def test_daily_budget_and_reset(economy):
    budget = get_humanizer_daily_budget()
    assert budget.daily_limit == 10
    assert budget.used_today == 0
    assert budget.remaining == 10
    reset = next_reset_at()
    assert reset.tzinfo is not None
    assert reset.hour == 5 and reset.minute == 0
    assert budget.seconds_until_reset >= 0
    assert "+05:00" in budget.reset_at


def test_reserve_no_overspend_and_concurrent(economy):
    r1 = reserve_humanizer_slots(6)
    assert r1.reserved == 6
    r2 = reserve_humanizer_slots(6)
    assert r2.reserved == 4  # only 4 left
    r3 = reserve_humanizer_slots(1)
    assert r3.reserved == 0
    budget = get_humanizer_daily_budget()
    assert budget.used_today == 10
    assert budget.remaining == 0

    # Reset for concurrency test
    release_humanizer_slots(10)
    update_site_settings(humanizer_daily_limit=20)

    def _take(_: int) -> int:
        return reserve_humanizer_slots(3).reserved

    with ThreadPoolExecutor(max_workers=8) as pool:
        got = list(pool.map(_take, range(8)))
    assert sum(got) == 20
    assert get_humanizer_daily_budget().remaining == 0


def test_ten_minute_window(economy):
    budget = get_humanizer_daily_budget()
    # Far from reset → outside 10 min window unless forced
    assert within_reset_window(minutes_before_reset=10, budget=budget) == (
        budget.seconds_until_reset <= 600
    )
    near = budget
    # Construct a fake-near budget via plan force_window
    plan = plan_daily_backfill(
        dry_run=True,
        minutes_before_reset=10,
        force_window=True,
        max_documents=3,
    )
    assert plan.within_window is True
    assert plan.documents_to_attempt == min(3, plan.budget.remaining)


def test_synthetic_real_separation_and_dry_run(economy, tmp_path: Path):
    plan = plan_daily_backfill(
        dry_run=True,
        force_window=True,
        max_documents=2,
        output_root=tmp_path / "synthetic_daily",
    )
    assert plan.dry_run is True
    assert "synthetic_daily" in str(plan.output_dir)
    assert plan.as_dict()["separated_from_real_user_raw"] is True
    assert plan.as_dict()["teacher"]["level"] == 8

    result = run_daily_backfill(
        dry_run=False,
        force_window=True,
        max_documents=2,
        output_root=tmp_path / "synthetic_daily",
        execute_collector=False,  # reservation only; no Chrome
    )
    assert result.reserved == 2
    assert get_humanizer_daily_budget().used_today == 2
    # Release path
    release_humanizer_slots(2)
    assert get_humanizer_daily_budget().used_today == 0
