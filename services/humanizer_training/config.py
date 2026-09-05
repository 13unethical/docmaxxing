"""Configuration and data models for offline humanizer dataset builds."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ALLOWED_SOURCE_TYPES = frozenset({"synthetic", "public", "opted_in"})

# Real-user dataset surfaces (humanizer_dataset_logs.source). Workspace is banned.
REAL_USER_ALLOWED_SURFACES = frozenset({"standalone", "assignment"})
BLOCKED_TRAINING_SURFACES = frozenset({"workspace_partial"})


@dataclass(slots=True)
class DatasetBuildConfig:
    """Offline dataset build settings."""

    input_path: Path | None = None
    output_dir: Path = Path("data/humanizer_training")
    min_words: int = 8
    max_words: int = 5_000
    train_ratio: float = 0.8
    validation_ratio: float = 0.1
    test_ratio: float = 0.1
    dataset_version: str = "humanizer-offline-v1"
    seed: int = 17
    include_database: bool = True


@dataclass(slots=True)
class RawExample:
    """Unprocessed row loaded from DB or synthetic/public JSON input."""

    source_text: str
    target_text: str
    source_type: str
    language: str = "en"
    domain: str = "academic"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrainingExample:
    """Canonical training row for filtering/dedup/split/export."""

    source_text: str
    target_text: str
    source_type: str
    language: str
    domain: str
    word_count_source: int
    word_count_target: int
    quality_flags: list[str]
    dedupe_key: str
    source_hash: str
    source_group: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        return {
            "source_text": self.source_text,
            "target_text": self.target_text,
            "source_type": self.source_type,
            "language": self.language,
            "domain": self.domain,
            "word_count_source": self.word_count_source,
            "word_count_target": self.word_count_target,
            "quality_flags": list(self.quality_flags),
            "dedupe_key": self.dedupe_key,
        }

