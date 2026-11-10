"""Privacy-conscious product growth events (activation, retention, conversion).

Server-side only for important successes. Never stores documents, prompts, passwords,
OTPs, cookies, tokens or raw IP addresses. Anonymous identity is a hash of the existing
guest session id. Failures in this module never break the product path.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from services.economy.db import connect

logger = logging.getLogger(__name__)

# Successful product funnel events. Client beacons may only emit CLIENT_EVENTS.
EVENTS = frozenset(
    {
        "registration_completed",
        "email_verified",
        "humanizer_first_success",
        "humanizer_success",
        "detector_first_success",
        "detector_success",
        "assignment_project_created",
        "assignment_analysis_completed",
        "pricing_viewed",
        "checkout_started",
        "payment_completed",
    }
)
CLIENT_EVENTS = frozenset({"pricing_viewed"})

RETENTION_DAYS = max(30, int(os.environ.get("PRODUCT_ANALYTICS_RETENTION_DAYS") or "365"))
_UTM_RE = re.compile(r"^[A-Za-z0-9_./+=-]{1,64}$")
_ACQ_KEYS = ("utm_source", "utm_medium", "utm_campaign")
_SESSION_PREFIX = "_pa_"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS product_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    user_id     INTEGER,
    anon_id     TEXT,
    tool        TEXT,
    word_bucket TEXT,
    outcome     TEXT NOT NULL DEFAULT 'success',
    source      TEXT,
    medium      TEXT,
    campaign    TEXT,
    dedupe_key  TEXT
);
CREATE INDEX IF NOT EXISTS idx_product_events_created ON product_events(created_at);
CREATE INDEX IF NOT EXISTS idx_product_events_event_created ON product_events(event, created_at);
CREATE INDEX IF NOT EXISTS idx_product_events_user_created ON product_events(user_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_product_events_dedupe
    ON product_events(dedupe_key) WHERE dedupe_key IS NOT NULL;
"""

_WORD_BUCKETS = (
    (500, "0-500"),
    (1000, "501-1000"),
    (2000, "1001-2000"),
    (5000, "2001-5000"),
)


def word_bucket(words: int | None) -> str | None:
    if words is None:
        return None
    try:
        n = int(words)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    for upper, label in _WORD_BUCKETS:
        if n <= upper:
            return label
    return "5000+"


def ensure_schema(conn: sqlite3.Connection | None = None) -> None:
    if conn is not None:
        conn.executescript(_SCHEMA)
        return
    with connect() as owned:
        owned.executescript(_SCHEMA)


def _salt() -> str:
    return (os.environ.get("PRODUCT_ANALYTICS_SALT") or os.environ.get("SECRET_KEY") or "dev").strip()


def anon_id_from_session(sess: Any) -> str | None:
    """Stable anonymous id derived from the existing guest humanizer session cookie value."""
    try:
        from services.free_humanize import GUEST_SESSION_KEY, guest_session_id

        raw = sess.get(GUEST_SESSION_KEY) if sess is not None else None
        if not isinstance(raw, str) or not raw:
            # Ensure a guest id exists so later guest→user stitches can use the same hash.
            if sess is None:
                return None
            raw = guest_session_id(sess)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, str) or not raw:
        return None
    return hashlib.sha256(f"{_salt()}|pa|{raw}".encode("utf-8")).hexdigest()[:32]


def capture_acquisition(req: Any, sess: Any) -> None:
    """Remember first-touch UTM params in the session (alphanumeric, length-capped)."""
    if sess is None or req is None:
        return
    try:
        args = req.args
    except Exception:  # noqa: BLE001
        return
    for key in _ACQ_KEYS:
        if sess.get(_SESSION_PREFIX + key):
            continue
        raw = args.get(key) if hasattr(args, "get") else None
        if isinstance(raw, str) and _UTM_RE.match(raw.strip()):
            sess[_SESSION_PREFIX + key] = raw.strip()[:64]


def _acquisition(sess: Any) -> dict[str, str | None]:
    out: dict[str, str | None] = {k: None for k in _ACQ_KEYS}
    if sess is None:
        return out
    for key in _ACQ_KEYS:
        val = sess.get(_SESSION_PREFIX + key)
        if isinstance(val, str) and val:
            out[key] = val[:64]
    return out


def _prune(conn: sqlite3.Connection) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM product_events WHERE created_at < ?", (cutoff,))


def record(
    event: str,
    *,
    user_id: int | None = None,
    anon_id: str | None = None,
    tool: str | None = None,
    words: int | None = None,
    outcome: str = "success",
    dedupe_key: str | None = None,
    session: Any = None,
    source: str | None = None,
    medium: str | None = None,
    campaign: str | None = None,
) -> bool:
    """Insert one event. Returns True when a new row was written. Never raises."""
    if event not in EVENTS:
        return False
    if outcome not in ("success", "failure"):
        outcome = "success"
    try:
        uid = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        uid = None
    if anon_id is None and session is not None:
        anon_id = anon_id_from_session(session)
    acq = _acquisition(session)
    src = (source or acq.get("utm_source"))
    med = (medium or acq.get("utm_medium"))
    camp = (campaign or acq.get("utm_campaign"))
    bucket = word_bucket(words)
    key = (dedupe_key or "")[:120] or None
    try:
        with connect() as conn:
            ensure_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            # Opportunistic cleanup (~1% of writes) keeps the table bounded without a cron.
            if (hash(event) + (uid or 0)) % 100 == 0:
                _prune(conn)
            try:
                conn.execute(
                    "INSERT INTO product_events "
                    "(event, user_id, anon_id, tool, word_bucket, outcome, source, medium, campaign, dedupe_key) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (event, uid, anon_id, tool, bucket, outcome, src, med, camp, key),
                )
            except sqlite3.IntegrityError:
                return False
            return True
    except Exception:  # noqa: BLE001
        logger.exception("product_analytics.record failed event=%s", event)
        return False


def record_tool_success(
    tool: str,
    *,
    user_id: int | None,
    words: int | None = None,
    session: Any = None,
) -> None:
    """Record both the recurring success and a one-shot first_success for the subject."""
    event = f"{tool}_success"
    first = f"{tool}_first_success"
    if event not in EVENTS or first not in EVENTS:
        return
    anon = anon_id_from_session(session) if user_id is None else None
    subject = f"u:{int(user_id)}" if user_id is not None else (f"a:{anon}" if anon else None)
    if subject:
        record(
            first,
            user_id=user_id,
            anon_id=anon,
            tool=tool,
            words=words,
            session=session,
            dedupe_key=f"{first}:{subject}",
        )
    record(event, user_id=user_id, anon_id=anon, tool=tool, words=words, session=session)


# --- metric definitions (admin) -------------------------------------------------

_METRIC_DEFS = {
    "dau": "Distinct authenticated users with any product_event on the selected UTC day (today: so far).",
    "wau": "Distinct authenticated users with any product_event in the last 7 UTC days including today.",
    "registrations": "Count of registration_completed events in the period.",
    "verified_rate": "email_verified ÷ registration_completed in the period. Unavailable when there are no registrations.",
    "first_use_activation": "Users with humanizer_first_success or detector_first_success within 7 UTC days of registration_completed, among users who registered in the period.",
    "humanizer_usage": "Count of humanizer_success events in the period.",
    "detector_usage": "Count of detector_success events in the period.",
    "assignment_usage": "assignment_project_created + assignment_analysis_completed in the period.",
    "d1_retention": "Share of users who registered on day D−1 (UTC) and had any product_event on day D (today). Unavailable with fewer than 5 cohort registrations.",
    "d7_retention": "Share of users who registered on day D−7 (UTC) and had any product_event on day D (today). Unavailable with fewer than 5 cohort registrations.",
    "pricing_views": "Count of pricing_viewed events in the period.",
    "checkout_conversion": "payment_completed ÷ checkout_started in the period. Unavailable when there are no checkouts.",
    "paid_conversion": "Distinct paying users (payment_completed) ÷ distinct registrations in the period. Unavailable when there are no registrations.",
    "revenue": "Gross USD from paid payment provider rows in the period (existing admin payment ledger). Not derived from product_events.",
    "returning_users": "Authenticated users with a product_event in the period who also had a product_event before the period start.",
}


def _day_start(offset_days: int = 0) -> str:
    day = datetime.now(timezone.utc).date() - timedelta(days=offset_days)
    return f"{day.isoformat()} 00:00:00"


def _unavailable(key: str, reason: str) -> dict[str, Any]:
    return {
        "key": key,
        "available": False,
        "value": None,
        "reason": reason,
        "definition": _METRIC_DEFS.get(key, ""),
    }


def _available(key: str, value: Any, **extra: Any) -> dict[str, Any]:
    out = {
        "key": key,
        "available": True,
        "value": value,
        "definition": _METRIC_DEFS.get(key, ""),
    }
    out.update(extra)
    return out


def _hidden_ids(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute(
        "SELECT id FROM users WHERE is_admin = 1 OR account_flag IN ('staff', 'test')"
    ).fetchall()
    return {int(r["id"]) for r in rows}


def _exclude_sql(hidden: set[int], column: str = "user_id") -> tuple[str, list[Any]]:
    if not hidden:
        return "", []
    placeholders = ",".join("?" * len(hidden))
    return f" AND ({column} IS NULL OR {column} NOT IN ({placeholders}))", list(hidden)


def growth_snapshot(*, period: str = "d7", exclude_staff: bool = True) -> dict[str, Any]:
    """Admin growth metrics. Never invents zeros for incomplete retention/rates."""
    if period not in ("today", "d7", "d30", "all"):
        period = "d7"
    starts = {"today": _day_start(0), "d7": _day_start(6), "d30": _day_start(29), "all": None}
    start = starts[period]
    with connect() as conn:
        ensure_schema(conn)
        has = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='product_events'"
        ).fetchone()
        if not has:
            return {
                "period": period,
                "metrics": [_unavailable(k, "product_events table missing") for k in _METRIC_DEFS],
                "funnel": [],
                "tools": [],
                "sources": [],
                "definitions": _METRIC_DEFS,
            }
        hidden = _hidden_ids(conn) if exclude_staff else set()
        excl, excl_params = _exclude_sql(hidden)

        def count_event(name: str, since: str | None = start) -> int:
            sql = f"SELECT COUNT(*) AS c FROM product_events WHERE event = ? AND outcome = 'success'{excl}"
            params: list[Any] = [name, *excl_params]
            if since:
                sql += " AND created_at >= ?"
                params.append(since)
            return int(conn.execute(sql, params).fetchone()["c"])

        def distinct_users(since: str | None = start) -> int:
            sql = (
                "SELECT COUNT(DISTINCT user_id) AS c FROM product_events "
                f"WHERE user_id IS NOT NULL AND outcome = 'success'{excl}"
            )
            params: list[Any] = [*excl_params]
            if since:
                sql += " AND created_at >= ?"
                params.append(since)
            return int(conn.execute(sql, params).fetchone()["c"])

        metrics: list[dict[str, Any]] = []
        metrics.append(_available("dau", distinct_users(_day_start(0))))
        metrics.append(_available("wau", distinct_users(_day_start(6))))

        regs = count_event("registration_completed")
        metrics.append(_available("registrations", regs))

        verified = count_event("email_verified")
        if regs <= 0:
            metrics.append(_unavailable("verified_rate", "No registrations in this period"))
        else:
            metrics.append(
                _available(
                    "verified_rate",
                    round(verified / regs, 4),
                    numerator=verified,
                    denominator=regs,
                )
            )

        # First-use activation among registrants in period.
        if regs <= 0:
            metrics.append(_unavailable("first_use_activation", "No registrations in this period"))
        else:
            since_clause = " AND r.created_at >= ?" if start else ""
            params: list[Any] = [*excl_params]
            if start:
                params.append(start)
            params.extend(excl_params)
            activated = conn.execute(
                f"""
                SELECT COUNT(DISTINCT r.user_id) AS c
                FROM product_events r
                WHERE r.event = 'registration_completed' AND r.outcome = 'success'
                  AND r.user_id IS NOT NULL{excl.replace('user_id', 'r.user_id')}
                  {since_clause}
                  AND EXISTS (
                    SELECT 1 FROM product_events f
                    WHERE f.user_id = r.user_id
                      AND f.event IN ('humanizer_first_success', 'detector_first_success')
                      AND f.outcome = 'success'
                      AND f.created_at >= r.created_at
                      AND f.created_at < datetime(r.created_at, '+7 days')
                      {excl.replace('user_id', 'f.user_id')}
                  )
                """,
                params,
            ).fetchone()["c"]
            metrics.append(
                _available(
                    "first_use_activation",
                    round(int(activated) / regs, 4),
                    numerator=int(activated),
                    denominator=regs,
                )
            )

        hum = count_event("humanizer_success")
        det = count_event("detector_success")
        asg = count_event("assignment_project_created") + count_event("assignment_analysis_completed")
        metrics.append(_available("humanizer_usage", hum))
        metrics.append(_available("detector_usage", det))
        metrics.append(_available("assignment_usage", asg))

        def retention(days: int, key: str) -> dict[str, Any]:
            # D1: registered yesterday [D-1, D), active today [D, D+1).
            # D7: registered on day D-7 [D-7, D-6), active today.
            today = _day_start(0)
            tomorrow = (
                datetime.now(timezone.utc).date() + timedelta(days=1)
            ).isoformat() + " 00:00:00"
            cohort_start = _day_start(days)
            cohort_end = _day_start(days - 1)
            rows = conn.execute(
                f"""
                SELECT COUNT(DISTINCT r.user_id) AS cohort,
                       COUNT(DISTINCT CASE WHEN a.user_id IS NOT NULL THEN r.user_id END) AS retained
                FROM product_events r
                LEFT JOIN product_events a
                  ON a.user_id = r.user_id
                 AND a.outcome = 'success'
                 AND a.created_at >= ? AND a.created_at < ?
                 {excl.replace('user_id', 'a.user_id')}
                WHERE r.event = 'registration_completed' AND r.outcome = 'success'
                  AND r.user_id IS NOT NULL
                  AND r.created_at >= ? AND r.created_at < ?
                  {excl.replace('user_id', 'r.user_id')}
                """,
                [today, tomorrow, *excl_params, cohort_start, cohort_end, *excl_params],
            ).fetchone()
            cohort = int(rows["cohort"] or 0)
            retained = int(rows["retained"] or 0)
            if cohort < 5:
                return _unavailable(key, f"Fewer than 5 registrations in the D{days} cohort ({cohort})")
            return _available(key, round(retained / cohort, 4), numerator=retained, denominator=cohort)

        metrics.append(retention(1, "d1_retention"))
        metrics.append(retention(7, "d7_retention"))

        metrics.append(_available("pricing_views", count_event("pricing_viewed")))

        checkouts = count_event("checkout_started")
        payments = count_event("payment_completed")
        if checkouts <= 0:
            metrics.append(_unavailable("checkout_conversion", "No checkout_started events in this period"))
        else:
            metrics.append(
                _available(
                    "checkout_conversion",
                    round(payments / checkouts, 4),
                    numerator=payments,
                    denominator=checkouts,
                )
            )

        if regs <= 0:
            metrics.append(_unavailable("paid_conversion", "No registrations in this period"))
        else:
            payers_sql = (
                "SELECT COUNT(DISTINCT user_id) AS c FROM product_events "
                f"WHERE event = 'payment_completed' AND outcome = 'success' AND user_id IS NOT NULL{excl}"
            )
            payers_params: list[Any] = [*excl_params]
            if start:
                payers_sql += " AND created_at >= ?"
                payers_params.append(start)
            payers = int(conn.execute(payers_sql, payers_params).fetchone()["c"])
            metrics.append(
                _available(
                    "paid_conversion",
                    round(payers / regs, 4),
                    numerator=payers,
                    denominator=regs,
                )
            )

        # Revenue from existing payment ledger (same sources as admin panel).
        try:
            from services.economy.admin_panel import _paid_rows, _in_window

            paid = _paid_rows(conn)
            rev = sum(
                p[2]
                for p in paid
                if (p[0] not in hidden) and (start is None or _in_window(p[1], start, None))
            )
            metrics.append(_available("revenue", round(float(rev), 2)))
        except Exception:  # noqa: BLE001
            metrics.append(_unavailable("revenue", "Payment ledger unavailable"))

        # Returning users
        if start is None:
            metrics.append(_unavailable("returning_users", "Not defined for all-time period"))
        else:
            returning = conn.execute(
                f"""
                SELECT COUNT(DISTINCT p.user_id) AS c
                FROM product_events p
                WHERE p.user_id IS NOT NULL AND p.outcome = 'success'
                  AND p.created_at >= ?{excl.replace('user_id', 'p.user_id')}
                  AND EXISTS (
                    SELECT 1 FROM product_events earlier
                    WHERE earlier.user_id = p.user_id
                      AND earlier.outcome = 'success'
                      AND earlier.created_at < ?
                      {excl.replace('user_id', 'earlier.user_id')}
                  )
                """,
                [start, *excl_params, start, *excl_params],
            ).fetchone()["c"]
            metrics.append(_available("returning_users", int(returning)))

        # Funnel counts (same period)
        funnel = [
            ["Registrations", regs],
            ["Email verified", verified],
            ["Humanizer first use", count_event("humanizer_first_success")],
            ["Detector first use", count_event("detector_first_success")],
            ["Pricing views", count_event("pricing_viewed")],
            ["Checkouts started", checkouts],
            ["Payments completed", payments],
        ]

        tools = [
            ["Humanizer", hum],
            ["Detector", det],
            ["Assignment create", count_event("assignment_project_created")],
            ["Assignment analysis", count_event("assignment_analysis_completed")],
        ]

        src_sql = (
            "SELECT COALESCE(NULLIF(source, ''), '(none)') AS src, COUNT(*) AS c "
            "FROM product_events WHERE outcome = 'success'"
        )
        src_params: list[Any] = []
        if start:
            src_sql += " AND created_at >= ?"
            src_params.append(start)
        src_sql += f"{excl} GROUP BY src ORDER BY c DESC LIMIT 8"
        sources = [
            [str(r["src"]), int(r["c"])]
            for r in conn.execute(src_sql, [*src_params, *excl_params]).fetchall()
        ]

    return {
        "period": period,
        "metrics": metrics,
        "funnel": funnel,
        "tools": tools,
        "sources": sources,
        "definitions": _METRIC_DEFS,
    }
