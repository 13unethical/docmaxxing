"""Offline humanizer dataset pipeline."""

from __future__ import annotations

from collections import Counter
from typing import Any

from services.humanizer_training.cleaner import normalize_text
from services.humanizer_training.config import DatasetBuildConfig, TrainingExample
from services.humanizer_training.dedupe import (
    dedupe_examples,
    make_pair_hash,
    make_source_group_key,
    make_source_hash,
)
from services.humanizer_training.export import write_dataset
from services.humanizer_training.filters import evaluate_example
from services.humanizer_training.loader import load_raw_examples
from services.humanizer_training.split import split_by_source_group


def build_dataset(config: DatasetBuildConfig) -> dict[str, Any]:
    raw = load_raw_examples(config)
    rejection_reasons: Counter[str] = Counter()
    rejected_examples_count = 0
    cleaned_ok: list[TrainingExample] = []

    for row in raw:
        source = normalize_text(row.source_text)
        target = normalize_text(row.target_text)
        verdict = evaluate_example(
            source,
            target,
            min_words=config.min_words,
            max_words=config.max_words,
        )
        if not verdict.accepted:
            rejected_examples_count += 1
            rejection_reasons.update(verdict.reasons)
            continue
        source_hash = make_source_hash(source)
        cleaned_ok.append(
            TrainingExample(
                source_text=source,
                target_text=target,
                source_type=row.source_type,
                language=row.language or "en",
                domain=row.domain or "academic",
                word_count_source=_word_count(source),
                word_count_target=_word_count(target),
                quality_flags=verdict.quality_flags,
                dedupe_key=make_pair_hash(source, target),
                source_hash=source_hash,
                source_group=make_source_group_key(source),
                metadata=row.metadata,
            )
        )

    deduped = dedupe_examples(cleaned_ok)
    splits = split_by_source_group(deduped.accepted, config=config)

    manifest = write_dataset(
        splits=splits,
        config=config,
        accepted_count=len(deduped.accepted),
        rejected_count=rejected_examples_count,
        rejection_reasons=rejection_reasons,
        dedupe_stats={
            "dropped_exact_pair": deduped.dropped_exact_pair,
            "dropped_same_source": deduped.dropped_same_source,
            "dropped_near_source": deduped.dropped_near_source,
        },
    )
    return manifest


def _word_count(text: str) -> int:
    return len([p for p in (text or "").split() if p.strip()])

