"""Shared helpers for markdown heading detection in humanizer/detection flows."""

from __future__ import annotations

import re

_HEADING_LINE_RE = re.compile(r"^##\s+.+$", re.MULTILINE)

# Common academic section titles that StealthWriter often collapses onto body text.
_SECTION_TITLE = (
    r"Journal Entry\s+\d+"
    r"|Introduction|Reflection|References|Conclusion|Discussion"
    r"|Literature Review|Critical Analysis|Cover Page|Abstract|Methodology"
)

# "## Introduction The body..." on one line.
_INLINE_HEADING_RE = re.compile(
    rf"(?im)^(##\s+(?:{_SECTION_TITLE}))[ \t]+(\S.+)$"
)

# "...compete. ## Journal Entry 1 Continuing..." mid-paragraph.
_MID_HEADING_RE = re.compile(
    rf"(?i)([.!?])[ \t]*(##\s+(?:{_SECTION_TITLE}))[ \t]+(?=\S)"
)

_BARE_MID_HEADING_RE = re.compile(
    rf"(?i)(?<=[^\n])(##\s+(?:{_SECTION_TITLE}))[ \t]+(?=(?-i:[A-Z(\"“\[]))"
)


def is_heading_only(text: str) -> bool:
    """True only for a single markdown heading line (no body)."""
    stripped = (text or "").strip()
    if not stripped.startswith("## "):
        return False
    return "\n" not in stripped


def protect_markdown_headings(text: str) -> tuple[str, list[str]]:
    """Replace ``##`` headings with placeholders so providers do not rewrite them."""
    headings: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        headings.append(match.group(0).strip())
        # Keep placeholder on its own paragraph so providers preserve breaks.
        return f"\n\n[[[HEADING_{len(headings) - 1}]]]\n\n"

    protected = _HEADING_LINE_RE.sub(_replace, text or "")
    protected = re.sub(r"\n{3,}", "\n\n", protected).strip()
    return protected, headings


def restore_markdown_headings(text: str, headings: list[str]) -> str:
    restored = text or ""
    for index, heading in enumerate(headings):
        token = f"[[[HEADING_{index}]]]"
        block = f"\n\n{heading}\n\n"
        if token in restored:
            restored = restored.replace(token, block)
            continue
        loose = re.compile(rf"\[+\s*\[*\s*HEADING[_\s-]*{index}\s*\]*\s*\]+", re.I)
        restored = loose.sub(block, restored, count=1)
    return normalize_markdown_headings(restored)


def _split_inline_heading(match: re.Match[str]) -> str:
    rest = match.group(2)
    # "## Introduction to EcoNova Solutions" is one heading, not heading + body.
    if len(rest.split()) < 8 and not rest.rstrip().endswith((".", "!", "?")):
        return match.group(0)
    return f"{match.group(1)}\n\n{rest}"


def normalize_markdown_headings(text: str) -> str:
    """Force ``##`` headings onto their own lines with a blank line after."""
    if not (text or "").strip():
        return text or ""

    normalized = text
    # Mid-sentence collapsed headings after punctuation.
    normalized = _MID_HEADING_RE.sub(r"\1\n\n\2\n\n", normalized)
    # Any remaining inline "## Title Body" at line start.
    normalized = _INLINE_HEADING_RE.sub(_split_inline_heading, normalized)
    # Bare mid-string headings without preceding punctuation.
    normalized = _BARE_MID_HEADING_RE.sub(r"\n\n\1\n\n", normalized)
    # Ensure blank line after heading-only lines.
    normalized = re.sub(r"(?m)^(##\s+.+)\n(?!\n)", r"\1\n\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def is_references_section_title(title: str) -> bool:
    t = (title or "").strip().lower()
    if ":" in t and re.match(r"^(?:section|part|chapter)\b", t):
        t = t.split(":", 1)[1].strip()
    return t in {"references", "reference list", "bibliography", "works cited"} or t.startswith(
        "reference"
    )


# Function words that alone (or only with each other) are broken sentence starts, not headings.
# Catches paste artifacts like a lone "<p>The</p>" before the rest of the paragraph.
_TITLE_STOPWORDS = frozenset(
    """
    a an the and or but if as at by for from in into of on to with without
    this that these those it its is are was were be been being have has had
    do does did will would could should may might must shall can not no nor
    so yet than then when where while although however therefore moreover
    furthermore thus hence also just only even about after before between
    during through under over up down out off again further once here there
    all each every both few more most other some such own same too very
    we our they their he she his her them us you your i my me
    """.split()
)
_TITLE_WORD = re.compile(r"[A-Za-z0-9][\w'-]*")
_SENTENCE_END_TITLE = re.compile(r"[.!?…][\"'”’)\]]*\s*$")
_MD_WRAP_TITLE = re.compile(r"^(?:\*\*|__)(.+?)(?:\*\*|__)$|^#{1,6}\s+(.+?)$")


def title_core(text: str) -> str:
    """Bare title text: strip ``**…**`` / ``## …`` wrappers used for bold/markdown headings."""
    stripped = (text or "").strip()
    m = _MD_WRAP_TITLE.match(stripped)
    if m:
        return (m.group(1) or m.group(2) or "").strip()
    return stripped


def _title_tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in _TITLE_WORD.finditer(text or "")]


def is_sentence_start_fragment(text: str) -> bool:
    """Lone articles / stopwords split into their own block (e.g. ``The`` before the body)."""
    core = title_core(text)
    if not core or "\n" in (text or "").strip():
        return False
    if _SENTENCE_END_TITLE.search(core):
        return False
    words = core.split()
    if not words or len(words) > 3:
        return False
    tokens = _title_tokens(core)
    return bool(tokens) and all(t in _TITLE_STOPWORDS for t in tokens)


def is_explicit_heading_text(text: str, *, max_words: int = 12) -> bool:
    """True only when the heading is marked — no guessing from short plain lines.

    Counts as a heading:
    - markdown ``# …`` / ``## …``
    - whole-line ``**…**`` / ``__…__``
    - a References / Bibliography label (structural section)

    Plain ``Methodology`` or ``The`` alone are prose.
    """
    stripped = (text or "").strip()
    if not stripped or "\n" in stripped:
        return False
    if _MD_WRAP_TITLE.match(stripped):
        core = title_core(stripped)
        if not core or len(core.split()) > max_words:
            return False
        if _SENTENCE_END_TITLE.search(core):
            return False
        return True
    core = stripped.rstrip(":")
    return len(core.split()) <= 3 and is_references_section_title(core)


def looks_like_bare_title(text: str, *, max_words: int = 12) -> bool:
    """Deprecated alias — only explicit / References headings, not length guesses."""
    return is_explicit_heading_text(text, max_words=max_words)


def split_off_references(content: str) -> tuple[str, str]:
    """Split markdown into (body_without_refs, references_block). Refs stay untouched by humanize."""
    text = (content or "").strip()
    if not text:
        return "", ""
    pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return text, ""

    body_parts: list[str] = []
    ref_parts: list[str] = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            body_parts.append(preamble)

    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : end].strip()
        if is_references_section_title(title):
            if block:
                ref_parts.append(block)
        else:
            if block:
                body_parts.append(block)

    body = normalize_markdown_headings("\n\n".join(body_parts))
    refs = normalize_markdown_headings("\n\n".join(ref_parts))
    return body, refs


def join_body_and_references(body: str, references: str) -> str:
    parts = [p for p in [(body or "").strip(), (references or "").strip()] if p]
    return normalize_markdown_headings("\n\n".join(parts))
