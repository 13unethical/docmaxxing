"""APA 7th edition formatting profile."""

from __future__ import annotations

from styles.academic_spacing import (
    with_heading2_spacing,
    with_heading3_spacing,
    with_title_spacing,
)
from styles.profile import (
    BodyStyleSpec,
    ContextualSpacingRules,
    CoverPageSpec,
    FontSpec,
    FormattingProfile,
    PageSpec,
    ParagraphFormatSpec,
    ReferencesStyleSpec,
)


def profile() -> FormattingProfile:
    body_font = FontSpec(family="Times New Roman", size_pt=12)
    h2_font = FontSpec(family="Times New Roman", size_pt=12, bold=True)
    h3_font = FontSpec(family="Times New Roman", size_pt=12, bold=True, italic=True)

    return FormattingProfile(
        id="apa7",
        name="APA 7",
        title=with_title_spacing(
            ParagraphFormatSpec(
                font=FontSpec(family="Times New Roman", size_pt=16, bold=True),
                alignment="center",
                line_spacing=2.0,
                line_spacing_rule="double",
                keep_with_next=True,
                capitalization="title_case",
            )
        ),
        heading1=with_title_spacing(
            ParagraphFormatSpec(
                font=FontSpec(family="Times New Roman", size_pt=16, bold=True),
                alignment="center",
                line_spacing=2.0,
                line_spacing_rule="double",
                keep_with_next=True,
                capitalization="title_case",
            )
        ),
        heading2=with_heading2_spacing(
            ParagraphFormatSpec(
                font=h2_font,
                alignment="left",
                line_spacing=2.0,
                line_spacing_rule="double",
                keep_with_next=True,
                capitalization="title_case",
            )
        ),
        heading3=with_heading3_spacing(
            ParagraphFormatSpec(
                font=h3_font,
                alignment="left",
                line_spacing=2.0,
                line_spacing_rule="double",
                keep_with_next=True,
                capitalization="title_case",
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
                    font=h2_font,
                    alignment="center",
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
        page=PageSpec(
            margin_top_inches=1.0,
            margin_bottom_inches=1.0,
            margin_left_inches=1.0,
            margin_right_inches=1.0,
            page_number_position="top_right",
        ),
        cover_page=CoverPageSpec(title_font=FontSpec(family="Times New Roman", size_pt=16, bold=True)),
    )
