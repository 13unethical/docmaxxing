"""Appendix tables (PESTLE, SWOT, decision matrices...) for briefs that allow appendices.

Appendices live outside the draft body: they are not humanized, trimmed or counted
towards the word limit, and the formatter appends them after the References.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

import requests

APPENDICES_ARTIFACT = "assignment_appendices"
_MAX_APPENDICES = 4
_MAX_ROWS = 12
_MAX_COLS = 5
_APPENDIX_RE = re.compile(r"\bappendi(?:x|ces)\b", re.I)
_CLAUDE_TIMEOUT_S = 180

_PROMPT = """You prepare the appendices of a student report.

The brief allows appendices. Build {max_n} or fewer appendix TABLES that support the report below:
one per analytical framework the report applies or the brief requires (for example PESTLE, SWOT,
Porter's Five Forces, a weighted decision matrix for the strategic options). Skip frameworks the
report does not use.

Rules:
- Every case fact must come from the assignment materials or the report. Do not invent figures.
- Keep the tables consistent with the report's analysis and recommendations.
- Cells are short phrases (max 25 words), plain academic English, no markdown, no citations.
- At most {max_rows} rows and {max_cols} columns per table; the first row of "rows" is data, not headers.
- "keyword" is the framework name exactly as the report writes it (e.g. "PESTLE", "SWOT"), so the
  report can point to the appendix.

Return ONE JSON object only:
{{"appendices": [{{"title": "PESTLE Analysis of <organisation>", "keyword": "PESTLE",
  "intro": "one sentence on what the table shows", "headers": ["Factor", "..."],
  "rows": [["Political", "..."]]}}]}}

REPORT:
{report}
"""


def appendices_wanted(requirement_json: dict[str, Any], materials: str = "") -> bool:
    sections = requirement_json.get("required_sections") or []
    if any(_APPENDIX_RE.search(str(s)) for s in sections):
        return True
    return bool(_APPENDIX_RE.search(materials or ""))


def generate_appendices(
    *,
    materials: str,
    draft_content: str,
    call: Callable[[str, str], str] | None = None,
) -> list[dict[str, Any]]:
    prompt = _PROMPT.format(
        max_n=_MAX_APPENDICES,
        max_rows=_MAX_ROWS,
        max_cols=_MAX_COLS,
        report=draft_content,
    )
    raw = (call or _call_claude)(prompt, materials)
    return _parse_appendices(raw)


def appendices_markdown(appendices: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for index, item in enumerate(appendices):
        blocks.append(f"## Appendix {_letter(index)}: {item['title']}")
        if item.get("intro"):
            blocks.append(item["intro"])
        lines = [_row(item["headers"]), _row(["---"] * len(item["headers"]))]
        lines.extend(_row(r) for r in item["rows"])
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def link_appendices(content: str, appendices: list[dict[str, Any]]) -> str:
    """Point the first body sentence that names each framework to its appendix."""
    text = content or ""
    for index, item in enumerate(appendices):
        keyword = str(item.get("keyword") or "").strip()
        label = f"Appendix {_letter(index)}"
        if not keyword or label in text:
            continue
        text = _link_first_mention(text, keyword, label)
    return text


def _link_first_mention(text: str, keyword: str, label: str) -> str:
    pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.I)
    offset = 0
    for block in re.split(r"(\n\s*\n)", text):
        stripped = block.strip()
        if stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("[["):
            offset += len(block)
            continue
        match = pattern.search(block)
        if match:
            end = re.compile(r"[.!?](?=\s|$)").search(block, match.end())
            if end:
                at = offset + end.start()
                return f"{text[:at]} (see {label}){text[at:]}"
        offset += len(block)
    return text


def _letter(index: int) -> str:
    return chr(ord("A") + index)


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(c.replace("|", "/") for c in cells) + " |"


def _clean_cell(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text.replace("**", "").replace("__", "")


def _parse_appendices(raw: str) -> list[dict[str, Any]]:
    text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    items = data.get("appendices") if isinstance(data, dict) else None
    out: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        title = _clean_cell(item.get("title"))
        headers = [_clean_cell(h) for h in (item.get("headers") or [])][:_MAX_COLS]
        if not title or len(headers) < 2:
            continue
        rows = []
        for row in (item.get("rows") or [])[:_MAX_ROWS]:
            if isinstance(row, list) and any(str(c).strip() for c in row):
                cells = [_clean_cell(c) for c in row][: len(headers)]
                rows.append(cells + [""] * (len(headers) - len(cells)))
        if not rows:
            continue
        out.append(
            {
                "title": title,
                "keyword": _clean_cell(item.get("keyword")),
                "intro": _clean_cell(item.get("intro")),
                "headers": headers,
                "rows": rows,
            }
        )
        if len(out) >= _MAX_APPENDICES:
            break
    return out


def _call_claude(prompt: str, materials: str) -> str:
    from services.writer_engine.llm_writer import (
        _CLAUDE_API_URL,
        _CLAUDE_MODEL,
        _claude_api_key,
        materials_system_blocks,
    )

    key = _claude_api_key()
    if not key:
        raise ValueError("Claude API key is not configured")
    body: dict[str, Any] = {
        "model": _CLAUDE_MODEL,
        "max_tokens": 4096,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    if materials:
        body["system"] = materials_system_blocks(materials)
    response = requests.post(
        _CLAUDE_API_URL,
        json=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        timeout=_CLAUDE_TIMEOUT_S,
    )
    if not response.ok:
        raise ValueError(f"Claude API error {response.status_code}: {response.text[:300]}")
    parts = response.json().get("content") or []
    return "\n".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
