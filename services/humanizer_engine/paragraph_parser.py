"""Split draft content into paragraph-level humanization tasks."""

from __future__ import annotations

import re
import uuid
from typing import Any

from services.humanizer_engine.constants import MAX_WORDS_PER_INPUT, MIN_HUMANIZE_CHARS
from services.humanizer_engine.models import HumanizerParagraph


def split_draft_into_paragraphs(content: str, blueprint: dict[str, Any] | None = None) -> list[HumanizerParagraph]:
    """Split draft into batched humanization tasks (up to MAX_WORDS_PER_INPUT each)."""
    raw = _split_raw_paragraphs(content, blueprint)
    return group_paragraphs_into_batches(raw)


def group_paragraphs_into_batches(
    paragraphs: list[HumanizerParagraph],
    *,
    max_words: int = MAX_WORDS_PER_INPUT,
    min_chars: int = MIN_HUMANIZE_CHARS,
) -> list[HumanizerParagraph]:
    """Merge body paragraphs into API-sized batches instead of one call per line."""
    if not paragraphs:
        return []

    batches: list[HumanizerParagraph] = []
    buffer_parts: list[str] = []
    buffer_section = "Document"
    buffer_words = 0

    def flush_buffer(*, force: bool = False) -> None:
        nonlocal buffer_parts, buffer_section, buffer_words
        if not buffer_parts:
            return

        combined = "\n\n".join(buffer_parts).strip()
        if not combined:
            buffer_parts = []
            buffer_words = 0
            return

        if len(combined) < min_chars and not force:
            return

        if len(combined) < min_chars and batches and not batches[-1].original_text.startswith("## "):
            previous = batches[-1]
            previous.original_text = f"{previous.original_text.rstrip()}\n\n{combined}"
            buffer_parts = []
            buffer_words = 0
            return

        batches.append(
            HumanizerParagraph(
                paragraph_id=_next_id(batches),
                section=buffer_section,
                original_text=combined,
            )
        )
        buffer_parts = []
        buffer_words = 0

    for paragraph in paragraphs:
        text = (paragraph.original_text or "").strip()
        if not text:
            continue

        if text.startswith("## "):
            flush_buffer(force=True)
            batches.append(
                HumanizerParagraph(
                    paragraph_id=_next_id(batches),
                    section=text[3:].strip(),
                    original_text=text,
                )
            )
            buffer_section = text[3:].strip()
            continue

        word_count = len(text.split())
        if buffer_parts and buffer_words + word_count > max_words:
            flush_buffer(force=True)

        if not buffer_parts:
            buffer_section = paragraph.section or buffer_section
        buffer_parts.append(text)
        buffer_words += word_count

    flush_buffer(force=True)
    return batches


def _split_raw_paragraphs(content: str, blueprint: dict[str, Any] | None = None) -> list[HumanizerParagraph]:
    """Split draft into logical paragraphs before batching for the API."""
    text = (content or "").strip()
    if not text:
        return []

    _ = blueprint
    paragraphs: list[HumanizerParagraph] = []
    current_section = "Document"
    section_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(section_pattern.finditer(text))

    if not matches:
        return _paragraphs_from_block(text, current_section, paragraphs)

    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            paragraphs.extend(_paragraphs_from_block(preamble, "Preamble", paragraphs))

    for index, match in enumerate(matches):
        current_section = match.group(1).strip()
        header = f"## {current_section}"
        paragraphs.append(
            HumanizerParagraph(
                paragraph_id=_next_id(paragraphs),
                section=current_section,
                original_text=header,
            )
        )
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            paragraphs.extend(_paragraphs_from_block(body, current_section, paragraphs))
    return paragraphs


def _paragraphs_from_block(
    block: str,
    section: str,
    existing: list[HumanizerParagraph],
) -> list[HumanizerParagraph]:
    items: list[HumanizerParagraph] = []
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", block) if chunk.strip()]
    if not chunks:
        chunks = [line.strip() for line in block.splitlines() if line.strip()]
    for chunk in chunks:
        if chunk.startswith("## "):
            continue
        items.append(
            HumanizerParagraph(
                paragraph_id=_next_id(existing + items),
                section=section,
                original_text=chunk,
            )
        )
    return items


def _next_id(paragraphs: list[HumanizerParagraph]) -> str:
    return f"p-{len(paragraphs) + 1}-{uuid.uuid4().hex[:6]}"
