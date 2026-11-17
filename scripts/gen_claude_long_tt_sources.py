#!/usr/bin/env python3
"""Generate long Claude academic sources (~27–29k words) for Turnitin training slots.

Writes JSON docs into ``data/humanizer_training/source_pool/pending/`` so
``tt_humanizer_slot_round.py --min-words 27000`` can pick them up.

Each document is built in multiple Claude section calls (single-shot max tokens
cannot reliably hit 28k). Topics/types/angles are varied across the batch.

  python3 scripts/gen_claude_long_tt_sources.py --count 5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.claude_client import generate_reply  # noqa: E402
from services.humanizer_training.teacher.documents.source_pool import (  # noqa: E402
    SYSTEM_PROMPT,
    clean_source_text,
    drop_non_prose_blocks,
)
from services.humanizer_training.teacher.documents.topic_catalog import (  # noqa: E402
    ANGLES,
    DOCUMENT_TYPE_LABELS,
    DOCUMENT_TYPES,
    DOCUMENT_TYPES_ALLOWING_REFERENCES,
    DOMAINS,
    TOPICS_BY_DOMAIN,
)

PENDING = ROOT / "data" / "humanizer_training" / "source_pool" / "pending"
_HEADING_RE = re.compile(r"(?m)^##\s+")


def _wc(text: str) -> int:
    return len([p for p in (text or "").split() if p.strip()])


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = val.strip().strip('"').strip("'")


def _existing_combo_keys(pool_root: Path) -> set[str]:
    keys: set[str] = set()
    for folder in ("pending", "used"):
        d = pool_root / folder
        if not d.is_dir():
            continue
        for path in d.glob("src-*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if row.get("purpose") != "tt_detector_long_slot" and len(
                str(row.get("source_text") or "").split()
            ) < 20000:
                continue
            domain = str(row.get("domain") or "")
            topic = str(row.get("topic") or "")
            doc_type = str(row.get("document_type") or "")
            angle = str(row.get("angle") or "")
            if domain and topic:
                keys.add(f"{domain}|{topic}|{doc_type}|{angle}")
                keys.add(f"{domain}|{topic}")  # also avoid same topic reuse
    return keys


def _pick_briefs(count: int, seed: str, *, exclude: set[str] | None = None) -> list[dict]:
    """Diverse domain/topic/type/angle briefs; skips already-generated long topics."""
    pool: list[tuple[str, str, str, str]] = []
    for domain in DOMAINS:
        for topic in TOPICS_BY_DOMAIN[domain]:
            for doc_type in DOCUMENT_TYPES:
                for angle in ANGLES:
                    pool.append((domain, topic, doc_type, angle))
    order = list(range(len(pool)))
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    stream = list(digest) * ((len(order) // 32) + 2)
    si = 0
    for i in range(len(order) - 1, 0, -1):
        si += 1
        j = stream[si % len(stream)] % (i + 1)
        order[i], order[j] = order[j], order[i]

    skip = exclude or set()
    picked: list[dict] = []
    seen_domain: set[str] = set()
    seen_topic: set[str] = set()

    def _try(idx: int, *, require_new_domain: bool) -> bool:
        domain, topic, doc_type, angle = pool[idx]
        combo = f"{domain}|{topic}|{doc_type}|{angle}"
        topic_key = f"{domain}|{topic}"
        if combo in skip or topic_key in skip:
            return False
        if topic_key in seen_topic:
            return False
        if require_new_domain and domain in seen_domain and len(seen_domain) < min(count, len(DOMAINS)):
            return False
        seen_domain.add(domain)
        seen_topic.add(topic_key)
        picked.append(
            {
                "domain": domain,
                "topic": topic,
                "document_type": doc_type,
                "angle": angle,
            }
        )
        return True

    for idx in order:
        if len(picked) >= count:
            break
        _try(idx, require_new_domain=True)
    for idx in order:
        if len(picked) >= count:
            break
        _try(idx, require_new_domain=False)
    return picked[:count]


SECTION_BLUEPRINTS: list[tuple[str, str]] = [
    ("Background and context", "Set historical and conceptual context; define key terms."),
    ("Theoretical frameworks", "Compare 2–3 theoretical lenses with concrete implications."),
    ("Evidence and case material", "Develop 2–3 detailed cases with numbers, years, mechanisms."),
    ("Mechanisms and processes", "Explain causal pathways and intervening variables."),
    ("Stakeholder and institutional analysis", "Map actors, incentives, constraints, and trade-offs."),
    ("Comparative perspectives", "Contrast jurisdictions, periods, or competing approaches."),
    ("Critiques and counterarguments", "Steelman opposing views; show where evidence is thin."),
    ("Policy and practice implications", "Derive actionable implications without sloganizing."),
    ("Limitations and open questions", "Acknowledge measurement, selection, and external-validity limits."),
    ("Synthesis and conclusion", "Integrate strands into a coherent closing argument."),
]


def _outline_prompt(brief: dict, target_low: int, target_high: int) -> str:
    label = DOCUMENT_TYPE_LABELS.get(brief["document_type"], brief["document_type"])
    topic = brief["topic"].replace("_", " ")
    angle = brief["angle"].replace("_", " ")
    domain = brief["domain"].replace("_", " ")
    n = len(SECTION_BLUEPRINTS)
    per = (target_low + target_high) // (2 * n)
    lines = [
        f"You will write a long {label} (~{target_low}–{target_high} words total) on "
        f"“{topic}” (domain: {domain}), angle: {angle}.",
        "Return ONLY a numbered section plan, one line per section, format:",
        "## <exact section title>",
        f"Use exactly {n} sections with these roles (rename titles to fit the topic):",
    ]
    for i, (role, hint) in enumerate(SECTION_BLUEPRINTS, 1):
        lines.append(f"{i}. role={role}; aim≈{per} words; hint={hint}")
    lines.append("No prose yet. No preamble.")
    return "\n".join(lines)


def _parse_outline(text: str) -> list[str]:
    titles = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("## "):
            titles.append(line[3:].strip())
        elif re.match(r"^\d+[\).\]]\s+", line):
            titles.append(re.sub(r"^\d+[\).\]]\s+", "", line).strip())
    # Dedupe / drop empties
    out: list[str] = []
    for t in titles:
        t = t.strip("# ").strip()
        if t and t.lower() not in {x.lower() for x in out}:
            out.append(t)
    if len(out) < 6:
        # Fallback to blueprint titles
        return [role for role, _ in SECTION_BLUEPRINTS]
    return out[: len(SECTION_BLUEPRINTS)]


def _section_prompt(
    brief: dict,
    *,
    titles: list[str],
    index: int,
    words_low: int,
    words_high: int,
    prior_tail: str,
) -> str:
    label = DOCUMENT_TYPE_LABELS.get(brief["document_type"], brief["document_type"])
    topic = brief["topic"].replace("_", " ")
    angle = brief["angle"].replace("_", " ")
    title = titles[index]
    role, hint = SECTION_BLUEPRINTS[min(index, len(SECTION_BLUEPRINTS) - 1)]
    allow_refs = brief["document_type"] in DOCUMENT_TYPES_ALLOWING_REFERENCES
    refs = (
        "You may weave brief in-text citations; do not dump a long bibliography here."
        if allow_refs
        else "Do not invent a References section."
    )
    prior = prior_tail.strip()
    prior_note = (
        f"Previous section ended with:\n\"\"\"\n{prior[-1200:]}\n\"\"\"\nContinue coherently; do not repeat."
        if prior
        else "This is the opening section."
    )
    return (
        f"Continue the {label} on “{topic}” (angle: {angle}).\n"
        f"Write ONLY section {index + 1}/{len(titles)}:\n"
        f"## {title}\n"
        f"Role: {role}. {hint}\n"
        f"Target length: {words_low}–{words_high} words of continuous academic prose.\n"
        f"{refs}\n"
        "- Start with the `##` heading line, then paragraphs separated by blank lines.\n"
        "- No lists, tables, code, or meta commentary.\n"
        "- Dense, specific prose with examples, mechanisms, and varied sentence rhythm.\n"
        f"{prior_note}\n"
    )


def _call_claude(user_prompt: str, *, max_tokens: int = 8192) -> str:
    text, diag = generate_reply(
        system_prompt=SYSTEM_PROMPT,
        content=user_prompt,
        temperature=0.55,
        max_tokens=max_tokens,
        timeout_s=180,
        max_retries=3,
    )
    if not text:
        raise RuntimeError(f"Claude failed: {diag.get('error_message') or diag}")
    return text


def _trim_to_range(text: str, low: int, high: int) -> str:
    """If slightly over high, drop trailing paragraphs until <= high; never below low if possible."""
    words = text.split()
    if len(words) <= high:
        return text
    # Drop from the end by paragraph
    parts = text.split("\n\n")
    while len(parts) > 2 and _wc("\n\n".join(parts)) > high:
        # Prefer dropping from last body section, keep final heading if alone
        parts.pop()
    trimmed = "\n\n".join(parts).strip()
    if _wc(trimmed) < low:
        # Hard cut on words but end on sentence if possible
        cut = " ".join(words[:high])
        for end in (". ", "? ", "! "):
            i = cut.rfind(end)
            if i >= int(0.85 * len(cut)):
                return cut[: i + 1].strip()
        return cut.strip()
    return trimmed


def generate_one(
    brief: dict,
    *,
    target_low: int,
    target_high: int,
) -> tuple[str, dict]:
    n = len(SECTION_BLUEPRINTS)
    # Aim mid-range; leave ~5% headroom for trim
    mid = (target_low + target_high) // 2
    per_low = max(2200, mid // n - 200)
    per_high = max(per_low + 200, mid // n + 250)

    outline_raw = _call_claude(_outline_prompt(brief, target_low, target_high), max_tokens=1500)
    titles = _parse_outline(outline_raw)

    sections: list[str] = []
    for i in range(len(titles)):
        # Adjust remaining budget
        have = _wc("\n\n".join(sections))
        remaining_sections = len(titles) - i
        need_low = max(target_low - have, 800)
        need_high = max(target_high - have, need_low + 200)
        w_low = max(1800, min(per_low, need_low // remaining_sections))
        w_high = max(w_low + 200, min(per_high + 400, need_high // remaining_sections + 400))
        # Last section: push to land in range
        if i == len(titles) - 1:
            w_low = max(1500, target_low - have)
            w_high = max(w_low + 200, target_high - have)

        prior = sections[-1] if sections else ""
        raw = _call_claude(
            _section_prompt(
                brief,
                titles=titles,
                index=i,
                words_low=w_low,
                words_high=w_high,
                prior_tail=prior,
            ),
            max_tokens=8192,
        )
        cleaned = drop_non_prose_blocks(clean_source_text(raw))
        if not _HEADING_RE.search(cleaned):
            cleaned = f"## {titles[i]}\n\n{cleaned}"
        sections.append(cleaned)
        print(
            json.dumps(
                {
                    "section": i + 1,
                    "of": len(titles),
                    "section_words": _wc(cleaned),
                    "total_so_far": _wc("\n\n".join(sections)),
                }
            ),
            flush=True,
        )
        # Soft stop if already past high after a full section
        if _wc("\n\n".join(sections)) >= target_high and i >= 6:
            break

    body = "\n\n".join(sections)
    body = drop_non_prose_blocks(clean_source_text(body))
    body = _trim_to_range(body, target_low, target_high)
    meta = {
        **brief,
        "section_titles": titles,
        "word_count": _wc(body),
        "target_low": target_low,
        "target_high": target_high,
        "writer": "claude",
        "purpose": "tt_detector_long_slot",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return body, meta


def _doc_id(brief: dict, body: str) -> str:
    h = hashlib.sha256(
        f"{brief['domain']}|{brief['topic']}|{brief['document_type']}|{brief['angle']}|{body[:2000]}".encode()
    ).hexdigest()[:16]
    return f"src-{h}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=5)
    # Aim a bit under 27–29k: student humanizer expands ~10–15%, and PlagDetect caps at 30k.
    ap.add_argument("--min-words", type=int, default=25000)
    ap.add_argument("--max-words", type=int, default=27500,
                    help="Source cap; humanizer may expand — leave headroom under 29k submit")
    ap.add_argument("--seed", type=str, default=time.strftime("%Y%m%d"))
    ap.add_argument("--out-dir", type=str, default=str(PENDING))
    args = ap.parse_args()

    _load_dotenv()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    root_pool = out_dir.parent if out_dir.name == "pending" else out_dir
    exclude = _existing_combo_keys(root_pool)
    briefs = _pick_briefs(args.count, args.seed, exclude=exclude)
    print(json.dumps({"planned": len(briefs), "seed": args.seed, "excluded_keys": len(exclude)}))
    ok = 0
    for i, brief in enumerate(briefs):
        print(json.dumps({"step": "generate", "i": i, **brief}), flush=True)
        try:
            body, meta = generate_one(
                brief,
                target_low=args.min_words,
                target_high=args.max_words,
            )
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"step": "fail", "i": i, "error": str(exc)[:400]}), flush=True)
            continue
        wc = meta["word_count"]
        if wc < args.min_words:
            print(json.dumps({"step": "too_short", "words": wc, "need": args.min_words}), flush=True)
            # Keep anyway only if within 5% — else skip
            if wc < int(args.min_words * 0.95):
                continue
        doc_id = _doc_id(brief, body)
        row = {
            "document_id": doc_id,
            "source_text": body,
            "language": "en",
            "word_count": wc,
            **{k: v for k, v in meta.items() if k != "word_count"},
        }
        path = out_dir / f"{doc_id}.json"
        path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        ok += 1
        print(json.dumps({"step": "saved", "path": str(path), "words": wc, "document_id": doc_id}), flush=True)

    print(json.dumps({"generated_ok": ok, "requested": args.count}))
    return 0 if ok == args.count else (0 if ok else 1)


if __name__ == "__main__":
    raise SystemExit(main())
