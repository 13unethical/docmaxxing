"""Section-by-section writer using Claude Sonnet 4 only."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

from services.writer_engine.mock_writer import SectionWriter
from services.writer_engine.models import WriterEngineInput, WriterSection

_CLAUDE_MODEL = "claude-sonnet-4-6"
_CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
_CLAUDE_TIMEOUT_S = 120
_CLAUDE_MAX_TOKENS = 4096


class LLMSectionWriter(SectionWriter):
    VERSION = "llm-writer-1.0"

    def write_section(
        self,
        *,
        section: WriterSection,
        payload: WriterEngineInput,
        revision: bool = False,
    ) -> str:
        result = self.generate_section_result(section=section, payload=payload, revision=revision)
        section.generated_text = result["draft"]
        section.citations_used = result["citations_used"]
        section.warnings = result["warnings"]
        section.generation_time = float(result["generation_time"])
        section.model_used = str(result["model_used"])
        return section.generated_text

    def generate_section_result(
        self,
        *,
        section: WriterSection,
        payload: WriterEngineInput,
        revision: bool = False,
    ) -> dict[str, Any]:
        claude_key = _claude_api_key()
        if not claude_key:
            raise ValueError(
                "Writer generation unavailable: missing Claude API key. "
                "Set ANTHROPIC_API_KEY (or Claude_API_Key)."
            )
        prompt = _build_section_prompt(section=section, payload=payload, revision=revision)
        result = _generate_with_claude(prompt=prompt, claude_key=claude_key)
        target = int(section.estimated_words or result.get("target_words") or 0)
        # Hard word budget: expand until within ±10% (or max attempts).
        from services.assignment_spec import needs_expansion, section_bounds

        max_expand_passes = 3
        for _ in range(max_expand_passes):
            draft_text = str(result.get("draft") or "")
            if not needs_expansion(_draft_word_count(draft_text), target):
                break
            expand_prompt = _build_expansion_prompt(
                section=section,
                payload=payload,
                short_draft=draft_text,
            )
            expanded = _generate_with_claude(prompt=expand_prompt, claude_key=claude_key)
            warnings = list(expanded.get("warnings") or [])
            warnings.append(
                f"Expanded short draft from {_draft_word_count(draft_text)} "
                f"toward {target} words (min {section_bounds(target)[0]})"
            )
            expanded["warnings"] = warnings
            if _draft_word_count(str(expanded.get("draft") or "")) > _draft_word_count(draft_text):
                result = expanded
            else:
                result["warnings"] = list(result.get("warnings") or []) + [
                    "Expansion pass did not increase length; kept previous draft"
                ]
                break
        final_words = _draft_word_count(str(result.get("draft") or ""))
        if needs_expansion(final_words, target):
            result["warnings"] = list(result.get("warnings") or []) + [
                f"HARD_WORD_BUDGET_FAIL: section has {final_words} words; "
                f"required min {section_bounds(target)[0]} of target {target}"
            ]
        return result


def _claude_api_key() -> str:
    # Keep compatibility with existing env naming in this project.
    return (
        (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        or (os.environ.get("Claude_API_Key") or "").strip()
    )


def _draft_word_count(draft: str) -> int:
    return len(str(draft or "").split())


def _needs_expansion(draft: str, target_words: int) -> bool:
    if target_words < 60:
        return False
    return _draft_word_count(draft) < int(target_words * 0.85)


def _build_expansion_prompt(*, section: WriterSection, payload: WriterEngineInput, short_draft: str) -> str:
    current = _draft_word_count(short_draft)
    target = int(section.estimated_words or 0)
    return (
        "You previously wrote a section that is TOO SHORT for the assignment word budget.\n"
        f"Current draft word count: {current}. Required target: about {target} words "
        f"(minimum {int(target * 0.9)}).\n"
        "Expand the draft with more analysis, evidence, and explanation. "
        "Keep the same section title/purpose and academic tone. "
        "Do not add new document sections. Do not invent a different structure.\n"
        "Return ONE strict JSON object only with keys: "
        "title, purpose, target_words, draft, citations_used, warnings, generation_time, model_used.\n"
        f"PREVIOUS_DRAFT:\n{short_draft}\n\n"
        f"SECTION_CONTEXT:\n{json.dumps({'title': section.title, 'purpose': section.objective, 'target_words': target, 'requirement_json': payload.requirement_json}, ensure_ascii=False)}"
    )


def _generate_with_claude(*, prompt: str, claude_key: str) -> dict[str, Any]:
    started = time.monotonic()
    body = {
        "model": _CLAUDE_MODEL,
        "max_tokens": _CLAUDE_MAX_TOKENS,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": claude_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    response = requests.post(
        _CLAUDE_API_URL,
        json=body,
        headers=headers,
        timeout=_CLAUDE_TIMEOUT_S,
    )
    elapsed = time.monotonic() - started
    if not response.ok:
        raise ValueError(f"Claude API error {response.status_code}: {response.text[:500]}")
    payload = response.json()
    content = payload.get("content") or []
    if not isinstance(content, list) or not content:
        raise ValueError("Claude returned empty content")
    text_chunks = [str(part.get("text") or "") for part in content if isinstance(part, dict)]
    raw_text = "\n".join(text_chunks).strip()
    parsed = _parse_section_json(raw_text)
    parsed["generation_time"] = round(float(elapsed), 3)
    parsed["model_used"] = _CLAUDE_MODEL
    return parsed


def _build_section_prompt(*, section: WriterSection, payload: WriterEngineInput, revision: bool) -> str:
    from services.assignment_spec import build_assignment_spec

    blueprint_section = _blueprint_section(payload.blueprint, section.id)
    try:
        spec = build_assignment_spec(payload.requirement_json, project_id=payload.project_id)
        grade_contract = {
            "optimize_for": "maximum predicted grade against uploaded rubric",
            "learning_outcomes": spec.learning_outcomes,
            "rubric_criteria": [c.to_dict() for c in spec.rubric_criteria],
            "assessment_weights": spec.assessment_weights,
            "mandatory_content_rules": spec.mandatory_content_rules,
            "required_lecture_seminar_refs": spec.required_lecture_seminar_refs,
            "required_evidence": spec.required_evidence,
            "citation_requirements": spec.citation_requirements,
            "mandatory_comparisons": spec.mandatory_comparisons,
            "mandatory_reflections": spec.mandatory_reflections,
            "forbidden_content": spec.forbidden_content,
            "section_linked_criteria": (
                spec.section_by_title(section.title).linked_criteria
                if spec.section_by_title(section.title)
                else []
            ),
            "min_rubric_coverage": spec.min_rubric_coverage,
        }
    except Exception:  # noqa: BLE001
        grade_contract = {
            "optimize_for": "maximum predicted grade against uploaded rubric",
            "rubric": payload.requirement_json.get("rubric") or [],
            "learning_outcomes": payload.requirement_json.get("learning_outcomes") or [],
        }

    blueprint_guard = {
        "section_id": section.id,
        "title": section.title,
        "purpose": section.objective,
        "target_words": section.estimated_words,
        "blueprint_section": blueprint_section,
        "research_plan": payload.research_plan,
        "requirement_json": payload.requirement_json,
        "assignment_spec_grade_contract": grade_contract,
        "revision": revision,
    }
    global_word_count = payload.requirement_json.get("word_count") or payload.blueprint.get("total_target_words")
    from services.assignment_spec.validate import is_references_section_title

    rules = (
        "You are an academic section writer optimizing for the UPLOADED GRADING RUBRIC.\n"
        "STRICT RULES:\n"
        "1) Use ONLY the provided blueprint section structure and purpose.\n"
        "2) Do not invent new document structure.\n"
        "3) Write only this one section draft — body prose only.\n"
        "4) Do NOT invent other document sections. Do NOT write a full essay.\n"
        "5) Do NOT include markdown headings in the draft field "
        "(no '#', no '## Introduction', etc.). The pipeline adds the section heading.\n"
        "6) Return ONE strict JSON object only. No markdown. No code fences. No commentary.\n"
        "7) Required keys: title, purpose, target_words, draft, citations_used, warnings, generation_time, model_used.\n"
        "8) The draft field must be a single JSON string with escaped quotes (\\\") and \\n for line breaks.\n"
        f"9) Hard word budget: this section must be about {section.estimated_words} words "
        f"(stay between {max(40, int(section.estimated_words * 0.9))} and "
        f"{max(int(section.estimated_words * 0.9), int(round(section.estimated_words * 1.1)))} words), "
        f"and the full assignment target is {global_word_count or 'the provided blueprint total'} words. "
        "Do not write a short stub — meet the minimum. Do not exceed the maximum.\n"
        "10) citations_used must be a list of citation placeholders like [Author, Year] used in the draft.\n"
        "11) GRADE-DRIVEN WRITING: explicitly satisfy linked rubric criteria and learning outcomes "
        "in assignment_spec_grade_contract. Aim for top-band descriptors. "
        "If lecture/seminar references are required, include at least one concrete lecture or seminar reference. "
        "If this is a reflection section, connect materials to personal major choice / decision-making. "
        "If comparison is mandatory for this section, compare two concepts across fields.\n"
        "12) Never include forbidden content listed in the grade contract.\n"
        "13) warnings should flag any requirement/rubric conflict or missing input.\n"
        "14) generation_time must be numeric and model_used must be string (they may be overridden by caller).\n"
    )
    if is_references_section_title(section.title):
        rules += (
            "15) REFERENCES SECTION: put EACH bibliographic entry on its own line, "
            "separated by a blank line. Do not glue entries into one paragraph.\n"
            "16) Do not use markdown (*italics*, **bold**, or # headings) in citations. "
            "Write book and article titles as plain text.\n"
            "17) Never write placeholder notes such as '(This is a placeholder for a relevant work…)'. "
            "If the brief names a required reading, cite that work with a complete real reference "
            "(author, year, title, publisher or journal). Do not invent fake sources.\n"
        )
    return rules + f"INPUT:\n{json.dumps(blueprint_guard, ensure_ascii=False)}"


def _blueprint_section(blueprint: dict[str, Any], section_id: str) -> dict[str, Any]:
    for item in blueprint.get("sections") or []:
        if str(item.get("id")) == section_id:
            return item
    return {}


def _strip_code_fences(text: str) -> str:
    raw = (text or "").strip()
    if not raw.startswith("```"):
        return raw
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    return text[start : end + 1]


def _parse_section_json(raw_text: str) -> dict[str, Any]:
    cleaned = _strip_code_fences(raw_text)
    candidates = [cleaned]
    extracted = _extract_json_object(cleaned)
    if extracted and extracted not in candidates:
        candidates.append(extracted)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(data, dict):
            return _normalize_section_result(data)

    repaired = _repair_section_json(cleaned)
    if repaired is not None:
        return repaired

    if last_error is not None:
        raise ValueError(str(last_error)) from last_error
    raise ValueError("Model response is not valid JSON")


def _repair_section_json(raw_text: str) -> dict[str, Any] | None:
    """Best-effort recovery when Claude leaves unescaped quotes/newlines in draft."""
    draft_match = re.search(
        r'"draft"\s*:\s*"(?P<draft>.*)"\s*,\s*"citations_used"',
        raw_text,
        flags=re.DOTALL,
    )
    title_match = re.search(r'"title"\s*:\s*"(?P<title>(?:\\.|[^"\\])*)"', raw_text)
    purpose_match = re.search(r'"purpose"\s*:\s*"(?P<purpose>(?:\\.|[^"\\])*)"', raw_text)
    if not draft_match or not title_match:
        return None

    draft_raw = draft_match.group("draft")
    draft = (
        draft_raw.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\r", " ")
    )
    draft = re.sub(r"\n{3,}", "\n\n", draft).strip()
    if not draft:
        return None

    citations: list[str] = []
    cits_start = raw_text.find('"citations_used"')
    warn_start = raw_text.find('"warnings"', cits_start if cits_start >= 0 else 0)
    if cits_start >= 0 and warn_start > cits_start:
        quotations = re.findall(r'"((?:\\.|[^"\\])*)"', raw_text[cits_start:warn_start])
        citations = [_decode_json_string(q) for q in quotations[1:]]

    warnings: list[str] = []
    warn_key = raw_text.find('"warnings"')
    gen_start = raw_text.find('"generation_time"', warn_key if warn_key >= 0 else 0)
    if warn_key >= 0 and gen_start > warn_key:
        quotations = re.findall(r'"((?:\\.|[^"\\])*)"', raw_text[warn_key:gen_start])
        warnings = [_decode_json_string(q) for q in quotations[1:]]

    target_words = 0
    target_match = re.search(r'"target_words"\s*:\s*(\d+)', raw_text)
    if target_match:
        target_words = int(target_match.group(1))

    purpose = _decode_json_string(purpose_match.group("purpose")) if purpose_match else ""
    title = _decode_json_string(title_match.group("title"))
    return _normalize_section_result(
        {
            "title": title,
            "purpose": purpose,
            "target_words": target_words,
            "draft": draft,
            "citations_used": citations,
            "warnings": warnings + ["Recovered malformed Claude JSON for draft field"],
            "generation_time": 0.0,
            "model_used": "",
        }
    )


def _decode_json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")


def _normalize_section_result(data: dict[str, Any]) -> dict[str, Any]:
    title = str(data.get("title") or "").strip()
    purpose = str(data.get("purpose") or "").strip()
    draft = str(data.get("draft") or "").strip()
    try:
        target_words = int(data.get("target_words") or 0)
    except (TypeError, ValueError):
        target_words = 0
    warnings = data.get("warnings")
    draft, trim_warning = _limit_draft_words(draft, target_words)
    citations = data.get("citations_used")
    normalized_warnings = [str(x) for x in warnings] if isinstance(warnings, list) else []
    if trim_warning:
        normalized_warnings.append(trim_warning)
    normalized = {
        "title": title,
        "purpose": purpose,
        "target_words": target_words,
        "draft": draft,
        "citations_used": [str(x) for x in citations] if isinstance(citations, list) else [],
        "warnings": normalized_warnings,
        "generation_time": float(data.get("generation_time") or 0.0),
        "model_used": str(data.get("model_used") or ""),
    }
    if not normalized["title"] or not normalized["draft"]:
        raise ValueError("Section JSON missing required fields: title/draft")
    return normalized


def _limit_draft_words(draft: str, target_words: int) -> tuple[str, str | None]:
    """Clamp section length to AssignmentSpec ±10% band (hard upper bound)."""
    if target_words <= 0:
        return draft, None
    from services.assignment_spec import section_bounds

    _lo, hi = section_bounds(target_words)
    words = draft.split()
    if len(words) <= hi:
        return draft, None
    trimmed_words = words[:hi]
    trimmed = " ".join(trimmed_words).rstrip(" ,;:")
    if trimmed and trimmed[-1] not in ".!?":
        trimmed += "."
    return trimmed, f"Trimmed section from {len(words)} to {len(trimmed_words)} words to respect ±10% budget"
