"""Section-by-section writer using Claude Sonnet 4 with Gemini fallback."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

from services.assignment_llm import STAGE_WRITER, assignment_uses_claude
from services.gemini_client import generate_json, gemini_enabled, gemini_model
from services.writer_engine.mock_writer import SectionWriter
from services.writer_engine.models import WriterEngineInput, WriterSection

_CLAUDE_MODEL = "claude-sonnet-4-6"
_CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
_CLAUDE_TIMEOUT_S = 120


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
        prompt = _build_section_prompt(section=section, payload=payload, revision=revision)

        claude_key = _claude_api_key()
        errors: list[str] = []
        if claude_key:
            try:
                return _generate_with_claude(prompt=prompt, claude_key=claude_key)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Claude: {exc}")

        if gemini_enabled() and not assignment_uses_claude(STAGE_WRITER):
            try:
                return _generate_with_gemini(prompt=prompt)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Gemini: {exc}")

        if errors:
            raise ValueError("; ".join(errors))
        raise ValueError(
            "Writer generation unavailable: missing Claude API key and Gemini GOOGLE_API_KEY. "
            "Set ANTHROPIC_API_KEY (or Claude_API_Key) or GOOGLE_API_KEY."
        )


def _claude_api_key() -> str:
    # Keep compatibility with existing env naming in this project.
    return (
        (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        or (os.environ.get("Claude_API_Key") or "").strip()
    )


def _generate_with_claude(*, prompt: str, claude_key: str) -> dict[str, Any]:
    started = time.monotonic()
    body = {
        "model": _CLAUDE_MODEL,
        "max_tokens": 2200,
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


def _generate_with_gemini(*, prompt: str) -> dict[str, Any]:
    started = time.monotonic()
    data, diagnostics = generate_json(
        system_prompt=(
            "Return strict JSON only for section writing. "
            "No markdown, no code fences."
        ),
        user_prompt=prompt,
        model=gemini_model(),
        temperature=0.3,
        max_retries=2,
    )
    elapsed = time.monotonic() - started
    if not isinstance(data, dict):
        raise ValueError(
            f"Gemini writer error: {diagnostics.get('error_message') or diagnostics.get('failure_reason')}"
        )
    parsed = _normalize_section_result(data)
    parsed["generation_time"] = round(float(elapsed), 3)
    parsed["model_used"] = str(diagnostics.get("model") or gemini_model())
    return parsed


def _build_section_prompt(*, section: WriterSection, payload: WriterEngineInput, revision: bool) -> str:
    blueprint_section = _blueprint_section(payload.blueprint, section.id)
    blueprint_guard = {
        "section_id": section.id,
        "title": section.title,
        "purpose": section.objective,
        "target_words": section.estimated_words,
        "blueprint_section": blueprint_section,
        "research_plan": payload.research_plan,
        "requirement_json": payload.requirement_json,
        "revision": revision,
    }
    return (
        "You are an academic section writer.\n"
        "STRICT RULES:\n"
        "1) Use ONLY the provided blueprint section structure and purpose.\n"
        "2) Do not invent new document structure.\n"
        "3) Write only this one section draft.\n"
        "4) Return strict JSON with keys: title,purpose,target_words,draft,citations_used,warnings,generation_time,model_used.\n"
        "5) citations_used must be a list of citation placeholders like [Author, Year] used in the draft.\n"
        "6) warnings should flag any requirement conflict or missing input.\n"
        "7) generation_time must be numeric and model_used must be string (they may be overridden by caller).\n\n"
        f"INPUT:\n{json.dumps(blueprint_guard, ensure_ascii=False)}"
    )


def _blueprint_section(blueprint: dict[str, Any], section_id: str) -> dict[str, Any]:
    for item in blueprint.get("sections") or []:
        if str(item.get("id")) == section_id:
            return item
    return {}


def _parse_section_json(raw_text: str) -> dict[str, Any]:
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(raw_text[start : end + 1])
        else:
            raise ValueError("Model response is not valid JSON")
    if not isinstance(data, dict):
        raise ValueError("Section response JSON is not an object")
    return _normalize_section_result(data)


def _normalize_section_result(data: dict[str, Any]) -> dict[str, Any]:
    title = str(data.get("title") or "").strip()
    purpose = str(data.get("purpose") or "").strip()
    draft = str(data.get("draft") or "").strip()
    try:
        target_words = int(data.get("target_words") or 0)
    except (TypeError, ValueError):
        target_words = 0
    citations = data.get("citations_used")
    warnings = data.get("warnings")
    normalized = {
        "title": title,
        "purpose": purpose,
        "target_words": target_words,
        "draft": draft,
        "citations_used": [str(x) for x in citations] if isinstance(citations, list) else [],
        "warnings": [str(x) for x in warnings] if isinstance(warnings, list) else [],
        "generation_time": float(data.get("generation_time") or 0.0),
        "model_used": str(data.get("model_used") or ""),
    }
    if not normalized["title"] or not normalized["draft"]:
        raise ValueError("Section JSON missing required fields: title/draft")
    return normalized
