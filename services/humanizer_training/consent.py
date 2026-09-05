"""Training eligibility stamp for real-user humanizer logs.

Per-row flag: ``humanizer_dataset_logs.training_eligible`` (default 0).
Stamped only on NEW successful inserts — never retroactively backfilled.

Policy (no user opt-in / no UI checkbox):
- ``standalone`` → eligible (1)
- ``assignment`` → eligible (1) for real_user_raw export
- ``workspace_partial`` → never eligible (0)
"""

from __future__ import annotations

from typing import Any

from services.economy.db import connect

# Write-path that stamps training_eligible on new successful logs.
ELIGIBILITY_WRITE_PATH_IMPLEMENTED = True
# Back-compat alias used by export helpers.
CONSENT_WRITE_PATH_IMPLEMENTED = ELIGIBILITY_WRITE_PATH_IMPLEMENTED

_AUTO_ELIGIBLE_SOURCES = frozenset({"standalone", "assignment"})


def ensure_training_consent_schema(conn: Any | None = None) -> None:
    """Idempotent migration for ``humanizer_dataset_logs.training_eligible``."""

    def _run(c: Any) -> None:
        c.execute(
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
        log_cols = {
            row["name"]
            for row in c.execute("PRAGMA table_info(humanizer_dataset_logs)").fetchall()
        }
        if "training_eligible" not in log_cols:
            # DEFAULT 0 — existing rows remain ineligible (SQLite fills existing with 0).
            c.execute(
                "ALTER TABLE humanizer_dataset_logs ADD COLUMN training_eligible "
                "INTEGER NOT NULL DEFAULT 0"
            )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_humanizer_dataset_eligible "
            "ON humanizer_dataset_logs(training_eligible, source, created_at DESC)"
        )

    if conn is not None:
        _run(conn)
        return
    with connect() as c:
        _run(c)


# Alias preferred by newer call sites.
ensure_training_eligibility_schema = ensure_training_consent_schema


def training_eligible_for_new_log(
    user_id: int | None = None,
    *,
    source: str | None = None,
) -> int:
    """Value to stamp on a NEW humanizer_dataset_logs row (0 or 1).

    No user opt-in required. Workspace is never eligible.
    ``user_id`` is ignored (kept for call-site compatibility).
    """
    del user_id
    src = (source or "").strip().lower()
    return 1 if src in _AUTO_ELIGIBLE_SOURCES else 0
