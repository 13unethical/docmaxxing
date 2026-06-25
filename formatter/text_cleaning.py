"""
Optional normalization before layout.

When enabled, these steps can change whitespace (not “rewrite” sentences).
They run only if the user turns the toggles on.
"""

from __future__ import annotations

import re


def collapse_internal_spaces(text: str) -> str:
    """Turn runs of spaces/tabs into a single space (per line segment)."""
    # Preserve newlines but collapse horizontal whitespace
    lines = text.split("\n")
    cleaned_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
    return "\n".join(cleaned_lines)


def collapse_extra_blank_lines_paste(full_text: str) -> str:
    """
    For pasted input: 3+ consecutive newlines become exactly two (one blank line).
    """
    return re.sub(r"\n{3,}", "\n\n", full_text)


def collapse_paragraph_linebreaks(text: str) -> str:
    """Inside one paragraph, multiple newlines become a single space."""
    return re.sub(r"\s*\n\s*", " ", text).strip()


def clean_pasted_raw(
    raw: str,
    *,
    extra_spaces: bool,
    extra_linebreaks: bool,
) -> str:
    """Apply cleaning options to pasted text before splitting into paragraphs."""
    text = raw
    if extra_linebreaks:
        text = collapse_extra_blank_lines_paste(text)
    if extra_spaces:
        text = collapse_internal_spaces(text)
    return text


def clean_paragraph_string(
    text: str,
    *,
    extra_spaces: bool,
    extra_linebreaks: bool,
) -> str:
    """Apply cleaning to a single paragraph's text (uploaded .docx)."""
    result = text
    if extra_linebreaks:
        result = collapse_paragraph_linebreaks(result)
    if extra_spaces:
        result = collapse_internal_spaces(result.replace("\n", " "))
        result = re.sub(r"[ \t]+", " ", result).strip()
    return result


def paragraphs_snapshot_apply_cleaning(document, *, extra_spaces: bool, extra_linebreaks: bool) -> None:
    """
    Walk body paragraphs on an opened document and rewrite text when cleaning
    changes something (flattening runs inside those paragraphs).
    """
    from formatter.headings import set_plain_paragraph_text

    for paragraph in document.paragraphs:
        old = paragraph.text
        new = clean_paragraph_string(
            old,
            extra_spaces=extra_spaces,
            extra_linebreaks=extra_linebreaks,
        )
        if new != old:
            set_plain_paragraph_text(paragraph, new)
