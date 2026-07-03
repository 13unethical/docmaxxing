"""Chicago 17th edition (student paper) formatting profile."""

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

    return FormattingProfile(
        id="chicago17",
        name="Chicago 17",
        title=with_title_spacing(
            ParagraphFormatSpec(
                font=FontSpec(family="Times New Roman", size_pt=14, bold=True),
                alignment="center",
                line_spacing=1.5,
                line_spacing_rule="multiple",
                keep_with_next=True,
            )
        ),
        heading1=with_title_spacing(
            ParagraphFormatSpec(
                font=FontSpec(family="Times New Roman", size_pt=14, bold=True),
                alignment="center",
                line_spacing=1.5,
                line_spacing_rule="multiple",
                keep_with_next=True,
            )
        ),
        heading2=with_heading2_spacing(
            ParagraphFormatSpec(
                font=FontSpec(family="Times New Roman", size_pt=13, bold=True),
                alignment="left",
                line_spacing=1.5,
                line_spacing_rule="multiple",
                keep_with_next=True,
            )
        ),
        heading3=with_heading3_spacing(
            ParagraphFormatSpec(
                font=FontSpec(family="Times New Roman", size_pt=12, bold=True, italic=True),
                alignment="left",
                line_spacing=1.5,
                line_spacing_rule="multiple",
                keep_with_next=True,
            )
        ),
        body=BodyStyleSpec(
            paragraph=ParagraphFormatSpec(
                font=body_font,
                alignment="left",
                line_spacing=1.5,
                line_spacing_rule="multiple",
                first_line_indent_inches=0.5,
            ),
            contextual=ContextualSpacingRules(
                body_space_before_pt=0,
                body_space_after_pt=6,
                body_space_after_when_next_is_heading_pt=0,
            ),
        ),
        references=ReferencesStyleSpec(
            heading=with_heading2_spacing(
                ParagraphFormatSpec(
                    font=FontSpec(family="Times New Roman", size_pt=12, bold=True),
                    alignment="center",
                    line_spacing=1.5,
                    line_spacing_rule="multiple",
                    keep_with_next=True,
                )
            ),
            entry=ParagraphFormatSpec(
                font=body_font,
                alignment="left",
                line_spacing=1.5,
                line_spacing_rule="multiple",
                hanging_indent_inches=0.5,
            ),
            contextual=ContextualSpacingRules(
                body_space_after_pt=6,
            ),
        ),
        page=PageSpec(page_number_position="top_right"),
    )
