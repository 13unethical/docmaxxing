"""Export real-user humanizer pairs for training.

Surfaces allowed: ``standalone``, ``assignment``.
Surface blocked: ``workspace_partial``.

Export requires per-row ``training_eligible=1`` (stamped on new successful
logs for standalone/assignment). No user opt-in gate.

Assignments enter ``real_user_raw`` but ``legacy51_sft_eligible`` only when
model/level prove Legacy 5.1 / level 8. Never mixes workspace into SFT.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from services.humanizer_training.config import (
    BLOCKED_TRAINING_SURFACES,
    REAL_USER_ALLOWED_SURFACES,
)
from services.humanizer_training.consent import ELIGIBILITY_WRITE_PATH_IMPLEMENTED
from services.humanizer_training.dedupe import make_pair_hash, make_source_hash

# ---------------------------------------------------------------------------
# Eligibility stamp — write path in services.humanizer_training.consent
# ---------------------------------------------------------------------------

# Inferred product defaults — NOT stored in humanizer_dataset_logs today.
_INFERRED_STANDALONE_LEVEL = 8
_INFERRED_ASSIGNMENT_LEVEL = 10
_CANONICAL_LEGACY_MODEL = "Legacy 5.1"
_CANONICAL_UI_LABEL = "Ghost 5.1 Legacy"
_CANONICAL_LEVEL = 8

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
    }
)

DEFAULT_OUTPUT_DIR = Path("data/humanizer_training/real_user_raw")
CHECKPOINT_FILENAME = "export_checkpoint.json"


@dataclass(slots=True)
class ExportCounts:
    eligible_standalone: int = 0
    eligible_assignment: int = 0
    excluded_workspace: int = 0
    excluded_missing_consent: int = 0
    excluded_invalid_output: int = 0
    excluded_duplicate: int = 0
    excluded_missing_metadata: int = 0
    excluded_other: int = 0
    scanned: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "eligible_standalone": self.eligible_standalone,
            "eligible_assignment": self.eligible_assignment,
            "excluded_workspace": self.excluded_workspace,
            "excluded_missing_consent": self.excluded_missing_consent,
            "excluded_invalid_output": self.excluded_invalid_output,
            "excluded_duplicate": self.excluded_duplicate,
            "excluded_missing_metadata": self.excluded_missing_metadata,
            "excluded_other": self.excluded_other,
            "scanned": self.scanned,
            "eligible_total": self.eligible_total,
        }

    @property
    def eligible_total(self) -> int:
        return self.eligible_standalone + self.eligible_assignment


@dataclass(slots=True)
class RealUserExportResult:
    blocked: bool
    block_reason: str | None
    counts: ExportCounts
    records_path: Path
    excluded_path: Path
    manifest_path: Path
    manifest: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IncrementalExportResult:
    dry_run: bool
    blocked: bool
    block_reason: str | None
    new_eligible_records: int
    exported: int
    skipped: int
    duplicates: int
    workspace_excluded: int
    exported_standalone: int
    exported_assignment: int
    legacy51_sft_eligible_exported: int
    checkpoint_before: dict[str, Any]
    checkpoint_after: dict[str, Any]
    records_path: Path
    excluded_path: Path
    checkpoint_path: Path
    counts: ExportCounts
    summary: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "new_eligible_records": self.new_eligible_records,
            "exported": self.exported,
            "skipped": self.skipped,
            "duplicates": self.duplicates,
            "workspace_excluded": self.workspace_excluded,
            "exported_standalone": self.exported_standalone,
            "exported_assignment": self.exported_assignment,
            "legacy51_sft_eligible_exported": self.legacy51_sft_eligible_exported,
            "checkpoint_before": self.checkpoint_before,
            "checkpoint_after": self.checkpoint_after,
            "records_path": str(self.records_path),
            "excluded_path": str(self.excluded_path),
            "checkpoint_path": str(self.checkpoint_path),
            "counts": self.counts.as_dict(),
            "summary": self.summary,
        }


def is_blocked_training_surface(source: str | None) -> bool:
    return (source or "").strip().lower() in BLOCKED_TRAINING_SURFACES


def is_allowed_real_user_surface(source: str | None) -> bool:
    return (source or "").strip().lower() in REAL_USER_ALLOWED_SURFACES


def has_reliable_consent_mechanism(*, columns: set[str] | None = None) -> bool:
    """True when training_eligible stamp column + write-path exist."""
    if not ELIGIBILITY_WRITE_PATH_IMPLEMENTED:
        return False
    if columns is not None and "training_eligible" not in columns:
        return False
    return True


def assert_safe_for_legacy51_sft(record: dict[str, Any]) -> bool:
    """Legacy 5.1 SFT must never consume workspace or unmarked real-user rows."""
    surface = str(
        record.get("source_surface")
        or record.get("origin_source")
        or record.get("source")
        or ""
    ).strip().lower()
    if is_blocked_training_surface(surface):
        return False
    if surface in REAL_USER_ALLOWED_SURFACES:
        return bool(record.get("legacy51_sft_eligible") is True)
    return True


def provider_metadata_for_surface(
    surface: str,
    *,
    verified_model: str | None = None,
    ui_model_label: str | None = None,
    verified_level: int | None = None,
    selection_verified: bool | None = None,
) -> dict[str, Any]:
    """Annotate provider knobs; DB usually lacks model/level — infer + gate Legacy51."""
    src = (surface or "").strip().lower()
    if src == "assignment":
        level = (
            int(verified_level)
            if verified_level is not None
            else _INFERRED_ASSIGNMENT_LEVEL
        )
        model = (verified_model or "").strip() or "not_recorded_in_dataset_logs"
        ui = (ui_model_label or "").strip()
        proves_legacy51 = bool(
            model == _CANONICAL_LEGACY_MODEL and level == _CANONICAL_LEVEL
        )
        return {
            "provider": "stealthwriter",
            "model": model,
            "ui_model_label": ui or None,
            "level": level,
            "level_source": (
                "recorded"
                if verified_level is not None
                else "inferred_assignment_product_pin"
            ),
            "level_recorded_in_db": verified_level is not None,
            "legacy51_sft_eligible": proves_legacy51,
            "consent_status": "auto_eligible",
            "note": (
                "Assignments default to StealthWriter level ~10. They export to "
                "real_user_raw automatically; Legacy 5.1 SFT only when model/level "
                "prove Legacy 5.1 / level 8."
            ),
        }
    if src == "standalone":
        level = (
            int(verified_level)
            if verified_level is not None
            else _INFERRED_STANDALONE_LEVEL
        )
        model = (verified_model or "").strip() or "not_recorded_in_dataset_logs"
        ui = (ui_model_label or "").strip()
        proves_legacy51 = bool(
            selection_verified is True
            and model == _CANONICAL_LEGACY_MODEL
            and ui == _CANONICAL_UI_LABEL
            and level == _CANONICAL_LEVEL
        )
        return {
            "provider": "stealthwriter",
            "model": model,
            "ui_model_label": ui or None,
            "level": level,
            "level_source": (
                "recorded" if verified_level is not None else "inferred_standalone_default"
            ),
            "level_recorded_in_db": verified_level is not None,
            "legacy51_sft_eligible": proves_legacy51,
            "consent_status": "auto_eligible",
            "selection_verified": selection_verified,
        }
    return {
        "provider": "unknown",
        "model": "not_recorded_in_dataset_logs",
        "level": None,
        "level_recorded_in_db": False,
        "legacy51_sft_eligible": False,
        "consent_status": "unknown",
    }


def strip_pii(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop known PII keys recursively (one level of nested dicts)."""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _PII_KEYS:
            continue
        if isinstance(value, dict):
            out[key] = strip_pii(value)
        else:
            out[key] = value
    return out


def evaluate_real_user_row(
    row: dict[str, Any],
    *,
    require_consent: bool = True,
    seen_exact: set[str] | None = None,
    seen_norm: set[str] | None = None,
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """Return (status, eligible_record|None, exclusion_record|None).

    status: accepted | excluded_workspace | excluded_missing_consent |
            excluded_invalid_output | excluded_duplicate | excluded_missing_metadata |
            excluded_other
    """
    surface = str(row.get("source") or row.get("source_surface") or "").strip().lower()
    sample_id = _sample_id(row)
    original = str(row.get("original_text") or "")
    humanized = str(row.get("humanized_text") or "")
    created_at = row.get("created_at")

    base_excl = {
        "sample_id": sample_id,
        "source_surface": surface or None,
        "timestamp": created_at,
    }

    if is_blocked_training_surface(surface):
        return (
            "excluded_workspace",
            None,
            {**base_excl, "reason": "workspace_partial_blocked"},
        )

    if not is_allowed_real_user_surface(surface):
        return (
            "excluded_other",
            None,
            {**base_excl, "reason": f"unsupported_surface:{surface or 'empty'}"},
        )

    if require_consent:
        eligible_flag = row.get("training_eligible")
        if eligible_flag is True or eligible_flag == 1 or eligible_flag == "1":
            pass
        else:
            return (
                "excluded_missing_consent",
                None,
                {**base_excl, "reason": "training_eligible_not_true"},
            )

    if not original.strip() or not humanized.strip():
        return (
            "excluded_invalid_output",
            None,
            {**base_excl, "reason": "empty_source_or_output"},
        )

    if _normalize(original) == _normalize(humanized):
        return (
            "excluded_invalid_output",
            None,
            {**base_excl, "reason": "unchanged_source_output"},
        )

    # Provider/model are not in DB; inferred annotation is required for assignment policy.
    meta = provider_metadata_for_surface(
        surface,
        verified_model=row.get("verified_model") or row.get("teacher_model"),
        ui_model_label=row.get("ui_model_label"),
        verified_level=row.get("verified_level") or row.get("teacher_level"),
        selection_verified=row.get("selection_verified"),
    )
    if surface == "assignment" and meta.get("level") is None:
        return (
            "excluded_missing_metadata",
            None,
            {**base_excl, "reason": "assignment_level_unknown"},
        )

    exact_key = make_pair_hash(original, humanized)
    norm_key = make_pair_hash(_normalize(original), _normalize(humanized))
    source_key = make_source_hash(original)
    if seen_exact is not None:
        if exact_key in seen_exact or norm_key in seen_exact:
            return (
                "excluded_duplicate",
                None,
                {**base_excl, "reason": "exact_or_normalized_duplicate"},
            )
        # Also treat identical source with different target as duplicate source for export.
        if source_key in seen_norm:
            return (
                "excluded_duplicate",
                None,
                {**base_excl, "reason": "duplicate_source"},
            )

    record = strip_pii(
        {
            "sample_id": sample_id,
            "source_surface": surface,
            "original_text": original,
            "humanized_text": humanized,
            "timestamp": created_at,
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "level": meta.get("level"),
            "level_source": meta.get("level_source"),
            "level_recorded_in_db": meta.get("level_recorded_in_db"),
            "legacy51_sft_eligible": bool(meta.get("legacy51_sft_eligible")),
            "training_eligible": True,
            "consent_status": "auto_eligible",
            "pair_hash": exact_key,
            "source_hash": source_key,
        }
    )
    if seen_exact is not None:
        seen_exact.add(exact_key)
        seen_exact.add(norm_key)
    if seen_norm is not None:
        seen_norm.add(source_key)
    return "accepted", record, None


def export_real_user_training_data(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    db_path: Path | None = None,
    rows: Iterable[dict[str, Any]] | None = None,
    require_reliable_consent: bool = True,
) -> RealUserExportResult:
    """Export training_eligible real-user pairs. Fail-closed without stamp column."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records_path = output_dir / "records.jsonl"
    excluded_path = output_dir / "excluded.jsonl"
    manifest_path = output_dir / "manifest.json"

    counts = ExportCounts()
    columns = set()
    blocked = False
    block_reason: str | None = None

    if rows is None:
        from services.economy.db import connect as economy_connect

        # Probe schema + optional COUNT stats without dumping unconsented text.
        with economy_connect() as conn:
            columns = _table_columns(conn, "humanizer_dataset_logs")
            if require_reliable_consent and not has_reliable_consent_mechanism(columns=columns):
                blocked = True
                block_reason = _block_reason(columns)
                counts = _count_without_exporting_text(conn, columns)
                _write_empty_exports(records_path, excluded_path)
                manifest = _build_manifest(
                    blocked=True,
                    block_reason=block_reason,
                    counts=counts,
                    columns=sorted(columns),
                    records_path=records_path,
                    excluded_path=excluded_path,
                )
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return RealUserExportResult(
                    blocked=True,
                    block_reason=block_reason,
                    counts=counts,
                    records_path=records_path,
                    excluded_path=excluded_path,
                    manifest_path=manifest_path,
                    manifest=manifest,
                )
            rows = list(_iter_db_rows(conn, columns))
    else:
        rows = list(rows)
        # Synthetic/unit-test path: trust explicit training_eligible on rows when
        # require_reliable_consent is False.
        if require_reliable_consent and not has_reliable_consent_mechanism(columns={"training_eligible"}):
            blocked = True
            block_reason = (
                "No reliable consent/eligibility write-path is implemented; "
                "refusing to export real-user text."
            )
            for row in rows:
                counts.scanned += 1
                surface = str(row.get("source") or "").strip().lower()
                if is_blocked_training_surface(surface):
                    counts.excluded_workspace += 1
                elif is_allowed_real_user_surface(surface):
                    counts.excluded_missing_consent += 1
                else:
                    counts.excluded_other += 1
            _write_empty_exports(records_path, excluded_path)
            manifest = _build_manifest(
                blocked=True,
                block_reason=block_reason,
                counts=counts,
                columns=["(injected_rows)"],
                records_path=records_path,
                excluded_path=excluded_path,
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return RealUserExportResult(
                blocked=True,
                block_reason=block_reason,
                counts=counts,
                records_path=records_path,
                excluded_path=excluded_path,
                manifest_path=manifest_path,
                manifest=manifest,
            )

    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    seen_exact: set[str] = set()
    seen_norm: set[str] = set()
    # When consent mechanism is unreliable we already returned. Here consent is
    # required per-row via training_eligible == true.
    require_consent = True

    for row in rows:
        counts.scanned += 1
        status, record, excl = evaluate_real_user_row(
            row,
            require_consent=require_consent,
            seen_exact=seen_exact,
            seen_norm=seen_norm,
        )
        if status == "accepted" and record is not None:
            accepted.append(record)
            if record["source_surface"] == "standalone":
                counts.eligible_standalone += 1
            else:
                counts.eligible_assignment += 1
        else:
            if excl is not None:
                # Never put PII into exclusions; also omit full text for consent misses.
                safe_excl = strip_pii(excl)
                if status == "excluded_missing_consent":
                    safe_excl.pop("original_text", None)
                    safe_excl.pop("humanized_text", None)
                excluded.append(safe_excl)
            if status == "excluded_workspace":
                counts.excluded_workspace += 1
            elif status == "excluded_missing_consent":
                counts.excluded_missing_consent += 1
            elif status == "excluded_invalid_output":
                counts.excluded_invalid_output += 1
            elif status == "excluded_duplicate":
                counts.excluded_duplicate += 1
            elif status == "excluded_missing_metadata":
                counts.excluded_missing_metadata += 1
            else:
                counts.excluded_other += 1

    _write_jsonl(records_path, accepted)
    _write_jsonl(excluded_path, excluded)
    manifest = _build_manifest(
        blocked=blocked,
        block_reason=block_reason,
        counts=counts,
        columns=sorted(columns) if columns else ["(injected_rows)"],
        records_path=records_path,
        excluded_path=excluded_path,
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return RealUserExportResult(
        blocked=blocked,
        block_reason=block_reason,
        counts=counts,
        records_path=records_path,
        excluded_path=excluded_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )


def checkpoint_path_for(output_dir: Path) -> Path:
    return Path(output_dir) / CHECKPOINT_FILENAME


def load_export_checkpoint(output_dir: Path) -> dict[str, Any]:
    path = checkpoint_path_for(output_dir)
    if not path.is_file():
        return {"last_id": 0, "last_created_at": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"last_id": 0, "last_created_at": ""}
    if not isinstance(data, dict):
        return {"last_id": 0, "last_created_at": ""}
    try:
        last_id = int(data.get("last_id") or 0)
    except (TypeError, ValueError):
        last_id = 0
    return {
        "last_id": max(0, last_id),
        "last_created_at": str(data.get("last_created_at") or ""),
        "updated_at": data.get("updated_at"),
        "exported_total": data.get("exported_total"),
    }


def save_export_checkpoint(
    output_dir: Path,
    *,
    last_id: int,
    last_created_at: str,
    exported_total: int | None = None,
) -> dict[str, Any]:
    path = checkpoint_path_for(output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    payload = {
        "last_id": int(last_id),
        "last_created_at": str(last_created_at or ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if exported_total is not None:
        payload["exported_total"] = int(exported_total)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def load_existing_export_indexes(
    records_path: Path,
) -> tuple[set[str], set[str], set[str]]:
    """Return (pair_hashes, source_hashes, sample_ids) already in records.jsonl."""
    pair_hashes: set[str] = set()
    source_hashes: set[str] = set()
    sample_ids: set[str] = set()
    if not records_path.is_file():
        return pair_hashes, source_hashes, sample_ids
    with records_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            ph = row.get("pair_hash")
            sh = row.get("source_hash")
            sid = row.get("sample_id")
            if ph:
                pair_hashes.add(str(ph))
            if sh:
                source_hashes.add(str(sh))
            if sid:
                sample_ids.add(str(sid))
            # Rebuild hashes if older lines lack them.
            if not ph and row.get("original_text") and row.get("humanized_text"):
                pair_hashes.add(
                    make_pair_hash(str(row["original_text"]), str(row["humanized_text"]))
                )
            if not sh and row.get("original_text"):
                source_hashes.add(make_source_hash(str(row["original_text"])))
    return pair_hashes, source_hashes, sample_ids


def export_real_user_training_data_incremental(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    dry_run: bool = False,
    limit: int | None = None,
    rows: Iterable[dict[str, Any]] | None = None,
    require_reliable_consent: bool = True,
) -> IncrementalExportResult:
    """Append-only export of new ``training_eligible=1`` rows since checkpoint.

    Checkpoint advances by ``(created_at, id)`` / ``last_id``. Reruns do not
    duplicate lines already present in ``records.jsonl``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records_path = output_dir / "records.jsonl"
    excluded_path = output_dir / "excluded.jsonl"
    manifest_path = output_dir / "manifest.json"
    ckpt_path = checkpoint_path_for(output_dir)

    checkpoint_before = load_export_checkpoint(output_dir)
    last_id = int(checkpoint_before.get("last_id") or 0)
    last_created_at = str(checkpoint_before.get("last_created_at") or "")

    counts = ExportCounts()
    columns: set[str] = set()
    blocked = False
    block_reason: str | None = None

    if rows is None:
        from services.economy.db import connect as economy_connect

        with economy_connect() as conn:
            columns = _table_columns(conn, "humanizer_dataset_logs")
            if require_reliable_consent and not has_reliable_consent_mechanism(columns=columns):
                blocked = True
                block_reason = _block_reason(columns)
                summary = {
                    "new_eligible_records": 0,
                    "exported": 0,
                    "skipped": 0,
                    "duplicates": 0,
                    "workspace_excluded": 0,
                }
                result = IncrementalExportResult(
                    dry_run=dry_run,
                    blocked=True,
                    block_reason=block_reason,
                    new_eligible_records=0,
                    exported=0,
                    skipped=0,
                    duplicates=0,
                    workspace_excluded=0,
                    exported_standalone=0,
                    exported_assignment=0,
                    legacy51_sft_eligible_exported=0,
                    checkpoint_before=checkpoint_before,
                    checkpoint_after=checkpoint_before,
                    records_path=records_path,
                    excluded_path=excluded_path,
                    checkpoint_path=ckpt_path,
                    counts=counts,
                    summary=summary,
                )
                if not dry_run:
                    manifest = _build_manifest(
                        blocked=True,
                        block_reason=block_reason,
                        counts=counts,
                        columns=sorted(columns),
                        records_path=records_path,
                        excluded_path=excluded_path,
                    )
                    manifest["mode"] = "incremental"
                    manifest["incremental"] = result.as_dict()
                    manifest_path.write_text(
                        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                return result
            candidate_rows = _iter_db_rows_since(
                conn,
                columns,
                last_id=last_id,
                last_created_at=last_created_at,
                limit=limit,
            )
    else:
        columns = {"training_eligible", "id", "source", "created_at"}
        if require_reliable_consent and not has_reliable_consent_mechanism(
            columns={"training_eligible"}
        ):
            blocked = True
            block_reason = (
                "No reliable eligibility write-path is implemented; "
                "refusing to export real-user text."
            )
            empty = IncrementalExportResult(
                dry_run=dry_run,
                blocked=True,
                block_reason=block_reason,
                new_eligible_records=0,
                exported=0,
                skipped=0,
                duplicates=0,
                workspace_excluded=0,
                exported_standalone=0,
                exported_assignment=0,
                legacy51_sft_eligible_exported=0,
                checkpoint_before=checkpoint_before,
                checkpoint_after=checkpoint_before,
                records_path=records_path,
                excluded_path=excluded_path,
                checkpoint_path=ckpt_path,
                counts=counts,
                summary={
                    "new_eligible_records": 0,
                    "exported": 0,
                    "skipped": 0,
                    "duplicates": 0,
                    "workspace_excluded": 0,
                },
            )
            return empty
        candidate_rows = [
            row
            for row in rows
            if _row_is_after_checkpoint(row, last_id=last_id, last_created_at=last_created_at)
        ]
        candidate_rows.sort(
            key=lambda r: (str(r.get("created_at") or ""), int(r.get("id") or 0))
        )
        if limit is not None:
            candidate_rows = candidate_rows[: max(0, int(limit))]

    seen_exact, seen_norm, seen_sample_ids = load_existing_export_indexes(records_path)
    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    new_eligible = 0
    exported = 0
    skipped = 0
    duplicates = 0
    workspace_excluded = 0
    exported_standalone = 0
    exported_assignment = 0
    legacy51_count = 0

    for row in candidate_rows:
        counts.scanned += 1
        row_id = int(row.get("id") or 0)
        created_at = str(row.get("created_at") or "")
        surface = str(row.get("source") or "").strip().lower()
        eligible_flag = row.get("training_eligible")
        is_eligible = eligible_flag is True or eligible_flag == 1 or eligible_flag == "1"

        if is_blocked_training_surface(surface):
            workspace_excluded += 1
            counts.excluded_workspace += 1
            excluded.append(
                strip_pii(
                    {
                        "sample_id": _sample_id(row),
                        "source_surface": surface,
                        "timestamp": created_at,
                        "reason": "workspace_partial_blocked",
                        "db_id": row_id or None,
                    }
                )
            )
            continue

        if not is_eligible:
            skipped += 1
            counts.excluded_missing_consent += 1
            continue

        new_eligible += 1
        sample_id = _sample_id(row)
        if sample_id in seen_sample_ids:
            duplicates += 1
            counts.excluded_duplicate += 1
            excluded.append(
                strip_pii(
                    {
                        "sample_id": sample_id,
                        "source_surface": surface,
                        "timestamp": created_at,
                        "reason": "sample_id_already_exported",
                        "db_id": row_id or None,
                    }
                )
            )
            continue

        status, record, excl = evaluate_real_user_row(
            row,
            require_consent=True,
            seen_exact=seen_exact,
            seen_norm=seen_norm,
        )
        if status == "accepted" and record is not None:
            accepted.append(record)
            exported += 1
            seen_sample_ids.add(sample_id)
            if record["source_surface"] == "standalone":
                exported_standalone += 1
                counts.eligible_standalone += 1
            else:
                exported_assignment += 1
                counts.eligible_assignment += 1
            if record.get("legacy51_sft_eligible") is True:
                legacy51_count += 1
        else:
            if status == "excluded_duplicate":
                duplicates += 1
                counts.excluded_duplicate += 1
            elif status == "excluded_workspace":
                workspace_excluded += 1
                counts.excluded_workspace += 1
            elif status == "excluded_missing_consent":
                skipped += 1
                counts.excluded_missing_consent += 1
            elif status == "excluded_invalid_output":
                skipped += 1
                counts.excluded_invalid_output += 1
            elif status == "excluded_missing_metadata":
                skipped += 1
                counts.excluded_missing_metadata += 1
            else:
                skipped += 1
                counts.excluded_other += 1
            if excl is not None:
                safe_excl = strip_pii(excl)
                safe_excl["db_id"] = row_id or None
                safe_excl.pop("original_text", None)
                safe_excl.pop("humanized_text", None)
                excluded.append(safe_excl)

    if candidate_rows:
        last_row = candidate_rows[-1]
        checkpoint_after = {
            "last_id": int(last_row.get("id") or last_id),
            "last_created_at": str(last_row.get("created_at") or last_created_at),
        }
    else:
        checkpoint_after = {
            "last_id": last_id,
            "last_created_at": last_created_at,
        }

    prev_total = 0
    try:
        prev_total = int(checkpoint_before.get("exported_total") or 0)
    except (TypeError, ValueError):
        prev_total = 0

    if not dry_run and not blocked:
        if accepted:
            _append_jsonl(records_path, accepted)
        if excluded:
            _append_jsonl(excluded_path, excluded)
        checkpoint_after = save_export_checkpoint(
            output_dir,
            last_id=int(checkpoint_after["last_id"]),
            last_created_at=str(checkpoint_after["last_created_at"]),
            exported_total=prev_total + exported,
        )
        manifest = _build_manifest(
            blocked=False,
            block_reason=None,
            counts=counts,
            columns=sorted(columns) if columns else ["(injected_rows)"],
            records_path=records_path,
            excluded_path=excluded_path,
        )
        manifest["mode"] = "incremental"
        manifest["checkpoint"] = checkpoint_after
        manifest["incremental_run"] = {
            "new_eligible_records": new_eligible,
            "exported": exported,
            "skipped": skipped,
            "duplicates": duplicates,
            "workspace_excluded": workspace_excluded,
            "exported_standalone": exported_standalone,
            "exported_assignment": exported_assignment,
            "legacy51_sft_eligible_exported": legacy51_count,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    elif dry_run:
        checkpoint_after = {
            **checkpoint_after,
            "note": "dry_run_checkpoint_not_written",
        }

    summary = {
        "new_eligible_records": new_eligible,
        "exported": exported,
        "skipped": skipped,
        "duplicates": duplicates,
        "workspace_excluded": workspace_excluded,
        "exported_standalone": exported_standalone,
        "exported_assignment": exported_assignment,
        "legacy51_sft_eligible_exported": legacy51_count,
    }
    return IncrementalExportResult(
        dry_run=dry_run,
        blocked=blocked,
        block_reason=block_reason,
        new_eligible_records=new_eligible,
        exported=exported,
        skipped=skipped,
        duplicates=duplicates,
        workspace_excluded=workspace_excluded,
        exported_standalone=exported_standalone,
        exported_assignment=exported_assignment,
        legacy51_sft_eligible_exported=legacy51_count,
        checkpoint_before=checkpoint_before,
        checkpoint_after=checkpoint_after,
        records_path=records_path,
        excluded_path=excluded_path,
        checkpoint_path=ckpt_path,
        counts=counts,
        summary=summary,
    )


def _row_is_after_checkpoint(
    row: dict[str, Any],
    *,
    last_id: int,
    last_created_at: str,
) -> bool:
    row_id = int(row.get("id") or 0)
    created_at = str(row.get("created_at") or "")
    if last_id <= 0 and not last_created_at:
        return True
    if last_created_at and created_at:
        if created_at > last_created_at:
            return True
        if created_at < last_created_at:
            return False
        return row_id > last_id
    return row_id > last_id


def _iter_db_rows_since(
    conn: Any,
    columns: set[str],
    *,
    last_id: int,
    last_created_at: str,
    limit: int | None,
) -> list[dict[str, Any]]:
    has_eligible = "training_eligible" in columns
    cols = "id, source, original_text, humanized_text, created_at"
    if has_eligible:
        cols += ", training_eligible"

    # Prefer eligible rows after checkpoint; also pull workspace after checkpoint
    # so exclusion stats remain visible even when stamped 0.
    if has_eligible:
        where = (
            "("
            "COALESCE(training_eligible, 0) = 1 OR source = 'workspace_partial'"
            ")"
        )
    else:
        where = "1=0"

    params: list[Any] = []
    if last_created_at:
        where += (
            " AND (created_at > ? OR (created_at = ? AND id > ?) OR "
            "(created_at IS NULL AND id > ?))"
        )
        params.extend([last_created_at, last_created_at, last_id, last_id])
    elif last_id > 0:
        where += " AND id > ?"
        params.append(last_id)

    sql = (
        f"SELECT {cols} FROM humanizer_dataset_logs WHERE {where} "
        "ORDER BY created_at ASC, id ASC"
    )
    if limit is not None:
        sql += " LIMIT ?"
        params.append(max(0, int(limit)))

    rows = conn.execute(sql, tuple(params)).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        item = {
            "id": r["id"],
            "source": r["source"],
            "original_text": r["original_text"],
            "humanized_text": r["humanized_text"],
            "created_at": r["created_at"],
        }
        if has_eligible:
            item["training_eligible"] = r["training_eligible"]
        else:
            item["training_eligible"] = 0
        out.append(item)
    return out


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _block_reason(columns: set[str]) -> str:
    if "training_eligible" not in columns:
        return (
            "humanizer_dataset_logs has no training_eligible column; "
            "refusing to export real-user text until eligibility stamps exist."
        )
    if not ELIGIBILITY_WRITE_PATH_IMPLEMENTED:
        return (
            "training_eligible column may exist, but no eligibility write-path "
            "stamps new successful logs; refusing to export real-user text."
        )
    return "Eligibility mechanism unavailable."


def _count_without_exporting_text(conn: Any, columns: set[str]) -> ExportCounts:
    """Aggregate exclusion stats via SQL COUNT — never read essay text when blocked."""
    counts = ExportCounts()
    try:
        total = int(
            conn.execute("SELECT COUNT(*) AS c FROM humanizer_dataset_logs").fetchone()["c"]
        )
    except Exception:  # noqa: BLE001
        return counts
    counts.scanned = total
    try:
        for row in conn.execute(
            "SELECT source, COUNT(*) AS c FROM humanizer_dataset_logs GROUP BY source"
        ).fetchall():
            src = str(row["source"] or "").strip().lower()
            n = int(row["c"])
            if src == "workspace_partial":
                counts.excluded_workspace += n
            elif src in REAL_USER_ALLOWED_SURFACES:
                counts.excluded_missing_consent += n
            else:
                counts.excluded_other += n
    except Exception:  # noqa: BLE001
        counts.excluded_other += total
    return counts


def _iter_db_rows(conn: Any, columns: set[str]) -> list[dict[str, Any]]:
    has_eligible = "training_eligible" in columns
    cols = "id, source, original_text, humanized_text, created_at"
    if has_eligible:
        cols += ", training_eligible"
    rows = conn.execute(f"SELECT {cols} FROM humanizer_dataset_logs ORDER BY id ASC").fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        item = {
            "id": r["id"],
            "source": r["source"],
            "original_text": r["original_text"],
            "humanized_text": r["humanized_text"],
            "created_at": r["created_at"],
        }
        if has_eligible:
            item["training_eligible"] = r["training_eligible"]
        else:
            item["training_eligible"] = 0
        out.append(item)
    return out


def _table_columns(conn: Any, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except Exception:  # noqa: BLE001
        return set()
    names: set[str] = set()
    for r in rows:
        if r is None:
            continue
        if hasattr(r, "keys") and "name" in r.keys():
            names.add(str(r["name"]))
        elif isinstance(r, (tuple, list)) and len(r) >= 2:
            names.add(str(r[1]))
    return names


def _sample_id(row: dict[str, Any]) -> str:
    if row.get("sample_id"):
        return str(row["sample_id"])
    # Stable non-PII id from row pk when present; never embed user_id.
    if row.get("id") is not None:
        return f"real-{int(row['id'])}"
    digest = hashlib.sha256(
        (_normalize(str(row.get("original_text") or "")) + "\n" + _normalize(str(row.get("humanized_text") or ""))).encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    return f"real-{digest}"


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_empty_exports(records_path: Path, excluded_path: Path) -> None:
    records_path.write_text("", encoding="utf-8")
    excluded_path.write_text("", encoding="utf-8")


def _build_manifest(
    *,
    blocked: bool,
    block_reason: str | None,
    counts: ExportCounts,
    columns: list[str],
    records_path: Path,
    excluded_path: Path,
) -> dict[str, Any]:
    return {
        "dataset_type": "real_user_raw",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "blocked": blocked,
        "block_reason": block_reason,
        "consent_write_path_implemented": ELIGIBILITY_WRITE_PATH_IMPLEMENTED,
        "eligibility_write_path_implemented": ELIGIBILITY_WRITE_PATH_IMPLEMENTED,
        "reliable_consent_mechanism": has_reliable_consent_mechanism(
            columns=set(columns) if columns != ["(injected_rows)"] else {"training_eligible"}
        ),
        "allowed_surfaces": sorted(REAL_USER_ALLOWED_SURFACES),
        "blocked_surfaces": sorted(BLOCKED_TRAINING_SURFACES),
        "legacy51_sft_auto_ingest": False,
        "assignment_policy": (
            "Assignments export to real_user_raw when training_eligible=1; "
            "legacy51_sft_eligible only when model/level prove Legacy 5.1 / level 8 "
            "(product default remains level ~10)."
        ),
        "pii_policy": "user_id/email/session/ip/payment omitted from export records",
        "opt_in_required": False,
        "schema_columns_seen": columns,
        "counts": counts.as_dict(),
        "files": {
            "records": str(records_path),
            "excluded": str(excluded_path),
        },
    }
