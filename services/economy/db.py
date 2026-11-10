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

CREATE TABLE IF NOT EXISTS extension_tokens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT,
    revoked      INTEGER NOT NULL DEFAULT 0,
    expires_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_extension_tokens_user
    ON extension_tokens(user_id);

CREATE TABLE IF NOT EXISTS veil_passes (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_plans (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    plan_id     TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    order_ref   TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS plan_usage (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    feature     TEXT NOT NULL,
    period_key  TEXT NOT NULL,
    used        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, feature, period_key)
);

-- One row per confirmed assignment payment ("payment cycle"); see assignment_payments.py.
CREATE TABLE IF NOT EXISTS assignment_payments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id         TEXT NOT NULL UNIQUE,
    project_id       TEXT NOT NULL,
    user_id          INTEGER NOT NULL,
    method           TEXT NOT NULL,       -- coins | plan_allowance
    coins            INTEGER NOT NULL DEFAULT 0,
    debit_tx_id      INTEGER,
    allowance_mode   TEXT,                -- quota | unlimited
    allowance_period TEXT,                -- plan_usage.period_key the allowance was taken from
    status           TEXT NOT NULL,       -- active | refunded | voided
    refund_tx_id     INTEGER,
    refunded_coins   INTEGER,
    refund_kind      TEXT,
    refund_reason    TEXT,
    refund_admin_id  INTEGER,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at        TEXT,
    output_tracking  INTEGER NOT NULL DEFAULT 0, -- 1: every paid operation of this cycle is journaled
    quote_id         TEXT,                -- server quote the cycle paid for (NULL: legacy cycle)
    scope_hash       TEXT,                -- billable project snapshot that quote priced
    quoted_word_count INTEGER,
    quoted_coins     INTEGER              -- list price of the quote, before any discount
);

CREATE INDEX IF NOT EXISTS idx_assignment_payments_project
    ON assignment_payments(project_id);

-- Proof that a project's generated text was durably stored. Append-only: once a row exists
-- the project can never get an automatic refund again, whatever its JSON bundle says.
CREATE TABLE IF NOT EXISTS assignment_output_evidence (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    cycle_id    TEXT NOT NULL DEFAULT '',
    operation   TEXT NOT NULL,
    source      TEXT NOT NULL,
    op_id       TEXT,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, cycle_id, operation)
);

CREATE TRIGGER IF NOT EXISTS trg_assignment_output_evidence_no_update
    BEFORE UPDATE ON assignment_output_evidence
BEGIN
    SELECT RAISE(ABORT, 'assignment_output_evidence is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_assignment_output_evidence_no_delete
    BEFORE DELETE ON assignment_output_evidence
BEGIN
    SELECT RAISE(ABORT, 'assignment_output_evidence is append-only');
END;

-- Journal of paid assignment operations. output_phase is 'persisting' from just before the
-- JSON write of generated text until its evidence row exists; a row left there means a
-- worker died (or the ledger failed) in between, so the outcome is unknown.
CREATE TABLE IF NOT EXISTS assignment_operations (
    op_id        TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL,
    cycle_id     TEXT NOT NULL DEFAULT '',
    operation    TEXT NOT NULL,
    status       TEXT NOT NULL,       -- started | completed | rejected | failed | interrupted
    output_phase TEXT,                -- NULL | persisting | recorded
    pid          INTEGER,
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_assignment_operations_project
    ON assignment_operations(project_id, output_phase);

-- Every Research Plan version a project had, by canonical content hash. Append-only, so a
-- stale JSON bundle can neither relabel a student's edit as server output nor bring back
-- an older plan as the current one.
CREATE TABLE IF NOT EXISTS assignment_plan_versions (
    project_id   TEXT NOT NULL,
    version      INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    source       TEXT NOT NULL,       -- server | client
    recorded_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (project_id, version)
);

CREATE TRIGGER IF NOT EXISTS trg_assignment_plan_versions_no_update
    BEFORE UPDATE ON assignment_plan_versions
BEGIN
    SELECT RAISE(ABORT, 'assignment_plan_versions is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_assignment_plan_versions_no_delete
    BEFORE DELETE ON assignment_plan_versions
BEGIN
    SELECT RAISE(ABORT, 'assignment_plan_versions is append-only');
END;

-- A paid stage of this payment cycle ran on student-provided input. Append-only: failures
-- of the cycle from then on are never automatic refund evidence.
CREATE TABLE IF NOT EXISTS assignment_client_input_use (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL,
    cycle_id     TEXT NOT NULL DEFAULT '',
    stage        TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    recorded_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, cycle_id, stage, content_hash)
);

CREATE TRIGGER IF NOT EXISTS trg_assignment_client_input_use_no_update
    BEFORE UPDATE ON assignment_client_input_use
BEGIN
    SELECT RAISE(ABORT, 'assignment_client_input_use is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_assignment_client_input_use_no_delete
    BEFORE DELETE ON assignment_client_input_use
BEGIN
    SELECT RAISE(ABORT, 'assignment_client_input_use is append-only');
END;

-- Post-delivery revision chat rounds, shared by all workers. A round is reserved before the
-- AI call and ends consumed or released; only 'reserved' rows can change.
CREATE TABLE IF NOT EXISTS assignment_revision_rounds (
    reservation_id TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    status         TEXT NOT NULL,     -- reserved | consumed | released
    reserved_at    TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_assignment_revision_rounds_project
    ON assignment_revision_rounds(project_id, status);

CREATE TRIGGER IF NOT EXISTS trg_assignment_revision_rounds_final
    BEFORE UPDATE ON assignment_revision_rounds
    WHEN OLD.status != 'reserved'
BEGIN
    SELECT RAISE(ABORT, 'a finished revision round cannot change');
END;

CREATE TRIGGER IF NOT EXISTS trg_assignment_revision_rounds_no_delete
    BEFORE DELETE ON assignment_revision_rounds
BEGIN
    SELECT RAISE(ABORT, 'assignment_revision_rounds is append-only');
END;

-- Signed-in browser sessions. The session cookie is client-side, so it only authenticates
-- while its sign-in id (stored hashed) has a row here: sign-out, a password change and
-- account deletion delete rows, and every copy of that cookie stops working.
CREATE TABLE IF NOT EXISTS auth_sessions (
    sid_hash   TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id, last_seen);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_last_seen ON auth_sessions(last_seen);

-- Any write of a new password hash (account page, recovery, ops scripts) signs out every
-- session of that account; the caller re-issues its own session if it should stay signed in.
CREATE TRIGGER IF NOT EXISTS trg_auth_sessions_password_changed
AFTER UPDATE OF password_hash ON users
WHEN NEW.password_hash IS NOT OLD.password_hash
BEGIN
    DELETE FROM auth_sessions WHERE user_id = NEW.id;
END;

-- Sliding-window rate limits shared by all gunicorn workers (services/rate_limit.py).
CREATE TABLE IF NOT EXISTS rate_limit_events (
    key TEXT NOT NULL,
    ts  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_events_key_ts ON rate_limit_events(key, ts);
CREATE INDEX IF NOT EXISTS idx_rate_limit_events_ts ON rate_limit_events(ts);

CREATE TRIGGER IF NOT EXISTS trg_auth_sessions_user_deleted
AFTER DELETE ON users
BEGIN
    DELETE FROM auth_sessions WHERE user_id = OLD.id;
END;

-- Failed password checks shared by all gunicorn workers (services/economy/login_throttle.py).
-- A row is written before the password is checked and deleted only on success, so a worker
-- that dies mid-check leaves a counted failure that ages out with the window.
CREATE TABLE IF NOT EXISTS auth_failures (
    id  INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    ts  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_failures_key_ts ON auth_failures(key, ts);
CREATE INDEX IF NOT EXISTS idx_auth_failures_ts ON auth_failures(ts);
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
        # wrong guesses against the current code; a new code starts again at 0
        (
            "verification_attempts",
            "ALTER TABLE users ADD COLUMN verification_attempts INTEGER NOT NULL DEFAULT 0",
        ),
        ("is_blocked", "ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0"),
        # 'staff' | 'test': hidden from admin analytics
        ("account_flag", "ALTER TABLE users ADD COLUMN account_flag TEXT"),
        # an admin reviewed the suspicious-account heuristics and cleared them
        ("flag_cleared", "ALTER TABLE users ADD COLUMN flag_cleared INTEGER NOT NULL DEFAULT 0"),
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


def _migrate_assignment_payments(conn: sqlite3.Connection) -> None:
    """Cycles opened before operation journaling keep output_tracking = 0 (outcome unknown).

    Cycles opened before quotes were bound keep NULL quote columns; the service verifies such
    a legacy payment against its stored pricing before binding a scope (never on its own).
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(assignment_payments)").fetchall()}
    if not cols:
        return
    if "output_tracking" not in cols:
        conn.execute(
            "ALTER TABLE assignment_payments ADD COLUMN output_tracking INTEGER NOT NULL DEFAULT 0"
        )
    for name, ddl in (
        ("quote_id", "TEXT"),
        ("scope_hash", "TEXT"),
        ("quoted_word_count", "INTEGER"),
        ("quoted_coins", "INTEGER"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE assignment_payments ADD COLUMN {name} {ddl}")


VEIL_TOKEN_DEFAULT_TTL_DAYS = 30


def _migrate_extension_tokens(conn: sqlite3.Connection) -> None:
    """Expiry, one live token per account, and revocation when the account changes.

    Tokens issued before ``expires_at`` existed expire ``VEIL_TOKEN_DEFAULT_TTL_DAYS`` after
    they were created. Duplicate live tokens (a pre-transaction race) keep only the newest.
    Revoked rows are never touched, so nothing revoked comes back.
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(extension_tokens)").fetchall()}
    if "expires_at" not in cols:
        conn.execute("ALTER TABLE extension_tokens ADD COLUMN expires_at TEXT")
    conn.execute(
        "UPDATE extension_tokens SET expires_at = datetime(created_at, ?) WHERE expires_at IS NULL",
        (f"+{VEIL_TOKEN_DEFAULT_TTL_DAYS} days",),
    )
    conn.execute(
        "UPDATE extension_tokens SET revoked = 1 WHERE revoked = 0 AND id NOT IN ("
        " SELECT MAX(id) FROM extension_tokens WHERE revoked = 0 GROUP BY user_id)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_extension_tokens_one_live "
        "ON extension_tokens(user_id) WHERE revoked = 0"
    )
    # Same events that end browser sessions also end the extension's sign-in.
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS trg_extension_tokens_password_changed
        AFTER UPDATE OF password_hash ON users
        WHEN NEW.password_hash IS NOT OLD.password_hash
        BEGIN
            UPDATE extension_tokens SET revoked = 1 WHERE user_id = NEW.id AND revoked = 0;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_extension_tokens_user_blocked
        AFTER UPDATE OF is_blocked ON users
        WHEN NEW.is_blocked = 1
        BEGIN
            UPDATE extension_tokens SET revoked = 1 WHERE user_id = NEW.id AND revoked = 0;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_extension_tokens_user_unverified
        AFTER UPDATE OF is_verified ON users
        WHEN NEW.is_verified = 0 AND OLD.is_verified = 1
        BEGIN
            UPDATE extension_tokens SET revoked = 1 WHERE user_id = NEW.id AND revoked = 0;
        END;
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
        # Superseded by auth_sessions: a sign-in id without a row there no longer authenticates.
        conn.execute("DROP TABLE IF EXISTS revoked_sessions")
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
        _migrate_extension_tokens(conn)
        _migrate_humanizer_dataset(conn)
        _migrate_support_messages(conn)
        _migrate_assignment_payments(conn)
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
        # One assignment refund per project payment (ref built server-side as
        # "assignment-refund:<project>:<payment time>"); legacy rows never match.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_assignment_refund_ref "
            "ON transactions(ref_id) "
            "WHERE kind = 'refund' AND feature = 'assignment' "
            "AND ref_id LIKE 'assignment-refund:%'"
        )
        # At most one live payment per project, and one debit per payment cycle; legacy
        # debits (ref_id = project id) never match.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_assignment_payments_active "
            "ON assignment_payments(project_id) WHERE status = 'active'"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_assignment_payment_ref "
            "ON transactions(ref_id) "
            "WHERE kind = 'debit' AND feature = 'assignment' "
            "AND ref_id LIKE 'assignment-payment:%'"
        )
        from .activity_log import backfill_activity

        try:
            backfill_activity(conn)
        except sqlite3.Error:
            pass
        conn.commit()
    finally:
        conn.close()
