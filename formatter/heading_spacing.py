"""Heading spacing — delegates to the formatting style engine."""

from __future__ import annotations

from formatter.style_engine import resolve_contextual_spacing
from styles import load_profile
from styles.profile import ACADEMIC_HEADING2_SPACE_BEFORE_PT


def heading_space_before_pt(font_size_pt: int, line_spacing: float) -> int:
    """Major heading (Heading 2) space before — fixed academic rule."""
    return ACADEMIC_HEADING2_SPACE_BEFORE_PT


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
    format_style: str = "harvard",
) -> tuple[int, int]:
    """Backward-compatible wrapper — spacing comes from the active profile."""
    profile = load_profile(format_style)
    if body_space_before_pt or body_space_after_pt:
        from dataclasses import replace

        profile = replace(
            profile,
            body=replace(
                profile.body,
                contextual=replace(
                    profile.body.contextual,
                    body_space_before_pt=body_space_before_pt or profile.body.contextual.body_space_before_pt,
                    body_space_after_pt=body_space_after_pt or profile.body.contextual.body_space_after_pt,
                ),
            ),
        )
    if level > 0:
        role = "heading2"
        if level == 1:
            role = "title"
        elif level == 3:
            role = "heading3"
        return resolve_contextual_spacing(
            profile,
            role=role,
            prev_level=prev_level,
            next_level=next_level,
            prev_has_text=prev_has_text,
        )
    return resolve_contextual_spacing(
        profile,
        role="body",
        prev_level=prev_level,
        next_level=next_level,
        prev_has_text=prev_has_text,
    )
