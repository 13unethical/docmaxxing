"""
Prepare a reference list: alphabetize entries and choose the correct section title.

Input lines are treated as already formatted in the chosen style; we do not fully
re-parse or rewrite unstructured sources (that would need dedicated parsers).
Light cleanup: strip, collapse spaces, dedupe (case-insensitive), stable sort.
"""

from __future__ import annotations

import re
from typing import Literal

CitationStyle = Literal["APA", "MLA", "Harvard", "Chicago", "IEEE", "Vancouver"]

ALLOWED_STYLES = frozenset({"APA", "MLA", "Harvard", "Chicago", "IEEE", "Vancouver"})


def normalize_style(raw: str | None) -> CitationStyle:
    s = (raw or "APA").strip().upper()
    if s not in ALLOWED_STYLES:
        return "APA"
    return s  # type: ignore[return-value]


def section_heading(style: CitationStyle) -> str:
    """Section title per citation style."""
    if style == "MLA":
        return "Works Cited"
    if style == "Chicago":
        return "Bibliography"
    if style == "IEEE":
        return "References"
    if style == "Vancouver":
        return "References"
    return "References"


def _clean_line(line: str) -> str:
    s = line.strip()
    s = re.sub(r"[ \t]+", " ", s)
    return s


def _alphabetical_sort_key(line: str) -> str:
    """
    Sort key for reference lines: prefer first author's surname (text before ',')
    or text before '(' for corporate / (Year) forms, else first words of title-first entries.
    """
    x = _clean_line(line)
    x = re.sub(r"^\*+", "", x)

    if "(" in x:
        head = x.split("(", 1)[0].strip()
        if "," in head:
            return head.split(",", 1)[0].strip().lower()
        return head.lower()

    m = re.match(r"^([^,]+),", x)
    if m:
        return m.group(1).strip().lower()

    t = re.sub(r"^\*([^*]+)\*", r"\1", x)
    if not t:
        t = x
    t = re.sub(r"^(a|an|the)\s+", "", t, count=1, flags=re.I)
    return t.strip().lower()[:240]


def _dedupe_preserve_order(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines:
        c = _clean_line(ln)
        if not c:
            continue
        low = c.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(c)
    return out


def apply_light_style_tweaks(line: str, style: CitationStyle) -> str:
    """
    Minimal, safe touch-ups. Full APA↔MLA conversion requires structured data.
    """
    c = _clean_line(line)
    if style == "MLA":
        # Many student lists use straight quotes; MLA titles often use italics for larger works.
        # Leave content as-is unless obvious doubled spaces already fixed.
        return c
    if style == "Harvard":
        # Reference list layout is close to APA; keep line, ensure single space after periods in '). '
        return re.sub(r"\)\s*\.\s*", "). ", c)
    return c


def prepare_reference_section(
    citations: list[str],
    style: str | None = None,
) -> tuple[str, list[str]]:
    """
    Return (section_heading, sorted_citation_lines) for the document or API.

    Citations are sorted alphabetically by inferred author / title key.
    """
    st = normalize_style(style)
    title = section_heading(st)
    raw = _dedupe_preserve_order([str(x) for x in citations])
    tweaked = [apply_light_style_tweaks(x, st) for x in raw]
    tweaked.sort(key=_alphabetical_sort_key)
    return title, tweaked


def format_reference_section_text(citations: list[str], style: str | None = None) -> str:
    """Plain-text block: heading + blank line + one entry per line."""
    heading, lines = prepare_reference_section(citations, style)
    body = "\n".join(lines)
    return f"{heading}\n{body}" if body else heading
