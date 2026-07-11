"""Parse humanized draft into paragraph detection tasks."""

from __future__ import annotations

import re
import uuid
from typing import Any

from services.ai_detection_engine.models import ParagraphDetection


def split_humanized_draft_into_paragraphs(
    content: str,
    *,
    humanizer_paragraph_ids: list[str] | None = None,
) -> list[ParagraphDetection]:
    text = (content or "").strip()
    if not text:
        return []

    paragraphs: list[ParagraphDetection] = []
    section_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(section_pattern.finditer(text))

    if not matches:
        return _from_block(text, "Document", paragraphs, humanizer_paragraph_ids)

    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            paragraphs.extend(_from_block(preamble, "Preamble", paragraphs, humanizer_paragraph_ids))

    for index, match in enumerate(matches):
        section = match.group(1).strip()
        header = f"## {section}"
        paragraphs.append(
            ParagraphDetection(
                paragraph_id=_next_id(paragraphs),
                section=section,
                text=header,
                humanizer_paragraph_id=_linked_id(paragraphs, humanizer_paragraph_ids),
            )
        )
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            paragraphs.extend(_from_block(body, section, paragraphs, humanizer_paragraph_ids))
    return paragraphs


def _from_block(
    block: str,
    section: str,
    existing: list[ParagraphDetection],
    humanizer_paragraph_ids: list[str] | None,
) -> list[ParagraphDetection]:
    items: list[ParagraphDetection] = []
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", block) if chunk.strip()]
    if not chunks:
        chunks = [line.strip() for line in block.splitlines() if line.strip()]
    for chunk in chunks:
        if chunk.startswith("## "):
            continue
        items.append(
            ParagraphDetection(
                paragraph_id=_next_id(existing + items),
                section=section,
                text=chunk,
                humanizer_paragraph_id=_linked_id(existing + items, humanizer_paragraph_ids),
            )
        )
    return items


def _next_id(paragraphs: list[ParagraphDetection]) -> str:
    return f"det-p-{len(paragraphs) + 1}-{uuid.uuid4().hex[:6]}"


def _linked_id(paragraphs: list[ParagraphDetection], humanizer_paragraph_ids: list[str] | None) -> str | None:
    if not humanizer_paragraph_ids:
        return None
    index = len(paragraphs)
    if index < len(humanizer_paragraph_ids):
        return humanizer_paragraph_ids[index]
    return None
