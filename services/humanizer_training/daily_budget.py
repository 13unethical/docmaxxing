"""Shared site-wide daily Humanizer budget (Asia/Tashkent).

Source of truth:
- limit: ``site_settings.humanizer_daily_limit`` (admin-configurable; default 50)
- used:  ``daily_stats.humanizer_requests_count`` for the current **05:00 period**
- reset: next **05:00 Asia/Tashkent** (not midnight)

Period rules (Asia/Tashkent):
- 04:59 → still previous period (started yesterday 05:00)
- 05:00 / 05:01 → new period
- 23:50 → ~5h10m until next reset

Synthetic backfill reserves slots atomically against the same counter so
real + synthetic usage cannot overspend the daily limit.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from typing import Any

from services.economy.db import connect  # used by get_humanizer_daily_budget
from services.economy.site_settings import (
    TZ_TASHKENT,
    ensure_schema,
    ensure_today_row,
    get_site_settings,
    now_tashkent,
)

# Business daily boundary for Humanizer allowance (Asia/Tashkent).
RESET_HOUR = 5
RESET_MINUTE = 0


@dataclass(slots=True)
class DailyHumanizerBudget:
    date: str
    timezone: str
    daily_limit: int
    used_today: int
    remaining: int
    reset_at: str
    seconds_until_reset: int
    minutes_until_reset: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "timezone": self.timezone,
            "daily_limit": self.daily_limit,
            "used_today": self.used_today,
            "remaining": self.remaining,
            "reset_at": self.reset_at,
            "seconds_until_reset": self.seconds_until_reset,
            "minutes_until_reset": self.minutes_until_reset,
        }


@dataclass(slots=True)
class ReservationResult:
    requested: int
    reserved: int
    budget: DailyHumanizerBudget

    @property
    def ok(self) -> bool:
        return self.reserved > 0


def _as_tashkent(now: datetime | None = None) -> datetime:
    current = now or now_tashkent()
    if current.tzinfo is None:
        return current.replace(tzinfo=TZ_TASHKENT)
    return current.astimezone(TZ_TASHKENT)


def humanizer_period_date(*, now: datetime | None = None) -> date:
    """Calendar date label for the open 05:00→05:00 period (Asia/Tashkent)."""
    current = _as_tashkent(now)
    if (current.hour, current.minute, current.second, current.microsecond) < (
        RESET_HOUR,
        RESET_MINUTE,
        0,
        0,
    ):
        return current.date() - timedelta(days=1)
    return current.date()


def humanizer_period_date_iso(*, now: datetime | None = None) -> str:
    return humanizer_period_date(now=now).isoformat()


def next_reset_at(*, now: datetime | None = None) -> datetime:
    """Nearest upcoming 05:00 Asia/Tashkent. At exactly 05:00, period has already rolled."""
    current = _as_tashkent(now)
    candidate = datetime.combine(
        current.date(),
        time(RESET_HOUR, RESET_MINUTE),
        tzinfo=TZ_TASHKENT,
    )
    if current >= candidate:
        candidate = candidate + timedelta(days=1)
    return candidate


def get_humanizer_daily_budget(
    *,
    day: str | None = None,
    now: datetime | None = None,
) -> DailyHumanizerBudget:
    """Read-only snapshot of the shared daily Humanizer allowance."""
    current = _as_tashkent(now)
    day_iso = day or humanizer_period_date_iso(now=current)
    settings = get_site_settings()
    limit = max(0, int(settings.get("humanizer_daily_limit") or 0))
    with connect() as conn:
        ensure_schema(conn)
        ensure_today_row(conn, day_iso)
        row = conn.execute(
            "SELECT humanizer_requests_count FROM daily_stats WHERE date = ?",
            (day_iso,),
        ).fetchone()
    used = int(row["humanizer_requests_count"] or 0) if row else 0
    remaining = max(0, limit - used)
    reset = next_reset_at(now=current)
    seconds = max(0, int((reset - current).total_seconds()))
    return DailyHumanizerBudget(
        date=day_iso,
        timezone="Asia/Tashkent",
        daily_limit=limit,
        used_today=used,
        remaining=remaining,
        reset_at=reset.isoformat(),
        seconds_until_reset=seconds,
        minutes_until_reset=round(seconds / 60.0, 3),
    )


def within_reset_window(
    *,
    minutes_before_reset: float = 10.0,
    now: datetime | None = None,
    budget: DailyHumanizerBudget | None = None,
) -> bool:
    snap = budget or get_humanizer_daily_budget(now=now)
    return snap.seconds_until_reset <= max(0.0, float(minutes_before_reset)) * 60.0


def reserve_humanizer_slots(
    n: int,
    *,
    day: str | None = None,
    now: datetime | None = None,
) -> ReservationResult:
    """Atomically reserve up to ``n`` slots against today's shared counter.

    Uses BEGIN IMMEDIATE so concurrent processes cannot overspend.
    Returns how many slots were actually reserved (may be 0).
    """
    from services.economy import db as economy_db

    requested = max(0, int(n))
    day_iso = day or humanizer_period_date_iso(now=now)
    take = 0
    conn = sqlite3.connect(str(economy_db.DB_PATH), timeout=30.0)
    economy_db._configure(conn)
    try:
        ensure_schema(conn)
        ensure_today_row(conn, day_iso)
        conn.commit()  # end any implicit txn from setup DDL/DML
        conn.execute("BEGIN IMMEDIATE")
        settings_row = conn.execute(
            "SELECT humanizer_daily_limit FROM site_settings WHERE id = 1"
        ).fetchone()
        limit = max(
            0,
            int((settings_row["humanizer_daily_limit"] if settings_row else None) or 50),
        )
        used_row = conn.execute(
            "SELECT humanizer_requests_count FROM daily_stats WHERE date = ?",
            (day_iso,),
        ).fetchone()
        used = int(used_row["humanizer_requests_count"] or 0) if used_row else 0
        remaining = max(0, limit - used)
        take = min(requested, remaining)
        if take > 0:
            conn.execute(
                "UPDATE daily_stats SET humanizer_requests_count = "
                "COALESCE(humanizer_requests_count, 0) + ? WHERE date = ?",
                (take, day_iso),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    budget = get_humanizer_daily_budget(day=day_iso, now=now)
    return ReservationResult(requested=requested, reserved=take, budget=budget)


def release_humanizer_slots(
    n: int,
    *,
    day: str | None = None,
    now: datetime | None = None,
) -> DailyHumanizerBudget:
    """Release previously reserved slots (e.g. failed synthetic attempts)."""
    from services.economy import db as economy_db

    give = max(0, int(n))
    day_iso = day or humanizer_period_date_iso(now=now)
    if give == 0:
        return get_humanizer_daily_budget(day=day_iso, now=now)
    conn = sqlite3.connect(str(economy_db.DB_PATH), timeout=30.0)
    economy_db._configure(conn)
    try:
        ensure_schema(conn)
        ensure_today_row(conn, day_iso)
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE daily_stats SET humanizer_requests_count = "
            "MAX(0, COALESCE(humanizer_requests_count, 0) - ?) WHERE date = ?",
            (give, day_iso),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_humanizer_daily_budget(day=day_iso, now=now)
