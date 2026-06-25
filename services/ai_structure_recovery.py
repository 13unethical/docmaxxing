"""
Gemini-assisted academic document structure recovery.

Uses multi-phase Gemini calls with retries and model fallback when documents are large.
Returns explicit failure metadata instead of silent None when Gemini is enabled.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from services.document_structure_engine import (
    _make_node,
    _normalize_doc_type,
    is_heading_like,
    normalize_paragraph_text,
    paragraphs_from_text,
)
from services.gemini_client import estimate_tokens, gemini_enabled, generate_json

logger = logging.getLogger(__name__)

MAX_PARAGRAPHS_FOR_AI = 120
MAX_CHARS_FOR_AI = 48_000
MULTI_PHASE_CHAR_THRESHOLD = 8_000
STRUCTURE_TIMEOUT_S = 120
STRUCTURE_MAX_RETRIES = 4
PARAGRAPH_BATCH_SIZE = 4
PREVIEW_CHARS = 350

STRUCTURE_SYSTEM_PROMPT = """You are an expert at recovering academic document structure from humanized or flattened text where headings and paragraph breaks were removed.

You receive numbered paragraphs from a student academic document. Infer logical structure from topic shifts, discourse cues, citation patterns, and genre conventions — not keyword matching alone.

Return ONE JSON object only (no markdown) with these keys:

- document_type: one of essay, report, research_paper, literature_review, case_study, reflection, learning_journal, dissertation_chapter, thesis_chapter, other
- document_type_confidence: number 0-1
- sections: array of section objects, each with:
  - title: canonical section label (e.g. Introduction, Literature Review, Methodology, Results, Discussion, Reflection, Conclusion, References, Title, Main Body)
  - heading_text: heading to insert in Word (usually same as title; for Title use the inferred document title string)
  - confidence: number 0-1 for this section boundary
  - paragraph_indices: array of 1-based integers referring to the ORIGINAL numbered paragraphs included in this section (every body paragraph exactly once)
  - insert_heading: boolean — true if a Word heading line should be inserted before this section (false for Title when the title is already the first paragraph)
- paragraph_splits: optional array for merged paragraphs — each { "index": 1-based paragraph number, "segments": ["...", "..."] } when one original paragraph clearly contains multiple ideas that should be separate paragraphs

Rules:
- Every original paragraph index must appear in exactly one section (except when paragraph_splits replaces an index with multiple segments).
- Identify title, introduction, body sections appropriate to document_type, conclusion, and references when present.
- References: citation-list paragraphs at the end (Author, Year patterns).
- Do not invent content; only reorganize and label structure.
- Prefer more sections with moderate confidence over one large undifferentiated body.
- If explicit headings already exist as standalone short lines, set insert_heading false for those sections.
"""

CLASSIFY_SYSTEM_PROMPT = """You classify student academic documents from paragraph previews.

Return ONE JSON object only:
- document_type: one of essay, report, research_paper, literature_review, case_study, reflection, learning_journal, dissertation_chapter, thesis_chapter, other
- document_type_confidence: number 0-1

Use genre cues, citation patterns, section-like openings, and assignment style — not keyword matching alone."""

HEADINGS_SYSTEM_PROMPT = """You identify section heading lines in humanized academic documents.

You receive numbered paragraphs (possibly a batch). Find every paragraph that begins or contains a section heading.

Return ONE JSON object only:
- candidates: array of objects, each with:
  - paragraph_index: 1-based integer
  - heading_text: exact heading text to use in Word (include entry titles like "Journal Entry 1: ...")
  - level: integer 1-3 (title=1, major sections=2, subsections=3)
  - confidence: number 0-1

Rules:
- Headings may be embedded at the start of a longer paragraph.
- Include title lines, journal entry headings, reflection, references, introduction, etc.
- Do not invent headings not supported by the paragraph text."""

HIERARCHY_SYSTEM_PROMPT = """You assign every numbered paragraph to academic sections using confirmed heading candidates.

Return ONE JSON object only:
- sections: array of section objects, each with:
  - title: canonical section label
  - heading_text: heading for Word
  - confidence: number 0-1
  - paragraph_indices: 1-based integers for paragraphs in this section (each paragraph in your batch exactly once)
  - insert_heading: boolean
  - level: optional integer 1-3
- paragraph_splits: optional array of { "index": int, "segments": [strings] }

Rules:
- Use the provided document_type and heading candidates.
- Every paragraph index in the batch must appear in exactly one section.
- Do not invent content; only group and label.
- Prefer meaningful sections over one undifferentiated block."""


def _numbered_block(paragraphs: list[str], *, start: int = 1, end: int | None = None) -> str:
    end = end if end is not None else len(paragraphs)
    lines = []
    for idx in range(start, min(end, len(paragraphs)) + 1):
        lines.append(f"[P{idx}]\n{paragraphs[idx - 1]}")
    return "\n\n".join(lines)


def _preview_block(paragraphs: list[str]) -> str:
    lines = []
    for idx, paragraph in enumerate(paragraphs[:MAX_PARAGRAPHS_FOR_AI], start=1):
        words = len(re.findall(r"\b[\w'-]+\b", paragraph))
        preview = paragraph[:PREVIEW_CHARS]
        suffix = "..." if len(paragraph) > PREVIEW_CHARS else ""
        lines.append(f"[P{idx}] ({words} words)\n{preview}{suffix}")
    return "\n\n".join(lines)


def _split_index(item: dict[str, Any]) -> int | None:
    try:
        return int(item.get("index"))
    except (TypeError, ValueError):
        return None


def _apply_splits_with_mapping(
    paragraphs: list[str],
    splits: list[dict[str, Any]],
) -> tuple[list[str], dict[int, list[int]]]:
    split_by_index: dict[int, list[str]] = {}
    for item in splits:
        index = _split_index(item)
        segments = item.get("segments")
        if index is None or index < 1 or index > len(paragraphs) or not isinstance(segments, list):
            continue
        cleaned = [str(s).strip() for s in segments if str(s).strip()]
        if len(cleaned) >= 2:
            split_by_index[index] = cleaned

    if not split_by_index:
        return list(paragraphs), {i: [i] for i in range(1, len(paragraphs) + 1)}

    new_paragraphs: list[str] = []
    old_to_new: dict[int, list[int]] = {}
    for old_idx, para in enumerate(paragraphs, start=1):
        if old_idx in split_by_index:
            start = len(new_paragraphs) + 1
            new_paragraphs.extend(split_by_index[old_idx])
            old_to_new[old_idx] = list(range(start, start + len(split_by_index[old_idx])))
        else:
            new_paragraphs.append(para)
            old_to_new[old_idx] = [len(new_paragraphs)]
    return new_paragraphs, old_to_new


def _remap_indices_after_splits(
    sections: list[dict[str, Any]],
    old_to_new: dict[int, list[int]],
) -> list[dict[str, Any]]:
    remapped: list[dict[str, Any]] = []
    for section in sections:
        old_indices = section.get("paragraph_indices") or []
        new_indices: list[int] = []
        for old in old_indices:
            try:
                oi = int(old)
            except (TypeError, ValueError):
                continue
            new_indices.extend(old_to_new.get(oi, []))
        if not new_indices:
            continue
        updated = dict(section)
        updated["paragraph_indices"] = sorted(set(new_indices))
        remapped.append(updated)
    return remapped


def _merge_diagnostics(phases: list[dict[str, Any]], *, strategy: str) -> dict[str, Any]:
    if not phases:
        return {"strategy": strategy, "api_call_success": False, "failure_reason": "parse_error"}
    success = all(p.get("api_call_success") for p in phases)
    total_retries = sum(int(p.get("retry_count") or 0) for p in phases)
    total_latency = sum(int(p.get("latency_ms") or 0) for p in phases)
    models_attempted: list[str] = []
    for phase in phases:
        for model in phase.get("models_attempted") or [phase.get("model")]:
            if model and model not in models_attempted:
                models_attempted.append(model)
    last = phases[-1]
    merged = {
        "strategy": strategy,
        "api_call_success": success,
        "enabled": last.get("enabled", gemini_enabled()),
        "model": last.get("model"),
        "models_attempted": models_attempted,
        "fallback_activated": any(p.get("fallback_activated") for p in phases),
        "retry_count": total_retries,
        "latency_ms": total_latency,
        "request_chars": sum(int(p.get("request_chars") or 0) for p in phases),
        "token_usage_estimate": sum(int(p.get("token_usage_estimate") or 0) for p in phases),
        "phases": phases,
    }
    if not success:
        failed = next((p for p in reversed(phases) if not p.get("api_call_success")), last)
        merged["failure_reason"] = failed.get("failure_reason")
        merged["http_status"] = failed.get("http_status")
        merged["error_message"] = failed.get("error_message")
    return merged


def _ai_failure_payload(reason: str, diagnostics: dict[str, Any], message: str | None = None) -> dict[str, Any]:
    return {
        "ai_failure": True,
        "failure_reason": reason,
        "error": message or f"AI structure recovery failed: {reason}",
        "recovery_mode": "ai_failed",
        "ai_powered": False,
        "gemini_diagnostics": diagnostics,
    }


def _structure_call(
    *,
    system_prompt: str,
    user_prompt: str,
    phase: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    data, diag = generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.2,
        max_retries=STRUCTURE_MAX_RETRIES,
        timeout_s=STRUCTURE_TIMEOUT_S,
    )
    diag = dict(diag)
    diag["phase"] = phase
    return data, diag


def _paragraph_batches(paragraphs: list[str], batch_size: int = PARAGRAPH_BATCH_SIZE) -> list[tuple[int, int]]:
    if not paragraphs:
        return []
    batches: list[tuple[int, int]] = []
    start = 1
    while start <= len(paragraphs):
        end = min(start + batch_size - 1, len(paragraphs))
        batches.append((start, end))
        start = end + 1
    return batches


def _classify_document(
    paragraphs: list[str],
    document_type: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    hint = _normalize_doc_type(document_type)
    hint_line = f"Suggested document type hint: {hint}\n\n" if hint and hint != "other" else ""
    user_content = (
        f"{hint_line}"
        f"Classify this {len(paragraphs)}-paragraph academic document from previews:\n\n"
        f"{_preview_block(paragraphs)}"
    )
    return _structure_call(
        system_prompt=CLASSIFY_SYSTEM_PROMPT,
        user_prompt=user_content,
        phase="classify",
    )


def _identify_heading_candidates(
    paragraphs: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    phase_diags: list[dict[str, Any]] = []
    for start, end in _paragraph_batches(paragraphs):
        body = _numbered_block(paragraphs, start=start, end=end)
        user_content = (
            f"Identify section heading candidates in paragraphs {start}-{end} "
            f"of a {len(paragraphs)}-paragraph document:\n\n{body}"
        )
        data, diag = _structure_call(
            system_prompt=HEADINGS_SYSTEM_PROMPT,
            user_prompt=user_content,
            phase=f"headings_{start}_{end}",
        )
        phase_diags.append(diag)
        if not data:
            return [], phase_diags
        batch_candidates = data.get("candidates") or []
        if isinstance(batch_candidates, list):
            for item in batch_candidates:
                if isinstance(item, dict):
                    candidates.append(item)
    return candidates, phase_diags


def _recover_hierarchy_batch(
    paragraphs: list[str],
    *,
    start: int,
    end: int,
    document_type: str,
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    body = _numbered_block(paragraphs, start=start, end=end)
    relevant_candidates = [
        c
        for c in candidates
        if isinstance(c.get("paragraph_index"), (int, float))
        and start <= int(c["paragraph_index"]) <= end
    ]
    user_content = (
        f"document_type: {document_type}\n"
        f"paragraph_range: {start}-{end} of {len(paragraphs)}\n"
        f"heading_candidates: {json_dumps_safe(relevant_candidates)}\n\n"
        f"Assign paragraphs {start}-{end} to sections:\n\n{body}"
    )
    return _structure_call(
        system_prompt=HIERARCHY_SYSTEM_PROMPT,
        user_prompt=user_content,
        phase=f"hierarchy_{start}_{end}",
    )


def json_dumps_safe(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _apply_candidate_metadata(
    sections: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_idx: dict[int, dict[str, Any]] = {}
    for candidate in candidates:
        try:
            idx = int(candidate.get("paragraph_index"))
        except (TypeError, ValueError):
            continue
        by_idx[idx] = candidate

    enriched: list[dict[str, Any]] = []
    for section in sections:
        updated = dict(section)
        indices = updated.get("paragraph_indices") or []
        if indices:
            try:
                cand = by_idx.get(int(indices[0]))
            except (TypeError, ValueError):
                cand = None
            if cand:
                if cand.get("heading_text"):
                    updated["heading_text"] = cand["heading_text"]
                if cand.get("level") is not None:
                    updated["level"] = cand["level"]
        enriched.append(updated)
    return enriched


def _merge_hierarchy_sections(section_groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for group in section_groups:
        for section in group:
            if isinstance(section, dict) and section.get("paragraph_indices"):
                merged.append(section)
    return merged


def _dict_sections(data: Any) -> list[dict[str, Any]]:
    """Extract the list of dict sections from a hierarchy batch response."""
    if not isinstance(data, dict):
        return []
    sections = data.get("sections")
    if not isinstance(sections, list):
        return []
    return [s for s in sections if isinstance(s, dict)]


def _section_indices_in_range(section: dict[str, Any], start: int, end: int) -> bool:
    indices = section.get("paragraph_indices")
    if not isinstance(indices, list) or not indices:
        return False
    for raw in indices:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if start <= value <= end:
            return True
    return False


def _chunk_has_mergeable_section(sections: list[dict[str, Any]], start: int, end: int) -> bool:
    """A chunk is valid when at least one section is a dict, has paragraph_indices,
    and owns at least one paragraph inside the batch range [start, end]."""
    return any(_section_indices_in_range(s, start, end) for s in sections)


def _owned_paragraph_indices(sections: list[dict[str, Any]]) -> set[int]:
    owned: set[int] = set()
    for section in sections:
        if not isinstance(section, dict):
            continue
        for raw in section.get("paragraph_indices") or []:
            try:
                owned.add(int(raw))
            except (TypeError, ValueError):
                continue
    return owned


def _recover_multiphase(
    paragraphs: list[str],
    document_type: str | None,
) -> dict[str, Any]:
    phase_diags: list[dict[str, Any]] = []

    classify_data, classify_diag = _classify_document(paragraphs, document_type)
    phase_diags.append(classify_diag)
    if not classify_data:
        diag = _merge_diagnostics(phase_diags, strategy="multi_phase")
        reason = str(diag.get("failure_reason") or "unavailable")
        return _ai_failure_payload(reason, diag)

    doc_type = _normalize_doc_type(str(classify_data.get("document_type") or document_type or "other"))
    type_conf = float(classify_data.get("document_type_confidence") or 0.75)
    type_conf = max(0.0, min(1.0, type_conf))

    candidates, heading_diags = _identify_heading_candidates(paragraphs)
    phase_diags.extend(heading_diags)
    if not heading_diags or not all(d.get("api_call_success") for d in heading_diags):
        diag = _merge_diagnostics(phase_diags, strategy="multi_phase")
        reason = str(diag.get("failure_reason") or "unavailable")
        return _ai_failure_payload(reason, diag)

    paragraph_count = len(paragraphs)
    section_groups: list[list[dict[str, Any]]] = []
    splits: list[dict[str, Any]] = []
    chunk_section_counts: list[dict[str, Any]] = []
    for start, end in _paragraph_batches(paragraphs):
        hierarchy_data, hierarchy_diag = _recover_hierarchy_batch(
            paragraphs,
            start=start,
            end=end,
            document_type=doc_type,
            candidates=candidates,
        )
        sections = _dict_sections(hierarchy_data)
        # A batch that produced no mergeable section gets exactly one retry before
        # the whole recovery is failed.
        if not (hierarchy_data and _chunk_has_mergeable_section(sections, start, end)):
            hierarchy_data, hierarchy_diag = _recover_hierarchy_batch(
                paragraphs,
                start=start,
                end=end,
                document_type=doc_type,
                candidates=candidates,
            )
            sections = _dict_sections(hierarchy_data)

        phase_diags.append(hierarchy_diag)
        chunk_section_counts.append(
            {
                "phase": f"hierarchy_{start}_{end}",
                "start": start,
                "end": end,
                "count": len(sections),
            }
        )

        if not (hierarchy_data and _chunk_has_mergeable_section(sections, start, end)):
            owned_so_far = _owned_paragraph_indices(
                [s for group in section_groups for s in group] + sections
            )
            unowned = sorted(set(range(1, paragraph_count + 1)) - owned_so_far)
            diag = _merge_diagnostics(phase_diags, strategy="multi_phase")
            diag["failure_reason"] = "incomplete_chunk"
            diag["api_call_success"] = False
            diag["chunk_section_counts"] = chunk_section_counts
            diag["coverage_ok"] = False
            diag["unowned_paragraphs"] = unowned
            return _ai_failure_payload("incomplete_chunk", diag)

        section_groups.append(sections)
        batch_splits = hierarchy_data.get("paragraph_splits") or []
        if isinstance(batch_splits, list):
            splits.extend([s for s in batch_splits if isinstance(s, dict)])

    merged_sections = _merge_hierarchy_sections(section_groups)

    # Coverage validation: every original paragraph must be owned by some section
    # before splits are applied. A partial union is never ai_reconstructed.
    owned = _owned_paragraph_indices(merged_sections)
    expected = set(range(1, paragraph_count + 1))
    unowned_paragraphs = sorted(expected - owned)
    coverage_ok = not unowned_paragraphs
    if not coverage_ok:
        diag = _merge_diagnostics(phase_diags, strategy="multi_phase")
        diag["failure_reason"] = "incomplete_coverage"
        diag["api_call_success"] = False
        diag["chunk_section_counts"] = chunk_section_counts
        diag["coverage_ok"] = False
        diag["unowned_paragraphs"] = unowned_paragraphs
        return _ai_failure_payload("incomplete_coverage", diag)

    combined = {
        "document_type": doc_type,
        "document_type_confidence": type_conf,
        "sections": _apply_candidate_metadata(merged_sections, candidates),
        "paragraph_splits": splits,
    }
    try:
        payload = ai_result_to_recovery_payload(combined, original_paragraphs=paragraphs, splits=splits)
    except ValueError as exc:
        diag = _merge_diagnostics(phase_diags, strategy="multi_phase")
        diag["failure_reason"] = "validation_error"
        diag["error_message"] = str(exc)
        diag["api_call_success"] = False
        diag["chunk_section_counts"] = chunk_section_counts
        diag["coverage_ok"] = coverage_ok
        diag["unowned_paragraphs"] = unowned_paragraphs
        return _ai_failure_payload("validation_error", diag, str(exc))

    diag = _merge_diagnostics(phase_diags, strategy="multi_phase")
    diag["chunk_section_counts"] = chunk_section_counts
    diag["coverage_ok"] = True
    diag["unowned_paragraphs"] = []
    payload["gemini_diagnostics"] = diag
    return payload


def _recover_monolithic(
    paragraphs: list[str],
    document_type: str | None,
) -> dict[str, Any]:
    body = _numbered_block(paragraphs)
    if len(body) > MAX_CHARS_FOR_AI:
        body = body[:MAX_CHARS_FOR_AI] + "\n\n[... document truncated for analysis ...]"

    hint = _normalize_doc_type(document_type)
    hint_line = f"Suggested document type hint: {hint}\n\n" if hint and hint != "other" else ""
    user_content = (
        f"{hint_line}"
        f"Recover the academic structure for these {len(paragraphs)} paragraphs:\n\n{body}"
    )
    data, diag = _structure_call(
        system_prompt=STRUCTURE_SYSTEM_PROMPT,
        user_prompt=user_content,
        phase="monolithic",
    )
    diag = dict(diag)
    diag["strategy"] = "monolithic"
    if not isinstance(data, dict):
        reason = str(diag.get("failure_reason") or "unavailable")
        return _ai_failure_payload(reason, diag)
    try:
        payload = ai_result_to_recovery_payload(data, original_paragraphs=paragraphs)
    except ValueError as exc:
        diag["failure_reason"] = "validation_error"
        diag["error_message"] = str(exc)
        diag["api_call_success"] = False
        return _ai_failure_payload("validation_error", diag, str(exc))
    payload["gemini_diagnostics"] = diag
    return payload


def ai_result_to_recovery_payload(
    data: dict[str, Any],
    *,
    original_paragraphs: list[str],
    splits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize LLM JSON into recovery payload compatible with structure engine + formatter."""
    sections_raw = data.get("sections")
    if not isinstance(sections_raw, list) or not sections_raw:
        raise ValueError("AI response missing sections array")

    splits = splits if isinstance(splits, list) else data.get("paragraph_splits") or []
    paragraphs, old_to_new = _apply_splits_with_mapping(original_paragraphs, splits)
    sections_raw = _remap_indices_after_splits(sections_raw, old_to_new)

    doc_type = _normalize_doc_type(str(data.get("document_type") or "other"))
    type_conf = float(data.get("document_type_confidence") or 0.75)
    type_conf = max(0.0, min(1.0, type_conf))

    structure_tree: list[dict[str, Any]] = []
    headings: list[str] = []
    confidence_scores: list[float] = []
    sections_out: list[dict[str, Any]] = []

    for raw in sections_raw:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or raw.get("heading_text") or "Section").strip()[:100]
        heading_text = str(raw.get("heading_text") or title).strip()[:100]
        try:
            conf = float(raw.get("confidence") or 0.7)
        except (TypeError, ValueError):
            conf = 0.7
        conf = max(0.0, min(1.0, conf))
        indices = raw.get("paragraph_indices") or []
        para_indices = sorted({int(i) for i in indices if isinstance(i, (int, float, str)) and str(i).isdigit()})
        para_indices = [i for i in para_indices if 1 <= i <= len(paragraphs)]
        if not para_indices:
            continue
        insert_heading = bool(raw.get("insert_heading", True))
        if insert_heading and heading_text.lower() not in ("title", "preamble"):
            first_para = paragraphs[para_indices[0] - 1] if para_indices else ""
            if normalize_paragraph_text(first_para) == normalize_paragraph_text(heading_text):
                insert_heading = False
            elif is_heading_like(first_para):
                insert_heading = False

        level = 1 if title.lower() == "title" else 2
        raw_level = raw.get("level")
        if isinstance(raw_level, (int, float)) and not isinstance(raw_level, bool):
            level = max(1, min(3, int(raw_level)))
        structure_tree.append(
            _make_node(
                title=title,
                level=level,
                confidence=conf,
                source="ai_inferred",
                paragraph_indices=para_indices,
            )
        )
        structure_tree[-1]["heading_text"] = heading_text
        structure_tree[-1]["insert_heading"] = insert_heading

        headings.append(heading_text)
        confidence_scores.append(conf)
        sections_out.append(
            {
                "title": title,
                "heading_text": heading_text,
                "confidence": conf,
                "paragraph_indices": para_indices,
                "insert_heading": insert_heading,
            }
        )

    if not structure_tree:
        raise ValueError("AI sections did not map to valid paragraphs")

    # Coverage guard: an ai_reconstructed payload must own every paragraph
    # (after splits are applied). Partial coverage is a validation failure.
    owned = _owned_paragraph_indices(sections_out)
    missing = sorted(set(range(1, len(paragraphs) + 1)) - owned)
    if missing:
        raise ValueError(f"incomplete_coverage: paragraphs {missing} unassigned")

    overall = round(sum(confidence_scores) / len(confidence_scores), 2)

    return {
        "headings_present": False,
        "recovery_mode": "ai_reconstructed",
        "inferred_document_type": doc_type,
        "document_type": doc_type,
        "document_type_confidence": round(type_conf, 2),
        "overall_confidence": overall,
        "structure_tree": structure_tree,
        "sections": sections_out,
        "headings": headings,
        "confidence_scores": confidence_scores,
        "paragraphs": paragraphs,
        "paragraph_count": len(paragraphs),
        "word_count": len(re.findall(r"\b[\w'-]+\b", "\n\n".join(paragraphs))),
        "ai_powered": True,
    }


def recover_structure_with_ai(
    *,
    text: str | None = None,
    paragraphs: list[str] | None = None,
    document_type: str | None = None,
) -> dict[str, Any] | None:
    """
    Call Gemini to recover document structure.

    Returns a recovery payload on success, an explicit ai_failure dict on Gemini
    failure, or None only when no paragraphs / Gemini disabled.
    """
    if not gemini_enabled():
        return None

    if paragraphs is None:
        paragraphs = paragraphs_from_text(text or "")
    if not paragraphs:
        return None

    if len(paragraphs) > MAX_PARAGRAPHS_FOR_AI:
        paragraphs = paragraphs[:MAX_PARAGRAPHS_FOR_AI]

    body = _numbered_block(paragraphs)
    estimated_chars = len(body)
    estimated_tokens = estimate_tokens(body)

    try:
        if estimated_chars >= MULTI_PHASE_CHAR_THRESHOLD:
            logger.info(
                "Structure recovery multi-phase mode chars=%s tokens~=%s paragraphs=%s",
                estimated_chars,
                estimated_tokens,
                len(paragraphs),
            )
            return _recover_multiphase(paragraphs, document_type)

        logger.info(
            "Structure recovery monolithic mode chars=%s tokens~=%s paragraphs=%s",
            estimated_chars,
            estimated_tokens,
            len(paragraphs),
        )
        return _recover_monolithic(paragraphs, document_type)
    except Exception:  # noqa: BLE001
        logger.exception("AI structure recovery failed")
        return _ai_failure_payload(
            "unavailable",
            {
                "strategy": "unknown",
                "api_call_success": False,
                "failure_reason": "unavailable",
                "request_chars": estimated_chars,
                "token_usage_estimate": estimated_tokens,
            },
        )
