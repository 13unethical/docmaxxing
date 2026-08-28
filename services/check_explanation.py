"""AI explanation engine — explains pre-computed results, does not score."""

from __future__ import annotations

import re
from typing import Any

from services.gemini_client import generate_json, gemini_enabled, gemini_model

_NUMBER_RE = re.compile(
    r"(?<!\w)(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:\s*(?:%|pts|pt|words?|credits?))?(?!\w)",
    re.I,
)

_COMPLIANCE_CLAIM_RE = re.compile(
    r"\b("
    r"required|requirement|requirements|assignment brief|rubric|word count|word limit|"
    r"reference count|peer[- ]reviewed|meets the|does not meet|compliance|"
    r"section count|required sections?|according to the brief|grading criteria"
    r")\b",
    re.I,
)


def _allowed_numbers(
    *,
    structured: dict[str, Any] | None,
    metrics: dict[str, Any] | None,
    readiness_score: int,
) -> set[str]:
    allowed: set[str] = {str(readiness_score), "100"}
    structured = structured or {}
    metrics = metrics or {}

    for key in ("word_min", "word_max", "font_size", "peer_reviewed_refs", "body_paragraphs"):
        val = structured.get(key)
        if val is not None:
            allowed.add(str(int(val)))
            allowed.add(f"{int(val):,}".replace(",", ","))

    for key in ("word_count", "reference_entries", "in_text_citations", "heading_count", "body_paragraph_count", "paragraph_count"):
        val = metrics.get(key)
        if val is not None:
            allowed.add(str(int(val)))

    expanded: set[str] = set()
    for token in list(allowed):
        expanded.add(token.replace(",", ""))
        if token.isdigit():
            expanded.add(f"{int(token):,}")
    return expanded


def validations_completion_numbers(validations: list[dict[str, Any]]) -> set[str]:
    nums: set[str] = set()
    for v in validations:
        for key in ("completion_pct", "weight", "points_earned", "points_possible"):
            val = v.get(key)
            if val is not None:
                nums.add(str(int(val) if float(val) == int(val) else val))
        detected = str(v.get("detected") or "")
        required = str(v.get("required") or "")
        for part in (detected, required):
            for m in _NUMBER_RE.findall(part):
                nums.add(m.replace(",", "").split()[0])
    return nums


def _collect_allowed_numbers(
    *,
    structured: dict[str, Any] | None,
    metrics: dict[str, Any] | None,
    validations: list[dict[str, Any]],
    readiness_score: int,
) -> set[str]:
    allowed = _allowed_numbers(structured=structured, metrics=metrics, readiness_score=readiness_score)
    allowed |= validations_completion_numbers(validations)
    expanded: set[str] = set()
    for token in allowed:
        expanded.add(token)
        expanded.add(token.replace(",", ""))
        if token.replace(",", "").isdigit():
            n = int(token.replace(",", ""))
            expanded.add(str(n))
            expanded.add(f"{n:,}")
    return expanded


def _number_in_sentence(sentence: str, allowed: set[str]) -> bool:
    for m in _NUMBER_RE.finditer(sentence):
        raw = m.group(0).strip()
        core = raw.replace(",", "").split()[0]
        if core.endswith("%"):
            core = core[:-1]
        if core not in allowed and raw not in allowed:
            try:
                if str(int(float(core))) not in allowed:
                    return True
            except ValueError:
                return True
    return False


def _filter_sentences_with_unknown_numbers(text: str, allowed: set[str]) -> str:
    if not (text or "").strip():
        return text
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [s for s in parts if s and not _number_in_sentence(s, allowed)]
    return " ".join(kept).strip() if kept else text.strip()


def _filter_compliance_claims_without_brief(text: str) -> str:
    if not (text or "").strip():
        return text
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    kept: list[str] = []
    for sentence in parts:
        if not sentence:
            continue
        low = sentence.lower()
        if any(
            phrase in low
            for phrase in (
                "no brief was",
                "no assignment brief",
                "brief was not provided",
                "without a brief",
                "without an assignment brief",
            )
        ):
            kept.append(sentence)
            continue
        if _COMPLIANCE_CLAIM_RE.search(sentence):
            continue
        kept.append(sentence)
    return " ".join(kept).strip() if kept else text.strip()


def _filter_string_list(items: list[str], allowed: set[str], *, has_brief: bool) -> list[str]:
    out: list[str] = []
    for item in items:
        cleaned = _filter_sentences_with_unknown_numbers(str(item), allowed)
        if not has_brief:
            cleaned = _filter_compliance_claims_without_brief(cleaned)
        if cleaned:
            out.append(cleaned)
    return out


def explain_check_results(
    *,
    requirements: str,
    validations: list[dict[str, Any]],
    readiness_score: int,
    metrics: dict[str, Any],
    document_type: str,
    structured_requirements: dict[str, Any] | None = None,
    has_assignment_brief: bool | None = None,
) -> dict[str, Any]:
    """Gemini summarizes validation outcomes; never overrides the numeric score."""
    has_brief = has_assignment_brief if has_assignment_brief is not None else bool((requirements or "").strip())
    diagnostics = {
        "enabled": gemini_enabled(),
        "model": gemini_model(),
        "api_call_success": False,
        "token_usage_estimate": 0,
    }
    allowed = _collect_allowed_numbers(
        structured=structured_requirements,
        metrics=metrics,
        validations=validations,
        readiness_score=readiness_score,
    )
    summary_local = _filter_sentences_with_unknown_numbers(
        _local_summary(validations, readiness_score, metrics=metrics, has_brief=has_brief),
        allowed,
    )
    if not has_brief:
        summary_local = _filter_compliance_claims_without_brief(summary_local)

    if not diagnostics["enabled"]:
        risks = _filter_string_list(_major_risks(validations, has_brief=has_brief), allowed, has_brief=has_brief)
        return {
            "compliance_analysis": {
                "summary": summary_local,
                "alignment_level": _alignment_level(readiness_score),
                "major_risks": risks,
            },
            "gemini_diagnostics": diagnostics,
            "source": "local",
        }

    validation_lines = []
    for v in validations[:14]:
        validation_lines.append(
            f"- {v.get('label')}: required={v.get('required')}, detected={v.get('detected')}, "
            f"completion={v.get('completion_pct')}%, status={v.get('status')}, weight={v.get('weight')}"
        )

    brief_rule = ""
    if not has_brief:
        brief_rule = """
NO-BRIEF MODE (no assignment brief was provided):
- Do NOT claim the document meets or fails any assignment requirement.
- Do NOT mention required section counts, word limits, reference totals, or rubric alignment.
- Only describe observable features of the text (headings, paragraphs, citations present or absent)."""

    system_prompt = f"""You explain academic document check results to a student.

You receive PRE-COMPUTED validation results and a readiness score. You must NOT change, recalculate, or contradict the score.

Return JSON only with keys:
- summary: 2-3 sentences explaining the biggest gaps and what to fix first
- major_risks: array of up to 4 short risk strings if submission now would likely fail grading

Be direct. Reference only the supplied validation rows and metrics.

STRICT RULES:
- Do NOT mention any numeric requirement (counts, limits, percentages, reference totals, word counts, section counts) unless that exact number appears in the validation rows provided.
- Do NOT infer quantities from the assignment brief excerpt.
- Do NOT invent requirements not shown in the validation data.{brief_rule}"""

    user_prompt = (
        f"Document type: {document_type}\n"
        f"Assignment brief provided: {'yes' if has_brief else 'no'}\n"
        f"Readiness score (fixed): {readiness_score}/100\n"
        f"Word count detected in document: {metrics.get('word_count')}\n\n"
        "Validation results (only source of truth for requirements):\n"
        + "\n".join(validation_lines)
    )

    payload, diagnostics = generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.2,
    )
    if not payload:
        risks = _filter_string_list(_major_risks(validations, has_brief=has_brief), allowed, has_brief=has_brief)
        return {
            "compliance_analysis": {
                "summary": summary_local,
                "alignment_level": _alignment_level(readiness_score),
                "major_risks": risks,
            },
            "gemini_diagnostics": diagnostics,
            "source": "local",
        }

    summary = _filter_sentences_with_unknown_numbers(
        str(payload.get("summary") or summary_local).strip(), allowed
    )
    if not has_brief:
        summary = _filter_compliance_claims_without_brief(summary)
    risks_raw = payload.get("major_risks") or _major_risks(validations, has_brief=has_brief)
    if not isinstance(risks_raw, list):
        risks_raw = [str(risks_raw)]
    risks = _filter_string_list(
        [str(x).strip() for x in risks_raw if str(x).strip()],
        allowed,
        has_brief=has_brief,
    )

    return {
        "compliance_analysis": {
            "summary": summary or summary_local,
            "alignment_level": _alignment_level(readiness_score),
            "major_risks": risks[:6],
        },
        "gemini_diagnostics": diagnostics,
        "source": "gemini",
    }


def _alignment_level(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _major_risks(validations: list[dict[str, Any]], *, has_brief: bool) -> list[str]:
    risks = []
    for v in validations:
        if v.get("status") == "PASS":
            continue
        label = v.get("label") or "Check"
        if has_brief:
            if v.get("priority") == "critical" or float(v.get("completion") or 0) < 0.4:
                risks.append(f"{label}: only {v.get('completion_pct')}% complete")
        else:
            detected = v.get("detected")
            if detected:
                risks.append(f"{label}: observed {detected}")
            else:
                risks.append(f"{label}: needs attention")
        if len(risks) >= 4:
            break
    return risks


def _local_summary(
    validations: list[dict[str, Any]],
    score: int,
    *,
    metrics: dict[str, Any],
    has_brief: bool,
) -> str:
    if not has_brief:
        headings = metrics.get("heading_count")
        body = metrics.get("body_paragraph_count")
        words = metrics.get("word_count")
        parts = [
            "No assignment brief was provided, so this review only describes what we see in the text."
        ]
        if words is not None:
            parts.append(f"The draft is about {words} words.")
        if headings is not None:
            parts.append(f"We found {headings} heading-like lines.")
        if body is not None:
            parts.append(f"There are {body} substantive body paragraphs.")
        return " ".join(parts)

    failed = [v for v in validations if v.get("status") not in ("PASS", "SKIP", "NOT_APPLICABLE")]
    if not failed:
        return f"Readiness score is {score}/100. Requirements appear largely met for the checks we could run."
    worst = sorted(failed, key=lambda v: float(v.get("completion") or 0))[:2]
    parts = [f"Readiness score is {score}/100."]
    for v in worst:
        parts.append(
            f"{v.get('label')} is only {v.get('completion_pct')}% complete "
            f"({v.get('detected')} vs {v.get('required')})."
        )
    parts.append("Address the highest-weight gaps shown in the validation list first.")
    return " ".join(parts)
