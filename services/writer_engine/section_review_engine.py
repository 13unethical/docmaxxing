"""Section review engine — Gemini or Claude per ASSIGNMENT_LLM."""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

import requests

from services.assignment_pipeline.models import utc_now
from services.assignment_llm import assignment_llm_model, assignment_uses_gemini
from services.gemini_client import generate_json, gemini_enabled, gemini_model
from services.writer_engine.llm_writer import _claude_api_key
from services.writer_engine.models import SectionReview, WriterEngineInput, WriterSection

_CLAUDE_MODEL = "claude-sonnet-4-6"
_CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
_CLAUDE_TIMEOUT_S = 90


class SectionReviewer(Protocol):
    def review_section(self, *, section: WriterSection, payload: WriterEngineInput) -> SectionReview:
        ...


class GeminiSectionReviewer:
    """Section reviewer — follows assignment LLM router (Gemini by default)."""

    VERSION = assignment_llm_model()
    _INVALID_JSON_RETRIES = 2

    def review_section(self, *, section: WriterSection, payload: WriterEngineInput) -> SectionReview:
        if not section.generated_text.strip():
            return _empty_section_review()

        review_input = _review_input(section=section, payload=payload)
        claude_key = _claude_api_key()
        errors: list[str] = []

        def try_gemini() -> SectionReview | None:
            if not gemini_enabled():
                return None
            try:
                return _review_with_gemini(review_input=review_input)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Gemini: {exc}")
                return None

        def try_claude() -> SectionReview | None:
            if not claude_key:
                return None
            try:
                return _review_with_claude(review_input=review_input, claude_key=claude_key)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Claude: {exc}")
                return None

        if assignment_uses_gemini():
            result = try_gemini() or try_claude()
        else:
            result = try_claude() or try_gemini()

        if result is not None:
            return result

        if errors:
            return _failed_section_review("; ".join(errors))
        return _failed_section_review("No review provider configured (GOOGLE_API_KEY or ANTHROPIC_API_KEY).")


def _empty_section_review() -> SectionReview:
    return SectionReview(
        passed=False,
        score=0,
        requirement_coverage=0,
        argument_quality=0,
        academic_style=0,
        citation_quality=0,
        critical_thinking=0,
        missing_points=["Section text is empty"],
        warnings=["No generated content to review"],
        needs_revision=True,
        review_message="Section text is empty.",
        reviewed_at=utc_now(),
    )


def _failed_section_review(message: str) -> SectionReview:
    return SectionReview(
        passed=False,
        score=0,
        requirement_coverage=0,
        argument_quality=0,
        academic_style=0,
        citation_quality=0,
        critical_thinking=0,
        missing_points=[],
        warnings=[message],
        needs_revision=True,
        review_message=f"Section review failed: {message}",
        reviewed_at=utc_now(),
    )


def _review_input(*, section: WriterSection, payload: WriterEngineInput) -> dict[str, Any]:
    return {
        "section": {
            "id": section.id,
            "title": section.title,
            "purpose": section.objective,
            "target_words": section.estimated_words,
            "draft": section.generated_text,
            "citations_used": section.citations_used,
        },
        "requirement_json": payload.requirement_json,
        "research_json": payload.research_plan,
        "blueprint_json": payload.blueprint,
    }


def _review_system_prompt() -> str:
    return (
        "You are an academic section reviewer. "
        "Do NOT rewrite text. Evaluate only and return strict JSON: "
        "score,requirement_coverage,argument_quality,academic_style,citation_quality,"
        "critical_thinking,missing_points,warnings,needs_revision,review_message."
    )


def _review_with_claude(*, review_input: dict[str, Any], claude_key: str) -> SectionReview:
    prompt = (
        f"{_review_system_prompt()}\n\n"
        f"INPUT:\n{json.dumps(review_input, ensure_ascii=False)}"
    )
    body = {
        "model": _CLAUDE_MODEL,
        "max_tokens": 1200,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": claude_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    started = time.monotonic()
    response = requests.post(
        _CLAUDE_API_URL,
        json=body,
        headers=headers,
        timeout=_CLAUDE_TIMEOUT_S,
    )
    _ = time.monotonic() - started
    if not response.ok:
        raise ValueError(f"Claude API error {response.status_code}: {response.text[:500]}")
    payload = response.json()
    content = payload.get("content") or []
    text_chunks = [str(part.get("text") or "") for part in content if isinstance(part, dict)]
    raw_text = "\n".join(text_chunks).strip()
    data = _parse_review_json(raw_text)
    return _to_section_review(data)


def _review_with_gemini(*, review_input: dict[str, Any]) -> SectionReview:
    user_prompt = json.dumps(review_input, ensure_ascii=False)
    last_error = "Reviewer returned invalid JSON"
    for _ in range(GeminiSectionReviewer._INVALID_JSON_RETRIES + 1):
        data, diagnostics = generate_json(
            system_prompt=_review_system_prompt(),
            user_prompt=user_prompt,
            model=gemini_model(),
            temperature=0.1,
            max_retries=2,
        )
        if not isinstance(data, dict):
            last_error = str(
                diagnostics.get("error_message") or diagnostics.get("failure_reason") or last_error
            )
            continue
        try:
            return _to_section_review(data)
        except ValueError as exc:
            last_error = str(exc)
            continue
    return _failed_section_review(last_error)


def _parse_review_json(raw_text: str) -> dict[str, Any]:
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(raw_text[start : end + 1])
        else:
            raise ValueError("Model response is not valid JSON") from None
    if not isinstance(data, dict):
        raise ValueError("Review response JSON is not an object")
    return data


def _to_section_review(data: dict[str, Any]) -> SectionReview:
    required = [
        "score",
        "requirement_coverage",
        "argument_quality",
        "academic_style",
        "citation_quality",
        "critical_thinking",
        "missing_points",
        "warnings",
        "needs_revision",
        "review_message",
    ]
    for key in required:
        if key not in data:
            raise ValueError(f"Missing review field: {key}")
    missing_points = data.get("missing_points")
    warnings = data.get("warnings")
    if not isinstance(missing_points, list) or not isinstance(warnings, list):
        raise ValueError("missing_points and warnings must be arrays")

    score = int(data.get("score") or 0)
    needs_revision = bool(data.get("needs_revision"))
    return SectionReview(
        passed=not needs_revision,
        score=score,
        requirement_coverage=int(data.get("requirement_coverage") or 0),
        argument_quality=int(data.get("argument_quality") or 0),
        academic_style=int(data.get("academic_style") or 0),
        citation_quality=int(data.get("citation_quality") or 0),
        critical_thinking=int(data.get("critical_thinking") or 0),
        missing_points=[str(x) for x in missing_points],
        warnings=[str(x) for x in warnings],
        needs_revision=needs_revision,
        review_message=str(data.get("review_message") or ""),
        reviewed_at=utc_now(),
    )
