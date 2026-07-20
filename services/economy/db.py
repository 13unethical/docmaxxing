"""SQLite storage for the economy (users, wallets, ledger).

A tiny, dependency-free persistence layer. A fresh connection is opened per
operation (SQLite connections are cheap) with WAL enabled so the Flask request
threads and the background BrowserWorker never block each other for long.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _default_db_path() -> Path:
    override = (os.environ.get("ECONOMY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT / "data" / "economy.db"


DB_PATH = _default_db_path()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT,
    password_hash TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wallets (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    balance    INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,            -- credit | debit | refund
    feature       TEXT NOT NULL,            -- humanize | detect | check | cite | turnitin | assignment | topup | welcome_bonus
    amount        INTEGER NOT NULL,         -- always positive; sign implied by kind
    balance_after INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'completed',
    ref_id        TEXT,
    meta_json     TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tx_user_created
    ON transactions(user_id, created_at DESC);
"""


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a configured connection and commit/rollback around the block."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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
    """Create tables/indexes if they do not exist. Safe to call repeatedly."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    _configure(conn)
    try:
        conn.executescript(_SCHEMA)
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()
