"""Site-wide settings + daily usage counters (economy SQLite).

All daily boundaries use Asia/Tashkent (GMT+5).
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from .db import connect

SITE_SETTINGS_ID = 1
TZ_TASHKENT = ZoneInfo("Asia/Tashkent")

DEFAULT_SETTINGS = {
    "is_humanizer_discount_active": False,
    "humanizer_discount_percent": 50,
    "humanizer_daily_limit": 50,
    "turnitin_global_balance": 0,
    "auto_discount_enabled": False,
    "auto_discount_time": "20:00",
    "auto_discount_min_remaining": 10,
}


def now_tashkent() -> datetime:
    return datetime.now(TZ_TASHKENT)


def today_tashkent_iso() -> str:
    return now_tashkent().date().isoformat()


def _parse_hhmm(value: str | None) -> time:
    raw = (value or "20:00").strip()
    try:
        parts = raw.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return time(max(0, min(23, hour)), max(0, min(59, minute)))
    except (TypeError, ValueError, IndexError):
        return time(20, 0)


def ensure_schema(conn) -> None:
    """Create tables + columns idempotently (safe for older production DBs)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS daily_stats (
            date                       TEXT PRIMARY KEY,
            humanizer_requests_count   INTEGER NOT NULL DEFAULT 0,
            turnitin_requests_count    INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS site_settings (
            id                             INTEGER PRIMARY KEY CHECK (id = 1),
            is_humanizer_discount_active   INTEGER NOT NULL DEFAULT 0,
            humanizer_discount_percent     INTEGER NOT NULL DEFAULT 50,
            updated_at                     TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(site_settings)").fetchall()
    }
    alters = [
        ("humanizer_daily_limit", "INTEGER NOT NULL DEFAULT 50"),
        ("turnitin_global_balance", "INTEGER NOT NULL DEFAULT 0"),
        ("auto_discount_enabled", "INTEGER NOT NULL DEFAULT 0"),
        ("auto_discount_time", "TEXT NOT NULL DEFAULT '20:00'"),
        ("auto_discount_min_remaining", "INTEGER NOT NULL DEFAULT 10"),
    ]
    for name, decl in alters:
        if name not in cols:
            try:
                conn.execute(f"ALTER TABLE site_settings ADD COLUMN {name} {decl}")
            except Exception:
                pass

    row = conn.execute(
        "SELECT id FROM site_settings WHERE id = ?", (SITE_SETTINGS_ID,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO site_settings "
            "(id, is_humanizer_discount_active, humanizer_discount_percent, "
            "humanizer_daily_limit, turnitin_global_balance, auto_discount_enabled, "
            "auto_discount_time, auto_discount_min_remaining) "
            "VALUES (?, 0, 50, 50, 0, 0, '20:00', 10)",
            (SITE_SETTINGS_ID,),
        )


def ensure_today_row(conn, day: str | None = None) -> str:
    day = day or today_tashkent_iso()
    conn.execute(
        "INSERT INTO daily_stats (date, humanizer_requests_count, turnitin_requests_count) "
        "VALUES (?, 0, 0) ON CONFLICT(date) DO NOTHING",
        (day,),
    )
    return day


def _row_to_settings(row) -> dict[str, Any]:
    if row is None:
        return {**DEFAULT_SETTINGS, "updated_at": None}
    keys = set(row.keys())

    def _bool(name: str, default: bool = False) -> bool:
        if name not in keys:
            return default
        return bool(row[name])

    def _int(name: str, default: int) -> int:
        if name not in keys or row[name] is None:
            return default
        try:
            return int(row[name])
        except (TypeError, ValueError):
            return default

    def _str(name: str, default: str) -> str:
        if name not in keys or row[name] is None:
            return default
        return str(row[name])

    return {
        "is_humanizer_discount_active": _bool("is_humanizer_discount_active"),
        "humanizer_discount_percent": max(0, min(100, _int("humanizer_discount_percent", 50))),
        "humanizer_daily_limit": max(0, _int("humanizer_daily_limit", 50)),
        "turnitin_global_balance": max(0, _int("turnitin_global_balance", 0)),
        "auto_discount_enabled": _bool("auto_discount_enabled"),
        "auto_discount_time": _str("auto_discount_time", "20:00"),
        "auto_discount_min_remaining": max(0, _int("auto_discount_min_remaining", 10)),
        "updated_at": row["updated_at"] if "updated_at" in keys else None,
    }


def get_site_settings() -> dict[str, Any]:
    with connect() as conn:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT * FROM site_settings WHERE id = ?", (SITE_SETTINGS_ID,)
        ).fetchone()
    return _row_to_settings(row)


def update_site_settings(**kwargs: Any) -> dict[str, Any]:
    allowed = {
        "is_humanizer_discount_active",
        "humanizer_discount_percent",
        "humanizer_daily_limit",
        "turnitin_global_balance",
        "auto_discount_enabled",
        "auto_discount_time",
        "auto_discount_min_remaining",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return get_site_settings()

    with connect() as conn:
        ensure_schema(conn)
        if "is_humanizer_discount_active" in updates:
            conn.execute(
                "UPDATE site_settings SET is_humanizer_discount_active = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (1 if updates["is_humanizer_discount_active"] else 0, SITE_SETTINGS_ID),
            )
        if "humanizer_discount_percent" in updates:
            pct = max(0, min(100, int(updates["humanizer_discount_percent"])))
            conn.execute(
                "UPDATE site_settings SET humanizer_discount_percent = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (pct, SITE_SETTINGS_ID),
            )
        if "humanizer_daily_limit" in updates:
            limit = max(0, int(updates["humanizer_daily_limit"]))
            conn.execute(
                "UPDATE site_settings SET humanizer_daily_limit = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (limit, SITE_SETTINGS_ID),
            )
        if "turnitin_global_balance" in updates:
            balance = max(0, int(updates["turnitin_global_balance"]))
            conn.execute(
                "UPDATE site_settings SET turnitin_global_balance = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (balance, SITE_SETTINGS_ID),
            )
        if "auto_discount_enabled" in updates:
            conn.execute(
                "UPDATE site_settings SET auto_discount_enabled = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (1 if updates["auto_discount_enabled"] else 0, SITE_SETTINGS_ID),
            )
        if "auto_discount_time" in updates:
            hhmm = _parse_hhmm(str(updates["auto_discount_time"]))
            conn.execute(
                "UPDATE site_settings SET auto_discount_time = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (f"{hhmm.hour:02d}:{hhmm.minute:02d}", SITE_SETTINGS_ID),
            )
        if "auto_discount_min_remaining" in updates:
            mn = max(0, int(updates["auto_discount_min_remaining"]))
            conn.execute(
                "UPDATE site_settings SET auto_discount_min_remaining = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (mn, SITE_SETTINGS_ID),
            )
    return get_site_settings()


def get_daily_stats(day: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        ensure_schema(conn)
        day = ensure_today_row(conn, day)
        row = conn.execute(
            "SELECT * FROM daily_stats WHERE date = ?", (day,)
        ).fetchone()
    used_h = int(row["humanizer_requests_count"] or 0) if row else 0
    settings = get_site_settings()
    h_limit = int(settings["humanizer_daily_limit"] or 0)
    return {
        "date": day,
        "timezone": "Asia/Tashkent",
        "humanizer_requests_count": used_h,
        "humanizer_daily_limit": h_limit,
        "humanizer_remaining": max(0, h_limit - used_h),
        "turnitin_global_balance": int(settings["turnitin_global_balance"] or 0),
    }


def get_admin_dashboard_stats() -> dict[str, Any]:
    """Safe payload for GET /api/admin/daily-stats — never raises to callers."""
    try:
        settings = get_site_settings()
        today = get_daily_stats()
        status = get_current_humanizer_discount_status()
        return {
            "today": today,
            "settings": settings,
            "discount": status,
        }
    except Exception as exc:  # noqa: BLE001
        day = today_tashkent_iso()
        return {
            "today": {
                "date": day,
                "timezone": "Asia/Tashkent",
                "humanizer_requests_count": 0,
                "humanizer_daily_limit": 50,
                "humanizer_remaining": 50,
                "turnitin_global_balance": 0,
            },
            "settings": {**DEFAULT_SETTINGS, "updated_at": None},
            "discount": {
                "active": False,
                "percent": 50,
                "source": "none",
                "error": str(exc),
            },
        }


def increment_daily_stat(field: str, *, day: str | None = None, by: int = 1) -> dict[str, Any]:
    if field not in ("humanizer_requests_count",):
        raise ValueError(f"Unsupported daily stat field: {field}")
    by = int(by)
    if by == 0:
        return get_daily_stats(day)
    with connect() as conn:
        ensure_schema(conn)
        day = ensure_today_row(conn, day)
        conn.execute(
            f"UPDATE daily_stats SET {field} = COALESCE({field}, 0) + ? WHERE date = ?",
            (by, day),
        )
    return get_daily_stats(day)


def record_humanizer_success() -> dict[str, Any]:
    return increment_daily_stat("humanizer_requests_count")


def decrement_turnitin_global_balance(*, by: int = 1) -> dict[str, Any]:
    """Hard global balance for 3rd-party Turnitin checks (does not reset daily)."""
    by = max(0, int(by))
    with connect() as conn:
        ensure_schema(conn)
        if by > 0:
            conn.execute(
                "UPDATE site_settings SET "
                "turnitin_global_balance = MAX(0, COALESCE(turnitin_global_balance, 0) - ?), "
                "updated_at = datetime('now') WHERE id = ?",
                (by, SITE_SETTINGS_ID),
            )
    settings = get_site_settings()
    return {
        "turnitin_global_balance": int(settings["turnitin_global_balance"] or 0),
    }


def record_turnitin_success() -> dict[str, Any]:
    return decrement_turnitin_global_balance(by=1)

def get_current_humanizer_discount_status() -> dict[str, Any]:
    """Lazy evaluation: manual toggle OR auto-pilot after trigger time (GMT+5).

    If percent <= 0, discount is never active (no badge, no price cut).
    """
    settings = get_site_settings()
    percent = int(settings["humanizer_discount_percent"] or 0)
    percent = max(0, min(100, percent))
    remaining = get_daily_stats().get("humanizer_remaining")

    if percent <= 0:
        return {
            "active": False,
            "percent": 0,
            "source": "none",
            "remaining": remaining,
        }

    if settings["is_humanizer_discount_active"]:
        return {
            "active": True,
            "percent": percent,
            "source": "manual",
            "remaining": remaining,
        }

    if not settings["auto_discount_enabled"]:
        return {
            "active": False,
            "percent": percent,
            "source": "none",
            "remaining": remaining,
        }

    now = now_tashkent()
    trigger = _parse_hhmm(settings["auto_discount_time"])
    trigger_dt = datetime.combine(now.date(), trigger, tzinfo=TZ_TASHKENT)
    remaining_n = int(remaining or 0)
    min_remaining = int(settings["auto_discount_min_remaining"] or 0)

    if now >= trigger_dt and remaining_n >= min_remaining:
        return {
            "active": True,
            "percent": percent,
            "source": "auto",
            "remaining": remaining_n,
            "triggered_at": trigger.strftime("%H:%M"),
        }

    return {
        "active": False,
        "percent": percent,
        "source": "auto_waiting",
        "remaining": remaining_n,
        "trigger_time": trigger.strftime("%H:%M"),
        "min_remaining": min_remaining,
    }


def apply_humanizer_site_discount(base_cost: int) -> int:
    """Charge (100 - percent)% of base when discount is active (manual or auto)."""
    base = int(base_cost)
    if base <= 0:
        return 0
    status = get_current_humanizer_discount_status()
    if not status.get("active"):
        return base
    pct = int(status.get("percent") or 0)
    pct = max(0, min(100, pct))
    if pct <= 0:
        return base
    if pct >= 100:
        return 0
    # Strict formula: original * (100 - discount_percent) / 100
    return max(0, int(base * (100 - pct) / 100))


def humanize_credit_cost(base_cost: int | None = None) -> dict[str, Any]:
    """Explicit cost breakdown for the humanize charge path."""
    from .pricing import FEATURE_COSTS

    original = int(base_cost if base_cost is not None else FEATURE_COSTS["humanize"])
    status = get_current_humanizer_discount_status()
    charged = apply_humanizer_site_discount(original)
    active = bool(status.get("active")) and int(status.get("percent") or 0) > 0
    return {
        "original_price": original,
        "charged": charged,
        "discount_active": active,
        "discount_percent": int(status.get("percent") or 0),
        "discount_source": status.get("source") if active else "none",
    }
