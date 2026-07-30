"""Word-budget helpers.

Pre-humanize: Gemini may rewrite-condense (StealthWriter rewrites afterward).
Post-humanize: Gemini only returns drop_ids; Python deletes those sentences.
Delivered post-humanize prose must remain StealthWriter text.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from services.assignment_spec.models import AssignmentSpec
from services.assignment_spec.validate import (
    count_body_words,
    count_words,
    is_references_section_title,
    parse_markdown_sections,
    render_structured_markdown,
)
from services.humanizer_engine.heading_utils import join_body_and_references, split_off_references

_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+(?=[\"'“‘(\[]*[A-Z0-9])")
_CITE_RE = re.compile(r"\([A-Z][^)]*\d{4}[^)]*\)|\[[^\]]*\d{4}[^\]]*\]")
_LECTURE_RE = re.compile(
    r"\b(lecture|seminar|module|tutor|workshop|canvas|blackboard|taught\s+session)\b",
    re.I,
)
_THESIS_RE = re.compile(
    r"\b(this\s+(assignment|proposal|essay|paper|journal|study)\s+"
    r"(aims?|will|argues?|examines?|explores?|investigates?)|"
    r"the\s+aim\s+of|research\s+question|objectives?\s+(are|include)|"
    r"the\s+purpose\s+of)\b",
    re.I,
)
_CONTRAST_RE = re.compile(
    r"^\s*(however|nevertheless|on\s+the\s+other\s+hand|conversely|in\s+contrast|"
    r"by\s+contrast|whereas)\b",
    re.I,
)
_FILLER_RE = re.compile(
    r"^\s*(it\s+is\s+important\s+to\s+note|it\s+should\s+be\s+noted|"
    r"as\s+mentioned\s+above|in\s+conclusion\s+of\s+this\s+point|"
    r"this\s+is\s+significant\s+because\s+it)\b",
    re.I,
)

_DROP_SYSTEM = """You choose which EXISTING sentences to DELETE so an academic draft
fits a hard body word budget. You must NOT rewrite or invent text.

Return ONLY JSON:
{
  "drop_ids": ["intro-s3", "intro-s4", "body-s12"],
  "words_removed_estimate": 0,
  "notes": ["why these units"]
}

HARD PROTECT (prefer never drop; only if the section still has enough other prose):
- Sentences with in-text citations (Author, Year) / numbered cites
- Lecture / seminar / module / tutor references
- Learning-outcome or rubric-critical claims (see constraints)
- Mandatory reflections / comparisons / personal-major links
- First definitions of key theories/frameworks in a section
- Aim / thesis / objective statements
- Do not leave a mandatory section with fewer than 2 sentences

LINKED DROP UNITS — drop ALL member ids together, or NONE:
- Question (?) + immediate answer
- Claim + following evidence / citation / example
- Topic sentence + elaboration that only expands it
- Members of one numbered objective / list set
- Contrast pairs (However / On the other hand completing the prior turn)
- Hypothesis + immediate justification
- Method step + immediate outcome of that step

PREFER TO DROP:
- Hedge / throat-clearing without new content
- Repeated paraphrase of a point already made in the same section
- Generic background with no citation / LO / lecture link

FORBIDDEN: returning rewritten content/sections/bodies. Only ids from the list.
"""

_REWRITE_SYSTEM = """You rewrite academic assignment BODY sections so the TOTAL body word count
fits a hard budget — WITHOUT unfinished sentences. Used ONLY before humanization.

Return ONLY JSON:
{
  "sections": [
    {"title": "Exact existing section title", "body": "Full rewritten body WITHOUT ## heading"}
  ],
  "body_words_estimate": 0,
  "notes": ["what changed"]
}

Rules:
- Keep the SAME section titles and order.
- Every section MUST end on a complete sentence.
- Preserve grade; cut filler first; keep citations and LO links.
- Do NOT alter References (not in payload).
"""


@dataclass
class _Sentence:
    id: str
    section_title: str
    text: str
    index_in_section: int


def _split_sentences(text: str) -> list[str]:
    stripped = (text or "").strip()
    if not stripped:
        return []
    parts = _SENTENCE_RE.split(stripped)
    return [p.strip() for p in parts if p.strip()]


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-") or "sec"


def _build_sentence_index(body_markdown: str) -> tuple[list[dict[str, str]], list[_Sentence]]:
    sections = parse_markdown_sections(body_markdown)
    sentences: list[_Sentence] = []
    for section in sections:
        title = (section.get("title") or "").strip()
        if title in {"Preamble", "Document"} or is_references_section_title(title):
            continue
        slug = _slug(title)
        for idx, text in enumerate(_split_sentences(section.get("body") or "")):
            sentences.append(
                _Sentence(
                    id=f"{slug}-s{idx + 1}",
                    section_title=title,
                    text=text,
                    index_in_section=idx,
                )
            )
    return sections, sentences


def _lo_pattern(spec: AssignmentSpec) -> re.Pattern[str] | None:
    terms: list[str] = []
    for item in spec.learning_outcomes or []:
        t = str(item or "").strip()
        if len(t) >= 4:
            terms.append(re.escape(t[:48]))
    for crit in spec.rubric_criteria or []:
        name = str(getattr(crit, "name", "") or getattr(crit, "criterion", "") or "").strip()
        if len(name) >= 4:
            terms.append(re.escape(name[:48]))
    for rule in spec.mandatory_content_rules or []:
        t = str(rule or "").strip()
        if len(t) >= 8:
            terms.append(re.escape(t[:40]))
    if not terms:
        return None
    return re.compile("|".join(terms), re.I)


def _is_protected(s: _Sentence, *, lo_re: re.Pattern[str] | None, group: list[_Sentence]) -> bool:
    text = s.text
    if _CITE_RE.search(text):
        return True
    if _LECTURE_RE.search(text):
        return True
    if _THESIS_RE.search(text):
        return True
    if lo_re and lo_re.search(text):
        return True
    # Keep last two sentences of each section when possible.
    if s.index_in_section >= max(0, len(group) - 2):
        return True
    return False


def _linked_partner_ids(s: _Sentence, group: list[_Sentence]) -> set[str]:
    """Ids that must travel with s if s is dropped (Q-A, claim-evidence, contrast)."""
    partners: set[str] = {s.id}
    i = s.index_in_section
    if i < 0 or i >= len(group):
        return partners
    cur = group[i]
    if cur.text.rstrip().endswith("?") and i + 1 < len(group):
        partners.add(group[i + 1].id)
    if i > 0 and group[i - 1].text.rstrip().endswith("?"):
        partners.add(group[i - 1].id)
    if _CITE_RE.search(cur.text) and i > 0:
        partners.add(group[i - 1].id)
    if i + 1 < len(group) and _CITE_RE.search(group[i + 1].text):
        partners.add(group[i + 1].id)
    if _CONTRAST_RE.search(cur.text) and i > 0:
        partners.add(group[i - 1].id)
    if i + 1 < len(group) and _CONTRAST_RE.search(group[i + 1].text):
        partners.add(group[i + 1].id)
    return partners


def _expand_linked_units(
    drop_ids: list[str],
    sentences: list[_Sentence],
) -> list[str]:
    by_id = {s.id: s for s in sentences}
    by_section: dict[str, list[_Sentence]] = {}
    for s in sentences:
        by_section.setdefault(s.section_title, []).append(s)

    expanded: set[str] = set()
    for sid in drop_ids:
        s = by_id.get(sid)
        if not s:
            continue
        group = by_section.get(s.section_title) or []
        expanded |= _linked_partner_ids(s, group)
    # Preserve order: original drop order then extras.
    out: list[str] = []
    for sid in drop_ids:
        if sid in expanded and sid not in out:
            out.append(sid)
    for sid in sorted(expanded):
        if sid not in out:
            out.append(sid)
    return out


def _heuristic_drop_ids(
    sentences: list[_Sentence],
    *,
    spec: AssignmentSpec,
    need_remove_words: int,
    already_dropped: set[str],
) -> list[str]:
    if need_remove_words <= 0 or not sentences:
        return []

    lo_re = _lo_pattern(spec)
    by_id = {s.id: s for s in sentences}
    by_section: dict[str, list[_Sentence]] = {}
    for s in sentences:
        by_section.setdefault(s.section_title, []).append(s)

    protected: set[str] = set(already_dropped)
    for _title, group in by_section.items():
        for s in group:
            if _is_protected(s, lo_re=lo_re, group=group):
                protected |= _linked_partner_ids(s, group)

    candidates = [s for s in sentences if s.id not in protected]
    candidates.sort(
        key=lambda s: (
            0 if _FILLER_RE.search(s.text) else 1,
            0 if not _CITE_RE.search(s.text) else 1,
            -count_words(s.text),
        )
    )

    remaining = {
        title: sum(1 for s in group if s.id not in already_dropped)
        for title, group in by_section.items()
    }
    drop: list[str] = []
    dropped_set: set[str] = set()
    removed = 0
    for s in candidates:
        unit = {
            uid
            for uid in _linked_partner_ids(s, by_section.get(s.section_title) or [])
            if uid not in already_dropped and uid not in dropped_set
        }
        if not unit:
            continue
        per_section: dict[str, int] = {}
        for uid in unit:
            sent = by_id.get(uid)
            if sent:
                per_section[sent.section_title] = per_section.get(sent.section_title, 0) + 1
        if any(remaining.get(sec, 0) - n < 2 for sec, n in per_section.items()):
            continue
        for uid in unit:
            drop.append(uid)
            dropped_set.add(uid)
            sent = by_id.get(uid)
            if sent:
                remaining[sent.section_title] = remaining.get(sent.section_title, 1) - 1
                removed += count_words(sent.text)
        if removed >= need_remove_words:
            break
    return drop


def _gemini_rank_drop_ids(
    sentences: list[_Sentence],
    *,
    spec: AssignmentSpec,
    current_words: int,
    already_dropped: set[str],
) -> list[str]:
    from services.assignment_llm import (
        STAGE_REVISION,
        assignment_generate_json,
        assignment_llm_configured,
    )

    if not assignment_llm_configured(STAGE_REVISION):
        return []

    available = [s for s in sentences if s.id not in already_dropped]
    if not available:
        return []

    excess = max(0, current_words - spec.max_total_words)
    payload = {
        "task": "rank_sentences_to_delete",
        "current_body_words": current_words,
        "max_total": spec.max_total_words,
        "min_total": spec.min_total_words,
        "target_words": spec.total_word_target,
        "minimum_words_to_remove": excess,
        "constraints": {
            "learning_outcomes": list(spec.learning_outcomes or []),
            "mandatory_content_rules": list(spec.mandatory_content_rules or []),
            "required_lecture_seminar_refs": spec.required_lecture_seminar_refs,
            "mandatory_reflections": list(spec.mandatory_reflections or []),
            "mandatory_comparisons": list(spec.mandatory_comparisons or []),
            "section_word_targets": dict(spec.section_word_targets or {}),
            "rubric_criteria": [c.to_dict() for c in (spec.rubric_criteria or [])][:12],
        },
        "sentences": [
            {
                "id": s.id,
                "section": s.section_title,
                "text": s.text,
                "words": count_words(s.text),
            }
            for s in available
        ],
    }
    data, _ = assignment_generate_json(
        system_prompt=_DROP_SYSTEM,
        user_prompt=json.dumps(payload, ensure_ascii=False, indent=2),
        temperature=0.1,
        max_retries=1,
        stage=STAGE_REVISION,
    )
    if not isinstance(data, dict):
        return []
    if data.get("content") or data.get("sections"):
        return []
    valid = {s.id for s in available}
    out: list[str] = []
    for item in data.get("drop_ids") or []:
        sid = str(item or "").strip()
        if sid in valid and sid not in out:
            out.append(sid)
    return _expand_linked_units(out, sentences)


def _apply_drop_ids(
    sections: list[dict[str, str]],
    sentences: list[_Sentence],
    drop_ids: set[str],
) -> tuple[list[dict[str, str]], set[str]]:
    """Apply drops; never leave a section with fewer than 2 sentences.

    Returns updated sections and the drop ids actually applied.
    """
    by_section: dict[str, list[_Sentence]] = {}
    for s in sentences:
        by_section.setdefault(s.section_title, []).append(s)

    applied: set[str] = set()
    updated: list[dict[str, str]] = []
    for section in sections:
        title = (section.get("title") or "").strip()
        if title in {"Preamble", "Document"} or is_references_section_title(title):
            updated.append(section)
            continue
        group = by_section.get(title, [])
        if not group:
            updated.append(section)
            continue
        kept = [s for s in group if s.id not in drop_ids]
        if len(kept) < 2:
            # Restore shortest dropped sentences (prefer later/section-end) until >= 2.
            dropped_here = [s for s in group if s.id in drop_ids]
            dropped_here.sort(key=lambda s: (count_words(s.text), -s.index_in_section))
            keep_ids = {s.id for s in kept}
            for s in dropped_here:
                keep_ids.add(s.id)
                if len(keep_ids) >= 2:
                    break
            kept = [s for s in group if s.id in keep_ids]
        for s in group:
            if s.id in drop_ids and s not in kept:
                applied.add(s.id)
        updated.append({"title": title, "body": " ".join(s.text for s in kept)})
    return updated, applied


def drop_complete_sentences_to_budget(
    content: str,
    *,
    spec: AssignmentSpec,
    max_rounds: int = 3,
) -> tuple[str, dict[str, Any]]:
    """Delete complete sentences (AI-ranked + linked units) until body <= hard max."""
    meta: dict[str, Any] = {"trimmed": False, "method": None, "dropped_ids": []}
    body, refs = split_off_references(content or "")
    body_words = count_body_words(body)
    if not spec.total_word_target or body_words <= spec.max_total_words:
        meta["body_words"] = body_words
        return content or "", meta

    sections, sentences = _build_sentence_index(body)
    if not sentences:
        meta["body_words"] = body_words
        return content or "", meta

    dropped: set[str] = set()
    current = body_words
    used_gemini = False

    for _round in range(max_rounds):
        if current <= spec.max_total_words:
            break
        need = current - spec.max_total_words
        ranked = _gemini_rank_drop_ids(
            sentences,
            spec=spec,
            current_words=current,
            already_dropped=dropped,
        )
        if ranked:
            used_gemini = True
        else:
            ranked = _heuristic_drop_ids(
                sentences,
                spec=spec,
                need_remove_words=need,
                already_dropped=dropped,
            )
            ranked = _expand_linked_units(ranked, sentences)
        new_ids = [sid for sid in ranked if sid not in dropped]
        if not new_ids:
            break
        candidate = dropped | set(new_ids)
        sections, applied = _apply_drop_ids(sections, sentences, candidate)
        if not applied - dropped:
            break
        dropped |= applied
        current = count_body_words(render_structured_markdown(sections))

    fitted = join_body_and_references(render_structured_markdown(sections), refs)
    after = count_body_words(fitted)
    meta.update(
        {
            "trimmed": after < body_words and bool(dropped),
            "method": "gemini_ranked_sentence_drop" if used_gemini else "heuristic_sentence_drop",
            "dropped_ids": sorted(dropped),
            "body_words": after,
            "before_body_words": body_words,
        }
    )
    return fitted, meta


def fit_humanized_content_to_budget(
    content: str,
    *,
    spec: AssignmentSpec,
) -> tuple[str, dict[str, Any]]:
    """Post-humanize budget fit — deletion only, no Gemini rewrite."""
    return drop_complete_sentences_to_budget(content, spec=spec)


def gemini_trim_markdown_to_budget(
    content: str,
    *,
    spec: AssignmentSpec,
    current_words: int | None = None,
) -> str | None:
    """Pre-humanize rewrite-condense (OK — StealthWriter rewrites afterward)."""
    from services.assignment_llm import (
        STAGE_REVISION,
        assignment_generate_json,
        assignment_llm_configured,
    )

    if not assignment_llm_configured(STAGE_REVISION):
        return None

    body, refs = split_off_references(content or "")
    total = int(current_words if current_words is not None else count_body_words(body))
    if total <= spec.max_total_words:
        return content

    excess = total - spec.max_total_words
    sections = [
        s
        for s in parse_markdown_sections(body)
        if not is_references_section_title(s.get("title") or "")
    ]
    payload = {
        "task": "rewrite_condense_pre_humanize",
        "current_body_words": total,
        "min_total": spec.min_total_words,
        "max_total": spec.max_total_words,
        "target_words": spec.total_word_target,
        "minimum_words_to_remove": excess,
        "sections": [
            {
                "title": s["title"],
                "body": s["body"],
                "target_words": (
                    spec.section_by_title(s["title"]).target_words
                    if spec.section_by_title(s["title"])
                    else 0
                ),
                "current_words": count_words(s["body"]),
            }
            for s in sections
            if s["title"] not in {"Preamble", "Document"}
        ],
    }
    data, _meta = assignment_generate_json(
        system_prompt=_REWRITE_SYSTEM,
        user_prompt=json.dumps(payload, ensure_ascii=False, indent=2),
        temperature=0.15,
        max_retries=1,
        stage=STAGE_REVISION,
    )
    if not isinstance(data, dict):
        return None

    by_title = {s["title"].strip().lower(): s for s in sections}
    updated = False
    for item in data.get("sections") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        body_text = str(item.get("body") or "").strip()
        if not title or not body_text or is_references_section_title(title):
            continue
        section = by_title.get(title.lower())
        if section is None:
            continue
        if count_words(body_text) < max(20, int(count_words(section.get("body") or "") * 0.45)):
            continue
        if not _ends_with_complete_sentence(body_text):
            continue
        section["body"] = body_text
        updated = True
    if not updated:
        return None
    trimmed_body = render_structured_markdown(sections)
    trimmed_words = count_body_words(trimmed_body)
    if trimmed_words >= total or trimmed_words < spec.min_total_words:
        return None
    return join_body_and_references(trimmed_body, refs)


def fit_content_to_word_budget(
    content: str,
    *,
    spec: AssignmentSpec,
) -> tuple[str, dict[str, Any]]:
    """Pre-humanize fit: rewrite-condense if needed (later humanized)."""
    meta: dict[str, Any] = {"trimmed": False, "method": None}
    body_words = count_body_words(content or "")
    if not spec.total_word_target or body_words <= spec.max_total_words:
        meta["body_words"] = body_words
        return content or "", meta

    trimmed = gemini_trim_markdown_to_budget(content, spec=spec, current_words=body_words)
    if trimmed:
        after = count_body_words(trimmed)
        meta.update(
            {
                "trimmed": True,
                "method": "gemini_rewrite_condense_pre_humanize",
                "body_words": after,
            }
        )
        return trimmed, meta

    meta.update({"body_words": body_words, "method": "keep_complete_prose"})
    return content or "", meta


def apply_trimmed_markdown_to_session(session: Any, trimmed_markdown: str) -> bool:
    """Write condensed section bodies back onto a writer session (pre-humanize)."""
    body, _refs = split_off_references(trimmed_markdown)
    by_title = {
        s["title"].strip().lower(): s["body"]
        for s in parse_markdown_sections(body)
    }
    changed = False
    for section in session.sections:
        if is_references_section_title(section.title or ""):
            continue
        body_text = by_title.get((section.title or "").strip().lower())
        if body_text is None:
            continue
        if body_text.strip() == (section.generated_text or "").strip():
            continue
        if not _ends_with_complete_sentence(body_text):
            continue
        section.generated_text = body_text.strip()
        section.warnings = list(section.warnings) + [
            "Pre-humanize rewrite-condense applied to fit word budget"
        ]
        changed = True
    return changed


def _ends_with_complete_sentence(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < 12:
        return False
    return bool(re.search(r'[.!?…]["\')\]]*\s*$', stripped))
