#!/usr/bin/env python3
"""One-shot backfill: project bundles → humanizer/detector dataset tables."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.dataset_logger import (  # noqa: E402
    ensure_dataset_schema,
    _insert_detector_row,
    _insert_humanizer_row,
)
from services.economy.db import connect, init_db  # noqa: E402


def _fallback_user_id() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        if row:
            return int(row["id"])
        row = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
        if not row:
            raise SystemExit("No users in economy.db — cannot backfill")
        return int(row["id"])


def _word_count(text: str) -> int:
    return len(str(text or "").split())


def backfill() -> dict[str, int]:
    init_db()
    ensure_dataset_schema()
    fallback_uid = _fallback_user_id()
    projects_root = ROOT / "data" / "projects"

    hum_para = 0
    hum_doc = 0
    det_auto = 0
    det_manual = 0
    skipped = 0

    for path in sorted(projects_root.glob("*/bundle.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped += 1
            continue

        project = data.get("project") or {}
        art = project.get("artifacts") or {}
        uid = project.get("user_id")
        try:
            user_id = int(uid) if uid is not None else fallback_uid
        except (TypeError, ValueError):
            user_id = fallback_uid

        # --- Humanizer paragraph pairs ---
        sess = art.get("humanizer_session") or {}
        for para in sess.get("paragraphs") or []:
            original = str(para.get("original_text") or "")
            humanized = str(para.get("humanized_text") or "")
            if not original.strip() or not humanized.strip():
                continue
            if original.strip() == humanized.strip():
                continue
            if _word_count(original) < 8:
                continue
            _insert_humanizer_row(
                user_id=user_id,
                source="assignment",
                original_text=original,
                humanized_text=humanized,
            )
            hum_para += 1

        # --- Whole draft → humanized draft ---
        draft = str((art.get("draft") or {}).get("content") or "")
        humanized_doc = str((art.get("humanized_draft") or {}).get("content") or "")
        if (
            draft.strip()
            and humanized_doc.strip()
            and draft.strip() != humanized_doc.strip()
            and _word_count(draft) >= 40
        ):
            _insert_humanizer_row(
                user_id=user_id,
                source="assignment",
                original_text=draft,
                humanized_text=humanized_doc,
            )
            hum_doc += 1

        # --- Detector samples from assignment AI detection ---
        report = art.get("detection_report") or {}
        dsess = art.get("detection_session") or {}
        paras = list(dsess.get("paragraphs") or [])
        if not paras:
            continue

        full_parts = [str(p.get("text") or "").strip() for p in paras if str(p.get("text") or "").strip()]
        if not full_parts:
            continue
        full_text = "\n\n".join(full_parts)

        ai_segments = []
        human_segments = []
        for p in paras:
            text = str(p.get("text") or "").strip()
            if not text or _word_count(text) < 5:
                continue
            score = float(p.get("ai_score") or 0)
            # Treat elevated paragraph scores as AI-flagged spans.
            if score > 20:
                ai_segments.append(text)
            else:
                human_segments.append(text)

        try:
            overall = float(
                report.get("overall_ai_score")
                if report.get("overall_ai_score") is not None
                else (report.get("average_score") or 0)
            )
        except (TypeError, ValueError):
            overall = 0.0
        highest = max((float(p.get("ai_score") or 0) for p in paras), default=0.0)

        if overall > 20 or highest > 20:
            capture = "auto_report_over_20"
            det_auto += 1
        elif ai_segments or any(float(p.get("ai_score") or 0) > 5 for p in paras):
            capture = "manual_highlights"
            det_manual += 1
        else:
            continue

        _insert_detector_row(
            user_id=user_id,
            full_text=full_text,
            ai_percentage=overall if overall else highest,
            ai_segments=ai_segments,
            human_segments=human_segments,
            capture_type=capture,
        )

    return {
        "humanizer_paragraphs": hum_para,
        "humanizer_documents": hum_doc,
        "detector_auto": det_auto,
        "detector_manual": det_manual,
        "skipped_bundles": skipped,
    }


if __name__ == "__main__":
    stats = backfill()
    print(json.dumps(stats, indent=2))
    from services.dataset_logger import get_dataset_stats

    print("totals:", json.dumps(get_dataset_stats(), indent=2))
