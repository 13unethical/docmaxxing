#!/usr/bin/env python3
"""Fetch Turnitin/PlagDetect Highlights PDFs for every ``*%`` (1–19% AI) submission that lacks one.

The AI report PDF hides cyan marks below 20%. Detector training needs the Highlights report
(Get Highlights) so those sentences enter labels.jsonl instead of being skipped as ``masked``.

    python3 scripts/tt_ensure_star_highlights.py
    python3 scripts/tt_ensure_star_highlights.py --dry-run

Uses PlagDetect API for plagdetect rows and TCA for official Turnitin. Deletes detector
label cache entries for folders that gain a Highlights PDF so the nightly label job rebuilds them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "data" / "turnitin" / "reports"
CACHE = ROOT / "data" / "humanizer_training" / "tt_detector" / "cache"


def _doc_score(pdf: Path) -> str | None:
    from pypdf import PdfReader

    try:
        head = "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf)).pages[:2])
    except Exception:  # noqa: BLE001
        return None
    import re

    m = re.search(r"(\*|\d{1,3})%\s*detected as AI", head)
    return m.group(1) if m else None


def star_missing_highlights() -> list[str]:
    missing: list[str] = []
    if not REPORTS.is_dir():
        return missing
    for folder in sorted(p for p in REPORTS.iterdir() if p.is_dir()):
        ai = next(iter(sorted(folder.glob("*ai_report.pdf"))), None)
        if ai is None:
            continue
        if _doc_score(ai) != "*":
            continue
        if next(iter(sorted(folder.glob("*highlights*.pdf"))), None) is not None:
            continue
        missing.append(folder.name)
    return missing


def invalidate_label_cache(submission_id: str) -> None:
    path = CACHE / f"{submission_id}.json"
    if path.is_file():
        path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max submissions to fetch (0 = all)")
    args = parser.parse_args()

    missing = star_missing_highlights()
    if args.limit > 0:
        missing = missing[: args.limit]
    print(json.dumps({"star_missing_highlights": len(missing), "ids": missing}))
    if args.dry_run or not missing:
        return 0

    from services.turnitin_service.service import TurnitinService

    svc = TurnitinService()
    stats = {"ok": 0, "failed": 0, "skipped": 0}
    for sid in missing:
        row = svc.store.get(sid) or {}
        meta = dict(row.get("meta") or {})
        if str(meta.get("ai_score_display") or "").strip() != "*%":
            # PDF says *% but DB display was never stored — still fetch for training.
            meta["ai_score_display"] = "*%"
            if not meta.get("provider"):
                meta["provider"] = "plagdetect"
            svc.store.update(sid, meta_json=json.dumps(meta))
            row = svc.store.get(sid) or row
        provider = str((row.get("meta") or {}).get("provider") or "plagdetect").strip().lower()
        try:
            if provider == "turnitin":
                user_id = int(row.get("user_id") or 0)
                if user_id <= 0:
                    stats["skipped"] += 1
                    print(json.dumps({"id": sid, "status": "skip_no_user"}))
                    continue
                result = svc._run_tca_highlights(submission_id=sid, user_id=user_id)
            else:
                result = svc._run_plagdetect_api_highlights(submission_id=sid, retry=False)
            ok = bool(result.get("success")) and svc.has_highlights_pdf(sid)
            stats["ok" if ok else "failed"] += 1
            if ok:
                invalidate_label_cache(sid)
            print(json.dumps({"id": sid, "status": "ok" if ok else "failed", "provider": provider}))
        except Exception as exc:  # noqa: BLE001
            stats["failed"] += 1
            print(json.dumps({"id": sid, "status": "error", "error": str(exc)[:200]}))
    print(json.dumps({"done": stats}))
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
