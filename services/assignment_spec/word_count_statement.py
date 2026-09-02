"""Detect whether the brief asks to PRINT the word count on the paper.

A length target like "2000 words" is not that instruction.
"""

from __future__ import annotations

import re
from typing import Any

# Verbs/cover placement — not a numeric limit like "Write 2000 words".
_STATE_WORD_COUNT_RE = re.compile(
    r"(?is)"
    r"(?:"
    r"\b(?:state|indicate|include|declare|show|display|put|print|write)\b.{0,48}\bword[\s-]*counts?"
    r"|"
    r"\bword[\s-]*counts?.{0,48}\b(?:on the\s+)?(?:cover|front|title\s*page|first\s+page|assessment|document)"
    r"|"
    r"\bword[\s-]*counts?\s+(?:must|should|needs?\s+to)\s+be\s+(?:stated|indicated|included|shown|declared|visible)"
    r")"
)

LEADING_WORD_COUNT_LINE = re.compile(
    r"(?im)\A\s*word[\s-]*count\s*:\s*[\d,]+\s*(?:\n+|$)"
)


def text_asks_to_state_word_count(text: str | None) -> bool:
    return bool(_STATE_WORD_COUNT_RE.search(text or ""))


def _requirement_text_blob(requirement_json: dict[str, Any] | None) -> str:
    data = requirement_json or {}
    parts: list[str] = [
        str(data.get("title") or ""),
        str(data.get("submission_format") or ""),
    ]
    parts.extend(str(s) for s in (data.get("required_sections") or []))
    parts.extend(str(s) for s in (data.get("missing_information") or []))
    for item in data.get("rubric") or []:
        if isinstance(item, dict):
            parts.append(str(item.get("criterion") or ""))
            parts.append(str(item.get("description") or ""))
        else:
            parts.append(str(item))
    fmt = data.get("formatting")
    if isinstance(fmt, dict):
        parts.extend(str(v) for v in fmt.values() if isinstance(v, str))
    return "\n".join(parts)


def requirement_asks_to_state_word_count(requirement_json: dict[str, Any] | None) -> bool:
    data = requirement_json or {}
    flag = data.get("state_word_count")
    if flag is True or str(flag).strip().lower() in {"true", "1", "yes"}:
        return True
    fmt = data.get("formatting")
    if isinstance(fmt, dict):
        for key in ("state_word_count", "include_word_count", "show_word_count"):
            value = fmt.get(key)
            if value is True or str(value).strip().lower() in {"true", "1", "yes"}:
                return True
    return text_asks_to_state_word_count(_requirement_text_blob(data))
