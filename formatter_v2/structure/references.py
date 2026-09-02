"""Reference-section latching shared by heuristic and Word-style extractors.

Order of operations (callers must respect this):

1. Detect a references **heading** (normalised title match), OR
2. Detect a references **block** by content (≥3 consecutive reference-like
   paragraphs in the last third of the document — appendices may follow),
3. Only then classify remaining body paragraphs (numbered headings/lists,
   captions, generic lists, heuristic headings).

Numbered bibliography lines must never become ``LIST_NUMBER`` because list
detection runs only on the body region *outside* the latch range.
"""

from __future__ import annotations

import re
from typing import Sequence

from docx.text.paragraph import Paragraph

from formatter_v2.render.document import Block
from formatter_v2.render.model import DocumentModel
from formatter_v2.spec import ParagraphRole
from formatter_v2.structure.numbered import classify_numbered_line

REFS_HEADING_TITLES: frozenset[str] = frozenset(
    {
        "references",
        "reference list",
        "list of references",
        "works cited",
        "works consulted",
        "bibliography",
        "sources",
        "literature",
        "literature cited",
        "references and bibliography",
    }
)

# Headings that end a references-by-title latch (leading numbering already stripped).
POST_REFS_SECTION_TITLES: frozenset[str] = frozenset(
    {
        "appendix",
        "appendices",
        "annex",
        "glossary",
        "notes",
        "acknowledgements",
        "acknowledgments",
        "abbreviations",
        "list of figures",
        "list of tables",
        "index",
    }
)

_APPENDIX_SECTION_TITLES: frozenset[str] = frozenset(
    {"appendix", "appendices", "annex"}
)

# Leading section mark: "7 References", "7. References", "VII References", "A References"
_LEADING_NUMBERING_RE = re.compile(
    r"^(?:[0-9IVXLC]+|[A-Za-z])(?:[.):\-])?\s+",
    re.IGNORECASE,
)

# "8 Appendix A", "8. Appendix", "VII Annex"
_LATCH_BREAK_NUMBER_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*|[IVXLCDM]+)[.)]?\s+\S",
    re.IGNORECASE,
)

_NUM_REF_PREFIX_RE = re.compile(r"^(?:\[\d+\]|\d+\.)\s+")
_FOUR_DIGIT_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_YEAR_IN_PARENS_RE = re.compile(r"\(\s*(?:19|20)\d{2}[a-z]?\s*\)")
_SURNAME_INITIALS_RE = re.compile(
    r"^[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+,\s*[A-Z]\.(?:\s*[A-Z]\.)*"
)
_DOI_OR_URL_RE = re.compile(r"(?i)\bdoi\b|https?://")
_PLACEHOLDER_NOTE_RE = re.compile(
    r"\s*\((?:this\s+is\s+a\s+|a\s+)?placeholder\b[^)]*\)\.?",
    re.IGNORECASE,
)
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+?)\*(?!\*)")
_PERSON_ENTRY_START_RE = re.compile(
    r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+,\s*[A-Z]\.(?:\s*[A-Z]\.)*"
    r"(?:\s*(?:&|and)\s*[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+,\s*[A-Z]\.(?:\s*[A-Z]\.)*)*"
    r"\s*\(\s*(?:19|20)\d{2}[a-z]?\s*\)"
)
_ORG_ENTRY_START_RE = re.compile(
    r"[A-Z][A-Za-z0-9&'’\-]{2,}(?:\s+[A-Z][A-Za-z0-9&'’\-]+){0,8}"
    r"\.\s*\(\s*(?:19|20)\d{2}[a-z]?\s*\)"
)
_NUMBERED_REF_PREFIX_ONLY_RE = re.compile(r"^(?:\[\d+\]|\d+[.)])$")


def normalize_refs_heading(text: str) -> str:
    """Strip leading numbering/punctuation and casefold for title matching."""
    cleaned = (text or "").strip()
    cleaned = _LEADING_NUMBERING_RE.sub("", cleaned)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().casefold()
    return cleaned


def is_references_heading(text: str) -> bool:
    return normalize_refs_heading(text) in REFS_HEADING_TITLES


def _normalized_matches_titles(normalized: str, titles: frozenset[str]) -> bool:
    if normalized in titles:
        return True
    return any(normalized.startswith(title + " ") for title in titles)


def is_refs_latch_breaker(text: str) -> bool:
    """True when a paragraph after a References heading starts a new section."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    if (
        len(stripped) < 60
        and not stripped.endswith(".")
        and _LATCH_BREAK_NUMBER_RE.match(stripped)
    ):
        return True
    return _normalized_matches_titles(
        normalize_refs_heading(stripped),
        POST_REFS_SECTION_TITLES,
    )


def refs_latch_break_role(text: str) -> ParagraphRole:
    """Role for the paragraph that interrupted a heading latch."""
    normalized = normalize_refs_heading(text)
    if _normalized_matches_titles(normalized, _APPENDIX_SECTION_TITLES):
        return ParagraphRole.APPENDIX_HEADING
    return ParagraphRole.HEADING_1


def find_heading_latch_end(texts: Sequence[str], start: int) -> int:
    """Exclusive end of a heading latch; stops at the first section breaker."""
    for index in range(start + 1, len(texts)):
        if is_refs_latch_breaker(texts[index]):
            return index
    return len(texts)


def _paragraph_has_italic(paragraph: Paragraph | None) -> bool:
    if paragraph is None:
        return False
    for run in paragraph.runs:
        if run.italic and (run.text or "").strip():
            return True
    return False


def looks_like_reference_entry(
    text: str,
    paragraph: Paragraph | None = None,
) -> bool:
    """True when a paragraph matches at least one bibliography cue."""
    stripped = (text or "").strip()
    if not stripped:
        return False

    if _NUM_REF_PREFIX_RE.match(stripped) and _FOUR_DIGIT_YEAR_RE.search(stripped):
        return True

    if _SURNAME_INITIALS_RE.match(stripped):
        return True

    if _YEAR_IN_PARENS_RE.search(stripped):
        if (
            ";" in stripped
            or _DOI_OR_URL_RE.search(stripped)
            or _paragraph_has_italic(paragraph)
        ):
            return True

    return False


def clean_reference_entry_text(text: str) -> str:
    """Drop markdown markers and LLM placeholder notes from a bibliography line."""
    cleaned = _PLACEHOLDER_NOTE_RE.sub("", text or "")
    cleaned = _MD_BOLD_RE.sub(r"\1", cleaned)
    cleaned = _MD_ITALIC_RE.sub(r"\1", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip(" \t,;")


def split_concatenated_reference_entries(text: str) -> list[str]:
    """Split a glued bibliography blob into one APA/Harvard-style entry each."""
    cleaned = clean_reference_entry_text(text)
    if not cleaned:
        return []
    parts: list[str] = []
    for line in cleaned.splitlines():
        line = line.strip()
        if not line:
            continue
        parts.extend(_split_inline_reference_entries(line))
    return parts or ([cleaned] if cleaned else [])


def _split_inline_reference_entries(text: str) -> list[str]:
    starts = [0]
    for match in _PERSON_ENTRY_START_RE.finditer(text):
        _maybe_mark_entry_start(text, match.start(), starts)
    for match in _ORG_ENTRY_START_RE.finditer(text):
        _maybe_mark_entry_start(text, match.start(), starts)
    unique = sorted({index for index in starts if 0 <= index < len(text)})
    unique.append(len(text))
    entries = [
        text[unique[i] : unique[i + 1]].strip()
        for i in range(len(unique) - 1)
        if text[unique[i] : unique[i + 1]].strip()
    ]
    return entries or [text]


def _maybe_mark_entry_start(text: str, index: int, starts: list[int]) -> None:
    if index <= 0:
        return
    previous = text[:index].rstrip()
    if _NUMBERED_REF_PREFIX_ONLY_RE.fullmatch(previous):
        return
    if previous.endswith((".", '."', ".”", ".'", ".’")):
        starts.append(index)


def find_heading_latch_index(texts: Sequence[str]) -> int | None:
    for index, text in enumerate(texts):
        if is_references_heading(text):
            return index
    return None


def find_content_latch_range(
    texts: Sequence[str],
    paragraphs: Sequence[Paragraph | None] | None = None,
) -> tuple[int, int] | None:
    """Return ``[start, end)`` of a ≥3 reference-like run in the last third.

    The block need not reach the document end (appendices may follow). When a
    candidate run is shorter than 3, search continues further up.
    """
    n = len(texts)
    if n < 3:
        return None

    paras: Sequence[Paragraph | None]
    if paragraphs is None:
        paras = [None] * n
    else:
        paras = paragraphs

    def is_ref(i: int) -> bool:
        para = paras[i] if i < len(paras) else None
        return looks_like_reference_entry(texts[i], para)

    region_start = (2 * n) // 3
    i = n - 1
    while i >= region_start:
        if not is_ref(i):
            i -= 1
            continue
        end = i + 1
        start = i
        while start > 0 and is_ref(start - 1):
            start -= 1
        if end - start >= 3 and end > region_start:
            return start, end
        i = start - 1
    return None


def find_content_latch_index(
    texts: Sequence[str],
    paragraphs: Sequence[Paragraph | None] | None = None,
) -> int | None:
    """Compatibility wrapper: start index of a content-latched range."""
    found = find_content_latch_range(texts, paragraphs)
    return None if found is None else found[0]


def _block_plain(block: Block) -> str:
    if isinstance(block.text, str):
        return block.text
    return str(block.text)


def explode_reference_blocks(references: list[Block]) -> list[Block]:
    """Turn concatenated REFERENCES_ENTRY paragraphs into one entry per block."""
    out: list[Block] = []
    for block in references:
        if block.role != ParagraphRole.REFERENCES_ENTRY:
            out.append(block)
            continue
        parts = split_concatenated_reference_entries(_block_plain(block))
        if not parts:
            continue
        for part in parts:
            out.append(Block(ParagraphRole.REFERENCES_ENTRY, part))
    return out


def apply_content_refs_latch(
    model: DocumentModel,
    paragraphs: Sequence[Paragraph | None] | None = None,
) -> DocumentModel:
    """Latch a bibliography block by content when no entry exists yet.

    Used by Word-styles extraction after style mapping: styles stay primary,
    but a Normal/List-Number bibliography without a heading still latches.
    Trailing non-reference paragraphs (appendices) stay in ``body``.
    """
    if any(b.role == ParagraphRole.REFERENCES_ENTRY for b in model.references):
        return model

    body_texts = [_block_plain(b) for b in model.body]
    if not body_texts:
        return model

    found = find_content_latch_range(body_texts, paragraphs)
    if found is None:
        return model
    start, end = found

    new_body = list(model.body[:start]) + list(model.body[end:])
    latched = [
        Block(ParagraphRole.REFERENCES_ENTRY, _block_plain(b))
        for b in model.body[start:end]
    ]
    return DocumentModel(
        cover=model.cover,
        front_matter=list(model.front_matter),
        body=new_body,
        references=list(model.references) + explode_reference_blocks(latched),
        appendices=list(model.appendices),
    )


def split_body_and_references(
    texts: Sequence[str],
    paragraphs: Sequence[Paragraph | None],
    role_for_body,
    *,
    content_latch: bool = True,
) -> tuple[list[Block], list[Block]]:
    """Apply heading/content latch, then classify only the body region.

    ``role_for_body(text, paragraph, is_first_nonempty) -> ParagraphRole``
    is invoked solely for paragraphs that remain in the body, and only when
    the numbered-heading/list rule does not claim the line.
    """
    if not texts:
        return [], []

    heading_idx = find_heading_latch_index(texts)
    content_range: tuple[int, int] | None = None
    if heading_idx is not None:
        latch_mode = "heading"
        latch_start = heading_idx
        latch_end = find_heading_latch_end(texts, heading_idx)
    elif content_latch:
        content_range = find_content_latch_range(texts, paragraphs)
        if content_range is None:
            latch_mode = "none"
            latch_start = len(texts)
            latch_end = len(texts)
        else:
            latch_mode = "content"
            latch_start, latch_end = content_range
    else:
        latch_mode = "none"
        latch_start = len(texts)
        latch_end = len(texts)

    # Body texts in document order, excluding the latched reference span.
    body_texts_for_numbering = [
        texts[i] for i in range(len(texts)) if not (latch_start <= i < latch_end)
    ]

    body: list[Block] = []
    references: list[Block] = []
    seen_nonempty = False
    body_numbering_index = 0

    for i, text in enumerate(texts):
        para = paragraphs[i] if i < len(paragraphs) else None
        stripped = (text or "").strip()
        if not stripped:
            continue

        if latch_start <= i < latch_end:
            if latch_mode == "heading" and i == latch_start:
                references.append(Block(ParagraphRole.REFERENCES_HEADING, stripped))
            else:
                references.append(Block(ParagraphRole.REFERENCES_ENTRY, stripped))
            continue

        if (
            latch_mode == "heading"
            and i == latch_end
            and is_refs_latch_breaker(stripped)
        ):
            body.append(Block(refs_latch_break_role(stripped), stripped))
            body_numbering_index += 1
            seen_nonempty = True
            continue

        numbered_role = classify_numbered_line(body_texts_for_numbering, body_numbering_index)
        body_numbering_index += 1
        if numbered_role is not None:
            body.append(Block(numbered_role, stripped))
            seen_nonempty = True
            continue
        is_first = not seen_nonempty
        seen_nonempty = True
        role = role_for_body(stripped, para, is_first)
        body.append(Block(role, stripped))

    return body, explode_reference_blocks(references)


def partition_blocks_by_references(
    blocks: list[Block],
    paragraphs: Sequence[Paragraph | None] | None = None,
    *,
    content_latch: bool = True,
) -> tuple[list[Block], list[Block]]:
    """Latch references on pre-classified blocks without re-running role heuristics."""
    if not blocks:
        return [], []

    texts = [
        b.text if isinstance(b.text, str) else str(b.text) for b in blocks
    ]
    paras = list(paragraphs) if paragraphs is not None else [None] * len(blocks)

    heading_idx = find_heading_latch_index(texts)
    content_range: tuple[int, int] | None = None
    if heading_idx is not None:
        latch_mode = "heading"
        latch_start = heading_idx
        latch_end = find_heading_latch_end(texts, heading_idx)
    elif content_latch:
        content_range = find_content_latch_range(texts, paras)
        if content_range is None:
            latch_mode = "none"
            latch_start = len(texts)
            latch_end = len(texts)
        else:
            latch_mode = "content"
            latch_start, latch_end = content_range
    else:
        latch_mode = "none"
        latch_start = len(texts)
        latch_end = len(texts)

    body: list[Block] = []
    references: list[Block] = []

    for i, block in enumerate(blocks):
        text = texts[i]
        stripped = (text or "").strip()
        if not stripped:
            continue

        if latch_start <= i < latch_end:
            if latch_mode == "heading" and i == latch_start:
                references.append(Block(ParagraphRole.REFERENCES_HEADING, stripped))
            else:
                references.append(Block(ParagraphRole.REFERENCES_ENTRY, stripped))
            continue

        if (
            latch_mode == "heading"
            and i == latch_end
            and is_refs_latch_breaker(stripped)
        ):
            body.append(Block(refs_latch_break_role(stripped), stripped))
            continue

        body.append(block)

    return body, explode_reference_blocks(references)


def move_appendices_from_body(model: DocumentModel) -> DocumentModel:
    """Move appendix blocks from ``body`` into ``appendices``.

    Rule:
    - when a paragraph has role ``APPENDIX_HEADING``, move it and all
      subsequent blocks into ``appendices`` until the next appendix heading
      (or end-of-document).
    - keep blocks before the first appendix heading in ``body``.
    """
    if not model.body:
        return model

    new_body: list[Block] = []
    appendices: list[Block] = []
    n = len(model.body)
    tail_start = (2 * n) // 3

    def _looks_like_appendix_heading(block: Block, index: int) -> bool:
        if block.role == ParagraphRole.APPENDIX_HEADING:
            return True
        # Heuristic appendix-heading recognition is allowed only in the
        # document tail; earlier "Appendix X ..." mentions stay in body.
        if index < tail_start:
            return False
        if not isinstance(block.text, str):
            return False
        stripped = block.text.strip()
        if len(stripped) >= 60:
            return False
        # Avoid treating sentences like "Appendix A text." as headings.
        if stripped.endswith("."):
            return False

        if refs_latch_break_role(block.text) != ParagraphRole.APPENDIX_HEADING:
            return False

        normalized = normalize_refs_heading(block.text)
        tokens = [t for t in normalized.split(" ") if t]
        # Expect: "appendix", "appendix a", "appendices b", "annex", etc.
        return 1 <= len(tokens) <= 2

    in_appendix = False
    for index, block in enumerate(model.body):
        if _looks_like_appendix_heading(block, index):
            in_appendix = True
            appendix_heading_text = block.text if isinstance(block.text, str) else ""
            appendices.append(
                Block(ParagraphRole.APPENDIX_HEADING, appendix_heading_text)
            )
            continue

        if in_appendix:
            appendices.append(block)
        else:
            new_body.append(block)

    return DocumentModel(
        cover=model.cover,
        front_matter=list(model.front_matter),
        body=new_body,
        references=list(model.references),
        appendices=appendices,
    )
