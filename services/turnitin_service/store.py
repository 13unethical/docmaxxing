"""SQLite persistence for Turnitin / PlagDetect submissions."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _default_db_path() -> Path:
    override = (os.environ.get("TURNITIN_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT / "data" / "turnitin" / "submissions.db"


DB_PATH = _default_db_path()
UPLOAD_ROOT = _REPO_ROOT / "data" / "turnitin" / "uploads"
REPORT_ROOT = _REPO_ROOT / "data" / "turnitin" / "reports"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turnitin_submissions (
    id                  TEXT PRIMARY KEY,
    user_id             INTEGER NOT NULL,
    filename            TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'queued',
    similarity          REAL,
    ai_score            REAL,
    ai_highlights       REAL,
    exclude_bibliography INTEGER NOT NULL DEFAULT 0,
    exclude_quotes      INTEGER NOT NULL DEFAULT 0,
    upload_path         TEXT,
    similarity_report_path TEXT,
    ai_report_path      TEXT,
    ai_highlights_report_path TEXT,
    highlights_status     TEXT,
    highlights_job_id     TEXT,
    external_id         TEXT,
    job_id              TEXT,
    error_message       TEXT,
    meta_json           TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    completed_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_turnitin_user_created
    ON turnitin_submissions(user_id, created_at DESC);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    _configure(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)
        for col_sql in (
            "ALTER TABLE turnitin_submissions ADD COLUMN ai_highlights REAL",
            "ALTER TABLE turnitin_submissions ADD COLUMN ai_highlights_report_path TEXT",
            "ALTER TABLE turnitin_submissions ADD COLUMN highlights_status TEXT",
            "ALTER TABLE turnitin_submissions ADD COLUMN highlights_job_id TEXT",
        ):
            try:
                conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass


def resolve_report_path(path: str | None) -> str | None:
    """Return an absolute path to a report PDF if it exists on disk."""
    if not path:
        return None
    candidate = Path(path).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    rooted = (_REPO_ROOT / candidate).resolve()
    if rooted.is_file():
        return str(rooted)
    return None


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    meta = data.pop("meta_json", None)
    if meta:
        try:
            data["meta"] = json.loads(meta)
        except json.JSONDecodeError:
            data["meta"] = {}
    else:
        data["meta"] = {}
    data["exclude_bibliography"] = bool(data.get("exclude_bibliography"))
    data["exclude_quotes"] = bool(data.get("exclude_quotes"))
    sim_path = resolve_report_path(data.get("similarity_report_path"))
    ai_path = resolve_report_path(data.get("ai_report_path"))
    hl_path = resolve_report_path(data.get("ai_highlights_report_path"))
    data["similarity_report_path"] = sim_path
    data["ai_report_path"] = ai_path
    data["ai_highlights_report_path"] = hl_path
    data["has_similarity_report"] = bool(sim_path)
    data["has_ai_report"] = bool(ai_path)
    data["has_highlights_report"] = bool(hl_path)
    data["has_report"] = bool(sim_path or ai_path or hl_path)
    return data


class TurnitinStore:
    def create(
        self,
        *,
        submission_id: str,
        user_id: int,
        filename: str,
        upload_path: str,
        exclude_bibliography: bool = False,
        exclude_quotes: bool = False,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        now = _now_iso()
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO turnitin_submissions (
                    id, user_id, filename, status, exclude_bibliography, exclude_quotes,
                    upload_path, job_id, created_at, updated_at
                ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    user_id,
                    filename,
                    1 if exclude_bibliography else 0,
                    1 if exclude_quotes else 0,
                    upload_path,
                    job_id,
                    now,
                    now,
                ),
            )
        return self.get(submission_id) or {}

    def get(self, submission_id: str) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM turnitin_submissions WHERE id = ?",
                (submission_id,),
            ).fetchone()
        return _row_to_dict(row)

    def get_for_user(self, submission_id: str, user_id: int) -> dict[str, Any] | None:
        row = self.get(submission_id)
        if row is None or int(row["user_id"]) != int(user_id):
            return None
        return row

    def list_for_user(self, user_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM turnitin_submissions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [_row_to_dict(r) for r in rows if r is not None]

    def update(self, submission_id: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get(submission_id)
        allowed = {
            "status",
            "similarity",
            "ai_score",
            "ai_highlights",
            "external_id",
            "job_id",
            "error_message",
            "upload_path",
            "similarity_report_path",
            "ai_report_path",
            "ai_highlights_report_path",
            "highlights_status",
            "highlights_job_id",
            "meta_json",
            "completed_at",
        }
        parts: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            parts.append(f"{key} = ?")
            values.append(value)
        if not parts:
            return self.get(submission_id)
        parts.append("updated_at = ?")
        values.append(_now_iso())
        values.append(submission_id)
        with connect() as conn:
            conn.execute(
                f"UPDATE turnitin_submissions SET {', '.join(parts)} WHERE id = ?",
                values,
            )
        return self.get(submission_id)

    def delete_for_user(self, submission_id: str, user_id: int) -> bool:
        with connect() as conn:
            cur = conn.execute(
                "DELETE FROM turnitin_submissions WHERE id = ? AND user_id = ?",
                (submission_id, user_id),
            )
            deleted = cur.rowcount > 0
        return deleted
