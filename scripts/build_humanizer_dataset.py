#!/usr/bin/env python3
"""Build offline humanizer training dataset from eligible sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.humanizer_training import DatasetBuildConfig, build_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build offline humanizer dataset JSONL shards")
    parser.add_argument("--input", type=str, default=None, help="Path to JSON/JSONL file or directory")
    parser.add_argument(
        "--output",
        type=str,
        default="data/humanizer_training",
        help="Output directory for train/validation/test JSONL",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=8,
        help="Minimum words required in target text to accept example",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=5000,
        help="Maximum words allowed for source/target text",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = DatasetBuildConfig(
        input_path=Path(args.input).resolve() if args.input else None,
        output_dir=Path(args.output).resolve(),
        min_words=max(1, int(args.min_words)),
        max_words=max(10, int(args.max_words)),
    )
    manifest = build_dataset(cfg)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

