"""Split draft content into batched humanization tasks (up to ~5000 words)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from services.humanizer_engine.constants import HUMANIZE_BATCH_WORDS, MIN_HUMANIZE_CHARS
from services.humanizer_engine.heading_utils import is_references_section_title
from services.humanizer_engine.models import HumanizerParagraph


def split_draft_into_paragraphs(content: str, blueprint: dict[str, Any] | None = None) -> list[HumanizerParagraph]:
    """Split draft into large humanization batches (not one API call per section/part)."""
    raw = _split_raw_paragraphs(content, blueprint)
    return group_paragraphs_into_batches(raw, max_words=HUMANIZE_BATCH_WORDS)


def group_paragraphs_into_batches(
    paragraphs: list[HumanizerParagraph],
    *,
    max_words: int = HUMANIZE_BATCH_WORDS,
    min_chars: int = MIN_HUMANIZE_CHARS,
) -> list[HumanizerParagraph]:
    """Merge body (+ headings) into API-sized batches up to ``max_words``.

    Writing remains section-based. Humanizing must NOT call the provider once per
    short paragraph/section — pack content until the ~5000-word provider limit.

    References / Bibliography are never mixed into body batches (pass-through later).
    """
    if not paragraphs:
        return []

    batches: list[HumanizerParagraph] = []
    buffer_parts: list[str] = []
    buffer_section = "Document"
    buffer_words = 0
    buffer_is_refs = False

    def flush_buffer() -> None:
        nonlocal buffer_parts, buffer_section, buffer_words, buffer_is_refs
        if not buffer_parts:
            return
        combined = "\n\n".join(buffer_parts).strip()
        buffer_parts = []
        buffer_words = 0
        was_refs = buffer_is_refs
        buffer_is_refs = False
        if not combined:
            return
        # Heading-only leftovers stay as pass-through units.
        if combined.startswith("## ") and "\n" not in combined:
            batches.append(
                HumanizerParagraph(
                    paragraph_id=_next_id(batches),
                    section=combined[3:].strip(),
                    original_text=combined,
                )
            )
            return
        if (
            not was_refs
            and len(combined) < min_chars
            and batches
            and not batches[-1].original_text.strip().startswith("## ")
            and not is_references_section_title(batches[-1].section or "")
        ):
            previous = batches[-1]
            previous.original_text = f"{previous.original_text.rstrip()}\n\n{combined}"
            return
        batches.append(
            HumanizerParagraph(
                paragraph_id=_next_id(batches),
                section=buffer_section,
                original_text=combined,
            )
        )

    for paragraph in paragraphs:
        text = (paragraph.original_text or "").strip()
        if not text:
            continue

        section_name = paragraph.section or buffer_section
        if text.startswith("## "):
            section_name = text[3:].strip() or section_name
        is_refs = is_references_section_title(section_name)

        # Never pack References into the same StealthWriter call as essay body.
        if buffer_parts and is_refs != buffer_is_refs:
            flush_buffer()

        word_count = max(1, len(text.split()))
        if word_count > max_words:
            flush_buffer()
            words = text.split()
            for index in range(0, len(words), max_words):
                chunk = " ".join(words[index : index + max_words])
                batches.append(
                    HumanizerParagraph(
                        paragraph_id=_next_id(batches),
                        section=section_name,
                        original_text=chunk,
                    )
                )
            buffer_section = section_name
            buffer_is_refs = is_refs
            continue

        if buffer_parts and buffer_words + word_count > max_words:
            flush_buffer()

        if not buffer_parts:
            buffer_section = section_name
            buffer_is_refs = is_refs
        elif text.startswith("## "):
            buffer_section = section_name
            buffer_is_refs = is_refs

        buffer_parts.append(text)
        buffer_words += word_count

    flush_buffer()
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
