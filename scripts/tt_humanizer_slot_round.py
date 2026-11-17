#!/usr/bin/env python3
"""Spend N PlagDetect/Turnitin slots on student-humanizer outputs for detector + v4 SFT.

Flow:
  1. Pick English source_pool docs (prefer 25–29k for long slots)
  2. Rewrite with the student humanizer (v4 in prod)
  3. Submit each rewrite to PlagDetect (1 slot each)
  4. Wait for AI report PDFs
  5. Extract sentence-window labels → batch_<tag>.jsonl
  6. Keep ``*.src.txt`` / ``*.hum.txt`` for ``tt_v4_sft_from_slots.py``

    python3 scripts/tt_humanizer_slot_round.py --limit 5 --tag v4sft20261117 \\
        --min-words 25000 --max-words 29000 --min-submit-words 25000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE_POOL = ROOT / "data" / "humanizer_training" / "source_pool"
OUT_ROOT = ROOT / "data" / "humanizer_training" / "tt_detector" / "slot_rounds"


def _excerpt(text: str, target_words: int) -> str:
    """Keep ~target_words from the start, preserving paragraph breaks.

    Joining on spaces alone would collapse markdown into one ``## …`` line, and the
    student humanizer would treat the whole excerpt as a heading (no prose to rewrite).
    """
    text = text.replace("\r\n", "\n").strip()
    if len(text.split()) <= target_words:
        return text
    parts: list[str] = []
    used = 0
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        n = len(block.split())
        if used and used + n > target_words:
            break
        parts.append(block)
        used += n
        if used >= target_words:
            break
    if not parts:
        # Single huge paragraph: cut on sentences, keep internal newlines if any.
        words = text.split()
        cut = " ".join(words[:target_words])
        for end in (". ", "? ", "! "):
            i = cut.rfind(end)
            if i >= int(0.6 * len(cut)):
                return cut[: i + 1].strip()
        return cut.strip()
    return "\n\n".join(parts).strip()


def _already_submitted_essays() -> set[str]:
    """Essays already in any slot-round manifest — never resubmit the same source."""
    skip: set[str] = set()
    if not OUT_ROOT.is_dir():
        return skip
    for man in OUT_ROOT.glob("*/manifest.json"):
        try:
            rows = json.loads(man.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            essay = str((row or {}).get("essay") or "").strip()
            if essay:
                skip.add(essay)
    return skip


def _pick_sources(
    limit: int,
    min_words: int,
    max_words: int,
    target_words: int,
    exclude: set[str] | None = None,
) -> list[dict]:
    del target_words  # clipping uses max_words only (at submit time)
    # Only pending: used/ is for retired sources; never re-spend slots on them.
    pending = SOURCE_POOL / "pending"
    files = sorted(pending.glob("src-*.json")) if pending.is_dir() else []
    out: list[dict] = []
    seen: set[str] = set()
    skip = set(exclude or set()) | _already_submitted_essays()
    for path in files:
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        doc_id = str(row.get("document_id") or path.stem)
        if doc_id in seen or doc_id in skip:
            continue
        text = str(row.get("source_text") or "").strip()
        words = len(text.split())
        if words < min_words:
            continue
        lang = str(row.get("language") or "en").lower()
        if lang and lang not in ("en", "english", "eng"):
            continue
        # Do NOT clip source here — humanizer expands; clip only at submit (≤max_words).
        seen.add(doc_id)
        out.append({**row, "_path": str(path), "source_text": text, "word_count": words})
    # Prefer longer docs first so remaining slots buy more training windows.
    out.sort(key=lambda r: int(r.get("word_count") or 0), reverse=True)
    return out[:limit]


def _humanize(text: str) -> str:
    from services.humanizer_engine.student_humanizer import try_student_humanize

    res = try_student_humanize(text, force=True, wait_for_boot=150.0)
    if not res:
        raise RuntimeError("student humanizer returned empty")
    # Result dict uses humanized_text (job-shaped); keep a text fallback for older callers.
    out = str(res.get("humanized_text") or res.get("text") or "").strip()
    if not out:
        raise RuntimeError("student humanizer returned empty")
    return out


def _submit_text(svc, text: str, filename: str) -> str:
    sid = uuid.uuid4().hex[:12]
    data = text.encode("utf-8")
    upload_path = svc.save_upload(sid, filename, data)
    svc.store.create(
        submission_id=sid,
        user_id=0,
        filename=filename,
        upload_path=upload_path,
    )
    svc.store.update(
        sid,
        meta_json=json.dumps({"provider": "plagdetect", "training_round": True}),
    )
    svc.start_plagdetect_api_check(
        submission_id=sid,
        user_id=0,
        cost=0,
        refund_fn=lambda **_kwargs: None,
    )
    return sid


def _wait_reports(svc, sids: list[str], timeout_s: int) -> dict[str, dict]:
    deadline = time.time() + timeout_s
    done: dict[str, dict] = {}
    while time.time() < deadline and len(done) < len(sids):
        for sid in sids:
            if sid in done:
                continue
            row = svc.store.get(sid) or {}
            status = str(row.get("status") or "")
            ai_path = str(row.get("ai_report_path") or "").strip()
            folder = svc.report_dir(sid)
            if not ai_path:
                ai = next(iter(sorted(folder.glob("*ai_report.pdf"))), None)
                if ai is not None:
                    ai_path = str(ai)
            if status == "completed" and ai_path and Path(ai_path).is_file():
                done[sid] = row
                svc.maybe_queue_star_highlights(sid)
            elif status == "completed":
                # Completed but no AI PDF (e.g. over 30k words) — stop waiting.
                done[sid] = row
            elif status in ("failed", "cancelled"):
                done[sid] = row
        if len(done) < len(sids):
            time.sleep(15)
    return done


def _label_submission(svc, sid: str, essay: str) -> list[dict]:
    from scripts import tt_detector_labels as labels

    folder = svc.report_dir(sid)
    status, rows = labels.label_report(folder)
    if status != "ok":
        return []
    out = []
    for i, row in enumerate(rows):
        out.append(
            {
                "doc": f"hum_{sid}",
                "doc_score": row.get("doc_score"),
                "essay": essay,
                "idx": i,
                "text": row["text"],
                "ai_frac": row["ai_frac"],
                "ai": bool(row["ai"]),
                "report": sid,
                "source": row.get("source"),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--tag", type=str, default="hum" + time.strftime("%Y%m%d"))
    ap.add_argument("--min-words", type=int, default=25000)
    ap.add_argument(
        "--max-words",
        type=int,
        default=29000,
        help="Hard cap for Turnitin submit (PlagDetect AI needs ≤30000; default 29000)",
    )
    ap.add_argument(
        "--target-words",
        type=int,
        default=29000,
        help="Deprecated alias; clipping uses --max-words",
    )
    ap.add_argument("--exclude-essay", action="append", default=[], help="Skip document_id already used")
    ap.add_argument("--timeout-s", type=int, default=90 * 60)
    ap.add_argument(
        "--min-submit-words",
        type=int,
        default=25000,
        help="Abort submit if clipped body is below this (default 25000)",
    )
    ap.add_argument(
        "--abort-on-bad-words",
        action="store_true",
        default=True,
        help="Stop the whole round if a doc is outside the submit word window",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = _pick_sources(
        args.limit,
        args.min_words,
        args.max_words,
        args.max_words,
        exclude=set(args.exclude_essay or []),
    )
    print(json.dumps({"picked": len(sources), "need": args.limit}))
    if len(sources) < args.limit:
        print(json.dumps({"error": "not_enough_sources", "have": len(sources)}))
        return 1
    if args.dry_run:
        for s in sources:
            print(json.dumps({"id": s.get("document_id"), "words": s["word_count"], "topic": s.get("topic")}))
        return 0

    from services.turnitin_service.service import TurnitinService

    svc = TurnitinService()
    round_dir = OUT_ROOT / args.tag
    round_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    sids: list[str] = []

    for i, src in enumerate(sources):
        essay = str(src.get("document_id") or Path(src["_path"]).stem)
        print(json.dumps({"step": "humanize", "i": i, "essay": essay, "words": src["word_count"]}))
        try:
            humanized = _humanize(src["source_text"])
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"step": "humanize_fail", "essay": essay, "error": str(exc)[:300]}))
            continue
        (round_dir / f"{essay}.src.txt").write_text(src["source_text"], encoding="utf-8")
        (round_dir / f"{essay}.hum.txt").write_text(humanized, encoding="utf-8")
        # PlagDetect AI needs ≤30000; keep a hard window and never submit outside it.
        submit_body = humanized
        hum_words = len(humanized.split())
        if hum_words > args.max_words:
            submit_body = _excerpt(humanized, args.max_words)
        submit_words = len(submit_body.split())
        print(
            json.dumps(
                {
                    "step": "word_gate",
                    "essay": essay,
                    "src_words": src["word_count"],
                    "hum_words": hum_words,
                    "submit_words": submit_words,
                    "min_submit": args.min_submit_words,
                    "max_submit": args.max_words,
                }
            ),
            flush=True,
        )
        if submit_words < args.min_submit_words or submit_words > args.max_words:
            print(
                json.dumps(
                    {
                        "step": "abort_bad_wordcount",
                        "essay": essay,
                        "submit_words": submit_words,
                        "allowed": [args.min_submit_words, args.max_words],
                    }
                ),
                flush=True,
            )
            if args.abort_on_bad_words:
                (round_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                return 2
            continue
        try:
            sid = _submit_text(svc, submit_body, f"{args.tag}_{essay}.txt")
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"step": "submit_fail", "essay": essay, "error": str(exc)[:300]}))
            if args.abort_on_bad_words:
                return 3
            continue
        sids.append(sid)
        manifest.append(
            {
                "essay": essay,
                "sid": sid,
                "src_words": src["word_count"],
                "hum_words": hum_words,
                "submit_words": submit_words,
                "src_path": f"{essay}.src.txt",
                "hum_path": f"{essay}.hum.txt",
                "purpose": "v4_tt_sft",
            }
        )
        print(json.dumps({"step": "submitted", "essay": essay, "sid": sid, "submit_words": submit_words}), flush=True)
        (round_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # Retire source so later batches do not resubmit the same long doc.
        try:
            src_path = Path(src["_path"])
            used_dir = SOURCE_POOL / "used"
            used_dir.mkdir(parents=True, exist_ok=True)
            dest = used_dir / src_path.name
            if src_path.is_file() and src_path.resolve() != dest.resolve():
                src_path.replace(dest)
        except OSError as exc:
            print(json.dumps({"step": "retire_warn", "essay": essay, "error": str(exc)[:200]}))

    print(json.dumps({"submitted": len(sids), "waiting": True}))
    done = _wait_reports(svc, sids, args.timeout_s)
    print(json.dumps({"completed_or_failed": len(done), "sids": list(done)}))

    # Give Highlights a bit of time for *% docs.
    time.sleep(30)
    all_rows: list[dict] = []
    stats = {"ok": 0, "skip": 0, "failed_status": 0}
    for item in manifest:
        sid = item["sid"]
        row = done.get(sid) or svc.store.get(sid) or {}
        if str(row.get("status")) != "completed":
            stats["failed_status"] += 1
            continue
        labeled = _label_submission(svc, sid, item["essay"])
        if not labeled:
            stats["skip"] += 1
            continue
        stats["ok"] += 1
        all_rows.extend(labeled)

    out_path = ROOT / "data" / "humanizer_training" / "tt_detector" / f"batch_{args.tag}.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for row in all_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    # Attach Turnitin AI highlights onto the manifest for SFT filtering.
    for item in manifest:
        sid = item["sid"]
        row = done.get(sid) or svc.store.get(sid) or {}
        meta = row.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        item["status"] = str(row.get("status") or "")
        item["ai_score_display"] = meta.get("ai_score_display")
        item["ai_highlights"] = row.get("ai_highlights")
        if item["ai_highlights"] is None:
            disp = meta.get("ai_highlights_display")
            if isinstance(disp, str) and disp.endswith("%"):
                try:
                    item["ai_highlights"] = float(disp.rstrip("%"))
                except ValueError:
                    pass
    (round_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "batch": str(out_path),
                "windows": len(all_rows),
                "flagged": sum(1 for r in all_rows if r["ai"]),
                "docs_ok": stats["ok"],
                "stats": stats,
                "slots_used": len(sids),
                "sft_hint": "python3 scripts/tt_v4_sft_from_slots.py --tags " + args.tag,
            }
        )
    )
    return 0 if stats["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
