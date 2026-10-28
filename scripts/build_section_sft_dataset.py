#!/usr/bin/env python3
"""Build the level-conditioned, section-level SFT dataset from collected teacher documents.

Offline: reads ``documents.jsonl`` from bulk and nightly collection runs, writes
``train/val/test.jsonl`` (chat messages) plus ``manifest.json`` to the output dir.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.humanizer_training.section_sft import (  # noqa: E402
    DEFAULT_INPUT_GLOBS,
    DEFAULT_OUT,
    build_section_sft,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Build section-level SFT dataset from teacher documents")
    p.add_argument("--root", type=Path, default=_ROOT)
    p.add_argument("--input-glob", action="append", default=None, help="Relative glob of documents.jsonl (repeatable)")
    p.add_argument("--out", type=Path, default=_ROOT / DEFAULT_OUT)
    args = p.parse_args()
    manifest = build_section_sft(
        root=args.root,
        input_globs=tuple(args.input_glob or DEFAULT_INPUT_GLOBS),
        output_dir=args.out,
    )
    manifest.pop("inputs", None)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
