"""IEEE StyleProfile (single-column adaptation) — FORMATTER_V2_STYLE_REFERENCE.md §4."""

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
        size_pt=10.0,  # [R] body is 10pt
        alignment="justify",  # [R]
        line_spacing=1.0,  # [R]
        first_line_indent_in=0.2,  # [R] narrow indent ~0.2", not 0.5"
    )

    doc_title = typography(
        family="Times New Roman",
        size_pt=24.0,  # [R]
        bold=False,  # [R] начертание «—» (not bold in reference table)
        alignment="center",  # [R]
        line_spacing=1.0,  # [R]
        space_before_pt=0.0,
        space_after_pt=12.0,  # [R] 0/12
    )

    heading_1 = typography(
        family="Times New Roman",
        size_pt=10.0,  # [R]
        # [R] small caps + Roman I, II, III — numbering is render-layer
        bold=False,
        small_caps=True,  # [R]
        text_case="preserve",  # small_caps ≠ UPPER — do not combine
        alignment="center",  # [R]
        line_spacing=1.0,  # [R]
        space_before_pt=12.0,  # [R] 12/6
        space_after_pt=6.0,
        keep_with_next=True,
    )

    heading_2 = typography(
        family="Times New Roman",
        size_pt=10.0,  # [R]
        italic=True,  # [R] italic; lettered A, B, C at render layer
        alignment="left",  # [R]
        line_spacing=1.0,  # [R]
        space_before_pt=6.0,  # [R] 6/3
        space_after_pt=3.0,
        keep_with_next=True,
    )

    heading_3 = typography(
        family="Times New Roman",
        size_pt=10.0,  # [R]
        italic=True,  # [R]
        alignment="left",  # [R]
        line_spacing=1.0,  # [R]
        space_before_pt=6.0,  # [R] 6/3
        space_after_pt=3.0,
        first_line_indent_in=0.25,  # [R]
        keep_with_next=True,
    )

    block_quote = typography(
        family="Times New Roman",
        size_pt=9.0,  # [C]
        alignment="justify",  # [C]
        line_spacing=1.0,  # [C]
        space_before_pt=6.0,  # [C]
        space_after_pt=6.0,  # [C]
        left_indent_in=0.25,  # [C]
        first_line_indent_in=0.0,
    )

    table_caption = typography(
        family="Times New Roman",
        size_pt=8.0,  # [R] TABLE I small caps — small_caps flag TBD
        text_case="upper",  # [H] approximate small caps
        alignment="center",  # [R] above, centered
        line_spacing=1.0,  # [R]
        space_after_pt=3.0,  # [R] 0/3
    )

    figure_caption = typography(
        family="Times New Roman",
        size_pt=8.0,  # [R]
        alignment="left",  # [R] Fig. 1. below
        line_spacing=1.0,  # [R]
        space_before_pt=3.0,  # [R] 3/0
    )

    refs_heading = typography(
        family="Times New Roman",
        size_pt=10.0,  # [R]
        small_caps=True,  # [R]
        text_case="preserve",  # small_caps ≠ UPPER — do not combine
        alignment="center",  # [R]
        line_spacing=1.0,  # [R]
        space_before_pt=12.0,  # [R] 12/6
        space_after_pt=6.0,
        keep_with_next=True,
    )

    refs_entry = typography(
        family="Times New Roman",
        size_pt=8.0,  # [R]
        alignment="left",  # [R]
        line_spacing=1.0,  # [R]
        hanging_indent_in=0.25,  # [R] hanging 0.25" + [1] numbering at render
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
        ParagraphRole.COVER_TITLE: clone(doc_title),  # inherited — IEEE has no separate cover page
        ParagraphRole.LIST_BULLET: clone(body, first_line_indent_in=0.0, left_indent_in=0.25),  # inherited
        ParagraphRole.LIST_NUMBER: clone(body, first_line_indent_in=0.0, left_indent_in=0.25),  # inherited
    }

    return StyleProfile(
        name=StyleName.IEEE,
        display_name="IEEE",
        source_manual="IEEE Editorial Style Manual; IEEE Reference Guide (single-column [H] adaptation)",
        date_format="month_day_year",
        page=PageSetup(
            size=PageSize.LETTER,  # [R]
            margins=Margins(
                top_in=0.75,  # [R] fixed — must not be overwritten by margin_preset
                bottom_in=1.0,  # [R]
                left_in=0.625,  # [R]
                right_in=0.625,  # [R]
            ),
        ),
        page_numbering=PageNumbering(
            position=PageNumberPosition.BOTTOM_CENTER,  # [C]
            skip_first_page=True,  # [C]/matrix: title page not numbered
        ),
        roles=apply_inheritance(core),
        citations=CitationConfig(
            default_in_text_mode=InTextMode.NUMERIC,  # [R] [n] from bibliography order — not hard-coded "[1]"
            et_al_threshold=3,  # n/a for numeric; keep schema minimum
            include_page_numbers=False,
        ),
        references=ReferencesConfig(
            heading_text="References",  # [R]
            on_new_page=False,  # [H] reference table does not require new page for IEEE
            sort=ReferenceSort.ORDER_OF_APPEARANCE,  # [R] not alphabetical
            numbered=True,  # [R]
        ),
        captions=CaptionConfig(
            table_position="above",  # [R]
            figure_position="below",  # [R]
            table_label="TABLE",  # [R]
            figure_label="Fig.",  # [R]
        ),
        cover_page=CoverPage(
            enabled=False,  # matrix: no title page
        ),
    )
