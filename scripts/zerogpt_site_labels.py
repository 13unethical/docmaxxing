#!/usr/bin/env python3
"""Label humanizer training candidates on the free ZeroGPT website (Playwright worker).

Typical flow on the VPS (same machine as StealthWriter teacher chrome)::

    /root/docmaxxing/venv/bin/playwright install chromium
    /root/docmaxxing/venv/bin/python scripts/zerogpt_site_labels.py \\
        --candidates data/zerogpt_dpo_run1/candidates.jsonl \\
        --out-dir data/zerogpt_site_dpo \\
        --resume --build-pairs

Input rows: ``candidates.jsonl`` from ``collect_zerogpt_dpo_run.py`` or any JSONL with a ``text`` field.
Sources for *new* candidates can be pulled from humanizer SFT shards (--sft, same as collect script).

This worker is for **offline training only** — it does not touch production humanize routes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from humanizer_student.dpo import build_pairs, split_by_essay  # noqa: E402
from scripts.collect_zerogpt_dpo_run import load_sources, sample_candidates  # noqa: E402
from services.humanizer_training.judge.zerogpt_site import (  # noqa: E402
    ZeroGPTSiteConfig,
    ZeroGPTSiteJudge,
    run_detect_loop,
)


def _load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _row_key(row: dict) -> str:
    for k in ("request_id", "label_id"):
        if row.get(k):
            return str(row[k])
    text = (row.get("text") or "")[:120]
    src = (row.get("source") or "")[:80]
    return f"{row.get('essay','')}:{row.get('candidate_i','')}:{hash(text)}:{hash(src)}"


def _load_done_keys(path: Path) -> set[str]:
    return {_row_key(r) for r in _load_jsonl(path)}


def _user_assistant_from_sft(path: Path, *, limit: int) -> list[dict]:
    """Assistant outputs from chat SFT (what we trained on) — useful baseline negatives."""
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        msgs = row.get("messages") or []
        user = next((m["content"] for m in msgs if m.get("role") == "user"), None)
        asst = next((m["content"] for m in msgs if m.get("role") == "assistant"), None)
        if not user or not asst:
            continue
        rows.append(
            {
                "essay": f"sft:{path.stem}:{abs(hash(user)) % 10_000_000}",
                "source": user.strip(),
                "text": asst.strip(),
                "candidate_i": 0,
                "origin": str(path),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidates", type=Path, help="JSONL with model rewrites to score")
    p.add_argument("--out-dir", type=Path, default=ROOT / "data" / "zerogpt_site_dpo")
    p.add_argument("--limit", type=int, default=0, help="max rows this run (0 = all pending)")
    p.add_argument("--resume", action="store_true", help="skip keys already in labeled_site.jsonl")
    p.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--sleep-on-error", type=float, default=5.0)
    p.add_argument("--build-pairs", action="store_true", help="write pairs_train/val from all labeled rows")
    p.add_argument("--chosen-max", type=float, default=0.15, help="DPO chosen ai_frac ceiling (site judge)")
    p.add_argument("--rejected-min", type=float, default=0.35, help="DPO rejected ai_frac floor")
    p.add_argument("--pair-seed", type=int, default=21)
    # Optional: fresh candidates from SFT + Modal (same as collect_zerogpt_dpo_run.py)
    p.add_argument("--gen-sources", type=int, default=0, help="if >0, sample this many SFT sources via student API")
    p.add_argument("--gen-candidates", type=int, default=4)
    p.add_argument(
        "--sft",
        nargs="*",
        default=[
            "data/humanizer_training/v4_tt_sft/train.jsonl",
            "data/humanizer_training/v4_tt_sft/val.jsonl",
            "data/humanizer_training/legacy51_sft/train.jsonl",
            "data/humanizer_training/human_pairs/sft/train.jsonl",
        ],
    )
    p.add_argument("--sft-assistant", type=int, default=0, help="label assistant turns from --sft (no Modal)")
    args = p.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    labeled_path = out_dir / "labeled_site.jsonl"

    pending: list[dict] = []
    if args.candidates:
        pending.extend(_load_jsonl(args.candidates))
    if args.sft_assistant > 0:
        for rel in args.sft:
            path = ROOT / rel
            if path.is_file():
                pending.extend(_user_assistant_from_sft(path, limit=args.sft_assistant))

    if args.gen_sources > 0:
        import os

        from scripts.collect_zerogpt_dpo_run import _load_dotenv

        _load_dotenv(ROOT / ".env")
        url = (os.environ.get("HUMANIZER_STUDENT_URL") or "").strip().rstrip("/")
        key = (os.environ.get("HUMANIZER_STUDENT_KEY") or "").strip()
        model = (os.environ.get("HUMANIZER_STUDENT_MODEL") or "humanizer-v4tt").strip()
        if not url or not key:
            print("HUMANIZER_STUDENT_URL and HUMANIZER_STUDENT_KEY required for --gen-sources", file=sys.stderr)
            return 2
        paths = [ROOT / rel for rel in args.sft]
        sources = load_sources(paths, limit=args.gen_sources, seed=args.pair_seed)
        generated = sample_candidates(
            sources,
            url=url,
            api_key=key,
            model=model,
            n=max(1, args.gen_candidates),
            temperature=1.2,
            level=8,
            timeout=180.0,
        )
        gen_path = out_dir / "candidates.jsonl"
        with gen_path.open("a", encoding="utf-8") as fh:
            for row in generated:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        pending.extend(generated)

    if not pending:
        print("no input rows", file=sys.stderr)
        return 1

    done: set[str] = _load_done_keys(labeled_path) if args.resume else set()
    queue = [r for r in pending if _row_key(r) not in done]
    if args.limit > 0:
        queue = queue[: args.limit]

    print(
        json.dumps(
            {
                "pending": len(queue),
                "skipped_done": len(pending) - len(queue),
                "out_dir": str(out_dir),
            }
        ),
        flush=True,
    )
    if not queue:
        print("nothing to label", flush=True)
    else:
        cfg = ZeroGPTSiteConfig()
        if args.headless is not None:
            cfg.headless = args.headless

        def _on_result(row: dict) -> None:
            row.setdefault("ts", datetime.now(timezone.utc).replace(microsecond=0).isoformat())
            row.setdefault("label_id", _row_key(row))
            _append_jsonl(labeled_path, row)

        with ZeroGPTSiteJudge(cfg) as judge:
            labeled, summary = run_detect_loop(
                queue,
                judge=judge,
                on_result=_on_result,
                sleep_on_error=args.sleep_on_error,
            )
        summary["out_dir"] = str(out_dir)
        (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2), flush=True)

    if args.build_pairs:
        import humanizer_student.dpo as dpo_mod

        all_labeled = _load_jsonl(labeled_path)
        if not all_labeled:
            print("no labeled rows for pairs", file=sys.stderr)
            return 1
        old_chosen, old_rej = dpo_mod.CHOSEN_MAX_FRAC, dpo_mod.REJECTED_MIN_FRAC
        dpo_mod.CHOSEN_MAX_FRAC = args.chosen_max
        dpo_mod.REJECTED_MIN_FRAC = args.rejected_min
        try:
            pairs = build_pairs(all_labeled, max_per_source=4, seed=args.pair_seed)
        finally:
            dpo_mod.CHOSEN_MAX_FRAC, dpo_mod.REJECTED_MIN_FRAC = old_chosen, old_rej
        train, val = split_by_essay(pairs, val_share=0.12)
        for name, rows in (("pairs_train.jsonl", train), ("pairs_val.jsonl", val)):
            with (out_dir / name).open("w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        full = {
            "labeled": len(all_labeled),
            "pairs": len(pairs),
            "pairs_train": len(train),
            "pairs_val": len(val),
            "chosen_max": args.chosen_max,
            "rejected_min": args.rejected_min,
        }
        (out_dir / "summary.json").write_text(json.dumps(full, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(full, indent=2), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())