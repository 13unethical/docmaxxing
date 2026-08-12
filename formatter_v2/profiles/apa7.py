"""APA 7 StyleProfile — values from docs/FORMATTER_V2_STYLE_REFERENCE.md §1."""

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
        size_pt=12.0,
        alignment="left",  # [R] APA: flush left, ragged right — not justify
        line_spacing=2.0,  # [R] double-spaced throughout
        space_before_pt=0.0,
        space_after_pt=0.0,
        first_line_indent_in=0.5,  # [R] first-line indent 0.5"
    )

    doc_title = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R] APA student paper: all text 12pt — not 16
        bold=True,
        text_case="title_case",  # [R]
        alignment="center",  # [R]
        line_spacing=2.0,  # [R] double
        space_before_pt=0.0,
        space_after_pt=0.0,
    )

    abstract_heading = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        bold=True,  # [R]
        alignment="center",  # [R]
        line_spacing=2.0,  # [R]
    )

    abstract = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
        first_line_indent_in=0.0,  # [R] abstract has no first-line indent
    )

    keywords = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        italic=True,  # [R] «Keywords:» italic (label styling)
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
        first_line_indent_in=0.5,  # [R]
    )

    heading_1 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R] APA headings stay 12pt
        bold=True,  # [R]
        text_case="title_case",  # [R]
        alignment="center",  # [R]
        line_spacing=2.0,  # [R] double — V1 incorrectly forced 1.0
        keep_with_next=True,
    )

    heading_2 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        bold=True,  # [R]
        text_case="title_case",  # [R]
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
        keep_with_next=True,
    )

    heading_3 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        bold=True,  # [R]
        italic=True,  # [R]
        text_case="title_case",  # [R]
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
        keep_with_next=True,
    )

    heading_4 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        bold=True,  # [R]
        text_case="title_case",  # [R] trailing period is content rule, not TypographySpec
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
        left_indent_in=0.5,  # [R]
        keep_with_next=True,
    )

    block_quote = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
        left_indent_in=0.5,  # [R]
        first_line_indent_in=0.0,  # [R] no first-line indent on block quotes
    )

    list_item = typography(
        family="Times New Roman",
        size_pt=12.0,  # [C]
        alignment="left",  # [C]
        line_spacing=2.0,  # [C]
        left_indent_in=0.5,  # [C]
    )

    table_caption = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R] number bold / title italic is multi-run layout, not one flag
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
    )

    figure_caption = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
    )

    refs_heading = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        bold=True,  # [R]
        alignment="center",  # [R]
        line_spacing=2.0,  # [R]
        page_break_before=True,  # [R] new page
        keep_with_next=True,
    )

    refs_entry = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        alignment="left",  # [R]
        line_spacing=2.0,  # [R]
        hanging_indent_in=0.5,  # [R] hanging 0.5" from profile
    )

    cover_title = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        bold=True,  # [R]
        text_case="title_case",  # [R]
        alignment="center",  # [R]
        line_spacing=2.0,  # [R]
    )

    core = {
        ParagraphRole.DOC_TITLE: doc_title,
        ParagraphRole.ABSTRACT_HEADING: abstract_heading,
        ParagraphRole.ABSTRACT: abstract,
        ParagraphRole.KEYWORDS: keywords,
        ParagraphRole.HEADING_1: heading_1,
        ParagraphRole.HEADING_2: heading_2,
        ParagraphRole.HEADING_3: heading_3,
        ParagraphRole.HEADING_4: heading_4,
        ParagraphRole.BODY: body,
        ParagraphRole.BLOCK_QUOTE: block_quote,
        ParagraphRole.LIST_BULLET: list_item,
        ParagraphRole.LIST_NUMBER: clone(list_item),
        ParagraphRole.TABLE_CAPTION: table_caption,
        ParagraphRole.FIGURE_CAPTION: figure_caption,
        ParagraphRole.REFERENCES_HEADING: refs_heading,
        ParagraphRole.REFERENCES_ENTRY: refs_entry,
        ParagraphRole.COVER_TITLE: cover_title,
        # inherited roles filled by apply_inheritance()
    }
    # FOOTNOTE not in APA student table — inherit BODY via apply_inheritance

    return StyleProfile(
        name=StyleName.APA7,
        display_name="APA 7",
        source_manual="Publication Manual of the American Psychological Association, 7th ed.",
        date_format="month_day_year",
        page=PageSetup(
            size=PageSize.A4,  # [H] default for non-US audience; Letter allowed in US
            margins=Margins(top_in=1.0, bottom_in=1.0, left_in=1.0, right_in=1.0),  # [R]
        ),
        page_numbering=PageNumbering(
            position=PageNumberPosition.TOP_RIGHT,  # [R]
            skip_first_page=False,  # [R] title page is numbered
        ),
        roles=apply_inheritance(core),
        citations=CitationConfig(
            default_in_text_mode=InTextMode.PARENTHETICAL,  # [R] (Smith, 2020)
            use_ampersand=True,  # [R] & in parenthetical
            et_al_threshold=3,  # [R] et al. at 3+ authors
        ),
        references=ReferencesConfig(
            heading_text="References",  # [R]
            on_new_page=True,  # [R]
            sort=ReferenceSort.ALPHABETICAL,  # [R]
            numbered=False,  # [R]
        ),
        captions=CaptionConfig(
            table_position="above",  # [R] APA table captions above
            figure_position="above",  # [R] APA figure captions also above
            table_label="Table",  # [R]
            figure_label="Figure",  # [R]
            two_line=True,  # [R] bold "Table N" + italic title on next line
        ),
        cover_page=CoverPage(
            enabled=True,  # [R] student paper has title page
            title="Assignment",  # placeholder until user/form fills real title
            top_spacer_lines=4,  # [R] 3–4 blank lines from top
        ),
    )
