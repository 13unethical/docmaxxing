"""MLA 9 StyleProfile — values from docs/FORMATTER_V2_STYLE_REFERENCE.md §2."""

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
        size_pt=12.0,  # [R]
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
        first_line_indent_in=0.5,  # [R]
    )

    doc_title = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        bold=False,  # [R] title is not bold
        text_case="title_case",  # [R]
        alignment="center",  # [R]
        line_spacing=2.0,  # [R]
    )

    heading_1 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [C] MLA does not prescribe hierarchy — house convention
        bold=True,  # [C]
        alignment="left",  # [C]
        line_spacing=2.0,  # [C]
        keep_with_next=True,
    )

    heading_2 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [C]
        italic=True,  # [C]
        alignment="left",  # [C]
        line_spacing=2.0,  # [C]
        keep_with_next=True,
    )

    heading_3 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [C]
        bold=True,  # [C]
        alignment="center",  # [C]
        line_spacing=2.0,  # [C]
        keep_with_next=True,
    )

    block_quote = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
        left_indent_in=0.5,  # [R]
        first_line_indent_in=0.0,  # [R]
    )

    table_caption = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R] Table 1 label above
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
    )

    figure_caption = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R] Fig. 1. below
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
    )

    refs_heading = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        bold=False,  # [R] Works Cited is NOT bold
        alignment="center",  # [R] centered — V1 wrongly used bold left
        line_spacing=2.0,  # [R]
        page_break_before=True,  # [R] new page
        keep_with_next=True,
    )

    refs_entry = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
        hanging_indent_in=0.5,  # [R]
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
        # COVER_TITLE: MLA has no title page — inherited from DOC_TITLE below
        ParagraphRole.COVER_TITLE: clone(doc_title),  # inherited (no MLA cover)
        ParagraphRole.LIST_BULLET: clone(body, left_indent_in=0.5, first_line_indent_in=0.0),  # inherited
        ParagraphRole.LIST_NUMBER: clone(body, left_indent_in=0.5, first_line_indent_in=0.0),  # inherited
    }

    return StyleProfile(
        name=StyleName.MLA9,
        display_name="MLA 9",
        source_manual="MLA Handbook, 9th ed.",
        date_format="day_month_year",
        page=PageSetup(
            size=PageSize.A4,  # [H]
            margins=Margins(top_in=1.0, bottom_in=1.0, left_in=1.0, right_in=1.0),  # [R]
        ),
        page_numbering=PageNumbering(
            position=PageNumberPosition.TOP_RIGHT,  # [R] «Surname 1» layout is render-layer
            skip_first_page=False,  # [R] every page including first
        ),
        roles=apply_inheritance(core),
        citations=CitationConfig(
            default_in_text_mode=InTextMode.PARENTHETICAL,  # [R] (Smith 42) — no year
            use_ampersand=False,  # [R]
            et_al_threshold=3,  # [R] et al. at 3+
        ),
        references=ReferencesConfig(
            heading_text="Works Cited",  # [R]
            on_new_page=True,  # [R]
            sort=ReferenceSort.ALPHABETICAL,  # [R]
            numbered=False,  # [R]
        ),
        captions=CaptionConfig(
            table_position="above",  # [R]
            figure_position="below",  # [R]
            table_label="Table",  # [R]
            figure_label="Fig.",  # [R] «Fig. 1.»
        ),
        cover_page=CoverPage(
            enabled=False,  # [R] MLA has no title page
        ),
    )
