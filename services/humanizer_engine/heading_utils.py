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
    rf"(?i)([.!?])\s*(##\s+(?:{_SECTION_TITLE}))[ \t]+(?=\S)"
)

_BARE_MID_HEADING_RE = re.compile(
    rf"(?i)(?<!\n)(##\s+(?:{_SECTION_TITLE}))[ \t]+(?=[A-Z(\"“\[])"
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


def normalize_markdown_headings(text: str) -> str:
    """Force ``##`` headings onto their own lines with a blank line after."""
    if not (text or "").strip():
        return text or ""

    normalized = text
    # Mid-sentence collapsed headings after punctuation.
    normalized = _MID_HEADING_RE.sub(r"\1\n\n\2\n\n", normalized)
    # Any remaining inline "## Title Body" at line start.
    normalized = _INLINE_HEADING_RE.sub(r"\1\n\n\2", normalized)
    # Bare mid-string headings without preceding punctuation.
    normalized = _BARE_MID_HEADING_RE.sub(r"\n\n\1\n\n", normalized)
    # Ensure blank line after heading-only lines.
    normalized = re.sub(r"(?m)^(##\s+.+)\n(?!\n)", r"\1\n\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def is_references_section_title(title: str) -> bool:
    t = (title or "").strip().lower()
    return t in {"references", "reference list", "bibliography", "works cited"} or t.startswith(
        "reference"
    )


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
