"""Parse and reassemble draft sections without touching unrelated content."""

from __future__ import annotations

import re
from typing import Any


def parse_sections(content: str) -> list[dict[str, str]]:
    """Split markdown-style draft into ordered sections."""
    text = (content or "").strip()
    if not text:
        return []

    pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return [{"title": "Document", "body": text}]

    sections: list[dict[str, str]] = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append({"title": "Preamble", "body": preamble})

    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append({"title": title, "body": body})
    return sections


def ensure_actionable_sections(
    content: str,
    blueprint: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Return sections revision can target, even when headings were lost during humanization."""
    sections = parse_sections(content)
    if _has_named_sections(sections):
        return sections

    text = (content or "").strip()
    if not text:
        return sections

    titles = section_titles(blueprint or {})
    if titles:
        by_titles = _split_by_blueprint_titles(text, titles)
        if by_titles:
            return by_titles

    if sections and sections[0].get("body", "").strip():
        return sections
    return [{"title": "Document", "body": text}]


def _has_named_sections(sections: list[dict[str, str]]) -> bool:
    if len(sections) > 1:
        return True
    if not sections:
        return False
    title = sections[0]["title"].strip().lower()
    return title not in {"document", "preamble"} and bool(sections[0].get("body", "").strip())


def _split_by_blueprint_titles(text: str, titles: list[str]) -> list[dict[str, str]]:
    """Split a flat humanized blob using known blueprint section titles."""
    markers: list[tuple[int, str]] = []
    lowered = text.lower()
    for title in titles:
        if not title or title.lower() == "references":
            continue
        for pattern in (
            re.compile(rf"^##\s+{re.escape(title)}\s*$", re.IGNORECASE | re.MULTILINE),
            re.compile(rf"^{re.escape(title)}\s*$", re.IGNORECASE | re.MULTILINE),
        ):
            for match in pattern.finditer(text):
                markers.append((match.start(), title))
                break
            else:
                continue
            break
        else:
            idx = lowered.find(title.lower())
            if idx >= 0:
                markers.append((idx, title))

    if not markers:
        return []

    markers.sort(key=lambda item: item[0])
    deduped: list[tuple[int, str]] = []
    seen_titles: set[str] = set()
    for pos, title in markers:
        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        deduped.append((pos, title))

    sections: list[dict[str, str]] = []
    for index, (start, title) in enumerate(deduped):
        header_end = text.find("\n", start)
        content_start = header_end + 1 if header_end >= 0 else start + len(title)
        end = deduped[index + 1][0] if index + 1 < len(deduped) else len(text)
        body = text[content_start:end].strip()
        sections.append({"title": title, "body": body})
    return [section for section in sections if section.get("body", "").strip() or section["title"]]


def find_section_index(sections: list[dict[str, str]], target: str) -> int | None:
    target_lower = (target or "").strip().lower()
    if not target_lower:
        return None
    for index, section in enumerate(sections):
        if section["title"].strip().lower() == target_lower:
            return index
    for index, section in enumerate(sections):
        title_lower = section["title"].strip().lower()
        if target_lower in title_lower or title_lower in target_lower:
            return index
    keywords = _section_match_keywords(target_lower)
    best_index: int | None = None
    best_score = 0
    for index, section in enumerate(sections):
        title_lower = section["title"].strip().lower()
        if title_lower in {"preamble", "document", "references"}:
            continue
        score = sum(1 for keyword in keywords if keyword in title_lower)
        if score > best_score:
            best_score = score
            best_index = index
    if best_index is not None and best_score > 0:
        return best_index
    if len(sections) == 1 and sections[0].get("body", "").strip():
        return 0
    for index, section in enumerate(sections):
        title_lower = section["title"].strip().lower()
        if title_lower not in {"preamble", "document", "references"}:
            return index
    return 0 if sections and sections[0].get("body", "").strip() else None


def _section_match_keywords(target_lower: str) -> list[str]:
    alias_map = {
        "discussion": ["discussion", "analysis", "critical", "evaluation", "debate"],
        "critical analysis": ["analysis", "critical", "discussion", "evaluation", "analytical"],
        "literature review": ["literature", "review", "thematic", "background", "scholarship"],
        "conclusion": ["conclusion", "summary", "closing"],
        "introduction": ["introduction", "intro", "opening"],
        "methodology": ["method", "methodology", "approach"],
        "background": ["background", "context", "setting"],
    }
    for key, keywords in alias_map.items():
        if key in target_lower or target_lower in key:
            return keywords
    return [part for part in re.split(r"[^a-z0-9]+", target_lower) if len(part) > 3]


def render_sections(sections: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for section in sections:
        title = section["title"]
        body = section.get("body", "").strip()
        if title == "Preamble":
            if body:
                parts.append(body)
            continue
        if title == "Document":
            if body:
                parts.append(body)
            continue
        parts.append(f"## {title}\n{body}".strip())
    return "\n\n".join(part for part in parts if part)


def section_titles(blueprint: dict[str, Any]) -> list[str]:
    titles = [str(item.get("title") or "") for item in (blueprint.get("sections") or []) if item.get("title")]
    if titles:
        return titles
    return list(blueprint.get("writing_queue") or [])
