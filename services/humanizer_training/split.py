"""Leak-safe dataset splitting by source group."""

from __future__ import annotations

import random
from collections import defaultdict

from services.humanizer_training.config import DatasetBuildConfig, TrainingExample


def split_by_source_group(
    examples: list[TrainingExample],
    *,
    config: DatasetBuildConfig,
) -> dict[str, list[TrainingExample]]:
    groups: dict[str, list[TrainingExample]] = defaultdict(list)
    for item in examples:
        groups[item.source_group].append(item)

    keys = list(groups.keys())
    rng = random.Random(config.seed)
    rng.shuffle(keys)

    total = len(examples)
    train_target = int(round(total * config.train_ratio))
    validation_target = int(round(total * config.validation_ratio))
    test_target = max(0, total - train_target - validation_target)

    splits = {"train": [], "validation": [], "test": []}
    targets = {"train": train_target, "validation": validation_target, "test": test_target}

    for key in keys:
        batch = groups[key]
        name = _best_split_name(splits, targets)
        splits[name].extend(batch)

    # Stable deterministic export order.
    for split_name in splits:
        splits[split_name] = sorted(splits[split_name], key=lambda ex: ex.dedupe_key)
    return splits


def _best_split_name(
    splits: dict[str, list[TrainingExample]],
    targets: dict[str, int],
) -> str:
    # Fill deficits first; if all exceeded, fall back to the smallest bucket.
    deficits = {
        name: targets[name] - len(splits[name])
        for name in ("train", "validation", "test")
    }
    positive = [name for name, deficit in deficits.items() if deficit > 0]
    if positive:
        return sorted(positive, key=lambda name: deficits[name], reverse=True)[0]
    return min(("train", "validation", "test"), key=lambda name: len(splits[name]))

