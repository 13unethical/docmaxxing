#!/usr/bin/env python3
"""Export real-user humanizer pairs for training.

Surfaces: standalone + assignment only. Workspace is never exported.
Does not mix into Legacy 5.1 teacher SFT automatically.
Does not call Chrome / StealthWriter / Turnitin / production humanize APIs.

Incremental mode (``--incremental``) appends only new ``training_eligible=1``
rows since ``export_checkpoint.json`` and never duplicates ``records.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.humanizer_training.real_user_export import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    export_real_user_training_data,
    export_real_user_training_data_incremental,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export real-user humanizer training pairs"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output directory for records.jsonl / excluded.jsonl / checkpoint",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Append-only export of new training_eligible=1 rows since checkpoint",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only: do not write records/checkpoint (incremental mode)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max candidate rows to scan after checkpoint (incremental mode)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    if args.incremental:
        result = export_real_user_training_data_incremental(
            output_dir=output_dir,
            dry_run=bool(args.dry_run),
            limit=args.limit,
            require_reliable_consent=True,
        )
        print(
            json.dumps(
                {
                    "new_eligible_records": result.new_eligible_records,
                    "exported": result.exported,
                    "skipped": result.skipped,
                    "duplicates": result.duplicates,
                    "workspace_excluded": result.workspace_excluded,
                    "exported_standalone": result.exported_standalone,
                    "exported_assignment": result.exported_assignment,
                    "legacy51_sft_eligible_exported": result.legacy51_sft_eligible_exported,
                    "dry_run": result.dry_run,
                    "checkpoint_before": result.checkpoint_before,
                    "checkpoint_after": result.checkpoint_after,
                    "full": result.as_dict(),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1 if result.blocked else 0

    if args.dry_run or args.limit is not None:
        print(
            "error: --dry-run / --limit require --incremental",
            file=sys.stderr,
        )
        return 2

    result = export_real_user_training_data(
        output_dir=output_dir,
        require_reliable_consent=True,
    )
    print(json.dumps(result.manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
