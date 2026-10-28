#!/usr/bin/env python3
"""QLoRA fine-tune of the student humanizer on ``section_sft`` (CUDA GPU host only).

Setup: ``bash scripts/setup_student_gpu_host.sh``; data: ``scripts/build_section_sft_dataset.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_student.train import TrainConfig, train  # noqa: E402


def parse_config(argv: list[str] | None = None) -> TrainConfig:
    defaults = TrainConfig()
    p = argparse.ArgumentParser(description=__doc__)
    for f in fields(TrainConfig):
        if f.name == "lora_targets":
            continue
        flag = "--" + f.name.replace("_", "-")
        value = getattr(defaults, f.name)
        if isinstance(value, bool):
            p.add_argument(flag, action=argparse.BooleanOptionalAction, default=value)
        elif f.name == "limit":
            p.add_argument(flag, type=int, default=None, help="Only the first N rows per split (smoke run)")
        else:
            p.add_argument(flag, type=type(value), default=value)
    return TrainConfig(**vars(p.parse_args(argv)))


def main() -> int:
    summary = train(parse_config())
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
