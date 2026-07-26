"""Gemini-backed academic reviewer for the assignment pipeline."""

from __future__ import annotations

import json
import uuid
from typing import Any

from services.assignment_llm import (
    STAGE_ACADEMIC_REVIEW,
    assignment_generate_json,
    assignment_llm_configured,
    assignment_llm_model,
)
from services.assignment_pipeline.models import utc_now
from services.reviewer_engine.mock_reviewer import MockAcademicReviewer
from services.reviewer_engine.models import (
    ChecklistItem,
    IssueSeverity,
    QualityScores,
    ReviewEngineInput,
    ReviewIssue,
    ReviewReport,
)

_SYSTEM = """You are a strict academic reviewer for university assignments.
Evaluate the draft against the requirement JSON, rubric, research plan, and blueprint.
Return ONLY valid JSON with this shape:
{
  "overall_score": 0-100,
  "passed": true/false,
  "requirement_checklist": [{"id":"","label":"","passed":true,"score":0-100,"notes":""}],
  "rubric_checklist": [{"id":"","label":"","passed":true,"score":0-100,"notes":""}],
  "issues": [{"issue_id":"","category":"","severity":"low|medium|high|critical","section":"","description":"","suggested_fix":""}],
  "recommendations": ["..."],
  "quality_scores": {
    "structure":0-100,"research":0-100,"critical_thinking":0-100,"evidence":0-100,
    "formatting":0-100,"language":0-100,"academic_tone":0-100,"overall":0-100
  }
}
passed must be true only when overall_score >= 75.
Prefer actionable issues with concrete suggested_fix text tied to a section title.
"""


class GeminiAcademicReviewer:
    VERSION = f"gemini-{assignment_llm_model(STAGE_ACADEMIC_REVIEW)}"

    def __init__(self, *, fallback: MockAcademicReviewer | None = None) -> None:
        self._fallback = fallback or MockAcademicReviewer()

    def review(self, payload: ReviewEngineInput) -> ReviewReport:
        if not assignment_llm_configured(STAGE_ACADEMIC_REVIEW):
            report = self._fallback.review(payload)
            report.engine_version = f"{self._fallback.VERSION}+unconfigured"
            return report

        user_prompt = _build_user_prompt(payload)
        data, meta = assignment_generate_json(
            system_prompt=_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.15,
            max_retries=2,
            stage=STAGE_ACADEMIC_REVIEW,
        )
        if not isinstance(data, dict):
            report = self._fallback.review(payload)
            report.engine_version = f"{self._fallback.VERSION}+parse-fallback"
            return report

        try:
            return _report_from_llm(data, payload=payload, engine_version=self.VERSION, meta=meta)
        except Exception:  # noqa: BLE001
            report = self._fallback.review(payload)
            report.engine_version = f"{self._fallback.VERSION}+map-fallback"
            return report


def _build_user_prompt(payload: ReviewEngineInput) -> str:
    draft = payload.draft or {}
    content = str(draft.get("content") or "")
    if len(content) > 24000:
        content = content[:24000] + "\n…[truncated]"
    bundle = {
        "requirement_json": payload.requirement_json,
        "research_plan": _compact(payload.research_plan),
        "blueprint": _compact(payload.blueprint),
        "draft_meta": {
            "id": draft.get("id"),
            "title": draft.get("title"),
            "total_words": draft.get("total_words"),
            "version": draft.get("version"),
        },
        "draft_content": content,
    }
    return json.dumps(bundle, ensure_ascii=False, indent=2)


def _compact(obj: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(obj or {}, ensure_ascii=False)
    if len(raw) <= 8000:
        return dict(obj or {})
    return {"_truncated": True, "preview": raw[:8000]}


def _report_from_llm(
    data: dict[str, Any],
    *,
    payload: ReviewEngineInput,
    engine_version: str,
    meta: dict[str, Any],
) -> ReviewReport:
    del meta
    overall = int(round(float(data.get("overall_score") or 0)))
    overall = max(0, min(100, overall))
    qs = QualityScores.from_dict(data.get("quality_scores") or {})
    if not qs.overall:
        qs.overall = overall
    issues = [_issue_from_dict(item, index=i) for i, item in enumerate(data.get("issues") or [])]
    return ReviewReport(
        id=str(uuid.uuid4()),
        project_id=payload.project_id,
        overall_score=overall,
        passed=bool(data.get("passed")) if "passed" in data else overall >= 75,
        requirement_checklist=[
            ChecklistItem.from_dict(item) for item in (data.get("requirement_checklist") or []) if isinstance(item, dict)
        ],
        rubric_checklist=[
            ChecklistItem.from_dict(item) for item in (data.get("rubric_checklist") or []) if isinstance(item, dict)
        ],
        issues=issues,
        recommendations=[str(x) for x in (data.get("recommendations") or []) if str(x).strip()],
        quality_scores=qs,
        engine_version=engine_version,
        reviewed_at=utc_now(),
    )


def _issue_from_dict(data: dict[str, Any], *, index: int) -> ReviewIssue:
    try:
        severity = IssueSeverity(str(data.get("severity") or IssueSeverity.MEDIUM.value).lower())
    except ValueError:
        severity = IssueSeverity.MEDIUM
    return ReviewIssue(
        issue_id=str(data.get("issue_id") or f"issue-{index + 1}"),
        category=str(data.get("category") or "quality"),
        severity=severity,
        section=str(data.get("section") or ""),
        description=str(data.get("description") or ""),
        suggested_fix=str(data.get("suggested_fix") or ""),
    )
