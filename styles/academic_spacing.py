"""Shared academic heading spacing applied to every citation-style profile."""

from __future__ import annotations

from dataclasses import replace

from styles.profile import (
    ACADEMIC_HEADING2_SPACE_AFTER_PT,
    ACADEMIC_HEADING2_SPACE_BEFORE_PT,
    ACADEMIC_HEADING3_SPACE_AFTER_PT,
    ACADEMIC_HEADING3_SPACE_BEFORE_PT,
    ACADEMIC_TITLE_SPACE_AFTER_PT,
    ACADEMIC_TITLE_SPACE_BEFORE_PT,
    ParagraphFormatSpec,
)


def with_title_spacing(spec: ParagraphFormatSpec) -> ParagraphFormatSpec:
    return replace(
        spec,
        space_before_pt=ACADEMIC_TITLE_SPACE_BEFORE_PT,
        space_after_pt=ACADEMIC_TITLE_SPACE_AFTER_PT,
    )


def with_heading2_spacing(spec: ParagraphFormatSpec) -> ParagraphFormatSpec:
    return replace(
        spec,
        space_before_pt=ACADEMIC_HEADING2_SPACE_BEFORE_PT,
        space_after_pt=ACADEMIC_HEADING2_SPACE_AFTER_PT,
    )


def with_heading3_spacing(spec: ParagraphFormatSpec) -> ParagraphFormatSpec:
    return replace(
        spec,
        space_before_pt=ACADEMIC_HEADING3_SPACE_BEFORE_PT,
        space_after_pt=ACADEMIC_HEADING3_SPACE_AFTER_PT,
    )
