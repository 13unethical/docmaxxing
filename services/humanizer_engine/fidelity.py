"""Undo meaning errors a humanizer introduced, with minimal word-level edits.

Humanizers swap words for near-synonyms and sometimes flip the meaning ("inimitable" ->
"imitable"), change facts ("about 55" -> "less than 55") or produce nonsense collocations.
Rewriting the text would undo the humanization, so the model may only return short
find/replace edits on the humanized text, each checked before it is applied.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

_MAX_EDITS = 40
_MAX_FIND_CHARS = 160
_MAX_FIND_WORDS = 15

_SYSTEM = """You proofread a humanized academic text against its original version.
The humanized text was produced from the original by a paraphrasing tool. Its style must stay as it
is. Find only places where the paraphrase is WRONG:
- a technical term, framework or model name changed (e.g. "inimitable" became "imitable",
  "component cost" became "element cost", "PESTLE" became "PEST");
- a fact, number, name, date, currency or qualifier changed (e.g. "about 55 employees" became
  "less than 55 employees", "£2.1 billion" lost its currency);
- a phrase that is nonsense or means something else in English (e.g. "subsidy addiction" for
  "reliance on subsidies", "allocated legally" where the original had no legal claim);
- a clear grammar error that blocks understanding.
For each, return the smallest edit that fixes it (usually 1-8 words), using the original's wording
where possible. Never rewrite a whole sentence.
Do NOT edit anything else: no style, rhythm or word-choice changes that keep the meaning.

Return ONLY JSON:
{"edits":[{"find":"exact text copied from the humanized version (a few words)",
"replace":"corrected text","why":"short reason"}]}
Return {"edits":[]} when nothing is wrong.
"""


def repair_humanizer_meaning(
    original: str,
    humanized: str,
    *,
    call: Callable[[str, str], dict[str, Any] | None] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """Return (fixed text, applied edits). Never fails: on any error the text is unchanged.

    Each changed section is checked on its own (whole-document checks miss most errors);
    the References list is never touched.
    """
    from concurrent.futures import ThreadPoolExecutor

    from services.humanizer_engine.heading_utils import join_body_and_references, split_off_references
    from services.humanizer_engine.incremental import _split_sections

    if not (original or "").strip() or not (humanized or "").strip():
        return humanized, []
    call = call or _default_call
    original_body, _refs = split_off_references(original)
    body, refs = split_off_references(humanized)
    originals = {_heading_key(h): t for h, t in _split_sections(original_body.strip())}
    sections = _split_sections(body.strip())
    jobs = [
        (i, originals[_heading_key(h)], t)
        for i, (h, t) in enumerate(sections)
        if _heading_key(h) in originals and originals[_heading_key(h)].strip() != t.strip() and t.strip()
    ]
    if not jobs:
        return humanized, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda job: _repair_section(job[1], job[2], call), jobs))
    applied: list[dict[str, str]] = []
    for (i, _orig, _text), (fixed, edits) in zip(jobs, results):
        if edits:
            sections[i] = (sections[i][0], fixed)
            applied.extend(edits)
    if not applied:
        return humanized, []
    new_body = "\n\n".join(f"{h}\n\n{t}".strip() if h else t for h, t in sections)
    return join_body_and_references(new_body, refs), applied


def _heading_key(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", heading.lower()).strip()


def _repair_section(
    original: str, humanized: str, call: Callable[[str, str], dict[str, Any] | None]
) -> tuple[str, list[dict[str, str]]]:
    try:
        data = call(_SYSTEM, json.dumps({"original": original, "humanized": humanized}, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        return humanized, []
    edits = (data or {}).get("edits") if isinstance(data, dict) else None
    if not isinstance(edits, list):
        return humanized, []
    text = humanized
    applied: list[dict[str, str]] = []
    for edit in edits[:_MAX_EDITS]:
        if not isinstance(edit, dict):
            continue
        find = str(edit.get("find") or "")
        replace = str(edit.get("replace") or "")
        if not _edit_is_safe(find, replace, text):
            continue
        text = text.replace(find, replace, 1)
        applied.append({"find": find, "replace": replace, "why": str(edit.get("why") or "")})
    return text, applied


def _edit_is_safe(find: str, replace: str, text: str) -> bool:
    if not find.strip() or find == replace or len(find) > _MAX_FIND_CHARS:
        return False
    if text.count(find) != 1:
        return False
    # Headings, table rows and citations stay as they are.
    if "\n" in find or "#" in find or "|" in find or "\n" in replace or "#" in replace:
        return False
    if not _same_citations(find, replace):
        return False
    # An edit is a correction, not a rewrite.
    return len(find.split()) <= _MAX_FIND_WORDS and len(replace.split()) <= len(find.split()) + 5


def _same_citations(find: str, replace: str) -> bool:
    cites = re.compile(r"\([^()]*\d{4}[a-z]?\)")
    return cites.findall(find) == cites.findall(replace)


def _default_call(system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
    """Claude when available (it catches far more garbled terms than the fast review model)."""
    from services.assignment_llm import STAGE_ACADEMIC_REVIEW, assignment_generate_json, assignment_llm_configured
    from services.claude_client import claude_enabled, generate_json

    if claude_enabled():
        data, _meta = generate_json(
            system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.0, max_retries=1, max_tokens=2000
        )
        return data if isinstance(data, dict) else None
    if not assignment_llm_configured(STAGE_ACADEMIC_REVIEW):
        return None
    data, _meta = assignment_generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        max_retries=1,
        stage=STAGE_ACADEMIC_REVIEW,
    )
    return data if isinstance(data, dict) else None
