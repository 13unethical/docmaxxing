"""Academic heading spacing — paragraph properties, not blank lines."""

from __future__ import annotations

HEADING_SPACE_AFTER_PT = 0


def body_line_height_pt(font_size_pt: int, line_spacing: float) -> int:
    """One body line height in points."""
    return max(6, int(round(font_size_pt * line_spacing)))


def heading_space_before_pt(font_size_pt: int, line_spacing: float) -> int:
    """
    Space before a heading that follows body text.

    Double-spaced body already starts on the next line, so extra space_before
    would look like a double blank line. Single / 1.5 spacing needs one line gap.
    """
    if line_spacing >= 1.99:
        return 0
    return body_line_height_pt(font_size_pt, line_spacing)


def resolve_paragraph_spacing(
    *,
    level: int,
    prev_level: int,
    next_level: int,
    prev_has_text: bool,
    font_size_pt: int,
    line_spacing: float,
    body_space_before_pt: int,
    body_space_after_pt: int,
) -> tuple[int, int]:
    """
    Space before/after for one paragraph.

    Headings get one line of space before when the previous block is body text.
    Body text before a heading gets no extra space after (gap lives on the heading).
    """
    if level > 0:
        after_body = prev_level == 0 and prev_has_text
        space_before = (
            heading_space_before_pt(font_size_pt, line_spacing) if after_body else 0
        )
        return space_before, HEADING_SPACE_AFTER_PT

    space_before = body_space_before_pt
    if next_level > 0:
        space_after = 0
    elif body_space_after_pt > 0:
        space_after = body_space_after_pt
    elif line_spacing < 1.99:
        space_after = min(12, body_line_height_pt(font_size_pt, line_spacing))
    else:
        space_after = 0
    return space_before, space_after
