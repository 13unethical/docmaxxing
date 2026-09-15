"""Unit tests for Humanizer daily budget 05:00 Asia/Tashkent reset."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from services.economy import db as economy_db
from services.economy.site_settings import (
    TZ_TASHKENT,
    ensure_schema,
    ensure_today_row,
    get_daily_stats,
    humanizer_stats_day_iso,
    record_humanizer_success,
    update_site_settings,
)
from services.humanizer_training.consent import ensure_training_consent_schema
from services.humanizer_training.daily_budget import (
    get_humanizer_daily_budget,
    humanizer_period_date_iso,
    next_reset_at,
    reserve_humanizer_slots,
    within_reset_window,
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


def _tashkent(y: int, m: int, d: int, hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, tzinfo=TZ_TASHKENT)


def test_reset_at_0459_still_current_period(economy):
    now = _tashkent(2026, 9, 5, 4, 59, 0)
    assert humanizer_period_date_iso(now=now) == "2026-09-04"
    reset = next_reset_at(now=now)
    assert reset == _tashkent(2026, 9, 5, 5, 0, 0)
    budget = get_humanizer_daily_budget(now=now)
    assert budget.date == "2026-09-04"
    assert budget.reset_at == reset.isoformat()
    assert budget.seconds_until_reset == 60
    assert budget.timezone == "Asia/Tashkent"


def test_reset_at_0500_new_period(economy):
    now = _tashkent(2026, 9, 5, 5, 0, 0)
    assert humanizer_period_date_iso(now=now) == "2026-09-05"
    reset = next_reset_at(now=now)
    assert reset == _tashkent(2026, 9, 6, 5, 0, 0)
    budget = get_humanizer_daily_budget(now=now)
    assert budget.date == "2026-09-05"
    assert budget.seconds_until_reset == 24 * 3600


def test_reset_at_0501_new_period(economy):
    now = _tashkent(2026, 9, 5, 5, 1, 0)
    assert humanizer_period_date_iso(now=now) == "2026-09-05"
    reset = next_reset_at(now=now)
    assert reset == _tashkent(2026, 9, 6, 5, 0, 0)
    budget = get_humanizer_daily_budget(now=now)
    assert budget.date == "2026-09-05"
    assert budget.seconds_until_reset == 24 * 3600 - 60


def test_reset_at_2350_about_five_hours_ten(economy):
    now = _tashkent(2026, 9, 4, 23, 50, 0)
    assert humanizer_period_date_iso(now=now) == "2026-09-04"
    reset = next_reset_at(now=now)
    assert reset == _tashkent(2026, 9, 5, 5, 0, 0)
    budget = get_humanizer_daily_budget(now=now)
    # 5h 10m = 18600 seconds
    assert budget.seconds_until_reset == 5 * 3600 + 10 * 60
    assert budget.minutes_until_reset == 310.0
    assert within_reset_window(minutes_before_reset=10, budget=budget) is False


def test_asia_tashkent_timezone_not_utc(economy):
    # 00:30 UTC = 05:30 Tashkent → already new period on that Tashkent date
    now_utc = datetime(2026, 9, 5, 0, 30, tzinfo=ZoneInfo("UTC"))
    budget = get_humanizer_daily_budget(now=now_utc)
    assert budget.timezone == "Asia/Tashkent"
    assert budget.date == "2026-09-05"
    assert "+05:00" in budget.reset_at
    reset = next_reset_at(now=now_utc)
    assert reset.hour == 5 and reset.minute == 0
    assert reset.utcoffset() == TZ_TASHKENT.utcoffset(reset)

    # 23:30 UTC = 04:30 next calendar morning Tashkent → still previous period
    before = datetime(2026, 9, 4, 23, 30, tzinfo=ZoneInfo("UTC"))
    assert humanizer_period_date_iso(now=before) == "2026-09-04"
    assert next_reset_at(now=before) == _tashkent(2026, 9, 5, 5, 0, 0)


def test_window_ten_minutes_before_0500(economy):
    near = _tashkent(2026, 9, 5, 4, 51, 0)
    budget = get_humanizer_daily_budget(now=near)
    assert budget.seconds_until_reset == 9 * 60
    assert within_reset_window(minutes_before_reset=10, now=near, budget=budget) is True

    far = _tashkent(2026, 9, 5, 4, 40, 0)
    budget_far = get_humanizer_daily_budget(now=far)
    assert within_reset_window(minutes_before_reset=10, now=far, budget=budget_far) is False


def test_0450_uses_previous_humanizer_period(economy):
    now = _tashkent(2026, 9, 15, 4, 50, 0)
    assert humanizer_period_date_iso(now=now) == "2026-09-14"
    assert humanizer_stats_day_iso(now=now) == "2026-09-14"
    # Calendar midnight key differs before 05:00 — stats must not use it.
    assert now.date().isoformat() == "2026-09-15"
    assert humanizer_stats_day_iso(now=now) != now.date().isoformat()
    stats = get_daily_stats(now=now)
    assert stats["date"] == "2026-09-14"


def test_0500_plus_uses_current_humanizer_period(economy):
    now = _tashkent(2026, 9, 15, 5, 0, 0)
    assert humanizer_period_date_iso(now=now) == "2026-09-15"
    assert humanizer_stats_day_iso(now=now) == "2026-09-15"
    stats = get_daily_stats(now=now)
    assert stats["date"] == "2026-09-15"


def test_record_humanizer_success_same_period_as_reserve(economy):
    before = _tashkent(2026, 9, 15, 4, 50, 0)
    period = humanizer_period_date_iso(now=before)
    assert period == "2026-09-14"

    reserved = reserve_humanizer_slots(3, now=before)
    assert reserved.reserved == 3
    assert reserved.budget.date == period

    recorded = record_humanizer_success(now=before)
    assert recorded["date"] == period
    assert recorded["humanizer_requests_count"] == 4  # 3 reserved + 1 success

    budget = get_humanizer_daily_budget(now=before)
    assert budget.date == period
    assert budget.used_today == 4
    assert get_daily_stats(now=before)["humanizer_remaining"] == budget.remaining

    after = _tashkent(2026, 9, 15, 5, 10, 0)
    period_new = humanizer_period_date_iso(now=after)
    assert period_new == "2026-09-15"
    recorded_new = record_humanizer_success(now=after)
    assert recorded_new["date"] == period_new
    assert recorded_new["humanizer_requests_count"] == 1
    # Previous period untouched by post-05:00 write
    assert get_daily_stats(day=period)["humanizer_requests_count"] == 4
