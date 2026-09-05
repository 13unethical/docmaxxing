"""Isolated Turnitin evaluation linkage (explicit workflow only).

Creates eval cases BEFORE Turnitin submission and attaches report metadata
AFTER results are available. Fail-closed hash matching. No production hooks.
Does not extract AI spans (unavailable with current parsers).
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_EVAL_ROOT = Path("data/humanizer_training/turnitin_eval")
CASES_DIRNAME = "cases"
INDEX_FILENAME = "index.jsonl"

_PII_KEYS = frozenset(
    {
        "user_id",
        "email",
        "session_id",
        "ip",
        "ip_address",
        "password",
        "password_hash",
        "payment",
        "card",
        "stripe",
        "wallet",
        "balance",
        "device_fingerprint",
        "phone",
        "name",
        "cookies",
        "authorization",
        "api_key",
        "token",
    }
)


class TurnitinEvalError(ValueError):
    """Fail-closed evaluation linkage error."""


@dataclass(slots=True)
class EvalCasePaths:
    root: Path
    cases_dir: Path
    index_path: Path

    @classmethod
    def from_root(cls, root: Path | None = None) -> "EvalCasePaths":
        base = Path(root) if root is not None else DEFAULT_EVAL_ROOT
        return cls(
            root=base,
            cases_dir=base / CASES_DIRNAME,
            index_path=base / INDEX_FILENAME,
        )

    def ensure(self) -> None:
        self.cases_dir.mkdir(parents=True, exist_ok=True)


def text_sha256(text: str) -> str:
    """Deterministic SHA-256 over UTF-8 bytes of the exact string (no normalization)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def new_eval_id() -> str:
    """Generate a new opaque evaluation id (UUID4 hex)."""
    return uuid.uuid4().hex


def strip_pii(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _PII_KEYS:
            continue
        if isinstance(value, dict):
            out[key] = strip_pii(value)
        else:
            out[key] = value
    return out


def create_eval_case(
    *,
    original_text: str,
    humanized_text: str,
    root: Path | None = None,
    eval_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an evaluation case BEFORE Turnitin submission.

    Stores the exact original/humanized pair with deterministic content hashes.
    Does not call Turnitin or modify production Humanizer flows.
    """
    original = original_text if original_text is not None else ""
    humanized = humanized_text if humanized_text is not None else ""
    if not str(original).strip():
        raise TurnitinEvalError("original_text is required")
    if not str(humanized).strip():
        raise TurnitinEvalError("humanized_text is required")

    paths = EvalCasePaths.from_root(root)
    paths.ensure()

    eid = (eval_id or new_eval_id()).strip()
    if not eid or not re.fullmatch(r"[0-9a-fA-F-]{8,64}", eid):
        raise TurnitinEvalError("invalid eval_id")
    eid = eid.replace("-", "").lower()
    case_path = paths.cases_dir / f"{eid}.json"
    if case_path.exists():
        raise TurnitinEvalError(f"eval_id already exists: {eid}")

    created_at = datetime.now(timezone.utc).isoformat()
    record = strip_pii(
        {
            "eval_id": eid,
            "original_text_hash": text_sha256(original),
            "humanized_text_hash": text_sha256(humanized),
            "original_text": original,
            "humanized_text": humanized,
            "turnitin_submission_id": None,
            "ai_score": None,
            "similarity": None,
            "report_path": None,
            "ai_report_path": None,
            "ai_highlights_report_path": None,
            "similarity_report_path": None,
            "ai_highlights": None,
            "provider": None,
            "span_extraction_status": "unavailable_with_current_parsers",
            "marked_ai_spans": [],
            "unmarked_spans": [],
            "status": "pending_turnitin",
            "created_at": created_at,
            "updated_at": created_at,
            "metadata": strip_pii(dict(metadata or {})),
        }
    )
    _write_json(case_path, record)
    _append_index(
        paths.index_path,
        {
            "eval_id": eid,
            "event": "created",
            "original_text_hash": record["original_text_hash"],
            "humanized_text_hash": record["humanized_text_hash"],
            "status": record["status"],
            "created_at": created_at,
        },
    )
    return record


def load_eval_case(eval_id: str, *, root: Path | None = None) -> dict[str, Any]:
    paths = EvalCasePaths.from_root(root)
    eid = _normalize_eval_id(eval_id)
    case_path = paths.cases_dir / f"{eid}.json"
    if not case_path.is_file():
        raise TurnitinEvalError(f"eval case not found: {eid}")
    try:
        payload = json.loads(case_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TurnitinEvalError(f"corrupt eval case: {eid}") from exc
    if not isinstance(payload, dict):
        raise TurnitinEvalError(f"corrupt eval case: {eid}")
    return payload


def attach_turnitin_result(
    eval_id: str,
    *,
    original_text_hash: str,
    humanized_text_hash: str,
    turnitin_submission_id: str | None = None,
    ai_score: float | int | None = None,
    similarity: float | int | None = None,
    report_path: str | None = None,
    ai_report_path: str | None = None,
    ai_highlights_report_path: str | None = None,
    similarity_report_path: str | None = None,
    ai_highlights: float | int | None = None,
    provider: str | None = None,
    extra_report_meta: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Attach an existing Turnitin result to a prior eval case.

    Fail-closed: hashes must match the stored pair exactly.
    Does not invent AI spans.
    """
    paths = EvalCasePaths.from_root(root)
    record = load_eval_case(eval_id, root=paths.root)
    eid = record["eval_id"]

    expected_o = str(record.get("original_text_hash") or "")
    expected_h = str(record.get("humanized_text_hash") or "")
    got_o = str(original_text_hash or "").strip().lower()
    got_h = str(humanized_text_hash or "").strip().lower()
    if got_o != expected_o.lower() or got_h != expected_h.lower():
        raise TurnitinEvalError(
            "hash mismatch: refusing to attach Turnitin result to a different text pair"
        )

    # Prefer explicit paths; fall back to generic report_path for ai report.
    ai_path = ai_report_path or report_path
    updated_at = datetime.now(timezone.utc).isoformat()
    record["turnitin_submission_id"] = (
        str(turnitin_submission_id).strip() if turnitin_submission_id else record.get("turnitin_submission_id")
    )
    if ai_score is not None:
        record["ai_score"] = float(ai_score)
    if similarity is not None:
        record["similarity"] = float(similarity)
    if ai_highlights is not None:
        record["ai_highlights"] = float(ai_highlights)
    if ai_path:
        record["report_path"] = str(ai_path)
        record["ai_report_path"] = str(ai_path)
    if ai_highlights_report_path:
        record["ai_highlights_report_path"] = str(ai_highlights_report_path)
    if similarity_report_path:
        record["similarity_report_path"] = str(similarity_report_path)
    if provider:
        record["provider"] = str(provider)
    # Spans remain unavailable — never populate from score alone.
    record["span_extraction_status"] = "unavailable_with_current_parsers"
    record["marked_ai_spans"] = []
    record["unmarked_spans"] = []
    record["status"] = "report_attached"
    record["updated_at"] = updated_at
    if extra_report_meta:
        meta = dict(record.get("metadata") or {})
        meta["turnitin_report"] = strip_pii(dict(extra_report_meta))
        record["metadata"] = strip_pii(meta)

    record = strip_pii(record)
    _write_json(paths.cases_dir / f"{eid}.json", record)
    _append_index(
        paths.index_path,
        {
            "eval_id": eid,
            "event": "report_attached",
            "original_text_hash": expected_o,
            "humanized_text_hash": expected_h,
            "turnitin_submission_id": record.get("turnitin_submission_id"),
            "status": record["status"],
            "updated_at": updated_at,
        },
    )
    return record


def attach_from_submission_row(
    eval_id: str,
    *,
    original_text_hash: str,
    humanized_text_hash: str,
    submission_row: dict[str, Any],
    root: Path | None = None,
) -> dict[str, Any]:
    """Attach using a TurnitinStore-like row dict (PII stripped)."""
    row = strip_pii(dict(submission_row or {}))
    report_path = (
        row.get("ai_report_path")
        or row.get("ai_highlights_report_path")
        or row.get("similarity_report_path")
    )
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    if not meta and isinstance(row.get("meta_json"), str):
        try:
            parsed = json.loads(row["meta_json"])
            if isinstance(parsed, dict):
                meta = parsed
        except json.JSONDecodeError:
            meta = {}
    return attach_turnitin_result(
        eval_id,
        original_text_hash=original_text_hash,
        humanized_text_hash=humanized_text_hash,
        turnitin_submission_id=str(row.get("id") or row.get("submission_id") or "") or None,
        ai_score=row.get("ai_score"),
        similarity=row.get("similarity"),
        report_path=report_path,
        ai_report_path=row.get("ai_report_path"),
        ai_highlights_report_path=row.get("ai_highlights_report_path"),
        similarity_report_path=row.get("similarity_report_path"),
        ai_highlights=row.get("ai_highlights"),
        provider=(meta.get("provider") if isinstance(meta, dict) else None),
        extra_report_meta={
            "status": row.get("status"),
            "external_id": row.get("external_id"),
            "ai_score_display": meta.get("ai_score_display") if isinstance(meta, dict) else None,
            "similarity_display": meta.get("similarity_display") if isinstance(meta, dict) else None,
            "ai_highlights_display": meta.get("ai_highlights_display")
            if isinstance(meta, dict)
            else None,
        },
        root=root,
    )


def _normalize_eval_id(eval_id: str) -> str:
    eid = str(eval_id or "").strip().replace("-", "").lower()
    if not eid:
        raise TurnitinEvalError("eval_id is required")
    return eid


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_index(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(strip_pii(row), ensure_ascii=False) + "\n")
