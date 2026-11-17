#!/usr/bin/env python3
"""Build v4 chat-SFT shards from Turnitin slot-round source/humanize pairs.

Reads ``data/humanizer_training/tt_detector/slot_rounds/*/`` (``*.src.txt`` + ``*.hum.txt``
+ manifest), attaches Turnitin AI highlights when available, and writes section-sized
chat examples in the same format as ``section_sft``:

  system: rewrite strength N/10
  user: source chunk
  assistant: humanized chunk

Only keeps docs whose AI highlights are at or below ``--max-ai-highlights`` (default 20).
Asterisk (``*%``) docs are kept when highlights exist and pass the cap.

  python3 scripts/tt_v4_sft_from_slots.py
  python3 scripts/tt_v4_sft_from_slots.py --tags v4sft20261117_b0 --max-ai-highlights 15
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.humanizer_training.section_sft import (  # noqa: E402
    CHUNK_WORDS,
    MAX_SECTION_WORDS,
    MIN_SECTION_WORDS,
    _jaccard,
    _paragraphs,
    _section_reject,
    _wc,
    section_pairs,
    split_for,
    split_sections,
    system_prompt,
)

ROUNDS = ROOT / "data" / "humanizer_training" / "tt_detector" / "slot_rounds"
DEFAULT_OUT = ROOT / "data" / "humanizer_training" / "v4_tt_sft"
_WORD = re.compile(r"[a-z0-9']+", re.I)


def _ai_highlights(svc, sid: str) -> tuple[float | None, str | None]:
    row = svc.store.get(sid) or {}
    meta = row.get("meta") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    display = str(meta.get("ai_score_display") or "").strip() or None
    highlights = row.get("ai_highlights")
    if highlights is None:
        highlights = meta.get("ai_highlights_display")
        if isinstance(highlights, str) and highlights.endswith("%"):
            try:
                highlights = float(highlights.rstrip("%"))
            except ValueError:
                highlights = None
    try:
        return (float(highlights) if highlights is not None else None), display
    except (TypeError, ValueError):
        return None, display


def _aligned_chunks(source: str, target: str) -> tuple[list[tuple[str, str]], str | None]:
    """Prefer ## section alignment; fall back to paragraph chunks / whole body."""
    src_secs, tgt_secs = split_sections(source), split_sections(target)
    if src_secs and [t for t, _ in src_secs] == [t for t, _ in tgt_secs]:
        out: list[tuple[str, str]] = []
        for (_title, s), (_t, t) in zip(src_secs, tgt_secs):
            pairs, why = section_pairs(s, t)
            if why:
                continue
            out.extend(pairs)
        if out:
            return out, None
    src_paras, tgt_paras = _paragraphs(source), _paragraphs(target)
    if len(src_paras) == len(tgt_paras) and src_paras:
        chunks: list[tuple[str, str]] = []
        cur_s: list[str] = []
        cur_t: list[str] = []
        for s, t in zip(src_paras, tgt_paras):
            if cur_s and _wc("\n\n".join(cur_s + [s])) > CHUNK_WORDS:
                chunks.append(("\n\n".join(cur_s), "\n\n".join(cur_t)))
                cur_s, cur_t = [], []
            cur_s.append(s)
            cur_t.append(t)
        if cur_s:
            chunks.append(("\n\n".join(cur_s), "\n\n".join(cur_t)))
        return chunks, None
    if _wc(source) <= MAX_SECTION_WORDS and _wc(target) <= MAX_SECTION_WORDS * 1.5:
        return [(source, target)], None
    return [], "UNALIGNED"


def _iter_round_docs(tags: list[str] | None) -> list[dict]:
    if not ROUNDS.is_dir():
        return []
    dirs = sorted(p for p in ROUNDS.iterdir() if p.is_dir())
    if tags:
        want = set(tags)
        dirs = [p for p in dirs if p.name in want]
    out: list[dict] = []
    for d in dirs:
        man_path = d / "manifest.json"
        if not man_path.is_file():
            continue
        try:
            rows = json.loads(man_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(rows, list):
            continue
        for item in rows:
            essay = str((item or {}).get("essay") or "").strip()
            sid = str((item or {}).get("sid") or "").strip()
            if not essay or not sid:
                continue
            src_path = d / f"{essay}.src.txt"
            hum_path = d / f"{essay}.hum.txt"
            if not src_path.is_file() or not hum_path.is_file():
                continue
            out.append(
                {
                    "tag": d.name,
                    "essay": essay,
                    "sid": sid,
                    "src_path": src_path,
                    "hum_path": hum_path,
                    "src_words": item.get("src_words"),
                    "hum_words": item.get("hum_words"),
                    "submit_words": item.get("submit_words"),
                }
            )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tags", nargs="*", default=None, help="Only these slot-round folder names")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--level", type=int, default=10, help="Rewrite strength in system prompt")
    ap.add_argument(
        "--max-ai-highlights",
        type=float,
        default=20.0,
        help="Keep docs with AI highlights ≤ this %% (default 20)",
    )
    ap.add_argument(
        "--allow-missing-highlights",
        action="store_true",
        help="Keep docs with no highlights number (still need completed AI report)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from services.turnitin_service.service import TurnitinService

    svc = TurnitinService()
    docs = _iter_round_docs(args.tags)
    print(json.dumps({"candidates": len(docs), "tags": args.tags or "all"}))

    args.out.mkdir(parents=True, exist_ok=True)
    handles = {
        name: (args.out / f"{name}.jsonl").open("w", encoding="utf-8")
        for name in ("train", "val", "test")
    }
    meta_path = args.out / "examples_meta.jsonl"
    meta_fh = meta_path.open("w", encoding="utf-8")
    stats = {
        "docs_seen": 0,
        "docs_kept": 0,
        "docs_skip_ai": 0,
        "docs_skip_align": 0,
        "examples": {"train": 0, "val": 0, "test": 0},
        "section_rejects": {},
    }
    seen: set[str] = set()

    try:
        for doc in docs:
            stats["docs_seen"] += 1
            highlights, display = _ai_highlights(svc, doc["sid"])
            if highlights is None and not args.allow_missing_highlights:
                stats["docs_skip_ai"] += 1
                continue
            if highlights is not None and highlights > args.max_ai_highlights:
                stats["docs_skip_ai"] += 1
                continue
            source = doc["src_path"].read_text(encoding="utf-8").strip()
            target = doc["hum_path"].read_text(encoding="utf-8").strip()
            chunks, why = _aligned_chunks(source, target)
            if why or not chunks:
                stats["docs_skip_align"] += 1
                continue
            split = split_for(doc["essay"])
            used = 0
            for part, (s, t) in enumerate(chunks):
                reject = _section_reject(s, t)
                if reject == "HEADING_IN_TARGET":
                    # Humanizer may leave ## titles; strip heading lines from target chunk.
                    t = re.sub(r"(?m)^##\s+.*\n?", "", t).strip()
                    reject = _section_reject(s, t)
                key = hashlib.sha256(s.encode("utf-8")).hexdigest()
                if reject is None and key in seen:
                    reject = "DUPLICATE_SOURCE"
                if reject:
                    stats["section_rejects"][reject] = stats["section_rejects"].get(reject, 0) + 1
                    continue
                if _wc(s) < MIN_SECTION_WORDS:
                    stats["section_rejects"]["TOO_SHORT"] = stats["section_rejects"].get("TOO_SHORT", 0) + 1
                    continue
                seen.add(key)
                if args.dry_run:
                    used += 1
                    continue
                handles[split].write(
                    json.dumps(
                        {
                            "messages": [
                                {"role": "system", "content": system_prompt(args.level)},
                                {"role": "user", "content": s},
                                {"role": "assistant", "content": t},
                            ]
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                meta_fh.write(
                    json.dumps(
                        {
                            "split": split,
                            "document_id": doc["essay"],
                            "tag": doc["tag"],
                            "sid": doc["sid"],
                            "part": part,
                            "level": args.level,
                            "ai_highlights": highlights,
                            "ai_score_display": display,
                            "source_words": _wc(s),
                            "target_words": _wc(t),
                            "submit_words": doc.get("submit_words"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                stats["examples"][split] += 1
                used += 1
            if used:
                stats["docs_kept"] += 1
    finally:
        for fh in handles.values():
            fh.close()
        meta_fh.close()

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "tt_slot_rounds",
        "max_ai_highlights": args.max_ai_highlights,
        "level": args.level,
        "stats": stats,
        "outputs": {
            "train": str(args.out / "train.jsonl"),
            "val": str(args.out / "val.jsonl"),
            "test": str(args.out / "test.jsonl"),
            "meta": str(meta_path),
        },
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if stats["docs_kept"] or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
