"""Site-wide activity ledger (admin-only audit trail).

Every notable action — registrations, logins, coin movements, admin edits,
and state-changing HTTP requests — lands in ``activity_log``. The table has no
foreign key to ``users`` on purpose: deleting an account must not erase its
history, so the email is snapshotted on each row.

Writers never raise; a logging failure must not break the action being logged.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from flask import current_app, g, has_request_context, request

from .db import connect

_SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    category     TEXT NOT NULL,
    action       TEXT NOT NULL,
    user_id      INTEGER,
    user_email   TEXT,
    actor_id     INTEGER,
    actor_email  TEXT,
    summary      TEXT,
    details_json TEXT,
    method       TEXT,
    path         TEXT,
    status_code  INTEGER,
    ip           TEXT,
    source_ref   TEXT
);

CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_category ON activity_log(category, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_source_ref
    ON activity_log(source_ref) WHERE source_ref IS NOT NULL;
"""

_CATEGORY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^/api/admin/|^/admin"), "admin"),
    (re.compile(r"^/api/auth/|^/(login|register|logout|verify-email)"), "auth"),
    (re.compile(r"paddle|cryptomus|gumroad|lemon|webhook|checkout|/api/billing|/api/payments?"), "payment"),
    (re.compile(r"^/api/assignment"), "assignment"),
    (re.compile(r"humaniz|stealthwriter|zerogpt"), "humanizer"),
    (re.compile(r"turnitin|plagdetect"), "turnitin"),
    (re.compile(r"detect|/api/check"), "detector"),
    (re.compile(r"support"), "support"),
    (re.compile(r"referral|withdraw"), "referral"),
    (re.compile(r"format|preview|/api/convert|/api/upload|workspace"), "formatter"),
    (re.compile(r"account|avatar|profile|password"), "account"),
]

# High-frequency autosaves / pings that would drown the ledger.
_NOISY_PATHS = re.compile(
    r"/chat-transcript$|/heartbeat$|/api/telemetry|/api/client-log|/api/track|/favicon"
)


def ensure_activity_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)


def category_for_path(path: str) -> str:
    low = (path or "").lower()
    for pattern, category in _CATEGORY_RULES:
        if pattern.search(low):
            return category
    return "other"


def _lookup_email(conn: sqlite3.Connection, user_id: int | None) -> str | None:
    if not user_id:
        return None
    row = conn.execute("SELECT email FROM users WHERE id = ?", (int(user_id),)).fetchone()
    return row["email"] if row else None


def _request_context() -> dict[str, Any]:
    if not has_request_context():
        return {}
    from .auth import client_ip_from_request, current_user_id

    try:
        actor_id = current_user_id()
    except Exception:  # noqa: BLE001
        actor_id = None
    return {
        "actor_id": actor_id,
        "method": request.method,
        "path": request.path,
        "ip": client_ip_from_request(),
    }


def log_activity(
    action: str,
    *,
    category: str | None = None,
    user_id: int | None = None,
    user_email: str | None = None,
    actor_id: int | None = None,
    summary: str | None = None,
    details: dict[str, Any] | None = None,
    status_code: int | None = None,
    source_ref: str | None = None,
    mark_request: bool = True,
) -> None:
    """Append one ledger row. Safe to call from anywhere; never raises.

    ``mark_request`` tells the generic request logger that this request already
    produced a meaningful entry, so it does not add a duplicate raw HTTP row.
    """
    try:
        ctx = _request_context()
        if actor_id is None:
            actor_id = ctx.get("actor_id")
        with connect() as conn:
            ensure_activity_schema(conn)
            if user_email is None:
                user_email = _lookup_email(conn, user_id)
            actor_email = user_email if actor_id and actor_id == user_id else _lookup_email(conn, actor_id)
            conn.execute(
                "INSERT OR IGNORE INTO activity_log "
                "(category, action, user_id, user_email, actor_id, actor_email, summary, "
                " details_json, method, path, status_code, ip, source_ref) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    category or action.split(".", 1)[0],
                    action,
                    int(user_id) if user_id else None,
                    user_email,
                    int(actor_id) if actor_id else None,
                    actor_email,
                    (summary or "")[:500] or None,
                    json.dumps(details, ensure_ascii=False, default=str) if details else None,
                    ctx.get("method"),
                    ctx.get("path"),
                    status_code,
                    ctx.get("ip"),
                    source_ref,
                ),
            )
        if mark_request and has_request_context():
            g._activity_logged = True
    except Exception:  # noqa: BLE001
        pass


def log_request(response: Any) -> Any:
    """``after_request`` hook: record state-changing requests and downloads."""
    try:
        # Test clients often run against the real DB without isolating it.
        if current_app.testing or getattr(g, "_activity_logged", False):
            return response
        method = request.method.upper()
        path = request.path or ""
        if path.startswith("/static/") or _NOISY_PATHS.search(path):
            return response
        is_download = method == "GET" and "/download" in path
        if method in {"GET", "HEAD", "OPTIONS"} and not is_download:
            return response
        ctx = _request_context()
        status = int(getattr(response, "status_code", 0) or 0)
        endpoint = request.endpoint or ""
        user_id = ctx.get("actor_id")
        log_activity(
            "request.download" if is_download else f"request.{method.lower()}",
            category=category_for_path(path),
            user_id=user_id,
            actor_id=user_id,
            summary=f"{method} {path} → {status}",
            details={"endpoint": endpoint} if endpoint else None,
            status_code=status,
            mark_request=False,
        )
    except Exception:  # noqa: BLE001
        pass
    return response


def backfill_activity(conn: sqlite3.Connection) -> None:
    """Import history that predates the ledger. Idempotent via ``source_ref``."""
    ensure_activity_schema(conn)
    conn.execute(
        """
        INSERT OR IGNORE INTO activity_log
            (created_at, category, action, user_id, user_email, actor_id, actor_email,
             summary, source_ref)
        SELECT created_at, 'account', 'user.register', id, email, id, email,
               'Registered ' || email, 'users:' || id
        FROM users
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO activity_log
            (created_at, category, action, user_id, user_email, summary, details_json, source_ref)
        SELECT t.created_at, 'wallet',
               'wallet.' || lower(COALESCE(t.type, t.kind)),
               t.user_id, u.email,
               printf('%s %+d coins (%d → %d)', t.feature,
                      CASE t.kind WHEN 'debit' THEN -t.amount ELSE t.amount END,
                      COALESCE(t.balance_before, 0), t.balance_after),
               json_object('feature', t.feature, 'kind', t.kind, 'amount', t.amount,
                           'reference_type', t.reference_type, 'ref_id', t.ref_id),
               'tx:' || t.id
        FROM transactions t
        LEFT JOIN users u ON u.id = t.user_id
        """
    )
    has_withdrawals = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='withdrawal_requests'"
    ).fetchone()
    if has_withdrawals:
        conn.execute(
            """
            INSERT OR IGNORE INTO activity_log
                (created_at, category, action, user_id, user_email, actor_id, actor_email,
                 summary, source_ref)
            SELECT w.created_at, 'referral', 'withdrawal.request', w.user_id, u.email,
                   w.user_id, u.email,
                   printf('Withdrawal $%.2f (%s)', w.amount_usd, w.status),
                   'withdrawal:' || w.id
            FROM withdrawal_requests w
            LEFT JOIN users u ON u.id = w.user_id
            """
        )


def _row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
    details = None
    if row["details_json"]:
        try:
            details = json.loads(row["details_json"])
        except (TypeError, ValueError):
            details = row["details_json"]
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "category": row["category"],
        "action": row["action"],
        "user_id": row["user_id"],
        "user_email": row["user_email"],
        "actor_id": row["actor_id"],
        "actor_email": row["actor_email"],
        "summary": row["summary"],
        "details": details,
        "method": row["method"],
        "path": row["path"],
        "status_code": row["status_code"],
        "ip": row["ip"],
    }


def list_activity(
    *,
    search: str = "",
    category: str = "",
    user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    clauses: list[str] = []
    params: list[Any] = []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if user_id:
        clauses.append("(user_id = ? OR actor_id = ?)")
        params.extend([int(user_id), int(user_id)])
    q = (search or "").strip().lower()
    if q:
        like = f"%{q}%"
        clauses.append(
            "(LOWER(COALESCE(user_email, '')) LIKE ? OR LOWER(COALESCE(actor_email, '')) LIKE ? "
            "OR LOWER(action) LIKE ? OR LOWER(COALESCE(summary, '')) LIKE ? "
            "OR LOWER(COALESCE(path, '')) LIKE ? OR COALESCE(ip, '') LIKE ? "
            "OR CAST(user_id AS TEXT) = ?)"
        )
        params.extend([like, like, like, like, like, like, q])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with connect() as conn:
        ensure_activity_schema(conn)
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM activity_log {where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM activity_log {where} "
            "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        categories = conn.execute(
            "SELECT category, COUNT(*) AS c FROM activity_log GROUP BY category ORDER BY c DESC"
        ).fetchall()
        counters = conn.execute(
            "SELECT "
            " SUM(action = 'user.register') AS registered, "
            " SUM(action = 'admin.user_deleted') AS deleted "
            "FROM activity_log"
        ).fetchone()

    return {
        "entries": [_row_to_entry(r) for r in rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "categories": [{"category": r["category"], "count": int(r["c"])} for r in categories],
        "registered_events": int(counters["registered"] or 0),
        "deleted_events": int(counters["deleted"] or 0),
    }
