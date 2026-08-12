"""Harvard (Cite Them Right) house style — FORMATTER_V2_STYLE_REFERENCE.md §5."""

from __future__ import annotations

from formatter_v2.profiles._helpers import apply_inheritance, clone, typography
from formatter_v2.spec import (
    CaptionConfig,
    CitationConfig,
    CoverPage,
    InTextMode,
    Margins,
    PageNumberPosition,
    PageNumbering,
    PageSetup,
    PageSize,
    ParagraphRole,
    ReferenceSort,
    ReferencesConfig,
    StyleName,
    StyleProfile,
)


def profile() -> StyleProfile:
    body = typography(
        family="Times New Roman",
        size_pt=12.0,  # [H]
        alignment="justify",  # [H] UK coursework look — space-after instead of first-line indent
        line_spacing=1.5,  # [H]
        space_after_pt=12.0,  # [H]
        first_line_indent_in=0.0,  # [H] no first-line indent
    )

    doc_title = typography(
        family="Times New Roman",
        size_pt=16.0,  # [H]
        bold=True,  # [H]
        alignment="center",  # [H]
        line_spacing=1.5,  # [H]
        space_before_pt=0.0,
        space_after_pt=24.0,  # [H] 0/24
    )

    heading_1 = typography(
        family="Times New Roman",
        size_pt=14.0,  # [H]
        bold=True,  # [H]
        alignment="left",  # [H]
        line_spacing=1.5,  # [H]
        space_before_pt=18.0,  # [H] 18/6
        space_after_pt=6.0,
        keep_with_next=True,
    )

    heading_2 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [H]
        bold=True,  # [H]
        alignment="left",  # [H]
        line_spacing=1.5,  # [H]
        space_before_pt=12.0,  # [H] 12/6
        space_after_pt=6.0,
        keep_with_next=True,
    )

    heading_3 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [H]
        bold=True,  # [H]
        italic=True,  # [H]
        alignment="left",  # [H]
        line_spacing=1.5,  # [H]
        space_before_pt=12.0,  # [H] 12/4
        space_after_pt=4.0,
        keep_with_next=True,
    )

    block_quote = typography(
        family="Times New Roman",
        size_pt=12.0,  # [H]
        alignment="left",  # [H]
        line_spacing=1.0,  # [H]
        space_before_pt=6.0,  # [H]
        space_after_pt=6.0,  # [H]
        left_indent_in=0.5,  # [H]
        first_line_indent_in=0.0,
    )

    table_caption = typography(
        family="Times New Roman",
        size_pt=11.0,  # [H] above
        alignment="left",  # [H]
        line_spacing=1.0,  # [H]
        space_after_pt=6.0,  # [H] 0/6
    )

    figure_caption = typography(
        family="Times New Roman",
        size_pt=11.0,  # [H] below
        alignment="left",  # [H]
        line_spacing=1.0,  # [H]
        space_before_pt=6.0,  # [H] 6/0
    )

    refs_heading = typography(
        family="Times New Roman",
        size_pt=14.0,  # [H]
        bold=True,  # [H]
        alignment="left",  # [H] left — unlike APA/MLA center
        line_spacing=1.5,  # [H]
        space_after_pt=12.0,  # [H] 0/12
        page_break_before=True,  # [H] new page
        keep_with_next=True,
    )

    refs_entry = typography(
        family="Times New Roman",
        size_pt=12.0,  # [H]
        alignment="left",  # [H]
        line_spacing=1.5,  # [H]
        space_after_pt=6.0,  # [H] 0/6
        hanging_indent_in=0.5,  # [H]
    )

    cover_title = typography(
        family="Times New Roman",
        size_pt=16.0,  # [H] match DOC_TITLE
        bold=True,  # [H]
        alignment="center",  # [H]
        line_spacing=1.5,  # [H]
    )

    core = {
        ParagraphRole.DOC_TITLE: doc_title,
        ParagraphRole.HEADING_1: heading_1,
        ParagraphRole.HEADING_2: heading_2,
        ParagraphRole.HEADING_3: heading_3,
        ParagraphRole.BODY: body,
        ParagraphRole.BLOCK_QUOTE: block_quote,
        ParagraphRole.TABLE_CAPTION: table_caption,
        ParagraphRole.FIGURE_CAPTION: figure_caption,
        ParagraphRole.REFERENCES_HEADING: refs_heading,
        ParagraphRole.REFERENCES_ENTRY: refs_entry,
        ParagraphRole.COVER_TITLE: cover_title,
        ParagraphRole.LIST_BULLET: clone(body, alignment="left", left_indent_in=0.5),  # inherited
        ParagraphRole.LIST_NUMBER: clone(body, alignment="left", left_indent_in=0.5),  # inherited
    }

    return StyleProfile(
        name=StyleName.HARVARD,
        display_name="Harvard (Cite Them Right)",
        source_manual="Cite Them Right (Pears & Shields) — DocMaxxing house style [H]",
        date_format="day_month_year",
        page=PageSetup(
            size=PageSize.A4,  # [H]
            margins=Margins(top_in=1.0, bottom_in=1.0, left_in=1.0, right_in=1.0),  # [H]
        ),
        page_numbering=PageNumbering(
            position=PageNumberPosition.BOTTOM_CENTER,  # [H]
            skip_first_page=True,  # [H] title page not numbered
        ),
        roles=apply_inheritance(core),
        citations=CitationConfig(
            default_in_text_mode=InTextMode.PARENTHETICAL,  # [R for CTR] (Smith, 2020)
            use_ampersand=False,  # [R for CTR] «and» between authors
            et_al_threshold=4,  # [R for CTR] et al. at 4+ (unlike APA 3+)
        ),
        references=ReferencesConfig(
            heading_text="References",  # [H] chose «References» over «Reference List»
            on_new_page=True,  # [H]
            sort=ReferenceSort.ALPHABETICAL,  # [H]
            numbered=False,  # [H]
        ),
        captions=CaptionConfig(
            table_position="above",  # [H]
            figure_position="below",  # [H]
        ),
        cover_page=CoverPage(
            enabled=True,  # [H]
            title="Assignment",  # placeholder until user/form fills real title
            top_spacer_lines=5,  # [H]
        ),
    )
