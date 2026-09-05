"""Scan isolated teacher artifacts and write Legacy-5.1 eligibility/quarantine manifests.

Does not modify raw teacher files. Does not call StealthWriter or production paths.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from services.humanizer_training.teacher_eligibility import (
    REASON_AMBIGUOUS_METADATA,
    REASON_FAILED_NO_OUTPUT,
    REASON_MOCK_DEFAULT,
    REASON_WRONG_LEVEL,
    REASON_WRONG_MODEL,
    evaluate_teacher_sample,
    primary_quarantine_bucket,
)

DEFAULT_ROOT = Path("data/humanizer_training")
DEFAULT_OUT = Path("data/humanizer_training/legacy51_clean")

# Teacher collection artifacts only (not synthetic student builds).
_SCAN_DIR_NAMES = ("teacher_raw", "teacher_raw_documents")
_PAIR_FILES = ("documents.jsonl", "teacher_pairs.jsonl")
_FAILURE_FILES = ("failures.jsonl",)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit Legacy 5.1 teacher eligibility / quarantine")
    p.add_argument("--root", type=str, default=str(DEFAULT_ROOT))
    p.add_argument("--output", type=str, default=str(DEFAULT_OUT))
    return p.parse_args()


def discover_jsonl_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for name in _SCAN_DIR_NAMES:
        base = root / name
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.jsonl")):
            if path.name in _PAIR_FILES or path.name in _FAILURE_FILES:
                files.append(path)
    return files


def iter_records(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            yield line_no, json.loads(line)


def sample_id(record: dict[str, Any], source_path: Path, line_no: int) -> str:
    for key in ("document_id", "source_id", "chunk_id", "id"):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return f"{source_path.as_posix()}#{line_no}"


def build_entry(
    *,
    record: dict[str, Any],
    source_path: Path,
    line_no: int,
    root: Path,
) -> dict[str, Any]:
    verdict = evaluate_teacher_sample(record)
    rel = str(source_path.relative_to(root)) if source_path.is_relative_to(root) else str(source_path)
    entry = {
        "sample_id": sample_id(record, source_path, line_no),
        "source_path": rel,
        "line_no": line_no,
        "run_dir": str(source_path.parent.relative_to(root))
        if source_path.parent.is_relative_to(root)
        else str(source_path.parent),
        "eligible": verdict.eligible,
        "quarantine_bucket": None
        if verdict.eligible
        else primary_quarantine_bucket(verdict.reasons),
        "quarantine_reasons": list(verdict.reasons),
        "provider": verdict.provider,
        "requested_model": verdict.requested_model,
        "verified_model": verdict.verified_model,
        "ui_model_label": verdict.ui_model_label,
        "requested_level": verdict.requested_level,
        "verified_level": verdict.verified_level,
        "selection_verified": verdict.selection_verified,
        "result_stage": verdict.result_stage,
        "has_source": verdict.has_source,
        "has_output": verdict.has_output,
        "output_differs": verdict.output_differs,
        "record_kind": verdict.record_kind,
        "domain": record.get("domain"),
        "document_type": record.get("document_type"),
        "status": record.get("status"),
        "quality_flags": record.get("quality_flags") or [],
        "source_word_count": record.get("source_word_count")
        or record.get("word_count_source")
        or (len(str(record.get("source_text") or "").split()) if record.get("source_text") else None),
        "teacher_word_count": record.get("teacher_word_count")
        or record.get("word_count_target")
        or (
            len(str(record.get("teacher_text") or record.get("target_text") or "").split())
            if (record.get("teacher_text") or record.get("target_text"))
            else None
        ),
    }
    return entry


def run_audit(*, root: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir = output_dir / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    files = discover_jsonl_files(root)
    eligible_rows: list[dict[str, Any]] = []
    quarantine_rows: list[dict[str, Any]] = []
    bucket_counts: Counter[str] = Counter()
    by_run: Counter[str] = Counter()

    for path in files:
        for line_no, record in iter_records(path):
            entry = build_entry(record=record, source_path=path, line_no=line_no, root=root)
            by_run[entry["run_dir"]] += 1
            if entry["eligible"]:
                eligible_rows.append(entry)
                bucket_counts["eligible_legacy51_level8"] += 1
            else:
                quarantine_rows.append(entry)
                bucket = entry["quarantine_bucket"] or REASON_AMBIGUOUS_METADATA
                bucket_counts[bucket] += 1

    eligible_path = output_dir / "eligible_manifest.jsonl"
    quarantine_path = quarantine_dir / "quarantine_manifest.jsonl"
    pairs_index_path = output_dir / "eligible_pairs_index.jsonl"
    summary_path = output_dir / "summary.json"

    _write_jsonl(eligible_path, eligible_rows)
    _write_jsonl(quarantine_path, quarantine_rows)
    # SFT prep pointer list: only eligible pairs, no text duplication.
    _write_jsonl(
        pairs_index_path,
        [
            {
                "sample_id": r["sample_id"],
                "source_path": r["source_path"],
                "line_no": r["line_no"],
                "run_dir": r["run_dir"],
                "provider": r["provider"],
                "verified_model": r["verified_model"],
                "ui_model_label": r["ui_model_label"],
                "verified_level": r["verified_level"],
                "selection_verified": r["selection_verified"],
                "result_stage": r["result_stage"],
                "source_word_count": r["source_word_count"],
                "teacher_word_count": r["teacher_word_count"],
                "domain": r["domain"],
                "document_type": r["document_type"],
            }
            for r in eligible_rows
        ],
    )

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root.resolve()),
        "output_dir": str(output_dir.resolve()),
        "scanned_files": [str(p.relative_to(root)) if p.is_relative_to(root) else str(p) for p in files],
        "total_records": len(eligible_rows) + len(quarantine_rows),
        "eligible_count": len(eligible_rows),
        "quarantine_count": len(quarantine_rows),
        "counts": {
            "eligible_legacy51_level8": int(bucket_counts.get("eligible_legacy51_level8", 0)),
            "wrong_model": int(bucket_counts.get(REASON_WRONG_MODEL, 0)),
            "wrong_level": int(bucket_counts.get(REASON_WRONG_LEVEL, 0)),
            "mock_default_provider": int(bucket_counts.get(REASON_MOCK_DEFAULT, 0)),
            "failed_no_output": int(bucket_counts.get(REASON_FAILED_NO_OUTPUT, 0)),
            "ambiguous_missing_metadata": int(bucket_counts.get(REASON_AMBIGUOUS_METADATA, 0)),
        },
        "records_by_run": dict(sorted(by_run.items())),
        "files": {
            "eligible_manifest": str(eligible_path),
            "quarantine_manifest": str(quarantine_path),
            "eligible_pairs_index": str(pairs_index_path),
            "summary": str(summary_path),
        },
        "notes": [
            "Raw teacher files were not modified or deleted.",
            "Eligibility requires stealthwriter_training + selection_verified + Ghost 5.1 Legacy + Legacy 5.1 + level 8 + RESULT_EXTRACTED.",
            "Samples lacking proven selection telemetry are quarantined as ambiguous_missing_metadata.",
        ],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    summary = run_audit(root=Path(args.root), output_dir=Path(args.output))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
