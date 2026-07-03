"""Harvard-style formatting profile."""

from __future__ import annotations

from styles.academic_spacing import with_heading2_spacing, with_heading3_spacing, with_title_spacing
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
    heading_font = FontSpec(family="Times New Roman", size_pt=16, bold=True)

    body_para = ParagraphFormatSpec(
        font=body_font,
        alignment="justify",
        line_spacing=1.5,
        line_spacing_rule="multiple",
        widow_control=True,
    )
    heading_para = with_heading2_spacing(
        ParagraphFormatSpec(
            font=heading_font,
            alignment="left",
            line_spacing=1.0,
            line_spacing_rule="single",
            keep_with_next=True,
            widow_control=True,
        )
    )

    return FormattingProfile(
        id="harvard",
        name="Harvard",
        title=with_title_spacing(
            ParagraphFormatSpec(
                font=FontSpec(family="Times New Roman", size_pt=16, bold=True),
                alignment="center",
                line_spacing=1.0,
                line_spacing_rule="single",
                keep_with_next=True,
            )
        ),
        heading1=heading_para,
        heading2=heading_para,
        heading3=with_heading3_spacing(
            ParagraphFormatSpec(
                font=FontSpec(family="Times New Roman", size_pt=14, bold=True, italic=True),
                alignment="left",
                line_spacing=1.0,
                line_spacing_rule="single",
                keep_with_next=True,
            )
        ),
        body=BodyStyleSpec(
            paragraph=body_para,
            contextual=ContextualSpacingRules(
                body_space_before_pt=0,
                body_space_after_pt=12,
                body_space_after_when_next_is_heading_pt=0,
            ),
        ),
        references=ReferencesStyleSpec(
            heading=heading_para,
            entry=ParagraphFormatSpec(
                font=body_font,
                alignment="justify",
                line_spacing=1.5,
                line_spacing_rule="multiple",
            ),
            contextual=ContextualSpacingRules(
                body_space_after_pt=12,
            ),
        ),
        page=PageSpec(margin_top_inches=1.0, margin_bottom_inches=1.0, margin_left_inches=1.0, margin_right_inches=1.0),
        cover_page=CoverPageSpec(),
    )
