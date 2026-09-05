"""Load raw examples from opted-in DB rows and external JSON/JSONL inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.economy.db import connect
from services.humanizer_training.config import (
    ALLOWED_SOURCE_TYPES,
    BLOCKED_TRAINING_SURFACES,
    DatasetBuildConfig,
    REAL_USER_ALLOWED_SURFACES,
    RawExample,
)


def load_raw_examples(config: DatasetBuildConfig) -> list[RawExample]:
    rows: list[RawExample] = []
    if config.include_database:
        rows.extend(_load_database_rows())
    if config.input_path:
        rows.extend(_load_input_path(config.input_path))
    return rows


def _load_database_rows() -> list[RawExample]:
    """Load only explicitly eligible production rows.

    If ``training_eligible`` column does not exist, treat all rows as not eligible.
    ``workspace_partial`` is always excluded, even if marked eligible.
    """
    output: list[RawExample] = []
    try:
        with connect() as conn:
            columns = _table_columns(conn, "humanizer_dataset_logs")
            if "training_eligible" not in columns:
                return output
            query = (
                "SELECT id, source, original_text, humanized_text, training_eligible, created_at "
                "FROM humanizer_dataset_logs "
                "WHERE COALESCE(training_eligible, 0) = 1"
            )
            for row in conn.execute(query).fetchall():
                origin_source = str(row["source"] or "").strip().lower()
                if origin_source in BLOCKED_TRAINING_SURFACES:
                    continue
                if origin_source and origin_source not in REAL_USER_ALLOWED_SURFACES:
                    # Unknown surfaces are not silently ingested.
                    continue
                output.append(
                    RawExample(
                        source_text=str(row["original_text"] or ""),
                        target_text=str(row["humanized_text"] or ""),
                        source_type="opted_in",
                        language="en",
                        domain="academic",
                        metadata={
                            "origin": "db",
                            "origin_source": origin_source,
                            "row_id": int(row["id"]),
                            "created_at": row["created_at"],
                            "legacy51_sft_eligible": False,
                        },
                    )
                )
    except Exception:
        return []
    return output


def _table_columns(conn: Any, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except Exception:
        return set()
    return {str(r["name"]) for r in rows if r is not None and "name" in r.keys()}


def _load_input_path(path: Path) -> list[RawExample]:
    files: list[Path]
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted([*path.rglob("*.jsonl"), *path.rglob("*.json")])
    else:
        return []

    out: list[RawExample] = []
    for file in files:
        if file.suffix.lower() == ".jsonl":
            out.extend(_load_jsonl(file))
        elif file.suffix.lower() == ".json":
            out.extend(_load_json(file))
    return out


def _load_jsonl(path: Path) -> list[RawExample]:
    out: list[RawExample] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item:
            continue
        try:
            payload = json.loads(item)
        except json.JSONDecodeError:
            continue
        ex = _raw_from_payload(payload, origin=str(path))
        if ex is not None:
            out.append(ex)
    return out


def _load_json(path: Path) -> list[RawExample]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload if isinstance(payload, list) else [payload]
    out: list[RawExample] = []
    for item in items:
        ex = _raw_from_payload(item, origin=str(path))
        if ex is not None:
            out.append(ex)
    return out


def _surface_from_payload(payload: dict[str, Any]) -> str:
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    for key in (
        "source_surface",
        "origin_source",
        "dataset_source",
    ):
        raw = payload.get(key) or meta.get(key)
        if raw:
            return str(raw).strip().lower()
    # Do not treat source_type (synthetic/public/opted_in) as a product surface.
    return ""


def _raw_from_payload(payload: Any, *, origin: str) -> RawExample | None:
    if not isinstance(payload, dict):
        return None
    surface = _surface_from_payload(payload)
    if surface in BLOCKED_TRAINING_SURFACES:
        return None

    source_type = str(payload.get("source_type") or "").strip().lower()
    # Legacy payloads sometimes used "source" for source_type; only accept when it
    # is an allowed source_type, never when it is a blocked product surface.
    if not source_type:
        maybe = str(payload.get("source") or "").strip().lower()
        if maybe in BLOCKED_TRAINING_SURFACES:
            return None
        if maybe in ALLOWED_SOURCE_TYPES:
            source_type = maybe
    if source_type not in ALLOWED_SOURCE_TYPES:
        return None
    eligible = payload.get("training_eligible")
    if eligible is False:
        return None
    # Real-user opted_in JSON must still carry an allowed surface when present.
    if source_type == "opted_in" and surface and surface not in REAL_USER_ALLOWED_SURFACES:
        return None
    source_text = str(
        payload.get("source_text")
        or payload.get("original_text")
        or ""
    )
    target_text = str(
        payload.get("target_text")
        or payload.get("humanized_text")
        or payload.get("target")
        or ""
    )
    language = str(payload.get("language") or "en")
    domain = str(payload.get("domain") or "academic")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    meta_out = {"origin": origin, **metadata}
    if surface:
        meta_out["origin_source"] = surface
        meta_out.setdefault("legacy51_sft_eligible", False)
    return RawExample(
        source_text=source_text,
        target_text=target_text,
        source_type=source_type,
        language=language,
        domain=domain,
        metadata=meta_out,
    )
