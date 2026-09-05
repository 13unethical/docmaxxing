"""Tests for synthetic daily backfill scheduling semantics (idempotency, budget, TZ)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from services.economy import db as economy_db
from services.economy.site_settings import (
    TZ_TASHKENT,
    ensure_schema,
    ensure_today_row,
    update_site_settings,
)
from services.humanizer_training.consent import ensure_training_consent_schema
from services.humanizer_training.daily_budget import (
    get_humanizer_daily_budget,
    humanizer_period_date_iso,
    next_reset_at,
    release_humanizer_slots,
    within_reset_window,
)
from services.humanizer_training.synthetic_daily import (
    claim_daily_run_marker,
    has_daily_run_marker,
    plan_daily_backfill,
    run_daily_backfill,
)


@pytest.fixture()
def economy(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "economy.db"
    monkeypatch.setattr(economy_db, "DB_PATH", db_path)
    economy_db.init_db()
    ensure_training_consent_schema()
    with economy_db.connect() as conn:
        ensure_schema(conn)
        ensure_today_row(conn)
    update_site_settings(humanizer_daily_limit=10)
    return tmp_path


def test_zero_remaining_does_nothing(economy, tmp_path: Path):
    # Exhaust allowance first
    from services.humanizer_training.daily_budget import reserve_humanizer_slots

    assert reserve_humanizer_slots(10).reserved == 10
    assert get_humanizer_daily_budget().remaining == 0

    root = tmp_path / "synthetic_daily"
    plan = plan_daily_backfill(
        dry_run=True,
        force_window=True,
        output_root=root,
    )
    assert plan.reason == "no_remaining_allowance"
    assert plan.documents_to_attempt == 0

    result = run_daily_backfill(
        dry_run=False,
        force_window=True,
        output_root=root,
        execute_collector=False,
    )
    assert result.reserved == 0
    assert not has_daily_run_marker(result.plan.output_dir)
    assert get_humanizer_daily_budget().used_today == 10


def test_remaining_budget_caps_attempt(economy, tmp_path: Path):
    from services.humanizer_training.daily_budget import reserve_humanizer_slots

    reserve_humanizer_slots(7)
    plan = plan_daily_backfill(
        dry_run=True,
        force_window=True,
        output_root=tmp_path / "synthetic_daily",
    )
    assert plan.budget.remaining == 3
    assert plan.documents_to_attempt == 3
    assert plan.reason == "ready"


def test_idempotent_daily_run_and_duplicate_invocation(economy, tmp_path: Path):
    root = tmp_path / "synthetic_daily"
    day = humanizer_period_date_iso()

    first = run_daily_backfill(
        dry_run=False,
        force_window=True,
        max_documents=4,
        date=day,
        output_root=root,
        execute_collector=False,
    )
    assert first.reserved == 4
    assert has_daily_run_marker(first.plan.output_dir)
    used_after_first = get_humanizer_daily_budget().used_today
    assert used_after_first == 4

    # Simulate released leftover remaining (would otherwise allow another spend)
    release_humanizer_slots(2)
    assert get_humanizer_daily_budget().remaining == 8

    plan2 = plan_daily_backfill(
        dry_run=True,
        force_window=True,
        date=day,
        output_root=root,
    )
    assert plan2.reason == "already_ran_today"
    assert plan2.documents_to_attempt == 0

    second = run_daily_backfill(
        dry_run=False,
        force_window=True,
        max_documents=4,
        date=day,
        output_root=root,
        execute_collector=False,
    )
    assert second.reserved == 0
    assert second.plan.reason == "already_ran_today"
    # Budget unchanged by duplicate (still 4-2=2 used after release above... wait:
    # after first used=4, release 2 → used=2. Duplicate must not change used.
    assert get_humanizer_daily_budget().used_today == 2


def test_duplicate_concurrent_claim_single_reservation(economy, tmp_path: Path):
    root = tmp_path / "synthetic_daily"
    day = humanizer_period_date_iso()

    def _once(_: int):
        return run_daily_backfill(
            dry_run=False,
            force_window=True,
            max_documents=5,
            date=day,
            output_root=root,
            execute_collector=False,
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(_once, range(6)))

    reserved_total = sum(r.reserved for r in results)
    assert reserved_total == 5
    assert sum(1 for r in results if r.reserved > 0) == 1
    assert get_humanizer_daily_budget().used_today == 5
    assert has_daily_run_marker(root / day)


def test_wrong_date_timezone_isolation(economy, tmp_path: Path):
    root = tmp_path / "synthetic_daily"
    tashkent_today = humanizer_period_date_iso()
    # Explicit past date must not share today's marker / budget day.
    other_day = "2020-01-15"
    assert other_day != tashkent_today

    other = run_daily_backfill(
        dry_run=False,
        force_window=True,
        max_documents=2,
        date=other_day,
        output_root=root,
        execute_collector=False,
    )
    assert other.reserved == 2
    assert has_daily_run_marker(root / other_day)
    assert not has_daily_run_marker(root / tashkent_today)

    # Budget counter is keyed by the requested day string.
    assert get_humanizer_daily_budget(day=other_day).used_today == 2
    assert get_humanizer_daily_budget(day=tashkent_today).used_today == 0

    today_plan = plan_daily_backfill(
        dry_run=True,
        force_window=True,
        date=tashkent_today,
        output_root=root,
        max_documents=3,
    )
    assert today_plan.reason == "ready"
    assert today_plan.documents_to_attempt == 3

    # Reset is next 05:00 Asia/Tashkent, not UTC midnight.
    budget = get_humanizer_daily_budget()
    assert budget.timezone == "Asia/Tashkent"
    assert "+05:00" in budget.reset_at
    assert next_reset_at().hour == 5
    # Far from 05:00 → outside 10-minute window
    if budget.seconds_until_reset > 600:
        assert within_reset_window(minutes_before_reset=10, budget=budget) is False
        outside = plan_daily_backfill(
            dry_run=True,
            minutes_before_reset=10,
            force_window=False,
            output_root=root,
            date=tashkent_today,
        )
        assert outside.documents_to_attempt == 0
        assert "outside_reset_window" in outside.reason

    # UTC evening can already be next calendar day in Tashkent (UTC+5).
    now_utc = datetime(2026, 9, 4, 20, 0, tzinfo=ZoneInfo("UTC"))
    now_tashkent = now_utc.astimezone(TZ_TASHKENT)
    assert now_tashkent.date().isoformat() == "2026-09-05"


def test_claim_marker_exclusive(tmp_path: Path):
    out = tmp_path / "2026-09-04"
    assert claim_daily_run_marker(out, day="2026-09-04") is True
    assert claim_daily_run_marker(out, day="2026-09-04") is False
    assert has_daily_run_marker(out) is True
