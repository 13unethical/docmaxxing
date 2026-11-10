"""Cross-worker records of what a paid assignment may use: Research Plan provenance and
post-delivery revision chat rounds.

Both live in SQLite next to the payment cycles because the project JSON can be rewritten by a
stale worker. Plan versions and client-input rows are append-only; a revision round moves
once from 'reserved' to 'consumed' or 'released' and never changes again.
"""

from __future__ import annotations

import uuid
from typing import Any

from .db import connect

SOURCE_SERVER = "server"
SOURCE_CLIENT = "client"

ROUND_RESERVED = "reserved"
ROUND_CONSUMED = "consumed"
ROUND_RELEASED = "released"


class RevisionRoundsExhausted(Exception):
    """Every revision round of the project is used or held by a running request."""


# ------------------------------------------------------------------ Research Plan versions


def record_plan_version(project_id: str, content_hash: str, source: str) -> dict[str, Any]:
    """Append ``content_hash`` as the project's current plan; a repeat of the latest row is a no-op."""
    if source not in (SOURCE_SERVER, SOURCE_CLIENT):
        raise ValueError(f"unknown plan source: {source}")
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        latest = conn.execute(
            "SELECT * FROM assignment_plan_versions WHERE project_id = ? ORDER BY version DESC LIMIT 1",
            (str(project_id),),
        ).fetchone()
        if latest is not None and latest["content_hash"] == content_hash and latest["source"] == source:
            return dict(latest)
        version = (int(latest["version"]) if latest is not None else 0) + 1
        conn.execute(
            "INSERT INTO assignment_plan_versions (project_id, version, content_hash, source) VALUES (?, ?, ?, ?)",
            (str(project_id), version, content_hash, source),
        )
        return dict(
            conn.execute(
                "SELECT * FROM assignment_plan_versions WHERE project_id = ? AND version = ?",
                (str(project_id), version),
            ).fetchone()
        )


def latest_plan_version(project_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM assignment_plan_versions WHERE project_id = ? ORDER BY version DESC LIMIT 1",
            (str(project_id),),
        ).fetchone()
    return dict(row) if row is not None else None


def server_generated_plan(project_id: str, content_hash: str) -> bool:
    """True when the server itself produced a plan with exactly this content for the project."""
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM assignment_plan_versions WHERE project_id = ? AND content_hash = ? AND source = ? LIMIT 1",
            (str(project_id), content_hash, SOURCE_SERVER),
        ).fetchone()
    return row is not None


def record_client_input_use(project_id: str, cycle_id: str | None, stage: str, content_hash: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO assignment_client_input_use (project_id, cycle_id, stage, content_hash) "
            "VALUES (?, ?, ?, ?)",
            (str(project_id), str(cycle_id or ""), str(stage), content_hash),
        )


def client_input_used(project_id: str, cycle_id: str | None) -> bool:
    """A paid stage of this payment cycle already ran on student-provided input."""
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM assignment_client_input_use WHERE project_id = ? AND cycle_id = ? LIMIT 1",
            (str(project_id), str(cycle_id or "")),
        ).fetchone()
    return row is not None


# ------------------------------------------------------------------ revision chat rounds


def revision_rounds_used(project_id: str) -> int:
    """Rounds consumed or still held by a running request."""
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM assignment_revision_rounds WHERE project_id = ? AND status IN (?, ?)",
            (str(project_id), ROUND_RESERVED, ROUND_CONSUMED),
        ).fetchone()
    return int(row["n"])


def reserve_revision_round(project_id: str, *, limit: int, legacy_used: int = 0) -> str:
    """Hold one round before the AI call; raises RevisionRoundsExhausted when none is left.

    ``legacy_used`` is the count kept in the project JSON before rounds were recorded here;
    it is turned into consumed rows the first time the project reserves a round.
    """
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM assignment_revision_rounds WHERE project_id = ?", (str(project_id),)
        ).fetchone()["n"]
        if int(total) == 0:
            for index in range(max(0, min(int(legacy_used), int(limit)))):
                conn.execute(
                    "INSERT INTO assignment_revision_rounds (reservation_id, project_id, status, finished_at) "
                    "VALUES (?, ?, ?, datetime('now'))",
                    (f"legacy-{project_id}-{index}", str(project_id), ROUND_CONSUMED),
                )
        used = conn.execute(
            "SELECT COUNT(*) AS n FROM assignment_revision_rounds WHERE project_id = ? AND status IN (?, ?)",
            (str(project_id), ROUND_RESERVED, ROUND_CONSUMED),
        ).fetchone()["n"]
        if int(used) >= int(limit):
            raise RevisionRoundsExhausted(project_id)
        reservation_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO assignment_revision_rounds (reservation_id, project_id, status) VALUES (?, ?, ?)",
            (reservation_id, str(project_id), ROUND_RESERVED),
        )
    return reservation_id


def finish_revision_round(reservation_id: str, *, consumed: bool) -> bool:
    """End a reservation once; False when it was already consumed or released (no change)."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE assignment_revision_rounds SET status = ?, finished_at = datetime('now') "
            "WHERE reservation_id = ? AND status = ?",
            (ROUND_CONSUMED if consumed else ROUND_RELEASED, str(reservation_id), ROUND_RESERVED),
        )
        return cur.rowcount == 1


def revision_round_status(reservation_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT status FROM assignment_revision_rounds WHERE reservation_id = ?", (str(reservation_id),)
        ).fetchone()
    return str(row["status"]) if row is not None else None
