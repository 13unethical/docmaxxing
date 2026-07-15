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
        return _generate_with_claude(prompt=prompt, claude_key=claude_key)


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
        "4) Return ONE strict JSON object only. No markdown. No code fences. No commentary.\n"
        "5) Required keys: title, purpose, target_words, draft, citations_used, warnings, generation_time, model_used.\n"
        "6) The draft field must be a single JSON string with escaped quotes (\\\") and \\n for line breaks.\n"
        "7) citations_used must be a list of citation placeholders like [Author, Year] used in the draft.\n"
        "8) warnings should flag any requirement conflict or missing input.\n"
        "9) generation_time must be numeric and model_used must be string (they may be overridden by caller).\n\n"
        f"INPUT:\n{json.dumps(blueprint_guard, ensure_ascii=False)}"
    )


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
