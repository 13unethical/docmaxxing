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
    type          TEXT,                     -- PURCHASE | USAGE | REFUND | ADMIN_ADD | ADMIN_REMOVE | ADMIN_SET | BONUS
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

CREATE TABLE IF NOT EXISTS gumroad_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id         TEXT NOT NULL UNIQUE,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    email           TEXT,
    product_id      TEXT,
    short_product_id TEXT,
    package_id      TEXT,
    price_cents     INTEGER NOT NULL DEFAULT 0,
    credits         INTEGER NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'usd',
    status          TEXT NOT NULL DEFAULT 'Paid',
    payload_json    TEXT,
    paid_at         TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_gumroad_payments_user
    ON gumroad_payments(user_id, created_at DESC);

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

CREATE TABLE IF NOT EXISTS withdrawal_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount_usd      REAL NOT NULL,
    wallet_details  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    admin_note      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_withdrawal_status
    ON withdrawal_requests(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_withdrawal_user
    ON withdrawal_requests(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS daily_stats (
    date                       TEXT PRIMARY KEY,
    humanizer_requests_count   INTEGER NOT NULL DEFAULT 0,
    turnitin_requests_count    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS site_settings (
    id                             INTEGER PRIMARY KEY CHECK (id = 1),
    is_humanizer_discount_active   INTEGER NOT NULL DEFAULT 0,
    humanizer_discount_percent     INTEGER NOT NULL DEFAULT 50,
    humanizer_daily_limit          INTEGER NOT NULL DEFAULT 50,
    turnitin_global_balance        INTEGER NOT NULL DEFAULT 0,
    auto_discount_enabled          INTEGER NOT NULL DEFAULT 0,
    auto_discount_time             TEXT NOT NULL DEFAULT '20:00',
    auto_discount_min_remaining    INTEGER NOT NULL DEFAULT 10,
    updated_at                     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS humanizer_dataset_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source            TEXT NOT NULL,
    original_text     TEXT NOT NULL,
    humanized_text    TEXT NOT NULL,
    final_user_edit   TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_humanizer_dataset_source
    ON humanizer_dataset_logs(source, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_humanizer_dataset_user
    ON humanizer_dataset_logs(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS detector_dataset_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    full_text         TEXT NOT NULL,
    ai_percentage     REAL,
    ai_segments       TEXT NOT NULL DEFAULT '[]',
    human_segments    TEXT NOT NULL DEFAULT '[]',
    capture_type      TEXT NOT NULL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_detector_dataset_capture
    ON detector_dataset_logs(capture_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_detector_dataset_user
    ON detector_dataset_logs(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS support_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sender      TEXT NOT NULL CHECK (sender IN ('user', 'admin')),
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_support_messages_user_created
    ON support_messages(user_id, created_at ASC);
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


def _migrate_referral_columns(conn: sqlite3.Connection) -> None:
    """Add referral/cashback columns + backfill referral_code for existing users."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if not exists:
        return
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }
    alters = [
        ("referral_code", "ALTER TABLE users ADD COLUMN referral_code TEXT"),
        ("referrer_id", "ALTER TABLE users ADD COLUMN referrer_id INTEGER"),
        (
            "referral_balance_usd",
            "ALTER TABLE users ADD COLUMN referral_balance_usd REAL NOT NULL DEFAULT 0",
        ),
        (
            "qualifying_referrals_count",
            "ALTER TABLE users ADD COLUMN qualifying_referrals_count INTEGER NOT NULL DEFAULT 0",
        ),
        ("is_pro", "ALTER TABLE users ADD COLUMN is_pro INTEGER NOT NULL DEFAULT 0"),
        (
            "free_turnitin_reports",
            "ALTER TABLE users ADD COLUMN free_turnitin_reports INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "has_qualified_deposit",
            "ALTER TABLE users ADD COLUMN has_qualified_deposit INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "milestones_claimed",
            "ALTER TABLE users ADD COLUMN milestones_claimed TEXT NOT NULL DEFAULT '[]'",
        ),
    ]
    for name, sql in alters:
        if name not in cols:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_referral_code "
        "ON users(referral_code) WHERE referral_code IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_referrer "
        "ON users(referrer_id) WHERE referrer_id IS NOT NULL"
    )

    # Backfill missing referral codes for existing users.
    import secrets
    import string

    alphabet = string.ascii_uppercase + string.digits
    rows = conn.execute(
        "SELECT id FROM users WHERE referral_code IS NULL OR referral_code = ''"
    ).fetchall()
    for row in rows:
        for _ in range(20):
            code = "DM" + "".join(secrets.choice(alphabet) for _ in range(8))
            taken = conn.execute(
                "SELECT 1 FROM users WHERE referral_code = ?", (code,)
            ).fetchone()
            if not taken:
                conn.execute(
                    "UPDATE users SET referral_code = ? WHERE id = ?",
                    (code, int(row["id"])),
                )
                break


def _migrate_daily_stats_and_settings(conn: sqlite3.Connection) -> None:
    """Ensure daily_stats + site_settings exist on older DBs."""
    from .site_settings import ensure_schema

    ensure_schema(conn)


def _migrate_gumroad_payments(conn: sqlite3.Connection) -> None:
    """Ensure gumroad_payments exists on older DBs."""
    from .gumroad_gateway import ensure_gumroad_schema

    ensure_gumroad_schema(conn)


def _migrate_lemon_squeezy_payments(conn: sqlite3.Connection) -> None:
    """Ensure lemon_squeezy_payments exists on older DBs."""
    from .lemon_squeezy_gateway import ensure_lemon_squeezy_schema

    ensure_lemon_squeezy_schema(conn)


def _migrate_security_columns(conn: sqlite3.Connection) -> None:
    """Email verify, anti-abuse fingerprint/IP, avatar path."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if not exists:
        return
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }
    newly_added_verified = "is_verified" not in cols
    alters = [
        ("is_verified", "ALTER TABLE users ADD COLUMN is_verified INTEGER NOT NULL DEFAULT 0"),
        ("ip_address", "ALTER TABLE users ADD COLUMN ip_address TEXT"),
        ("device_fingerprint", "ALTER TABLE users ADD COLUMN device_fingerprint TEXT"),
        ("avatar_file", "ALTER TABLE users ADD COLUMN avatar_file TEXT"),
        (
            "welcome_bonus_granted",
            "ALTER TABLE users ADD COLUMN welcome_bonus_granted INTEGER NOT NULL DEFAULT 0",
        ),
        ("verification_code", "ALTER TABLE users ADD COLUMN verification_code TEXT"),
        (
            "verification_code_expires",
            "ALTER TABLE users ADD COLUMN verification_code_expires TEXT",
        ),
    ]
    for name, sql in alters:
        if name not in cols:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass

    # First-time rollout: grandfather existing accounts as verified.
    if newly_added_verified:
        try:
            conn.execute("UPDATE users SET is_verified = 1")
        except sqlite3.OperationalError:
            pass

    # Grandfather welcome_bonus_granted for accounts that already received the bonus.
    try:
        conn.execute(
            "UPDATE users SET welcome_bonus_granted = 1 "
            "WHERE id IN ("
            "  SELECT DISTINCT user_id FROM transactions "
            "  WHERE feature = 'welcome_bonus' AND kind = 'credit'"
            ")"
        )
    except sqlite3.OperationalError:
        pass
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_ip_address "
        "ON users(ip_address) WHERE ip_address IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_device_fingerprint "
        "ON users(device_fingerprint) WHERE device_fingerprint IS NOT NULL"
    )


def _migrate_humanizer_dataset(conn: sqlite3.Connection) -> None:
    """ML fine-tuning corpus: humanize pairs + AI detector samples."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS humanizer_dataset_logs (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source            TEXT NOT NULL,
            original_text     TEXT NOT NULL,
            humanized_text    TEXT NOT NULL,
            final_user_edit   TEXT,
            created_at        TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(humanizer_dataset_logs)").fetchall()
    }
    if "training_eligible" not in cols:
        try:
            conn.execute(
                "ALTER TABLE humanizer_dataset_logs ADD COLUMN training_eligible "
                "INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_humanizer_dataset_source "
        "ON humanizer_dataset_logs(source, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_humanizer_dataset_user "
        "ON humanizer_dataset_logs(user_id, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_humanizer_dataset_eligible "
        "ON humanizer_dataset_logs(training_eligible, source, created_at DESC)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS detector_dataset_logs (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            full_text         TEXT NOT NULL,
            ai_percentage     REAL,
            ai_segments       TEXT NOT NULL DEFAULT '[]',
            human_segments    TEXT NOT NULL DEFAULT '[]',
            capture_type      TEXT NOT NULL,
            created_at        TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_detector_dataset_capture "
        "ON detector_dataset_logs(capture_type, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_detector_dataset_user "
        "ON detector_dataset_logs(user_id, created_at DESC)"
    )


def _migrate_support_messages(conn: sqlite3.Connection) -> None:
    """Two-way Telegram helpdesk transcript."""
    from .support_chat import ensure_support_messages_schema

    ensure_support_messages_schema(conn)


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
        _migrate_gumroad_payments(conn)
        _migrate_lemon_squeezy_payments(conn)
        _migrate_referral_columns(conn)
        _migrate_daily_stats_and_settings(conn)
        _migrate_security_columns(conn)
        _migrate_humanizer_dataset(conn)
        _migrate_support_messages(conn)
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
        # Same for Lemon Squeezy (webhook retries must not double-credit).
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_lemon_topup_ref "
            "ON transactions(ref_id) "
            "WHERE reference_type = 'LemonSqueezy' AND feature = 'topup' "
            "AND ref_id IS NOT NULL"
        )
        conn.commit()
    finally:
        conn.close()
