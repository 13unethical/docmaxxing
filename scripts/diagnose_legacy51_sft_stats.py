#!/usr/bin/env python3
"""Read-only length statistics for legacy51_sft (word-based token estimates).

Does not mutate the SFT dataset. Token counts are heuristic approximations
(words * 1.3 + chat-template overhead) until a tokenizer is installed.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


TOKENS_PER_WORD = 1.3
CHAT_OVERHEAD_TOKENS = 40


def _words(text: str) -> int:
    return len((text or "").split())


def _approx_tokens_from_words(word_count: int) -> int:
    return int(round(word_count * TOKENS_PER_WORD))


def _summarize(values: list[int | float]) -> dict:
    xs = sorted(values)
    n = len(xs)
    p90_idx = max(0, int(0.9 * n) - 1)
    return {
        "n": n,
        "avg": round(statistics.mean(xs), 1) if xs else None,
        "median": round(statistics.median(xs), 1) if xs else None,
        "p90": xs[p90_idx] if xs else None,
        "min": xs[0] if xs else None,
        "max": xs[-1] if xs else None,
    }


def _load_split(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        msgs = obj["messages"]
        src = msgs[0]["content"]
        tgt = msgs[1]["content"]
        sw = _words(src)
        tw = _words(tgt)
        seq_w = sw + tw
        rows.append(
            {
                "source_words": sw,
                "target_words": tw,
                "seq_words": seq_w,
                "source_chars": len(src),
                "target_chars": len(tgt),
                "approx_source_tokens": _approx_tokens_from_words(sw),
                "approx_target_tokens": _approx_tokens_from_words(tw),
                "approx_seq_tokens": _approx_tokens_from_words(seq_w) + CHAT_OVERHEAD_TOKENS,
                "approx_seq_tokens_chars_div4": int(round(len(src) / 4 + len(tgt) / 4))
                + CHAT_OVERHEAD_TOKENS,
            }
        )
    return rows


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    sft = repo / "data" / "humanizer_training" / "legacy51_sft"
    meta_path = sft / "samples_metadata.jsonl"
    meta = [json.loads(l) for l in meta_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    splits = {name: _load_split(sft / f"{name}.jsonl") for name in ("train", "val", "test")}
    all_rows = splits["train"] + splits["val"] + splits["test"]

    ratios = [float(m["ratio"]) for m in meta if m.get("ratio") is not None]
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_dir": str(sft.relative_to(repo)),
        "counts": {
            "total": len(meta),
            "train": len(splits["train"]),
            "val": len(splits["val"]),
            "test": len(splits["test"]),
        },
        "word_stats_from_metadata": {
            "source_words": _summarize([int(m["source_word_count"]) for m in meta]),
            "target_words": _summarize([int(m["target_word_count"]) for m in meta]),
            "ratio": _summarize(ratios) if ratios else None,
        },
        "split_approx_token_stats": {
            name: {
                "source_words": _summarize([r["source_words"] for r in rows]),
                "target_words": _summarize([r["target_words"] for r in rows]),
                "approx_seq_tokens_words_x1_3": _summarize([r["approx_seq_tokens"] for r in rows]),
                "approx_seq_tokens_chars_div4": _summarize(
                    [r["approx_seq_tokens_chars_div4"] for r in rows]
                ),
            }
            for name, rows in splits.items()
        },
        "all_approx_seq_tokens_words_x1_3": _summarize([r["approx_seq_tokens"] for r in all_rows]),
        "context_need": {
            "samples_approx_seq_gt_2048": sum(1 for r in all_rows if r["approx_seq_tokens"] > 2048),
            "samples_approx_seq_gt_4096": sum(1 for r in all_rows if r["approx_seq_tokens"] > 4096),
            "samples_approx_seq_gt_8192": sum(1 for r in all_rows if r["approx_seq_tokens"] > 8192),
            "samples_approx_seq_gt_16384": sum(
                1 for r in all_rows if r["approx_seq_tokens"] > 16384
            ),
            "recommendation": "Use model context >= 16384; 8192 truncates essentially all pairs.",
            "method": f"approx_tokens = round(words * {TOKENS_PER_WORD}) + {CHAT_OVERHEAD_TOKENS}",
        },
        "notes": [
            "Token estimates are heuristic until transformers tokenizer is available.",
            "SFT dataset was not modified.",
        ],
    }

    out = repo / "data" / "humanizer_training" / "legacy51_sft_length_stats.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(out),
                "total": report["counts"]["total"],
                "approx_seq_tokens_median": report["all_approx_seq_tokens_words_x1_3"]["median"],
                "approx_seq_tokens_max": report["all_approx_seq_tokens_words_x1_3"]["max"],
                "need_16k": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
