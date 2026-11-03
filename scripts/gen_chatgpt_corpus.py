#!/usr/bin/env python3
"""Generate ChatGPT-written student texts (paid OpenAI API) and export detector rows.

    python3 scripts/gen_chatgpt_corpus.py --count 1500 --budget-usd 30
    python3 scripts/gen_chatgpt_corpus.py --export-detector data/detector_corpus/chatgpt_v1.jsonl

Appends to ``data/detector_corpus/chatgpt.jsonl`` and skips briefs already generated, so a run
can be repeated with the same seed to resume. Stops submitting new requests once the spend of
this run reaches ``--budget-usd``. Needs OPENAI_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.humanizer_training.chatgpt_corpus import (  # noqa: E402
    DEFAULT_MODEL_MIX,
    DEFAULT_OUT,
    detector_rows,
    generate_one,
    make_briefs,
    parse_model_mix,
    read_docs,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--count", type=int, default=0, help="Briefs to plan (already generated ones are skipped)")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--models", default=DEFAULT_MODEL_MIX)
    p.add_argument("--budget-usd", type=float, default=0.0, help="Required with --count")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--export-detector", type=Path, default=None, help="Write detector window rows here")
    p.add_argument("--dry-run", action="store_true", help="Print planned prompts only")
    args = p.parse_args()

    if args.count:
        briefs = make_briefs(args.count, seed=args.seed, model_mix=parse_model_mix(args.models))
        done = {d["id"] for d in read_docs(args.out)}
        todo = [b for b in briefs if b.brief_id not in done]
        if args.dry_run:
            for b in todo[:20]:
                print(f"{b.model:12} {b.split:5} {b.prompt}")
            print(json.dumps({"planned": len(briefs), "todo": len(todo), "models": Counter(b.model for b in todo)}))
            return 0
        if args.budget_usd <= 0:
            p.error("--budget-usd is required for a paid run")
        from services.openai_client import generate_text

        args.out.parent.mkdir(parents=True, exist_ok=True)
        lock = threading.Lock()
        spent = [0.0]
        stats: Counter[str] = Counter()

        def run(brief):
            with lock:
                if spent[0] >= args.budget_usd:
                    stats["skipped_budget"] += 1
                    return
            doc, diag = generate_one(brief, generate_text)
            with lock:
                spent[0] += float(diag.get("cost_usd") or 0.0)
                if doc is None:
                    stats["failed"] += 1
                    stats[f"failed:{(diag.get('error_message') or diag.get('finish_reason') or '?')[:60]}"] += 1
                    return
                stats["ok"] += 1
                with args.out.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
                if stats["ok"] % 50 == 0:
                    print(f"ok={stats['ok']} spent=${spent[0]:.2f}", flush=True)

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            list(ex.map(run, todo))
        print(json.dumps({"spent_usd": round(spent[0], 2), **stats}, indent=2))

    if args.export_detector:
        docs = read_docs(args.out)
        rows = detector_rows(docs)
        args.export_detector.parent.mkdir(parents=True, exist_ok=True)
        with args.export_detector.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(json.dumps({"docs": len(docs), "rows": len(rows), "test_rows": sum(r["split"] == "test" for r in rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
