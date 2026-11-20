"""The $2,500 Challenge (referral race) — scoring, phases, leaderboard, admin."""

from __future__ import annotations

import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .db import connect
from .referral import ensure_referral_code
from .wallet import WalletService

_wallet = WalletService()

ET = ZoneInfo("America/New_York")

# Official windows (ET). End is exclusive midnight Dec 31 → contest runs through Dec 30.
CONTEST_START = datetime(2026, 11, 20, 0, 0, 0, tzinfo=ET)
CONTEST_END = datetime(2026, 12, 31, 0, 0, 0, tzinfo=ET)
VERIFY_END = datetime(2027, 1, 8, 0, 0, 0, tzinfo=ET)  # winners announced Jan 8
WINNERS_DATE = datetime(2027, 1, 8, 0, 0, 0, tzinfo=ET)

PENDING_CONFIRM_DAYS = 7
CREDITS_POOL = 100_000
CREDITS_MIN_PTS = 3
CREDITS_CAP = 10_000

TIERS: tuple[dict[str, Any], ...] = (
    {"from": 1, "to": 1, "prize": "$700", "min": 500, "group": "Cash", "plan": None, "cash_usd": 700},
    {"from": 2, "to": 2, "prize": "$200", "min": 250, "group": "Cash", "plan": None, "cash_usd": 200},
    {"from": 3, "to": 3, "prize": "$100", "min": 150, "group": "Cash", "plan": None, "cash_usd": 100},
    {"from": 4, "to": 10, "prize": "Max", "min": 50, "group": "Max · 1 month", "plan": "max", "cash_usd": None},
    {"from": 11, "to": 20, "prize": "Pro", "min": 25, "group": "Pro · 1 month", "plan": "pro", "cash_usd": None},
    {"from": 21, "to": 30, "prize": "Basic", "min": 10, "group": "Basic · 1 month", "plan": "basic", "cash_usd": None},
)

KIND_ELIGIBLE = "eligible"
KIND_FRIEND_HUM = "friend_humanize"
KIND_SPEND_SELF = "spend_self"
KIND_SPEND_FRIEND = "spend_friend"
KIND_PRIZE_CREDITS = "prize_credits"

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_REVERSED = "reversed"

FLAG_CLEAR = "clear"
FLAG_REJECT = "reject_signups"
FLAG_DQ = "dq"


class ContestError(Exception):
    """User-facing contest error."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(raw[:26], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def ensure_contest_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS contest_ledger (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            kind            TEXT NOT NULL,
            points          INTEGER NOT NULL DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'confirmed',
            pending_until   TEXT,
            source_user_id  INTEGER,
            payment_ref     TEXT,
            ref_id          TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_contest_ledger_ref
            ON contest_ledger(ref_id);
        CREATE INDEX IF NOT EXISTS idx_contest_ledger_user
            ON contest_ledger(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_contest_ledger_pending
            ON contest_ledger(status, pending_until);
        CREATE INDEX IF NOT EXISTS idx_contest_ledger_payment
            ON contest_ledger(payment_ref);

        CREATE TABLE IF NOT EXISTS contest_flags (
            user_id     INTEGER PRIMARY KEY,
            status      TEXT NOT NULL,
            reason      TEXT NOT NULL DEFAULT '',
            admin_id    INTEGER,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS contest_meta (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def _meta_get(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM contest_meta WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else None


def _meta_set(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO contest_meta (key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
        (key, value),
    )


def contest_phase(now: datetime | None = None) -> str:
    """before | live | verify | results."""
    override = (os.environ.get("CONTEST_PHASE_OVERRIDE") or "").strip().lower()
    if override in ("before", "live", "verify", "results"):
        return override
    with connect() as conn:
        ensure_contest_schema(conn)
        published = _meta_get(conn, "published")
        forced = _meta_get(conn, "phase_override")
    if forced in ("before", "live", "verify", "results"):
        return forced
    if published == "1":
        return "results"
    moment = now or _utc_now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    if moment < CONTEST_START.astimezone(timezone.utc):
        return "before"
    if moment < CONTEST_END.astimezone(timezone.utc):
        return "live"
    if moment < VERIFY_END.astimezone(timezone.utc):
        return "verify"
    return "results"


def display_name(row: Any) -> str:
    """First name + last initial, or email local-part."""
    raw = ""
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    for key in ("name", "display_name"):
        if key in keys:
            try:
                raw = (row[key] or "").strip()
            except (KeyError, IndexError, TypeError):
                raw = ""
            if raw:
                break
    if not raw:
        try:
            email = (row["email"] or "").strip() if "email" in keys else ""
            raw = email.split("@")[0] if email else f"User {int(row['id'])}"
        except (KeyError, IndexError, TypeError, ValueError):
            return "User"
    parts = raw.split()
    if len(parts) == 1:
        return parts[0][:24]
    return f"{parts[0][:20]} {parts[-1][0].upper()}."


def _is_eligible(conn, user_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM contest_ledger WHERE user_id = ? AND kind = ? AND status != ?",
        (int(user_id), KIND_ELIGIBLE, STATUS_REVERSED),
    ).fetchone()
    return row is not None


def _flag_status(conn, user_id: int) -> str | None:
    row = conn.execute(
        "SELECT status FROM contest_flags WHERE user_id = ?", (int(user_id),)
    ).fetchone()
    return str(row["status"]) if row else None


def _insert_ledger(
    conn,
    *,
    user_id: int,
    kind: str,
    points: int,
    ref_id: str,
    status: str = STATUS_CONFIRMED,
    pending_until: str | None = None,
    source_user_id: int | None = None,
    payment_ref: str | None = None,
) -> bool:
    """Insert if ref_id is new. Returns True when a row was added."""
    try:
        cur = conn.execute(
            "INSERT INTO contest_ledger "
            "(user_id, kind, points, status, pending_until, source_user_id, payment_ref, ref_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(user_id),
                kind,
                int(points),
                status,
                pending_until,
                int(source_user_id) if source_user_id is not None else None,
                payment_ref,
                ref_id,
            ),
        )
        return cur.rowcount == 1
    except sqlite3.IntegrityError:
        return False


def confirm_pending_points(now: datetime | None = None) -> int:
    """Flip pending rows whose pending_until has passed to confirmed."""
    moment = now or _utc_now()
    stamp = _iso(moment)
    with connect() as conn:
        ensure_contest_schema(conn)
        cur = conn.execute(
            "UPDATE contest_ledger SET status = ? "
            "WHERE status = ? AND pending_until IS NOT NULL AND pending_until <= ?",
            (STATUS_CONFIRMED, STATUS_PENDING, stamp),
        )
        return int(cur.rowcount or 0)


def mark_eligible(user_id: int) -> bool:
    """Record that this user has run Humanizer (points may count for them)."""
    with connect() as conn:
        ensure_contest_schema(conn)
        return _insert_ledger(
            conn,
            user_id=int(user_id),
            kind=KIND_ELIGIBLE,
            points=0,
            ref_id=f"contest_eligible_{int(user_id)}",
        )


def _award_referrer_for_verified_friend(conn, friend_id: int) -> bool:
    """+1 to referrer once per verified invitee (contest_hum_{friend_id})."""
    user = conn.execute(
        "SELECT id, referrer_id, is_verified FROM users WHERE id = ?",
        (int(friend_id),),
    ).fetchone()
    if user is None:
        return False
    keys = set(user.keys())
    if "is_verified" in keys and not bool(user["is_verified"]):
        return False
    referrer_id = user["referrer_id"]
    if referrer_id is None:
        return False
    referrer_id = int(referrer_id)
    uid = int(friend_id)
    if referrer_id == uid:
        return False
    if _flag_status(conn, referrer_id) in (FLAG_DQ, FLAG_REJECT):
        return False
    awarded = _insert_ledger(
        conn,
        user_id=referrer_id,
        kind=KIND_FRIEND_HUM,
        points=1,
        ref_id=f"contest_hum_{uid}",
        source_user_id=uid,
        status=STATUS_CONFIRMED,
    )
    if awarded:
        _insert_ledger(
            conn,
            user_id=referrer_id,
            kind=KIND_ELIGIBLE,
            points=0,
            ref_id=f"contest_eligible_{referrer_id}",
        )
    return awarded


def on_referral_verified(user_id: int) -> dict[str, Any]:
    """After invitee verifies email: mark them eligible + award referrer +1 once."""
    uid = int(user_id)
    out: dict[str, Any] = {"eligible": False, "friend_point": False}
    phase = contest_phase()
    out["eligible"] = mark_eligible(uid)
    if phase not in ("live", "verify"):
        return out
    with connect() as conn:
        ensure_contest_schema(conn)
        out["friend_point"] = _award_referrer_for_verified_friend(conn, uid)
    return out


def on_humanize_success(user_id: int, *, email_verified: bool = True) -> dict[str, Any]:
    """After a signed-in humanize: mark eligible + award referrer +1 once (idempotent)."""
    uid = int(user_id)
    out: dict[str, Any] = {"eligible": False, "friend_point": False}
    phase = contest_phase()
    out["eligible"] = mark_eligible(uid)
    if phase == "before" or phase not in ("live", "verify"):
        return out
    if not email_verified:
        return out
    with connect() as conn:
        ensure_contest_schema(conn)
        out["friend_point"] = _award_referrer_for_verified_friend(conn, uid)
    return out


def _has_humanize_history_sql() -> str:
    """SQL fragment: user id alias must be `u`.

    Usage rows are labeled ``Humanizer`` (see usage.FEATURE_HUMANIZER); wallet
    debits and plan_usage use ``humanize``. Match both.
    """
    return """
              (
                EXISTS (
                  SELECT 1 FROM contest_ledger e
                  WHERE e.user_id = u.id AND e.kind = ? AND e.status != ?
                )
                OR EXISTS (
                  SELECT 1 FROM usage_events ue
                  WHERE ue.user_id = u.id
                    AND lower(ue.feature) LIKE 'humaniz%'
                )
                OR EXISTS (
                  SELECT 1 FROM humanizer_dataset_logs h
                  WHERE h.user_id = u.id
                )
                OR EXISTS (
                  SELECT 1 FROM transactions t
                  WHERE t.user_id = u.id
                    AND lower(t.feature) LIKE 'humaniz%'
                    AND t.kind = 'debit'
                )
                OR EXISTS (
                  SELECT 1 FROM plan_usage pu
                  WHERE pu.user_id = u.id
                    AND pu.feature = 'humanize'
                    AND pu.used > 0
                )
              )
    """


def _backfill_eligibility_from_history(conn) -> int:
    """Mark eligible: historical humanizers + anyone who already has race points."""
    marked = 0
    # Anyone who already humanized (so they leave "Run Humanizer once").
    rows = conn.execute(
        f"""
        SELECT u.id AS user_id
        FROM users u
        WHERE {_has_humanize_history_sql()}
        """,
        (KIND_ELIGIBLE, STATUS_REVERSED),
    ).fetchall()
    for row in rows:
        if _insert_ledger(
            conn,
            user_id=int(row["user_id"]),
            kind=KIND_ELIGIBLE,
            points=0,
            ref_id=f"contest_eligible_{int(row['user_id'])}",
        ):
            marked += 1
    # Hosts who already have confirmed race points but were never marked eligible
    # (v1 backfill awarded friend_hum without opening eligibility).
    hosts = conn.execute(
        """
        SELECT DISTINCT user_id FROM contest_ledger
        WHERE status = ? AND kind != ? AND points > 0
        """,
        (STATUS_CONFIRMED, KIND_ELIGIBLE),
    ).fetchall()
    for row in hosts:
        uid = int(row["user_id"])
        if _insert_ledger(
            conn,
            user_id=uid,
            kind=KIND_ELIGIBLE,
            points=0,
            ref_id=f"contest_eligible_{uid}",
        ):
            marked += 1
    return marked


def backfill_friend_humanize_points(*, force: bool = False) -> int:
    """Award +1 for every historical invitee with a referrer (all-time).

    Opens eligibility for historical humanizers and for hosts who already hold
    race points. Idempotent via contest_hum_{friend_id}. Meta key
    friend_hum_backfill_v5 re-runs to also count older unverified invitees so
    the public board is not empty.
    """
    phase = contest_phase()
    if phase not in ("live", "verify", "results") and not force:
        return 0
    with connect() as conn:
        ensure_contest_schema(conn)
        if not force and _meta_get(conn, "friend_hum_backfill_v5") == "1":
            # Still heal eligibility if points/history exist without eligible rows.
            _backfill_eligibility_from_history(conn)
            return 0
        _backfill_eligibility_from_history(conn)
        # Historical race: every attributed invitee counts for the host.
        # Live scoring still awards on verify (same ref_id → no double count).
        rows = conn.execute(
            """
            SELECT u.id AS friend_id, u.referrer_id AS referrer_id
            FROM users u
            WHERE u.referrer_id IS NOT NULL
              AND u.referrer_id != u.id
            """
        ).fetchall()
        awarded = 0
        for row in rows:
            friend_id = int(row["friend_id"])
            referrer_id = int(row["referrer_id"])
            if _flag_status(conn, referrer_id) in (FLAG_DQ, FLAG_REJECT):
                continue
            if _insert_ledger(
                conn,
                user_id=referrer_id,
                kind=KIND_FRIEND_HUM,
                points=1,
                ref_id=f"contest_hum_{friend_id}",
                source_user_id=friend_id,
                status=STATUS_CONFIRMED,
            ):
                awarded += 1
            # Hosts with historical referrals must appear on the board.
            _insert_ledger(
                conn,
                user_id=referrer_id,
                kind=KIND_ELIGIBLE,
                points=0,
                ref_id=f"contest_eligible_{referrer_id}",
            )
        _meta_set(conn, "friend_hum_backfill", "1")
        _meta_set(conn, "friend_hum_backfill_v2", "1")
        _meta_set(conn, "friend_hum_backfill_v3", "1")
        _meta_set(conn, "friend_hum_backfill_v4", "1")
        _meta_set(conn, "friend_hum_backfill_v5", "1")
        return awarded


def on_contest_deposit(
    user_id: int,
    amount_usd: float,
    *,
    payment_ref: str | None = None,
) -> dict[str, Any]:
    """Award floor($) pending points to spender and their referrer."""
    phase = contest_phase()
    if phase not in ("live", "verify"):
        return {"handled": False, "reason": "not_live"}
    pts = int(math.floor(float(amount_usd or 0)))
    if pts < 1:
        return {"handled": False, "reason": "zero"}
    uid = int(user_id)
    ref = (payment_ref or "").strip() or f"deposit_{uid}_{_iso(_utc_now())}"
    pending_until = _iso(_utc_now() + timedelta(days=PENDING_CONFIRM_DAYS))
    awarded_self = awarded_friend = False
    with connect() as conn:
        ensure_contest_schema(conn)
        user = conn.execute(
            "SELECT id, referrer_id FROM users WHERE id = ?", (uid,)
        ).fetchone()
        if user is None:
            return {"handled": False, "reason": "missing"}
        # Self spend — only if eligible and not DQ
        if _is_eligible(conn, uid) and _flag_status(conn, uid) != FLAG_DQ:
            awarded_self = _insert_ledger(
                conn,
                user_id=uid,
                kind=KIND_SPEND_SELF,
                points=pts,
                ref_id=f"contest_spend_self_{ref}",
                status=STATUS_PENDING,
                pending_until=pending_until,
                source_user_id=uid,
                payment_ref=ref,
            )
        referrer_id = user["referrer_id"]
        if referrer_id is not None:
            rid = int(referrer_id)
            if (
                rid != uid
                and _is_eligible(conn, rid)
                and _flag_status(conn, rid) not in (FLAG_DQ, FLAG_REJECT)
            ):
                awarded_friend = _insert_ledger(
                    conn,
                    user_id=rid,
                    kind=KIND_SPEND_FRIEND,
                    points=pts,
                    ref_id=f"contest_spend_friend_{ref}",
                    status=STATUS_PENDING,
                    pending_until=pending_until,
                    source_user_id=uid,
                    payment_ref=ref,
                )
    return {
        "handled": awarded_self or awarded_friend,
        "points": pts,
        "self": awarded_self,
        "referrer": awarded_friend,
        "payment_ref": ref,
    }


def reverse_contest_deposit(payment_ref: str) -> int:
    """Reverse pending/confirmed spend points for a refunded payment."""
    ref = (payment_ref or "").strip()
    if not ref:
        return 0
    with connect() as conn:
        ensure_contest_schema(conn)
        cur = conn.execute(
            "UPDATE contest_ledger SET status = ? "
            "WHERE payment_ref = ? AND status IN (?, ?) AND kind IN (?, ?)",
            (
                STATUS_REVERSED,
                ref,
                STATUS_PENDING,
                STATUS_CONFIRMED,
                KIND_SPEND_SELF,
                KIND_SPEND_FRIEND,
            ),
        )
        return int(cur.rowcount or 0)


def set_flag(
    user_id: int,
    status: str,
    *,
    reason: str = "",
    admin_id: int | None = None,
) -> None:
    if status not in (FLAG_CLEAR, FLAG_REJECT, FLAG_DQ):
        raise ContestError("Invalid flag status.")
    uid = int(user_id)
    with connect() as conn:
        ensure_contest_schema(conn)
        if status == FLAG_CLEAR:
            conn.execute("DELETE FROM contest_flags WHERE user_id = ?", (uid,))
            return
        conn.execute(
            "INSERT INTO contest_flags (user_id, status, reason, admin_id, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET status = excluded.status, "
            "reason = excluded.reason, admin_id = excluded.admin_id, updated_at = datetime('now')",
            (uid, status, (reason or "").strip()[:500], admin_id),
        )
        if status == FLAG_REJECT:
            # Drop friend_humanize points this user earned from referrals.
            conn.execute(
                "UPDATE contest_ledger SET status = ? "
                "WHERE user_id = ? AND kind = ? AND status != ?",
                (STATUS_REVERSED, uid, KIND_FRIEND_HUM, STATUS_REVERSED),
            )


def tier_for_rank(rank: int) -> dict[str, Any] | None:
    for t in TIERS:
        if int(t["from"]) <= rank <= int(t["to"]):
            return t
    return None


def resolve_prize(rank: int, pts: int) -> dict[str, Any]:
    """Highest prize for this place whose minimum the score meets; else credits share hint."""
    t = tier_for_rank(rank)
    if t:
        candidates = [x for x in TIERS if int(x["from"]) >= int(t["from"]) and pts >= int(x["min"])]
        # Prefer the tier for this place if met, else next lower prize band by from desc
        if pts >= int(t["min"]):
            chosen = t
        elif candidates:
            chosen = min(candidates, key=lambda x: int(x["from"]))
        else:
            chosen = None
        if chosen:
            return {
                "label": chosen["prize"],
                "group": chosen["group"],
                "plan": chosen["plan"],
                "cash_usd": chosen["cash_usd"],
                "kind": "cash" if chosen["cash_usd"] else "plan",
            }
    if pts >= CREDITS_MIN_PTS:
        return {"label": "credits", "group": "Credits pool", "plan": None, "cash_usd": None, "kind": "credits"}
    return {"label": "—", "group": "", "plan": None, "cash_usd": None, "kind": "none"}


def _scores(conn) -> list[dict[str, Any]]:
    """Eligible, non-DQ users with confirmed points, earliest first for ties."""
    confirm_pending_points()
    rows = conn.execute(
        """
        SELECT l.user_id AS user_id,
               SUM(CASE WHEN l.status = ? AND l.kind != ? THEN l.points ELSE 0 END) AS pts,
               MIN(l.created_at) AS first_at
        FROM contest_ledger l
        WHERE EXISTS (
            SELECT 1 FROM contest_ledger e
            WHERE e.user_id = l.user_id AND e.kind = ? AND e.status != ?
        )
        AND NOT EXISTS (
            SELECT 1 FROM contest_flags f
            WHERE f.user_id = l.user_id AND f.status = ?
        )
        GROUP BY l.user_id
        HAVING pts > 0
        ORDER BY pts DESC, first_at ASC, user_id ASC
        """,
        (STATUS_CONFIRMED, KIND_ELIGIBLE, KIND_ELIGIBLE, STATUS_REVERSED, FLAG_DQ),
    ).fetchall()
    out = []
    for i, r in enumerate(rows, start=1):
        out.append(
            {
                "user_id": int(r["user_id"]),
                "rank": i,
                "pts": int(r["pts"] or 0),
                "first_at": r["first_at"],
            }
        )
    return out


def _pending_pts(conn, user_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(points), 0) AS n FROM contest_ledger "
        "WHERE user_id = ? AND status = ?",
        (int(user_id), STATUS_PENDING),
    ).fetchone()
    return int(row["n"] or 0)


def _credits_share(pts: int, pool_pts: int) -> int:
    if pts < CREDITS_MIN_PTS or pool_pts <= 0:
        return 0
    return min(CREDITS_CAP, int(round(pts / pool_pts * CREDITS_POOL)))


def leaderboard(*, limit: int = 30) -> list[dict[str, Any]]:
    backfill_friend_humanize_points()
    with connect() as conn:
        ensure_contest_schema(conn)
        scores = _scores(conn)[: max(1, int(limit))]
        if not scores:
            return []
        ids = [s["user_id"] for s in scores]
        placeholders = ",".join("?" * len(ids))
        users = {
            int(r["id"]): r
            for r in conn.execute(
                f"SELECT id, email, name FROM users WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        }
        all_scores = _scores(conn)
        pool_pts = sum(s["pts"] for s in all_scores if s["rank"] > 30 and s["pts"] >= CREDITS_MIN_PTS)
        phase = contest_phase()
        out = []
        for s in scores:
            u = users.get(s["user_id"])
            prize = resolve_prize(s["rank"], s["pts"])
            label = prize["label"]
            if prize["kind"] == "credits":
                share = _credits_share(s["pts"], pool_pts or 1)
                label = f"{'' if phase == 'results' else '~'}{share:,} credits"
            out.append(
                {
                    "rank": s["rank"],
                    "user_id": s["user_id"],
                    "name": display_name(u) if u else f"User {s['user_id']}",
                    "pts": s["pts"],
                    "prize": label,
                    "prize_meta": prize,
                }
            )
        return out


def public_config() -> dict[str, Any]:
    return {
        "name": "The $2,500 Challenge",
        "pool": "$2,500 in prizes",
        "poolExact": "$2,500",
        "start": CONTEST_START.isoformat(),
        "end": CONTEST_END.isoformat(),
        "winners": "Jan 8",
        "startShort": "Nov 20",
        "phase": contest_phase(),
        "tiers": [
            {"from": t["from"], "to": t["to"], "prize": t["prize"], "min": t["min"], "group": t["group"]}
            for t in TIERS
        ],
        "credits": {"pool": CREDITS_POOL, "min": CREDITS_MIN_PTS, "cap": CREDITS_CAP},
    }


def profile_for_user(
    user: dict[str, Any] | None,
    *,
    public_origin: str = "",
) -> dict[str, Any]:
    """Payload for GET /api/contest/me and SPA race card."""
    confirm_pending_points()
    phase = contest_phase()
    top = leaderboard(limit=30)
    cfg = public_config()
    base = {
        "success": True,
        "phase": phase,
        "config": cfg,
        "top": top,
        "me": None,
        "invite_link": "",
        "state": "guest",
    }
    if not user or user.get("id") is None:
        return base

    uid = int(user["id"])
    code = ensure_referral_code(uid)
    origin = (public_origin or "").rstrip("/")
    link = f"{origin}/register?ref={code}" if origin else f"/register?ref={code}"
    # Signed-in users are on the board for scoring; prize Humanizer gate is rules-only.
    mark_eligible(uid)

    with connect() as conn:
        ensure_contest_schema(conn)
        flag = _flag_status(conn, uid)
        eligible = _is_eligible(conn, uid)
        pending = _pending_pts(conn, uid)
        scores = _scores(conn)
        mine = next((s for s in scores if s["user_id"] == uid), None)
        pts = int(mine["pts"]) if mine else 0
        # Confirmed pts even if 0 for eligible
        if eligible and mine is None:
            row = conn.execute(
                "SELECT COALESCE(SUM(points), 0) AS n FROM contest_ledger "
                "WHERE user_id = ? AND status = ? AND kind != ?",
                (uid, STATUS_CONFIRMED, KIND_ELIGIBLE),
            ).fetchone()
            pts = int(row["n"] or 0)

        if flag == FLAG_DQ:
            state = "excluded"
            kind = "dq"
        elif phase == "before":
            state = "before"
            kind = "ready"
        elif pts <= 0:
            state = "zero"
            kind = "zero"
        else:
            state = "ranked"
            kind = "ranked"

        rank = int(mine["rank"]) if mine else None
        prize_meta = resolve_prize(rank or 999, pts) if pts else resolve_prize(999, 0)
        all_scores = scores
        pool_pts = sum(s["pts"] for s in all_scores if s["rank"] > 30 and s["pts"] >= CREDITS_MIN_PTS)
        prize_label = prize_meta["label"]
        if prize_meta["kind"] == "credits" and pts >= CREDITS_MIN_PTS:
            share = _credits_share(pts, pool_pts or 1)
            prize_label = f"{'' if phase == 'results' else '~'}{share:,} credits"

        # Rough credits estimate for non-top-30
        credits_hint = _credits_share(pts, pool_pts or max(pts, 1)) if pts >= CREDITS_MIN_PTS else 0

        me = {
            "kind": kind,
            "rank": rank,
            "pts": pts,
            "pending": pending,
            "prize": prize_label,
            "prize_meta": prize_meta,
            "credits_hint": credits_hint,
            "eligible": eligible,
            "flag": flag,
            "name": "You",
        }

    base.update(
        {
            "me": me,
            "invite_link": link,
            "referral_code": code,
            "state": state,
        }
    )
    return base


def admin_snapshot() -> dict[str, Any]:
    confirm_pending_points()
    with connect() as conn:
        ensure_contest_schema(conn)
        scores = _scores(conn)
        participants = conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS n FROM contest_ledger WHERE kind = ?",
            (KIND_ELIGIBLE,),
        ).fetchone()
        confirmed = conn.execute(
            "SELECT COALESCE(SUM(points), 0) AS n FROM contest_ledger "
            "WHERE status = ? AND kind != ?",
            (STATUS_CONFIRMED, KIND_ELIGIBLE),
        ).fetchone()
        pending = conn.execute(
            "SELECT COALESCE(SUM(points), 0) AS n FROM contest_ledger WHERE status = ?",
            (STATUS_PENDING,),
        ).fetchone()
        rejected = conn.execute(
            "SELECT COUNT(*) AS n FROM contest_flags WHERE status = ?",
            (FLAG_REJECT,),
        ).fetchone()
        flags = conn.execute(
            "SELECT f.user_id, f.status, f.reason, f.updated_at, u.email, u.name "
            "FROM contest_flags f "
            "LEFT JOIN users u ON u.id = f.user_id "
            "WHERE f.status IN (?, ?) "
            "ORDER BY f.updated_at DESC LIMIT 50",
            (FLAG_REJECT, FLAG_DQ),
        ).fetchall()
        # Heuristic queue: high friend_humanize velocity — simple list of top referrers
        hot = conn.execute(
            """
            SELECT user_id, COUNT(*) AS refs, COALESCE(SUM(points), 0) AS pts
            FROM contest_ledger
            WHERE kind = ? AND status = ?
            GROUP BY user_id
            HAVING refs >= 5
            ORDER BY refs DESC LIMIT 20
            """,
            (KIND_FRIEND_HUM, STATUS_CONFIRMED),
        ).fetchall()
        hot_ids = [int(r["user_id"]) for r in hot]
        names = {}
        if hot_ids:
            ph = ",".join("?" * len(hot_ids))
            for u in conn.execute(
                f"SELECT id, email, name FROM users WHERE id IN ({ph})", hot_ids
            ).fetchall():
                names[int(u["id"])] = display_name(u)

        top = leaderboard(limit=30)
        published = _meta_get(conn, "published") == "1"

    flag_rows = []
    for f in flags:
        flag_rows.append(
            {
                "user_id": int(f["user_id"]),
                "name": display_name(f),
                "status": f["status"],
                "reason": f["reason"] or "",
                "updated_at": f["updated_at"],
            }
        )
    # Merge hot into open flags queue if not already flagged
    flagged_ids = {r["user_id"] for r in flag_rows}
    open_flags = []
    for r in hot:
        uid = int(r["user_id"])
        if uid in flagged_ids:
            continue
        open_flags.append(
            {
                "user_id": uid,
                "name": names.get(uid, f"User {uid}"),
                "why": f"{int(r['refs'])} qualified referrals",
                "refs": int(r["refs"]),
                "pts": int(r["pts"]),
            }
        )

    return {
        "success": True,
        "phase": contest_phase(),
        "published": published,
        "totals": {
            "participants": int(participants["n"] or 0),
            "confirmed_points": int(confirmed["n"] or 0),
            "pending_points": int(pending["n"] or 0),
            "rejected_flags": int(rejected["n"] or 0),
            "ranked": len(scores),
        },
        "open_flags": open_flags,
        "flags": flag_rows,
        "top": top,
    }


def publish_results(*, admin_id: int | None = None) -> dict[str, Any]:
    """Lock results, grant plan months + credit pool; cash left for manual payout."""
    confirm_pending_points()
    from .plans import grant_plan

    with connect() as conn:
        ensure_contest_schema(conn)
        if _meta_get(conn, "published") == "1":
            return {"success": True, "already": True}
        _meta_set(conn, "published", "1")
        _meta_set(conn, "phase_override", "results")
        if admin_id is not None:
            _meta_set(conn, "published_by", str(int(admin_id)))

    board = leaderboard(limit=10_000)
    granted_plans: list[dict[str, Any]] = []
    granted_credits: list[dict[str, Any]] = []
    cash: list[dict[str, Any]] = []

    all_scores = board
    pool_pts = sum(s["pts"] for s in all_scores if s["rank"] > 30 and s["pts"] >= CREDITS_MIN_PTS)

    for row in board:
        prize = row.get("prize_meta") or resolve_prize(row["rank"], row["pts"])
        uid = int(row["user_id"])
        if prize.get("cash_usd"):
            cash.append({"user_id": uid, "rank": row["rank"], "usd": prize["cash_usd"], "name": row["name"]})
            continue
        if prize.get("plan"):
            try:
                grant_plan(
                    uid,
                    str(prize["plan"]),
                    days=30,
                    order_ref=f"contest_prize_{row['rank']}_{uid}",
                    extend_same=True,
                )
                granted_plans.append({"user_id": uid, "plan": prize["plan"], "rank": row["rank"]})
            except Exception:
                pass
            continue
        if row["rank"] > 30 and row["pts"] >= CREDITS_MIN_PTS:
            share = _credits_share(row["pts"], pool_pts or 1)
            if share < 1:
                continue
            ref = f"contest_credits_{uid}"
            with connect() as conn:
                ensure_contest_schema(conn)
                inserted = _insert_ledger(
                    conn,
                    user_id=uid,
                    kind=KIND_PRIZE_CREDITS,
                    points=0,
                    ref_id=ref,
                )
            if inserted:
                try:
                    _wallet.credit(
                        uid,
                        share,
                        "contest_prize",
                        ref_id=ref,
                        meta={"rank": row["rank"], "pts": row["pts"]},
                    )
                    granted_credits.append({"user_id": uid, "credits": share, "rank": row["rank"]})
                except Exception:
                    pass

    with connect() as conn:
        ensure_contest_schema(conn)
        _meta_set(conn, "cash_payouts", str(len(cash)))

    return {
        "success": True,
        "plans": granted_plans,
        "credits": granted_credits,
        "cash": cash,
    }
