"""Match brief-required section titles against extracted body blocks.

Ports the V1 ``requirement_headings`` behaviour into the V2 block model:
exact title → ``HEADING_1``; merged title+body → split; missing titles → warnings.
"""

from __future__ import annotations

import re

from formatter_v2.render.document import Block
from formatter_v2.resolve import ResolutionNotice
from formatter_v2.spec import ParagraphRole

_LEADING_NUMBERING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*)[.)]?\s+",
    re.IGNORECASE,
)
_TRAILING_PUNCT_RE = re.compile(r"[\s.:;,\-–—]+$")

_MIN_SPLIT_BODY_CHARS = 20

_HEADING_ROLES = frozenset(
    {
        ParagraphRole.HEADING_1,
        ParagraphRole.HEADING_2,
        ParagraphRole.HEADING_3,
        ParagraphRole.HEADING_4,
    }
)

_SKIP_ROLES = _HEADING_ROLES | frozenset(
    {
        ParagraphRole.REFERENCES_HEADING,
        ParagraphRole.REFERENCES_ENTRY,
        ParagraphRole.APPENDIX_HEADING,
    }
)


def normalize_section_key(text: str) -> str:
    """Lowercase key with collapsed spaces, no leading numbering or trailing punctuation."""
    cleaned = (text or "").strip().lower()
    cleaned = _LEADING_NUMBERING_RE.sub("", cleaned)
    cleaned = _TRAILING_PUNCT_RE.sub("", cleaned)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _display_heading(section: str) -> str:
    words = section.strip().split()
    if not words:
        return section.strip()
    if len(words) == 1:
        return words[0].capitalize()
    return " ".join(w.capitalize() if w.isalpha() else w for w in words)


def _section_start_pattern(section: str) -> re.Pattern[str]:
    words = section.strip().split()
    inner = r"\s+".join(re.escape(w) for w in words)
    return re.compile(
        rf"^(?:\d+(?:\.\d+)*[.)]?\s+)?{inner}(?:\s|[.:;,\-–—]|$)",
        re.IGNORECASE,
    )


def _match_heading_span(text: str, section: str) -> tuple[str, str] | None:
    """Return ``(heading_text, trailing)`` when *section* opens *text*, else ``None``."""
    stripped = (text or "").strip()
    if not stripped or not section.strip():
        return None

    if normalize_section_key(stripped) == normalize_section_key(section):
        return (_display_heading(section), "")

    pattern = _section_start_pattern(section)
    match = pattern.match(stripped)
    if not match:
        return None

    heading_end = match.end()
    while heading_end < len(stripped) and stripped[heading_end] in " \t":
        heading_end += 1
    heading_text = stripped[:heading_end].strip()
    trailing = stripped[heading_end:].strip()
    trailing = re.sub(r"^[.:;,\-–—]\s*", "", trailing)

    if not trailing:
        return (_display_heading(section), "")

    if len(trailing) < _MIN_SPLIT_BODY_CHARS:
        return (_display_heading(section), "")

    if trailing[0].islower():
        return None

    return (_display_heading(section), trailing)


def _block_plain(block: Block) -> str:
    if isinstance(block.text, str):
        return block.text
    return str(block.text)


def apply_expected_sections(
    blocks: list[Block],
    expected_sections: list[str],
) -> tuple[list[Block], list[ResolutionNotice]]:
    """Reclassify or split blocks using the brief's required section list."""
    if not expected_sections:
        return blocks, []

    used_keys: set[str] = set()
    found_keys: set[str] = set()
    out: list[Block] = []

    for block in blocks:
        if block.role in _SKIP_ROLES and block.role not in _HEADING_ROLES:
            out.append(block)
            continue

        text = _block_plain(block)
        matched = False
        for section in expected_sections:
            key = normalize_section_key(section)
            if not key or key in used_keys:
                continue
            span = _match_heading_span(text, section)
            if span is None:
                continue
            heading, body = span
            used_keys.add(key)
            found_keys.add(key)
            if block.role in _HEADING_ROLES and not body:
                out.append(block)
            else:
                out.append(Block(ParagraphRole.HEADING_1, heading))
                if body:
                    out.append(Block(ParagraphRole.BODY, body))
            matched = True
            break
        if not matched:
            out.append(block)

    missing = [
        section
        for section in expected_sections
        if normalize_section_key(section) not in found_keys
    ]
    found_labels = [
        section
        for section in expected_sections
        if normalize_section_key(section) in found_keys
    ]

    notices: list[ResolutionNotice] = []
    if expected_sections:
        parts: list[str] = []
        if found_labels:
            parts.append("Found: " + ", ".join(found_labels))
        if missing:
            parts.append("Missing: " + ", ".join(missing))
        if parts:
            notices.append(
                ResolutionNotice(
                    field="structure.expected_sections",
                    severity="info",
                    message="; ".join(parts),
                )
            )

    return out, notices
