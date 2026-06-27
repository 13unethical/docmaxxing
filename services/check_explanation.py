"""AI explanation engine — explains pre-computed results, does not score."""

from __future__ import annotations

from typing import Any

from services.gemini_client import generate_json, gemini_enabled, gemini_model


def explain_check_results(
    *,
    requirements: str,
    validations: list[dict[str, Any]],
    readiness_score: int,
    metrics: dict[str, Any],
    document_type: str,
) -> dict[str, Any]:
    """Gemini summarizes validation outcomes; never overrides the numeric score."""
    diagnostics = {
        "enabled": gemini_enabled(),
        "model": gemini_model(),
        "api_call_success": False,
        "token_usage_estimate": 0,
    }
    summary_local = _local_summary(validations, readiness_score)

    if not diagnostics["enabled"]:
        return {
            "summary": summary_local,
            "action_plan_narrative": summary_local,
            "compliance_analysis": {
                "summary": summary_local,
                "alignment_level": _alignment_level(readiness_score),
                "major_risks": _major_risks(validations),
            },
            "formatting_recommendations": _recommendations_from_validations(validations),
            "gemini_diagnostics": diagnostics,
            "source": "local",
        }

    validation_lines = []
    for v in validations[:14]:
        validation_lines.append(
            f"- {v.get('label')}: required={v.get('required')}, detected={v.get('detected')}, "
            f"completion={v.get('completion_pct')}%, status={v.get('status')}, weight={v.get('weight')}"
        )

    system_prompt = """You explain academic document check results to a student.

You receive PRE-COMPUTED validation results and a readiness score. You must NOT change, recalculate, or contradict the score.

Return JSON only with keys:
- summary: 2-3 sentences explaining the biggest gaps and what to fix first
- action_plan_narrative: array of 3-5 short actionable strings ordered by impact
- major_risks: array of up to 4 short risk strings if submission now would likely fail grading

Be direct. Reference the supplied metrics. Do not invent requirements not in the data."""

    user_prompt = (
        f"Document type: {document_type}\n"
        f"Readiness score (fixed): {readiness_score}/100\n"
        f"Word count: {metrics.get('word_count')}\n\n"
        "Requirements excerpt:\n"
        f"{(requirements or '')[:4000]}\n\n"
        "Validation results:\n"
        + "\n".join(validation_lines)
    )

    payload, diagnostics = generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.2,
    )
    if not payload:
        return {
            "summary": summary_local,
            "action_plan_narrative": _recommendations_from_validations(validations),
            "compliance_analysis": {
                "summary": summary_local,
                "alignment_level": _alignment_level(readiness_score),
                "major_risks": _major_risks(validations),
            },
            "formatting_recommendations": _recommendations_from_validations(validations),
            "gemini_diagnostics": diagnostics,
            "source": "local",
        }

    summary = str(payload.get("summary") or summary_local).strip()
    narrative = payload.get("action_plan_narrative") or payload.get("formatting_recommendations") or []
    if not isinstance(narrative, list):
        narrative = [str(narrative)]
    risks = payload.get("major_risks") or _major_risks(validations)
    if not isinstance(risks, list):
        risks = [str(risks)]

    return {
        "summary": summary,
        "action_plan_narrative": [str(x).strip() for x in narrative if str(x).strip()][:6],
        "compliance_analysis": {
            "summary": summary,
            "alignment_level": _alignment_level(readiness_score),
            "major_risks": [str(x).strip() for x in risks if str(x).strip()][:6],
        },
        "formatting_recommendations": [str(x).strip() for x in narrative if str(x).strip()][:6],
        "gemini_diagnostics": diagnostics,
        "source": "gemini",
    }


def _alignment_level(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _major_risks(validations: list[dict[str, Any]]) -> list[str]:
    risks = []
    for v in validations:
        if v.get("status") == "PASS":
            continue
        if v.get("priority") == "critical" or float(v.get("completion") or 0) < 0.4:
            risks.append(f"{v.get('label')}: only {v.get('completion_pct')}% complete")
        if len(risks) >= 4:
            break
    return risks


def _recommendations_from_validations(validations: list[dict[str, Any]]) -> list[str]:
    from services.check_scoring import build_action_plan

    return [s["action"] for s in build_action_plan(validations)]


def _local_summary(validations: list[dict[str, Any]], score: int) -> str:
    failed = [v for v in validations if v.get("status") not in ("PASS", "SKIP")]
    if not failed:
        return f"Readiness score is {score}/100. Requirements appear largely met for the checks we could run."
    worst = sorted(failed, key=lambda v: float(v.get("completion") or 0))[:2]
    parts = [f"Readiness score is {score}/100."]
    for v in worst:
        parts.append(f"{v.get('label')} is only {v.get('completion_pct')}% complete ({v.get('detected')} vs {v.get('required')}).")
    parts.append("Fix the highest-weight gaps first — especially word count and references.")
    return " ".join(parts)
