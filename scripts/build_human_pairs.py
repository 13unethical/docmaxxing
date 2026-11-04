#!/usr/bin/env python3
"""Human conclusion targets for the humanizer (services/humanizer_training/human_pairs.py).

    python3 scripts/build_human_pairs.py collect --count 6000          # Europe PMC, free
    python3 scripts/build_human_pairs.py rewrite --budget-usd 8         # AI rewrites (paid APIs)
    python3 scripts/build_human_pairs.py export data/humanizer_training/human_pairs/sft

``collect`` appends to human_conclusions.jsonl, ``rewrite`` to conclusions.jsonl; both skip what
is already there, so runs can be repeated to resume.
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

from services.humanizer_training import human_pairs as hp  # noqa: E402

HUMAN = hp.DEFAULT_OUT.parent / "human_conclusions.jsonl"


def collect(count: int, workers: int) -> None:
    import requests

    session = requests.Session()

    def get(url, **kw):
        return session.get(url, timeout=60, **kw)

    done = {r["pmcid"] for r in hp.read_jsonl(HUMAN)}
    HUMAN.parent.mkdir(parents=True, exist_ok=True)
    lock, stats = threading.Lock(), Counter()

    def one(rec):
        try:
            res = get(hp.FULLTEXT_URL.format(pmcid=rec["pmcid"]))
            text = hp.usable_conclusion(hp.conclusion_paragraphs(res.text)) if res.ok else None
        except Exception:  # noqa: BLE001
            text = None
        with lock:
            stats["ok" if text else "skipped"] += 1
            if text:
                with HUMAN.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({**rec, "human": text, "split": hp.split_of(rec["pmcid"])}) + "\n")
            if sum(stats.values()) % 500 == 0:
                print(dict(stats), flush=True)

    todo = [r for r in hp.search(count * 4, get=get) if r["pmcid"] not in done]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for start in range(0, len(todo), 200):
            if stats["ok"] >= count:
                break
            list(ex.map(one, todo[start:start + 200]))
    print(json.dumps(dict(stats)))


def rewrite(budget: float, mix_raw: str, workers: int) -> None:
    from services.humanizer_training.teacher.documents.source_pool import _reply_fn_for, parse_source_mix, pick_writer

    mix = parse_source_mix(mix_raw)
    done = {r["pmcid"] for r in hp.read_jsonl(hp.DEFAULT_OUT)}
    todo = [r for r in hp.read_jsonl(HUMAN) if r["pmcid"] not in done]
    lock, spent, stats = threading.Lock(), [0.0], Counter()

    def one(rec):
        with lock:
            if spent[0] >= budget:
                stats["skipped_budget"] += 1
                return
        provider, model = pick_writer(rec["pmcid"], mix)
        raw, diag = _reply_fn_for(provider)(
            system_prompt="You are a helpful assistant.", content=hp.ai_prompt(rec["human"]),
            temperature=0.7, model=model, timeout_s=120, max_tokens=4000,
        )
        ai = (raw or "").strip()
        problem = hp.ai_problem(rec["human"], ai)
        with lock:
            spent[0] += float(diag.get("cost_usd") or 0.0)
            stats[problem or "ok"] += 1
            if not problem:
                with hp.DEFAULT_OUT.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({**rec, "ai": ai, "writer": f"{provider}:{model}"}) + "\n")
            if stats["ok"] and stats["ok"] % 200 == 0:
                print(f"ok={stats['ok']} spent=${spent[0]:.2f}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, todo))
    print(json.dumps({"spent_usd": round(spent[0], 2), **stats}))


def export(out_dir: Path, level: int) -> None:
    pairs = hp.read_jsonl(hp.DEFAULT_OUT)
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    files = {s: (out_dir / f"{s}.jsonl").open("w", encoding="utf-8") for s in ("train", "test")}
    with (out_dir / "examples_meta.jsonl").open("w", encoding="utf-8") as meta:
        for p in pairs:
            files[p["split"]].write(json.dumps(hp.sft_example(p, level), ensure_ascii=False) + "\n")
            meta.write(json.dumps({k: p[k] for k in ("pmcid", "license", "journal", "year", "writer", "split")}) + "\n")
            counts[p["split"]] += 1
    for fh in files.values():
        fh.close()
    print(json.dumps(dict(counts)))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=("collect", "rewrite", "export"))
    p.add_argument("out_dir", nargs="?", type=Path)
    p.add_argument("--count", type=int, default=6000)
    p.add_argument("--budget-usd", type=float, default=0.0)
    p.add_argument("--writers", default=hp.DEFAULT_WRITER_MIX)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--level", type=int, default=10)
    a = p.parse_args()
    if a.action == "collect":
        collect(a.count, a.workers)
    elif a.action == "rewrite":
        if a.budget_usd <= 0:
            p.error("--budget-usd is required")
        rewrite(a.budget_usd, a.writers, a.workers)
    else:
        export(a.out_dir or hp.DEFAULT_OUT.parent / "sft", a.level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
