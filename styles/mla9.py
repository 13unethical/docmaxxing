"""MLA 9th edition formatting profile."""

from __future__ import annotations

from styles.academic_spacing import (
    with_heading2_spacing,
    with_heading3_spacing,
    with_title_spacing,
)
from styles.profile import (
    BodyStyleSpec,
    ContextualSpacingRules,
    FontSpec,
    FormattingProfile,
    PageSpec,
    ParagraphFormatSpec,
    ReferencesStyleSpec,
)


def profile() -> FormattingProfile:
    body_font = FontSpec(family="Times New Roman", size_pt=12)
    heading_font = FontSpec(family="Times New Roman", size_pt=12, bold=False)

    heading = with_heading2_spacing(
        ParagraphFormatSpec(
            font=heading_font,
            alignment="left",
            line_spacing=2.0,
            line_spacing_rule="double",
            keep_with_next=True,
        )
    )

    return FormattingProfile(
        id="mla9",
        name="MLA 9",
        title=with_title_spacing(
            ParagraphFormatSpec(
                font=FontSpec(family="Times New Roman", size_pt=12),
                alignment="center",
                line_spacing=2.0,
                line_spacing_rule="double",
                keep_with_next=True,
            )
        ),
        heading1=heading,
        heading2=heading,
        heading3=with_heading3_spacing(
            ParagraphFormatSpec(
                font=heading_font,
                alignment="left",
                line_spacing=2.0,
                line_spacing_rule="double",
                keep_with_next=True,
            )
        ),
        body=BodyStyleSpec(
            paragraph=ParagraphFormatSpec(
                font=body_font,
                alignment="left",
                line_spacing=2.0,
                line_spacing_rule="double",
                first_line_indent_inches=0.5,
            ),
            contextual=ContextualSpacingRules(
                body_space_before_pt=0,
                body_space_after_pt=0,
                body_space_after_when_next_is_heading_pt=0,
            ),
        ),
        references=ReferencesStyleSpec(
            heading=with_heading2_spacing(
                ParagraphFormatSpec(
                    font=FontSpec(family="Times New Roman", size_pt=12, bold=True),
                    alignment="left",
                    line_spacing=2.0,
                    line_spacing_rule="double",
                    keep_with_next=True,
                )
            ),
            entry=ParagraphFormatSpec(
                font=body_font,
                alignment="left",
                line_spacing=2.0,
                line_spacing_rule="double",
                hanging_indent_inches=0.5,
            ),
            contextual=ContextualSpacingRules(
                body_space_after_pt=0,
            ),
        ),
        page=PageSpec(page_number_position="top_right"),
    )
