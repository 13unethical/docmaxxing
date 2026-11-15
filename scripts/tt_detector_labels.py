"""Detector training labels from stored Turnitin AI reports: which text Turnitin highlighted as AI.

Runs nightly on the VPS (deploy/docmaxxing-tt-detector-labels.*) with /root/tt_label_venv
(pypdfium2, numpy, pypdf). Each report is labelled once and cached; the full label set is written to
data/humanizer_training/tt_detector/labels.jsonl and, with --upload, sent to the Modal volume
(ai_detector/train_modal.py ``upload``) for the weekly retrain. Report texts go only there.

Env for --upload: AI_DETECTOR_UPLOAD_URL, AI_DETECTOR_UPLOAD_TOKEN.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data" / "turnitin" / "reports"
OUT_DIR = ROOT / "data" / "humanizer_training" / "tt_detector"
SCALE = 2.0
# Same shape as services/ai_detector.py: 5–8 sentence windows, one-sentence stride.
WINDOW_SENTENCES = 6
MIN_WINDOW_SENTENCES = 5
MAX_WINDOW_SENTENCES = 8
MIN_WINDOW_WORDS = 40
# Bump when label extraction / window rules change so per-report cache is rebuilt.
LABEL_VERSION = 3
_HEADER = re.compile(r"Page \d+ of \d+ - [^\n]*")
_SUBMISSION = re.compile(r"Submission ID trn:oid:::[\d:]+")
_SENT = re.compile(r"(?<=[.!?])[\"'”’)]*\s+(?=[A-Z\"“(])")
_REFERENCE_HINT = re.compile(r"https?://|doi\.org|\bdoi:|\(\d{4}[a-z]?\)\.|Retrieved from", re.I)


def doc_score(pdf: Path) -> str | None:
    from pypdf import PdfReader

    try:
        head = "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf)).pages[:2])
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r"(\*|\d{1,3})%\s*detected as AI", head)
    return m.group(1) if m else None


def flagged_text(pdf: Path) -> tuple[str, list[bool]]:
    """Report text after the two cover pages, with a flag per character: under Turnitin's cyan highlight."""
    import numpy as np
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    doc = pdfium.PdfDocument(str(pdf))
    chars, flags = [], []
    for index in range(2, len(doc)):
        page = doc[index]
        height = page.get_height()
        img = np.asarray(page.render(scale=SCALE).to_pil().convert("RGB")).astype(np.int16)
        r, g, b = img[..., 0], img[..., 1], img[..., 2]
        cyan = (b > 204) & (g > 204) & (r < 217)
        tp = page.get_textpage()
        page_chars, page_flags = [], []
        for i in range(tp.count_chars()):
            code = pdfium_c.FPDFText_GetUnicode(tp.raw, i)
            # Halves of UTF-16 surrogate pairs (emoji etc.) cannot be written as UTF-8.
            ch = " " if 0xD800 <= code <= 0xDFFF else chr(code)
            left, bottom, right, top = tp.get_charbox(i)
            x0, x1 = int(left * SCALE), int(right * SCALE) + 1
            y0, y1 = int((height - top) * SCALE), int((height - bottom) * SCALE) + 1
            box = cyan[max(0, y0):y1, max(0, x0):x1]
            page_chars.append(ch)
            page_flags.append(bool(box.size and box.mean() > 0.15))
        text = "".join(page_chars)
        for pattern in (_HEADER, _SUBMISSION):
            for m in reversed(list(pattern.finditer(text))):
                text = text[: m.start()] + " " * (m.end() - m.start()) + text[m.end():]
        chars.extend(text)
        flags.extend(page_flags)
        chars.append("\n")
        flags.append(False)
    return "".join(chars), flags


def windows(text: str, flags: list[bool]):
    """Sliding sentence windows (~WINDOW_SENTENCES, stride 1) with highlighted-letter share."""
    spans, start = [], 0
    flat = text.replace("\r", " ").replace("\n", " ")
    for m in _SENT.finditer(flat):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(flat)))
    # Drop empty / whitespace-only spans so window counts match scored prose sentences.
    spans = [(a, b) for a, b in spans if flat[a:b].strip()]

    def emit(group: list[tuple[int, int]]):
        a, b = group[0][0], group[-1][1]
        body = re.sub(r"\s+", " ", flat[a:b]).strip()
        letters = [flags[i] for i in range(a, b) if flat[i].isalnum()]
        if len(body.split()) < MIN_WINDOW_WORDS or not letters or _REFERENCE_HINT.search(body):
            return None
        return {"text": body, "ai_frac": round(float(sum(letters)) / len(letters), 3)}

    n = len(spans)
    if not n:
        return
    size = max(1, min(MAX_WINDOW_SENTENCES, WINDOW_SENTENCES))
    min_size = 1 if size < MIN_WINDOW_SENTENCES else MIN_WINDOW_SENTENCES
    if n < min_size:
        row = emit(spans)
        if row:
            yield row
        return
    for i in range(n):
        group = spans[i : i + size]
        if len(group) < min_size:
            break
        row = emit(group)
        if row:
            yield row
        if i + size >= n:
            break


def label_report(folder: Path) -> tuple[str, list[dict]]:
    """("ok" | reason skipped, rows) for one report folder."""
    ai = next(iter(sorted(folder.glob("*ai_report.pdf"))), None)
    hl = next(iter(sorted(folder.glob("*highlights_report.pdf"))), None)
    if ai is None:
        return "no_ai_report", []
    score = doc_score(ai)
    if score is None:
        return "no_score", []
    source = ai
    if score == "*":
        # The AI report hides highlights below 20%; only the Highlights report shows them.
        if hl is None:
            return "masked", []
        source = hl
    text, flags = flagged_text(source)
    if len(text.split()) < 200 and source is hl:
        return "image_only", []
    rows = []
    for row in windows(text, flags):
        row |= {"report": folder.name, "doc_score": score, "source": source.name, "ai": row["ai_frac"] > 0.5}
        rows.append(row)
    return "ok", rows


def _cache_key(folder: Path) -> str:
    stamps = sorted(f"{p.name}:{int(p.stat().st_mtime)}" for p in folder.glob("*.pdf"))
    return f"v{LABEL_VERSION}|" + "|".join(stamps)


def build(reports: Path = REPORTS, out_dir: Path = OUT_DIR) -> dict:
    cache_dir = out_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    stats: dict = {"reports": 0, "labelled_now": 0, "windows": 0, "flagged": 0}
    all_rows: list[dict] = []
    for folder in sorted(p for p in reports.iterdir() if p.is_dir()) if reports.exists() else []:
        cache = cache_dir / f"{folder.name}.json"
        key = _cache_key(folder)
        cached = json.loads(cache.read_text()) if cache.exists() else None
        if cached and cached.get("key") == key:
            status, rows = cached["status"], cached["rows"]
        else:
            try:
                status, rows = label_report(folder)
            except Exception as exc:  # noqa: BLE001
                print("failed", folder.name, exc, file=sys.stderr)
                continue
            cache.write_text(json.dumps({"key": key, "status": status, "rows": rows}, ensure_ascii=False))
            stats["labelled_now"] += 1
        stats[status] = stats.get(status, 0) + 1
        if status == "ok":
            stats["reports"] += 1
            all_rows += rows
    tmp = out_dir / "labels.jsonl.new"
    with tmp.open("w", encoding="utf-8") as fh:
        for row in all_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, out_dir / "labels.jsonl")
    stats["windows"] = len(all_rows)
    stats["flagged"] = sum(r["ai"] for r in all_rows)
    return stats


def upload(path: Path) -> dict:
    req = urllib.request.Request(
        os.environ["AI_DETECTOR_UPLOAD_URL"],
        data=path.read_bytes(),
        headers={"x-token": os.environ["AI_DETECTOR_UPLOAD_TOKEN"], "Content-Type": "application/x-ndjson"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", action="store_true", help="send labels.jsonl to the Modal training volume")
    args = parser.parse_args()
    stats = build()
    print(json.dumps(stats))
    if args.upload and stats["windows"]:
        print(json.dumps({"upload": upload(OUT_DIR / "labels.jsonl")}))


if __name__ == "__main__":
    main()
