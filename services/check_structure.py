"""Academic Check structure metrics from formatter_v2 DocumentModel."""

from __future__ import annotations

from typing import Any

from docx import Document

from formatter.headings import normalize_paragraph_text
from formatter_v2.pipeline import select_extractor
from formatter_v2.render.document import Block
from formatter_v2.render.model import DocumentModel
from formatter_v2.render.rich_text import is_formatted_text
from formatter_v2.spec import ParagraphRole
from formatter_v2.structure.text_integrity import normalize_source
from services.check_text import document_word_count
from services.check_validator import heading_label_without_number

HEADING_ROLES = frozenset(
    {
        ParagraphRole.ABSTRACT_HEADING,
        ParagraphRole.HEADING_1,
        ParagraphRole.HEADING_2,
        ParagraphRole.HEADING_3,
        ParagraphRole.HEADING_4,
        ParagraphRole.TOC_HEADING,
        ParagraphRole.APPENDIX_HEADING,
        ParagraphRole.REFERENCES_HEADING,
    }
)
BODY_ROLES = frozenset(
    {
        ParagraphRole.BODY,
        ParagraphRole.BODY_FIRST,
        ParagraphRole.BLOCK_QUOTE,
        ParagraphRole.LIST_BULLET,
        ParagraphRole.LIST_NUMBER,
        ParagraphRole.TABLE_CAPTION,
        ParagraphRole.FIGURE_CAPTION,
        ParagraphRole.KEYWORDS,
        ParagraphRole.ABSTRACT,
        ParagraphRole.TABLE_CELL,
        ParagraphRole.TOC_ENTRY,
        ParagraphRole.ABBREVIATION_ENTRY,
        ParagraphRole.FOOTNOTE,
    }
)
SUBSTANTIVE_BODY_ROLES = frozenset(
    {
        ParagraphRole.BODY,
        ParagraphRole.BODY_FIRST,
        ParagraphRole.ABSTRACT,
        ParagraphRole.BLOCK_QUOTE,
    }
)


def block_plain(block: Block) -> str:
    text = block.text
    if isinstance(text, str):
        return text
    if is_formatted_text(text):
        return "".join(getattr(part, "text", "") or "" for part in text)
    return str(text)


def extract_document_model(
    *,
    text: str,
    paragraphs: list[str] | None = None,
    doc: Document | None = None,
    expected_sections: list[str] | None = None,
) -> tuple[DocumentModel, str]:
    """Same extractor choice as formatter_v2: Word styles when marked up, else heuristics."""
    if doc is not None:
        source: object = doc
    elif paragraphs:
        source = list(paragraphs)
    else:
        source = text or ""
    source, _notices = normalize_source(source)
    extractor, extractor_name, document = select_extractor(source)
    extract_kwargs = {"expected_sections": expected_sections or None}
    if document is not None:
        model = extractor.extract(document, **extract_kwargs)
    else:
        model = extractor.extract(source, **extract_kwargs)
    return model, extractor_name


def _iter_blocks(model: DocumentModel) -> list[Block]:
    blocks: list[Block] = []
    blocks.extend(model.front_matter)
    blocks.extend(model.body)
    blocks.extend(model.references)
    blocks.extend(model.appendices)
    return blocks


def _new_section(title: str, role: str) -> dict[str, Any]:
    return {
        "title": title,
        "canonical": heading_label_without_number(title) or normalize_paragraph_text(title),
        "role": role,
        "body_word_count": 0,
        "reference_entries": 0,
    }


def model_to_detected_sections(model: DocumentModel) -> list[dict[str, Any]]:
    """Headings become sections; list items and bibliography entries do not."""
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def close() -> None:
        nonlocal current
        if current is not None:
            sections.append(current)
            current = None

    for block in _iter_blocks(model):
        title = block_plain(block).strip()
        if block.role in HEADING_ROLES:
            close()
            current = _new_section(title, block.role.value)
            continue
        if current is None and block.role == ParagraphRole.REFERENCES_ENTRY:
            current = _new_section("References", ParagraphRole.REFERENCES_HEADING.value)
        if current is None:
            continue
        if block.role == ParagraphRole.REFERENCES_ENTRY:
            current["reference_entries"] = int(current["reference_entries"]) + 1
        if block.role in BODY_ROLES or block.role == ParagraphRole.REFERENCES_ENTRY:
            current["body_word_count"] = int(current["body_word_count"]) + document_word_count(title)
    close()
    return sections


def reference_entry_lines(model: DocumentModel) -> list[str]:
    lines: list[str] = []
    for block in model.references:
        if block.role != ParagraphRole.REFERENCES_ENTRY:
            continue
        text = block_plain(block).strip()
        if text:
            lines.append(text)
    if lines:
        return lines
    for block in _iter_blocks(model):
        if block.role != ParagraphRole.REFERENCES_ENTRY:
            continue
        text = block_plain(block).strip()
        if text:
            lines.append(text)
    return lines


def body_text_for_citations(model: DocumentModel) -> str:
    parts: list[str] = []
    for block in list(model.front_matter) + list(model.body) + list(model.appendices):
        if block.role in HEADING_ROLES:
            continue
        if block.role == ParagraphRole.REFERENCES_ENTRY:
            continue
        text = block_plain(block).strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def heading_count(model: DocumentModel) -> int:
    return sum(1 for block in _iter_blocks(model) if block.role in HEADING_ROLES)


def body_paragraph_count(model: DocumentModel) -> int:
    count = 0
    for block in _iter_blocks(model):
        if block.role not in SUBSTANTIVE_BODY_ROLES:
            continue
        if document_word_count(block_plain(block)) >= 20:
            count += 1
    return count


def iter_section_paragraphs(model: DocumentModel) -> list[dict[str, Any]]:
    """Body paragraphs with the heading they currently sit under."""
    current_title = ""
    current_canonical = ""
    out: list[dict[str, Any]] = []
    for block in _iter_blocks(model):
        if block.role in HEADING_ROLES:
            current_title = block_plain(block).strip()
            current_canonical = heading_label_without_number(current_title)
            continue
        if block.role not in SUBSTANTIVE_BODY_ROLES:
            continue
        text = block_plain(block).strip()
        words = document_word_count(text)
        if words < 8:
            continue
        out.append(
            {
                "text": text,
                "word_count": words,
                "section_title": current_title,
                "section_canonical": current_canonical,
            }
        )
    return out
