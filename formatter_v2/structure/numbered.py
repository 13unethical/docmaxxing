"""Distinguish numbered section headings from numbered list items.

Runs after references latching and before the generic list heuristics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from formatter_v2.render.document import Block
from formatter_v2.render.model import DocumentModel
from formatter_v2.resolve import ResolutionNotice
from formatter_v2.spec import ParagraphRole

# "1. …", "1) …", "2.1 …", "3.1.4 …"
_NUMBERED_LINE_RE = re.compile(
    r"^(?P<nums>\d+(?:\.\d+)*)(?P<sep>[.)]?)\s+(?P<rest>\S.*)$"
)

_HEADING_TERMINAL_RE = re.compile(r"[.,;:]$")

_DEPTH_TO_ROLE = {
    1: ParagraphRole.HEADING_1,
    2: ParagraphRole.HEADING_2,
    3: ParagraphRole.HEADING_3,
}


@dataclass(frozen=True)
class NumberedPrefix:
    parts: tuple[int, ...]
    sep: str  # "." | ")" | ""


def parse_numbered_prefix(text: str) -> NumberedPrefix | None:
    stripped = (text or "").strip()
    match = _NUMBERED_LINE_RE.match(stripped)
    if not match:
        return None
    nums = match.group("nums")
    sep = match.group("sep") or ""
    parts = tuple(int(p) for p in nums.split("."))
    # Single-level must use "." or ")" — bare "1 Title" is not numbered.
    if len(parts) == 1 and sep not in {".", ")"}:
        return None
    # Multilevel "2.1 Title" — sep after the last digit is optional / empty.
    if len(parts) > 1 and sep == ")":
        # "2.1) Title" is odd; treat as multilevel heading still.
        pass
    return NumberedPrefix(parts=parts, sep=sep)


def _same_format(a: NumberedPrefix, b: NumberedPrefix) -> bool:
    if len(a.parts) != len(b.parts):
        return False
    if len(a.parts) == 1:
        return a.sep == b.sep
    return True


def _differs_by_one(a: NumberedPrefix, b: NumberedPrefix) -> bool:
    if not _same_format(a, b):
        return False
    if a.parts[:-1] != b.parts[:-1]:
        return False
    return abs(a.parts[-1] - b.parts[-1]) == 1


def _has_consecutive_numbered_neighbor(
    texts: Sequence[str],
    index: int,
    prefix: NumberedPrefix,
) -> bool:
    for neighbor_index in (index - 1, index + 1):
        if neighbor_index < 0 or neighbor_index >= len(texts):
            continue
        neighbor = parse_numbered_prefix(texts[neighbor_index])
        if neighbor is None:
            continue
        if _differs_by_one(prefix, neighbor):
            return True
    return False


def _next_nonempty(texts: Sequence[str], index: int) -> str | None:
    for neighbor_index in range(index + 1, len(texts)):
        stripped = (texts[neighbor_index] or "").strip()
        if stripped:
            return stripped
    return None


def _is_heading_despite_list_neighbor(
    texts: Sequence[str],
    index: int,
    prefix: NumberedPrefix,
    text: str,
) -> bool:
    """Section heading that happens to continue a list's numbering.

    All three must hold: short, no list-like punctuation, and the next
    nonempty paragraph is not another item in the same numbering format.
    """
    if len(text) >= 60:
        return False
    if ":" in text:
        return False
    if text.endswith((".", ",", ";")):
        return False
    nxt = _next_nonempty(texts, index)
    if nxt is None:
        return True
    nxt_prefix = parse_numbered_prefix(nxt)
    if nxt_prefix is not None and _same_format(prefix, nxt_prefix):
        return False
    return True


def classify_numbered_line(
    texts: Sequence[str],
    index: int,
) -> ParagraphRole | None:
    """Return a role for a numbered line, or ``None`` to fall through.

    Multilevel numbers are always headings. Single-level numbers become a list
    item when a neighbor continues the sequence, a heading when isolated and
    short without terminal punctuation, otherwise BODY.
    """
    if index < 0 or index >= len(texts):
        return None
    text = (texts[index] or "").strip()
    prefix = parse_numbered_prefix(text)
    if prefix is None:
        return None

    depth = len(prefix.parts)
    if depth >= 2:
        return _DEPTH_TO_ROLE.get(min(depth, 3), ParagraphRole.HEADING_3)

    # Single-level: N. / N)
    if _has_consecutive_numbered_neighbor(texts, index, prefix):
        if _is_heading_despite_list_neighbor(texts, index, prefix, text):
            return ParagraphRole.HEADING_1
        return ParagraphRole.LIST_NUMBER

    if len(text) < 100 and not _HEADING_TERMINAL_RE.search(text):
        return ParagraphRole.HEADING_1

    return ParagraphRole.BODY


def count_longest_consecutive_numbered_sections(model: DocumentModel) -> int:
    """Longest run of single-level numbered headings with sequential numbers."""
    headings: list[NumberedPrefix] = []
    for block in model.body:
        if block.role not in {
            ParagraphRole.HEADING_1,
            ParagraphRole.HEADING_2,
            ParagraphRole.HEADING_3,
            ParagraphRole.HEADING_4,
        }:
            continue
        text = block.text if isinstance(block.text, str) else str(block.text)
        prefix = parse_numbered_prefix(text)
        if prefix is None or len(prefix.parts) != 1:
            continue
        headings.append(prefix)

    if not headings:
        return 0

    best = 1
    run = 1
    for i in range(1, len(headings)):
        prev = headings[i - 1]
        cur = headings[i]
        if _same_format(prev, cur) and cur.parts[-1] == prev.parts[-1] + 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def numbered_section_notices(model: DocumentModel) -> list[ResolutionNotice]:
    """Info notice when the source uses manual section numbering (4+ in a row)."""
    longest = count_longest_consecutive_numbered_sections(model)
    if longest <= 3:
        return []
    return [
        ResolutionNotice(
            field="structure.numbered_sections",
            severity="info",
            message=(
                "В исходнике найдена ручная нумерация разделов "
                f"({longest} секций подряд). Стоит проверить, нужна ли она "
                "в итоговом документе — номера в тексте сохранены без изменений."
            ),
        )
    ]
