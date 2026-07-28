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
    kind          TEXT NOT NULL,            -- credit | debit | refund (legacy sign helper)
    feature       TEXT NOT NULL,            -- humanize | detect | turnitin | assignment | topup | …
    amount        INTEGER NOT NULL,         -- always positive; sign implied by kind/type
    balance_before INTEGER,                 -- balance before this movement
    balance_after INTEGER NOT NULL,
    type          TEXT,                     -- PURCHASE | USAGE | REFUND | ADMIN_ADD | ADMIN_REMOVE | BONUS
    reference_type TEXT,                    -- Paddle | Humanizer | Turnitin | Assignment | Admin | …
    status        TEXT NOT NULL DEFAULT 'completed',
    ref_id        TEXT,                     -- reference_id (job/project/package/…)
    meta_json     TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tx_user_created
    ON transactions(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS paddle_purchases (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    paddle_transaction_id  TEXT NOT NULL UNIQUE,
    product_id             TEXT,
    price_id               TEXT,
    credits                INTEGER NOT NULL,
    amount                 REAL NOT NULL,
    currency               TEXT NOT NULL DEFAULT 'USD',
    status                 TEXT NOT NULL DEFAULT 'Pending',
    country                TEXT,
    created_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_paddle_purchases_user
    ON paddle_purchases(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paddle_purchases_status
    ON paddle_purchases(status);

CREATE TABLE IF NOT EXISTS cryptomus_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_id        TEXT NOT NULL UNIQUE,
    cryptomus_uuid  TEXT,
    amount          REAL NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD',
    credits         INTEGER NOT NULL,
    package_id      TEXT,
    status          TEXT NOT NULL DEFAULT 'Pending',
    txid            TEXT,
    paid_at         TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cryptomus_payments_user
    ON cryptomus_payments(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cryptomus_payments_status
    ON cryptomus_payments(status);

CREATE TABLE IF NOT EXISTS usage_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    feature        TEXT NOT NULL,
    credits_used   INTEGER NOT NULL DEFAULT 0,
    provider       TEXT,
    provider_cost  REAL,
    latency        INTEGER,
    request_id     TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_usage_user_created
    ON usage_events(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_usage_feature
    ON usage_events(feature);
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


def _migrate_transactions(conn: sqlite3.Connection) -> None:
    """Add CreditTransaction columns to existing DBs (safe, idempotent)."""
    # Table may not exist yet on a brand-new DB before CREATE TABLE runs.
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='transactions'"
    ).fetchone()
    if not exists:
        return
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(transactions)").fetchall()
    }
    alters = [
        ("balance_before", "ALTER TABLE transactions ADD COLUMN balance_before INTEGER"),
        ("type", "ALTER TABLE transactions ADD COLUMN type TEXT"),
        ("reference_type", "ALTER TABLE transactions ADD COLUMN reference_type TEXT"),
    ]
    for name, sql in alters:
        if name not in cols:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass


def _migrate_paddle_purchases(conn: sqlite3.Connection) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paddle_purchases'"
    ).fetchone()
    if not exists:
        return
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(paddle_purchases)").fetchall()
    }
    if "country" not in cols:
        try:
            conn.execute("ALTER TABLE paddle_purchases ADD COLUMN country TEXT")
        except sqlite3.OperationalError:
            pass


def _migrate_cryptomus_payments(conn: sqlite3.Connection) -> None:
    """Ensure cryptomus_payments exists on older DBs (CREATE IF NOT EXISTS in schema)."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cryptomus_payments'"
    ).fetchone()
    if exists:
        return
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cryptomus_payments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            order_id        TEXT NOT NULL UNIQUE,
            cryptomus_uuid  TEXT,
            amount          REAL NOT NULL,
            currency        TEXT NOT NULL DEFAULT 'USD',
            credits         INTEGER NOT NULL,
            package_id      TEXT,
            status          TEXT NOT NULL DEFAULT 'Pending',
            txid            TEXT,
            paid_at         TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cryptomus_payments_user
            ON cryptomus_payments(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cryptomus_payments_status
            ON cryptomus_payments(status);
        """
    )


def init_db() -> None:
    """Create tables/indexes if they do not exist. Safe to call repeatedly."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    _configure(conn)
    try:
        # 1) Create base tables (IF NOT EXISTS leaves old tables unchanged).
        conn.executescript(_SCHEMA)
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
        # 2) Add new ledger columns to existing DBs BEFORE indexes that need them.
        _migrate_transactions(conn)
        _migrate_paddle_purchases(conn)
        _migrate_cryptomus_payments(conn)
        # 3) Indexes that depend on migrated columns.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tx_user_type ON transactions(user_id, type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paddle_purchases_country "
            "ON paddle_purchases(country)"
        )
        # Defense in depth: one Cryptomus ledger credit per order_id.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_cryptomus_topup_ref "
            "ON transactions(ref_id) "
            "WHERE reference_type = 'Cryptomus' AND feature = 'topup' "
            "AND ref_id IS NOT NULL"
        )
        conn.commit()
    finally:
        conn.close()
