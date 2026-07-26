"""Gemini requirement validation against Requirement JSON + rubric."""

from __future__ import annotations

import json
import uuid
from typing import Any

from services.assignment_llm import (
    STAGE_REQUIREMENT_VALIDATION,
    assignment_generate_json,
    assignment_llm_configured,
    assignment_llm_model,
)
from services.assignment_pipeline.models import utc_now

_SYSTEM = """You validate a finished academic assignment against its Requirement JSON and rubric.
Return ONLY JSON:
{
  "passed": true/false,
  "overall_score": 0-100,
  "coverage_checklist": [{"id":"","label":"","passed":true,"notes":""}],
  "rubric_scores": [{"id":"","label":"","score":0-100,"notes":""}],
  "missing_requirements": ["..."],
  "blocking_issues": ["..."],
  "recommendations": ["..."]
}
passed is true only when all critical requirements are met and overall_score >= 70.
Word count must be within ±10% of the required total. Missing mandatory sections are blocking.
"""


class GeminiRequirementValidator:
    VERSION = f"gemini-{assignment_llm_model(STAGE_REQUIREMENT_VALIDATION)}"

    def validate(
        self,
        *,
        document_text: str,
        requirement_json: dict[str, Any],
        citation_pack: dict[str, Any] | None = None,
        formatted_document: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        if not assignment_llm_configured(STAGE_REQUIREMENT_VALIDATION):
            return _heuristic_report(
                document_text=document_text,
                requirement_json=requirement_json,
                project_id=project_id,
                engine_version=f"{self.VERSION}+unconfigured",
            )

        payload = {
            "requirement_json": requirement_json,
            "citation_pack": citation_pack or {},
            "formatted_document": {
                "style_id": (formatted_document or {}).get("style_id"),
                "profile_summary": (formatted_document or {}).get("profile_summary"),
                "word_count": (formatted_document or {}).get("word_count"),
            },
            "document_text": (document_text or "")[:24000],
        }
        data, _meta = assignment_generate_json(
            system_prompt=_SYSTEM,
            user_prompt=json.dumps(payload, ensure_ascii=False, indent=2),
            temperature=0.1,
            max_retries=2,
            stage=STAGE_REQUIREMENT_VALIDATION,
        )
        if not isinstance(data, dict):
            return _heuristic_report(
                document_text=document_text,
                requirement_json=requirement_json,
                project_id=project_id,
                engine_version=f"{self.VERSION}+parse-fallback",
            )
        overall = int(round(float(data.get("overall_score") or 0)))
        overall = max(0, min(100, overall))
        return {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "passed": bool(data.get("passed")) if "passed" in data else overall >= 70,
            "overall_score": overall,
            "coverage_checklist": list(data.get("coverage_checklist") or []),
            "rubric_scores": list(data.get("rubric_scores") or []),
            "missing_requirements": [str(x) for x in (data.get("missing_requirements") or [])],
            "blocking_issues": [str(x) for x in (data.get("blocking_issues") or [])],
            "recommendations": [str(x) for x in (data.get("recommendations") or [])],
            "engine_version": self.VERSION,
            "validated_at": utc_now().isoformat(),
        }


def _heuristic_report(
    *,
    document_text: str,
    requirement_json: dict[str, Any],
    project_id: str | None,
    engine_version: str,
) -> dict[str, Any]:
    words = len((document_text or "").split())
    target = int(requirement_json.get("word_count") or requirement_json.get("estimatedWordCount") or 0)
    missing: list[str] = []
    blocking: list[str] = []
    if target and words < int(target * 0.90):
        msg = f"Word count below ±10% target ({words}/{target})"
        missing.append(msg)
        blocking.append(msg)
    elif target and words > int(target * 1.10):
        msg = f"Word count above ±10% target ({words}/{target})"
        missing.append(msg)
        blocking.append(msg)
    required_sections = list(
        requirement_json.get("required_sections") or requirement_json.get("requiredSections") or []
    )
    low = (document_text or "").lower()
    for section in required_sections:
        label = str(section).strip()
        if not label:
            continue
        base = label.split("(", 1)[0].strip().lower()
        if base in {"cover page", "cover", "title page"}:
            continue
        if base and base not in low:
            missing.append(f"Missing section: {label}")
            blocking.append(f"Missing section: {label}")
    score = 85 if not missing else max(40, 80 - 10 * len(missing))
    return {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "passed": not missing and score >= 70,
        "overall_score": score,
        "coverage_checklist": [
            {
                "id": "word_count",
                "label": "Word count within ±10%",
                "passed": not any("Word count" in m for m in missing),
                "notes": f"{words}/{target}" if target else str(words),
            }
        ],
        "rubric_scores": [],
        "missing_requirements": missing,
        "blocking_issues": blocking,
        "recommendations": ["Address missing requirements before delivery"] if missing else [],
        "engine_version": engine_version,
        "validated_at": utc_now().isoformat(),
        "export_blocked": bool(blocking),
    }
