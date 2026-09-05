"""Build chat-SFT shards from Legacy-5.1 eligible teacher pairs (offline, no browser).

Preserves teacher target text byte-for-byte from raw records (no clean_text_for_ml).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.humanizer_engine.heading_utils import split_off_references
from services.humanizer_training.config import DatasetBuildConfig, TrainingExample
from services.humanizer_training.dedupe import (
    make_pair_hash,
    make_source_group_key,
    make_source_hash,
)
from services.humanizer_training.filters import evaluate_example
from services.humanizer_training.split import split_by_source_group
from services.humanizer_training.teacher_eligibility import evaluate_teacher_sample
from services.humanizer_training.real_user_export import (
    assert_safe_for_legacy51_sft,
    is_blocked_training_surface,
)

_HEADING_RE = re.compile(r"(?m)^##\s+.+$")

DEFAULT_SEED = 51
DEFAULT_INDEX = Path("data/humanizer_training/legacy51_clean/eligible_pairs_index.jsonl")
DEFAULT_ROOT = Path("data/humanizer_training")
DEFAULT_OUT = Path("data/humanizer_training/legacy51_sft")


@dataclass(slots=True)
class SoftFlagRecord:
    sample_id: str
    flags: list[str]
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BuildStats:
    total_eligible: int = 0
    hard_rejected: int = 0
    soft_flagged: int = 0
    final_usable: int = 0
    duplicate_count: int = 0
    rejection_reasons: Counter[str] = field(default_factory=Counter)
    soft_flag_counts: Counter[str] = field(default_factory=Counter)


def build_legacy51_sft(
    *,
    pairs_index: Path = DEFAULT_INDEX,
    data_root: Path = DEFAULT_ROOT,
    output_dir: Path = DEFAULT_OUT,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    index_rows = _read_jsonl(pairs_index)
    stats = BuildStats(total_eligible=len(index_rows))

    candidates: list[TrainingExample] = []
    soft_records: list[SoftFlagRecord] = []
    sidecar_rows: list[dict[str, Any]] = []
    seen_pair: set[str] = set()
    seen_source: set[str] = set()
    target_fingerprints: dict[str, str] = {}

    for pointer in index_rows:
        sample_id = str(pointer.get("sample_id") or "")
        try:
            record = _load_raw_record(data_root, pointer)
        except Exception as exc:  # noqa: BLE001
            stats.hard_rejected += 1
            stats.rejection_reasons["CORRUPTED_UNREADABLE"] += 1
            sidecar_rows.append(
                {
                    "sample_id": sample_id,
                    "status": "hard_rejected",
                    "hard_reject_reasons": ["CORRUPTED_UNREADABLE", str(exc)[:200]],
                }
            )
            continue

        # Fail-closed: never ingest Workspace / unmarked real-user rows into Legacy51 SFT.
        surface_probe = {
            "source_surface": record.get("source_surface")
            or record.get("origin_source")
            or pointer.get("source_surface")
            or pointer.get("origin_source")
            or record.get("source"),
            "legacy51_sft_eligible": record.get("legacy51_sft_eligible")
            or pointer.get("legacy51_sft_eligible"),
        }
        if is_blocked_training_surface(str(surface_probe.get("source_surface") or "")) or (
            str(surface_probe.get("source_surface") or "").strip().lower()
            in {"standalone", "assignment"}
            and not assert_safe_for_legacy51_sft(surface_probe)
        ):
            stats.hard_rejected += 1
            stats.rejection_reasons["REAL_USER_OR_WORKSPACE_BLOCKED"] += 1
            sidecar_rows.append(
                {
                    "sample_id": sample_id or record.get("document_id"),
                    "status": "hard_rejected",
                    "hard_reject_reasons": ["REAL_USER_OR_WORKSPACE_BLOCKED"],
                    "source_path": pointer.get("source_path"),
                }
            )
            continue

        hard_reasons = _hard_reject_reasons(record, pointer)
        if hard_reasons:
            stats.hard_rejected += 1
            stats.rejection_reasons.update(hard_reasons)
            sidecar_rows.append(
                {
                    "sample_id": sample_id or record.get("document_id"),
                    "status": "hard_rejected",
                    "hard_reject_reasons": hard_reasons,
                    "source_path": pointer.get("source_path"),
                    "line_no": pointer.get("line_no"),
                }
            )
            continue

        source = record["source_text"]
        target = record["teacher_text"]
        # Identity check: target must remain exactly as stored in raw JSON.
        target_fingerprints[sample_id] = _sha_preview(target)

        pair_key = make_pair_hash(source, target)
        source_key = make_source_hash(source)
        if pair_key in seen_pair:
            stats.hard_rejected += 1
            stats.duplicate_count += 1
            stats.rejection_reasons["DUPLICATE_PAIR"] += 1
            sidecar_rows.append(
                {
                    "sample_id": sample_id,
                    "status": "hard_rejected",
                    "hard_reject_reasons": ["DUPLICATE_PAIR"],
                }
            )
            continue
        if source_key in seen_source:
            stats.hard_rejected += 1
            stats.duplicate_count += 1
            stats.rejection_reasons["DUPLICATE_SOURCE"] += 1
            sidecar_rows.append(
                {
                    "sample_id": sample_id,
                    "status": "hard_rejected",
                    "hard_reject_reasons": ["DUPLICATE_SOURCE"],
                }
            )
            continue

        seen_pair.add(pair_key)
        seen_source.add(source_key)

        soft_flags, soft_notes = _soft_flags(source, target, record)
        if soft_flags:
            stats.soft_flagged += 1
            stats.soft_flag_counts.update(soft_flags)
            soft_records.append(SoftFlagRecord(sample_id=sample_id, flags=soft_flags, reasons=soft_notes))

        src_wc = _word_count(source)
        tgt_wc = _word_count(target)
        ratio = (tgt_wc / float(src_wc)) if src_wc else None
        heading_status = _heading_preservation(source, target)
        refs_status = _references_preservation(source, target)
        meta = record.get("teacher_meta") or {}

        metadata = {
            "sample_id": sample_id,
            "teacher_model": meta.get("verified_model") or record.get("teacher_model"),
            "ui_model_label": meta.get("ui_model_label"),
            "teacher_level": meta.get("verified_level")
            if meta.get("verified_level") is not None
            else record.get("teacher_level"),
            "provider": record.get("teacher_provider"),
            "selection_verified": meta.get("selection_verified"),
            "result_stage": meta.get("last_successful_stage"),
            "source_word_count": src_wc,
            "target_word_count": tgt_wc,
            "ratio": round(ratio, 6) if ratio is not None else None,
            "heading_preservation": heading_status,
            "references_preservation": refs_status,
            "quality_flags": soft_flags,
            "quality_flag_notes": soft_notes,
            "source_path": pointer.get("source_path"),
            "line_no": pointer.get("line_no"),
            "run_dir": pointer.get("run_dir"),
            "domain": record.get("domain"),
            "document_type": record.get("document_type"),
            "raw_quality_flags": list(record.get("quality_flags") or []),
            "target_sha256_prefix": target_fingerprints[sample_id],
        }

        candidates.append(
            TrainingExample(
                source_text=source,
                target_text=target,
                source_type="opted_in",
                language=str(record.get("language") or "en"),
                domain=str(record.get("domain") or "academic"),
                word_count_source=src_wc,
                word_count_target=tgt_wc,
                quality_flags=list(soft_flags),
                dedupe_key=pair_key,
                source_hash=source_key,
                source_group=make_source_group_key(source),
                metadata=metadata,
            )
        )
        sidecar_rows.append({"sample_id": sample_id, "status": "accepted", **metadata})

    stats.final_usable = len(candidates)
    split_cfg = DatasetBuildConfig(
        output_dir=output_dir,
        train_ratio=0.8,
        validation_ratio=0.1,
        test_ratio=0.1,
        seed=int(seed),
        dataset_version="legacy51-sft-v1",
        include_database=False,
    )
    splits = split_by_source_group(candidates, config=split_cfg)
    # Export as train/val/test (user-requested names).
    export_map = {
        "train": splits.get("train") or [],
        "val": splits.get("validation") or [],
        "test": splits.get("test") or [],
    }

    for name, rows in export_map.items():
        _write_messages_jsonl(output_dir / f"{name}.jsonl", rows)

    _write_jsonl(output_dir / "samples_metadata.jsonl", sidecar_rows)

    # Verify targets unchanged vs raw reload.
    unchanged = _verify_targets_unchanged(data_root, export_map, target_fingerprints)

    quality_report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": int(seed),
        "total_eligible": stats.total_eligible,
        "hard_rejected": stats.hard_rejected,
        "soft_flagged": stats.soft_flagged,
        "final_usable": stats.final_usable,
        "duplicate_count": stats.duplicate_count,
        "rejection_reasons": dict(sorted(stats.rejection_reasons.items())),
        "soft_flag_counts": dict(sorted(stats.soft_flag_counts.items())),
        "soft_flagged_samples": [
            {"sample_id": s.sample_id, "flags": s.flags, "notes": s.reasons} for s in soft_records
        ],
        "split_counts": {k: len(v) for k, v in export_map.items()},
        "targets_unchanged_verified": unchanged,
        "turnitin_reports_included": False,
        "notes": [
            "Targets are copied verbatim from raw teacher_text; no ML cleanup applied.",
            "Soft flags are retained in samples_metadata.jsonl; samples are not auto-dropped.",
            "Turnitin reports are not part of this SFT dataset.",
        ],
    }
    (output_dir / "quality_report.json").write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "dataset_version": "legacy51-sft-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "teacher_model": "Legacy 5.1",
        "ui_model_label": "Ghost 5.1 Legacy",
        "teacher_level": 8,
        "provider": "stealthwriter_training",
        "seed": int(seed),
        "split_ratios": {"train": 0.8, "val": 0.1, "test": 0.1},
        "source_index": str(pairs_index),
        "data_root": str(data_root),
        "total_eligible": stats.total_eligible,
        "hard_rejected": stats.hard_rejected,
        "soft_flagged": stats.soft_flagged,
        "final_usable": stats.final_usable,
        "duplicate_count": stats.duplicate_count,
        "train_count": len(export_map["train"]),
        "val_count": len(export_map["val"]),
        "test_count": len(export_map["test"]),
        "files": {
            "train": str(output_dir / "train.jsonl"),
            "val": str(output_dir / "val.jsonl"),
            "test": str(output_dir / "test.jsonl"),
            "samples_metadata": str(output_dir / "samples_metadata.jsonl"),
            "quality_report": str(output_dir / "quality_report.json"),
            "readme": str(output_dir / "README.md"),
        },
        "message_format": {
            "user": "source academic text",
            "assistant": "StealthWriter Legacy 5.1 level 8 teacher output (verbatim)",
        },
        "targets_unchanged_verified": unchanged,
        "turnitin_reports_included": False,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_readme(output_dir / "README.md", manifest, quality_report)
    return manifest


def _hard_reject_reasons(record: dict[str, Any], pointer: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    verdict = evaluate_teacher_sample(record)
    if not verdict.eligible:
        reasons.append("WRONG_OR_MISSING_TEACHER_METADATA")
        reasons.extend(f"META:{r}" for r in verdict.reasons)
    source = record.get("source_text")
    target = record.get("teacher_text")
    if not isinstance(source, str) or not source.strip():
        reasons.append("EMPTY_SOURCE")
    if not isinstance(target, str) or not target.strip():
        reasons.append("EMPTY_TARGET")
    if isinstance(source, str) and isinstance(target, str) and source.strip() and source.strip() == target.strip():
        reasons.append("IDENTICAL_OUTPUT")
    meta = record.get("teacher_meta") if isinstance(record.get("teacher_meta"), dict) else {}
    if meta.get("last_successful_stage") != "RESULT_EXTRACTED":
        reasons.append("FAILED_RESULT_EXTRACTED")
    # Pointer/sample identity sanity
    if pointer.get("sample_id") and record.get("document_id") and pointer["sample_id"] != record["document_id"]:
        reasons.append("SAMPLE_ID_MISMATCH")
    return sorted(set(reasons))


def _soft_flags(source: str, target: str, record: dict[str, Any]) -> tuple[list[str], list[str]]:
    flags: list[str] = []
    notes: list[str] = []
    # Reuse marker soft flags from evaluate_example; ignore its hard rejects for this path.
    verdict = evaluate_example(source, target, min_words=1, max_words=100_000)
    for flag in verdict.quality_flags:
        flags.append(flag)
        notes.append(f"filter:{flag}")
    for raw_flag in record.get("quality_flags") or []:
        if isinstance(raw_flag, str) and raw_flag not in flags:
            flags.append(raw_flag)
            notes.append(f"raw:{raw_flag}")

    src_wc = _word_count(source)
    tgt_wc = _word_count(target)
    if src_wc > 0:
        ratio = tgt_wc / float(src_wc)
        if ratio < 0.8 or ratio > 1.6:
            flags.append("UNUSUAL_RATIO")
            notes.append(f"ratio={ratio:.4f}")

    heading = _heading_preservation(source, target)
    if heading == "mismatch":
        if "HEADING_MISMATCH" not in flags:
            flags.append("HEADING_MISMATCH")
            notes.append("heading_lines_not_exact")
    refs = _references_preservation(source, target)
    if refs == "changed":
        flags.append("REFERENCES_CHANGED")
        notes.append("references_block_changed")

    return sorted(set(flags)), notes


def _heading_preservation(source: str, target: str) -> str:
    src = [m.group(0).strip() for m in _HEADING_RE.finditer(source or "")]
    tgt = [m.group(0).strip() for m in _HEADING_RE.finditer(target or "")]
    if not src:
        return "no_headings"
    if src == tgt:
        return "exact"
    return "mismatch"


def _references_preservation(source: str, target: str) -> str:
    _, refs_s = split_off_references(source or "")
    _, refs_t = split_off_references(target or "")
    if not refs_s.strip():
        return "no_references"
    if " ".join(refs_s.lower().split()) == " ".join(refs_t.lower().split()):
        return "unchanged"
    return "changed"


def _load_raw_record(data_root: Path, pointer: dict[str, Any]) -> dict[str, Any]:
    rel = str(pointer.get("source_path") or "")
    line_no = int(pointer.get("line_no") or 0)
    path = data_root / rel
    if not path.is_file():
        raise FileNotFoundError(f"missing source_path={rel}")
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh, start=1):
            if i == line_no:
                if not line.strip():
                    raise ValueError("empty line")
                return json.loads(line)
    raise IndexError(f"line_no {line_no} out of range for {rel}")


def _verify_targets_unchanged(
    data_root: Path,
    export_map: dict[str, list[TrainingExample]],
    fingerprints: dict[str, str],
) -> bool:
    for rows in export_map.values():
        for ex in rows:
            sample_id = str((ex.metadata or {}).get("sample_id") or "")
            source_path = (ex.metadata or {}).get("source_path")
            line_no = (ex.metadata or {}).get("line_no")
            if not sample_id or not source_path or not line_no:
                return False
            raw = _load_raw_record(data_root, {"source_path": source_path, "line_no": line_no})
            if raw.get("teacher_text") != ex.target_text:
                return False
            if _sha_preview(ex.target_text) != fingerprints.get(sample_id):
                return False
    return True


def _write_messages_jsonl(path: Path, rows: list[TrainingExample]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for ex in rows:
            payload = {
                "messages": [
                    {"role": "user", "content": ex.source_text},
                    {"role": "assistant", "content": ex.target_text},
                ]
            }
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_readme(path: Path, manifest: dict[str, Any], quality: dict[str, Any]) -> None:
    text = f"""# Legacy 5.1 SFT dataset

## Provenance
- Eligible index: `{manifest["source_index"]}`
- Raw teacher roots under: `{manifest["data_root"]}`
- Provider: `{manifest["provider"]}`
- Teacher model (canonical): `{manifest["teacher_model"]}`
- UI model label: `{manifest["ui_model_label"]}`
- Teacher level: `{manifest["teacher_level"]}`

## Counts
- Original eligible samples: **{manifest["total_eligible"]}**
- Hard-filter rejected: **{manifest["hard_rejected"]}**
- Soft-flagged (kept): **{manifest["soft_flagged"]}**
- Final usable: **{manifest["final_usable"]}**
- Train / val / test: **{manifest["train_count"]} / {manifest["val_count"]} / {manifest["test_count"]}**
- Duplicate hard rejects: **{manifest["duplicate_count"]}**

## Reproducibility
- Seed: `{manifest["seed"]}`
- Split ratios: train 0.8 / val 0.1 / test 0.1
- Split is by source-group to prevent the same source leaking across splits

## Record format
Each line in `train.jsonl` / `val.jsonl` / `test.jsonl`:

```json
{{
  "messages": [
    {{"role": "user", "content": "<source academic text>"}},
    {{"role": "assistant", "content": "<StealthWriter Legacy 5.1 level 8 output>"}}
  ]
}}
```

- **source** = original academic document text (`source_text` from teacher records)
- **target** = real StealthWriter teacher output (`teacher_text`), copied **verbatim**
- Teacher metadata lives in `samples_metadata.jsonl` and `manifest.json` (not inside message content)

## Soft flags
Soft-flagged samples remain in the dataset; reasons are stored in metadata / `quality_report.json`.
Soft flag counts: `{json.dumps(quality.get("soft_flag_counts") or {}, ensure_ascii=False)}`

## Exclusions
- Turnitin reports are **not** included in this SFT dataset
- Quarantined / mock / unverified teacher runs are **not** included
- Targets are not rewritten, re-humanized, or ML-cleaned

## Files
- `train.jsonl`, `val.jsonl`, `test.jsonl`
- `manifest.json`
- `quality_report.json`
- `samples_metadata.jsonl`
- `README.md`
"""
    path.write_text(text, encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _word_count(text: str) -> int:
    return len([p for p in (text or "").split() if p.strip()])


def _sha_preview(text: str) -> str:
    import hashlib

    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]
