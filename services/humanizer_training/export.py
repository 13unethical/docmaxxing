"""Export JSONL shards and build manifest."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.humanizer_training.config import DatasetBuildConfig, TrainingExample


def write_dataset(
    *,
    splits: dict[str, list[TrainingExample]],
    config: DatasetBuildConfig,
    accepted_count: int,
    rejected_count: int,
    rejection_reasons: Counter[str],
    dedupe_stats: dict[str, int],
) -> dict[str, Any]:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "train": output_dir / "train.jsonl",
        "validation": output_dir / "validation.jsonl",
        "test": output_dir / "test.jsonl",
    }
    for split_name, path in files.items():
        _write_jsonl(path, splits.get(split_name) or [])

    source_counts: Counter[str] = Counter()
    for split_items in splits.values():
        for item in split_items:
            source_counts[item.source_type] += 1

    dataset_hash = _combined_dataset_hash(list(files.values()))
    manifest = {
        "dataset_version": config.dataset_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_counts": dict(sorted(source_counts.items())),
        "accepted_count": int(accepted_count),
        "rejected_count": int(rejected_count),
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
        "dedupe": {
            "dropped_exact_pair": int(dedupe_stats.get("dropped_exact_pair", 0)),
            "dropped_same_source": int(dedupe_stats.get("dropped_same_source", 0)),
            "dropped_near_source": int(dedupe_stats.get("dropped_near_source", 0)),
        },
        "train_count": len(splits.get("train") or []),
        "validation_count": len(splits.get("validation") or []),
        "test_count": len(splits.get("test") or []),
        "dataset_sha256": dataset_hash,
        "files": {name: str(path) for name, path in files.items()},
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _write_jsonl(path: Path, rows: list[TrainingExample]) -> None:
    payload = "\n".join(
        json.dumps(item.as_record(), ensure_ascii=False, sort_keys=True)
        for item in rows
    )
    if payload:
        payload += "\n"
    path.write_text(payload, encoding="utf-8")


def _combined_dataset_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\n")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()

