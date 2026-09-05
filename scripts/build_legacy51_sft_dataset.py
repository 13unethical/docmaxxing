#!/usr/bin/env python3
"""Build Legacy 5.1 chat-SFT dataset from eligible teacher pairs (offline)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.humanizer_training.legacy51_sft import (
    DEFAULT_INDEX,
    DEFAULT_OUT,
    DEFAULT_ROOT,
    DEFAULT_SEED,
    build_legacy51_sft,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Legacy 5.1 SFT shards from eligible pairs")
    p.add_argument("--index", type=str, default=str(DEFAULT_INDEX))
    p.add_argument("--data-root", type=str, default=str(DEFAULT_ROOT))
    p.add_argument("--output", type=str, default=str(DEFAULT_OUT))
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_legacy51_sft(
        pairs_index=Path(args.index),
        data_root=Path(args.data_root),
        output_dir=Path(args.output),
        seed=int(args.seed),
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
