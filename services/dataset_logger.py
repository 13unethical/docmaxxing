"""Passive dataset loggers for future ML fine-tuning.

Store-raw principle: humanize/detect payloads are persisted exactly as received.
Sanitization belongs in a later export pipeline (see ``clean_text_for_ml``).
Writes run on daemon threads so API latency is unaffected.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from typing import Any

from bs4 import BeautifulSoup

from services.economy.db import connect

logger = logging.getLogger(__name__)

VALID_SOURCES = frozenset({"standalone", "assignment", "workspace_partial"})
VALID_CAPTURE_TYPES = frozenset({"auto_report_over_20", "manual_highlights"})


@dataclass
class HumanizerDatasetLog:
    """Schema mirror for ``humanizer_dataset_logs`` (raw store)."""

    id: int | None
    user_id: int
    source: str
    original_text: str
    humanized_text: str
    final_user_edit: str | None = None
    created_at: datetime | None = None


@dataclass
class DetectorDatasetLog:
    """Schema mirror for ``detector_dataset_logs`` (raw store)."""

    id: int | None
    user_id: int
    full_text: str
    ai_percentage: float | None
    ai_segments: list[Any]
    human_segments: list[Any]
    capture_type: str
    created_at: datetime | None = None

# Kept for export-time sanitization — NOT used when logging events.
_WS_MARKER_RE = re.compile(
    r"(?:⟦\s*WS\s*:\s*\d+\s*⟧|\[\s*WS\s*:\s*\d+\s*\]|(?:^|\n)\s*(?:#{1,3}\s*)?(?:\[+\s*)?WS\s*[:_\-]?\s*\d+\s*(?:\]+)?\s*(?=\n|$))",
    re.IGNORECASE | re.MULTILINE,
)
_WS_INSTRUCTION_RE = re.compile(
    r"(?im)^IMPORTANT:\s*Keep every marker line.*?Do not merge sections\.\s*",
)
_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def clean_text_for_ml(raw_text: str | None) -> str:
    """Export-time helper: strip HTML / Workspace markers. Do not use at insert time."""
    if not raw_text:
        return ""
    text = str(raw_text)
    try:
        soup = BeautifulSoup(text, "html.parser")
        text = soup.get_text(separator="\n")
    except Exception:  # noqa: BLE001
        text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    text = _WS_INSTRUCTION_RE.sub("", text)
    text = _WS_MARKER_RE.sub("\n", text)
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def ensure_dataset_schema() -> None:
    """Create humanizer + detector dataset tables if missing (idempotent)."""
    with connect() as conn:
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_humanizer_dataset_source "
            "ON humanizer_dataset_logs(source, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_humanizer_dataset_user "
            "ON humanizer_dataset_logs(user_id, created_at DESC)"
        )
        # Explicit training eligibility (default 0). Existing rows stay ineligible.
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(humanizer_dataset_logs)").fetchall()
        }
        if "training_eligible" not in cols:
            conn.execute(
                "ALTER TABLE humanizer_dataset_logs ADD COLUMN training_eligible "
                "INTEGER NOT NULL DEFAULT 0"
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
    # Keep training_eligible column migrations in sync.
    try:
        from services.humanizer_training.consent import ensure_training_consent_schema

        ensure_training_consent_schema()
    except Exception:  # noqa: BLE001
        logger.exception("training eligibility schema ensure failed")


def _insert_humanizer_row(
    *,
    user_id: int,
    source: str,
    original_text: str,
    humanized_text: str,
    training_eligible: int = 0,
) -> None:
    with connect() as conn:
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(humanizer_dataset_logs)").fetchall()
        }
        if "training_eligible" in cols:
            conn.execute(
                """
                INSERT INTO humanizer_dataset_logs
                    (user_id, source, original_text, humanized_text, training_eligible)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(user_id), source, original_text, humanized_text, int(training_eligible)),
            )
        else:
            conn.execute(
                """
                INSERT INTO humanizer_dataset_logs
                    (user_id, source, original_text, humanized_text)
                VALUES (?, ?, ?, ?)
                """,
                (int(user_id), source, original_text, humanized_text),
            )


def _insert_detector_row(
    *,
    user_id: int,
    full_text: str,
    ai_percentage: float | None,
    ai_segments: list[Any],
    human_segments: list[Any],
    capture_type: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO detector_dataset_logs
                (user_id, full_text, ai_percentage, ai_segments, human_segments, capture_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id),
                full_text,
                float(ai_percentage) if ai_percentage is not None else None,
                json.dumps(list(ai_segments or []), ensure_ascii=False),
                json.dumps(list(human_segments or []), ensure_ascii=False),
                capture_type,
            ),
        )


def log_humanization_event(
    user_id: int | None,
    source: str,
    original_text: str | None,
    humanized_text: str | None,
) -> None:
    """Enqueue a raw humanize pair (no sanitization). Never raises into the request path."""
    try:
        if user_id is None:
            return
        src = (source or "").strip().lower()
        if src not in VALID_SOURCES:
            logger.warning("dataset_logger: invalid source %r — skipped", source)
            return
        original = "" if original_text is None else str(original_text)
        humanized = "" if humanized_text is None else str(humanized_text)
        if not original.strip() or not humanized.strip():
            return

        uid = int(user_id)

        def _run() -> None:
            try:
                ensure_dataset_schema()
                try:
                    from services.humanizer_training.consent import (
                        training_eligible_for_new_log,
                    )

                    eligible = training_eligible_for_new_log(uid, source=src)
                except Exception:  # noqa: BLE001
                    eligible = 0
                _insert_humanizer_row(
                    user_id=uid,
                    source=src,
                    original_text=original,
                    humanized_text=humanized,
                    training_eligible=eligible,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "dataset_logger humanizer insert failed user_id=%s source=%s",
                    uid,
                    src,
                )

        threading.Thread(target=_run, daemon=True).start()
    except Exception:  # noqa: BLE001
        logger.exception("dataset_logger humanizer schedule failed")


def infer_human_segments(full_text: str, ai_segments: list[str]) -> list[str]:
    """Best-effort: remove AI spans from full text and keep remaining chunks."""
    remaining = str(full_text or "")
    for seg in ai_segments or []:
        piece = str(seg or "").strip()
        if piece and piece in remaining:
            remaining = remaining.replace(piece, "\n\n", 1)
    parts = [p.strip() for p in re.split(r"\n{2,}", remaining) if p.strip()]
    return parts


def log_detection_event(
    user_id: int | None,
    full_text: str | None,
    ai_percentage: float | int | None,
    ai_segments_list: list[Any] | None,
    human_segments_list: list[Any] | None,
    capture_type: str,
) -> None:
    """Enqueue a raw AI-detection sample. Never raises into the request path."""
    try:
        if user_id is None:
            return
        ctype = (capture_type or "").strip()
        if ctype not in VALID_CAPTURE_TYPES:
            logger.warning("dataset_logger: invalid capture_type %r — skipped", capture_type)
            return
        text = "" if full_text is None else str(full_text)
        if not text.strip():
            return

        ai_segs = [str(s) for s in (ai_segments_list or []) if str(s).strip()]
        human_segs = [str(s) for s in (human_segments_list or []) if str(s).strip()]
        if not human_segs and ai_segs:
            human_segs = infer_human_segments(text, ai_segs)

        pct: float | None
        try:
            pct = float(ai_percentage) if ai_percentage is not None else None
        except (TypeError, ValueError):
            pct = None

        uid = int(user_id)

        def _run() -> None:
            try:
                ensure_dataset_schema()
                _insert_detector_row(
                    user_id=uid,
                    full_text=text,
                    ai_percentage=pct,
                    ai_segments=ai_segs,
                    human_segments=human_segs,
                    capture_type=ctype,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "dataset_logger detector insert failed user_id=%s type=%s",
                    uid,
                    ctype,
                )

        threading.Thread(target=_run, daemon=True).start()
    except Exception:  # noqa: BLE001
        logger.exception("dataset_logger detector schedule failed")


def get_dataset_stats() -> dict[str, Any]:
    """Totals for the admin dataset widget (humanizer + detector)."""
    ensure_dataset_schema()
    with connect() as conn:
        total = int(
            conn.execute("SELECT COUNT(*) AS c FROM humanizer_dataset_logs").fetchone()["c"]
        )
        rows = conn.execute(
            """
            SELECT source, COUNT(*) AS c
            FROM humanizer_dataset_logs
            GROUP BY source
            """
        ).fetchall()
        det_total = int(
            conn.execute("SELECT COUNT(*) AS c FROM detector_dataset_logs").fetchone()["c"]
        )
        det_rows = conn.execute(
            """
            SELECT capture_type, COUNT(*) AS c
            FROM detector_dataset_logs
            GROUP BY capture_type
            """
        ).fetchall()
    by_source = {str(r["source"]): int(r["c"]) for r in rows}
    by_capture = {str(r["capture_type"]): int(r["c"]) for r in det_rows}
    return {
        "total": total,
        "standalone": int(by_source.get("standalone") or 0),
        "assignment": int(by_source.get("assignment") or 0),
        "workspace_partial": int(by_source.get("workspace_partial") or 0),
        "by_source": by_source,
        "detector_total": det_total,
        "auto_report_over_20": int(by_capture.get("auto_report_over_20") or 0),
        "manual_highlights": int(by_capture.get("manual_highlights") or 0),
        "detector_by_capture_type": by_capture,
    }


def _preview(text: str | None, limit: int = 180) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def get_dataset_recent_samples(limit: int = 8) -> dict[str, Any]:
    """Recent raw rows for admin preview tables."""
    ensure_dataset_schema()
    lim = max(1, min(int(limit), 50))
    with connect() as conn:
        humanizer = conn.execute(
            """
            SELECT id, user_id, source, original_text, humanized_text, created_at
            FROM humanizer_dataset_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
        detector = conn.execute(
            """
            SELECT id, user_id, full_text, ai_percentage, ai_segments, human_segments,
                   capture_type, created_at
            FROM detector_dataset_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()

    humanizer_out = []
    for r in humanizer:
        humanizer_out.append(
            {
                "id": int(r["id"]),
                "user_id": int(r["user_id"]),
                "source": r["source"],
                "original_preview": _preview(r["original_text"]),
                "humanized_preview": _preview(r["humanized_text"]),
                "created_at": r["created_at"],
            }
        )

    detector_out = []
    for r in detector:
        try:
            ai_segs = json.loads(r["ai_segments"] or "[]")
        except json.JSONDecodeError:
            ai_segs = []
        try:
            human_segs = json.loads(r["human_segments"] or "[]")
        except json.JSONDecodeError:
            human_segs = []
        detector_out.append(
            {
                "id": int(r["id"]),
                "user_id": int(r["user_id"]),
                "capture_type": r["capture_type"],
                "ai_percentage": r["ai_percentage"],
                "full_text_preview": _preview(r["full_text"]),
                "ai_segments_count": len(ai_segs),
                "human_segments_count": len(human_segs),
                "ai_segment_preview": _preview(ai_segs[0] if ai_segs else ""),
                "created_at": r["created_at"],
            }
        )

    return {"humanizer_recent": humanizer_out, "detector_recent": detector_out}
