"""Chicago 17 / Turabian 9 (notes-bibliography) — FORMATTER_V2_STYLE_REFERENCE.md §3."""

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
        line_spacing=2.0,  # [R] body double-spaced
        first_line_indent_in=0.5,  # [R]
    )

    doc_title = typography(
        family="Times New Roman",
        size_pt=12.0,  # [C]
        bold=True,  # [C]
        alignment="center",  # [C]
        line_spacing=2.0,  # [C]
    )

    heading_1 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [C]
        bold=True,  # [C]
        text_case="title_case",  # [C]
        alignment="center",  # [C]
        line_spacing=2.0,  # [C]
        keep_with_next=True,
    )

    heading_2 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [C]
        bold=False,  # [C] «—» = not bold
        alignment="center",  # [C]
        line_spacing=2.0,  # [C]
        keep_with_next=True,
    )

    heading_3 = typography(
        family="Times New Roman",
        size_pt=12.0,  # [C]
        bold=True,  # [C]
        italic=True,  # [C]
        alignment="left",  # [C]
        line_spacing=2.0,  # [C]
        keep_with_next=True,
    )

    block_quote = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        alignment="left",  # [R]
        line_spacing=1.0,  # [R] block quotes single-spaced
        space_before_pt=12.0,  # [R]
        space_after_pt=12.0,  # [R]
        left_indent_in=0.5,  # [R]
        first_line_indent_in=0.0,
    )

    footnote = typography(
        family="Times New Roman",
        size_pt=10.0,  # [R]
        alignment="left",  # [R]
        line_spacing=1.0,  # [R] footnotes single-spaced
        first_line_indent_in=0.5,  # [R]
    )

    table_caption = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R] above table
        alignment="left",  # [R]
        line_spacing=1.0,  # [R]
        space_before_pt=0.0,
        space_after_pt=6.0,  # [R] 0/6
    )

    figure_caption = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R] below figure
        alignment="left",  # [R]
        line_spacing=1.0,  # [R]
        space_before_pt=6.0,  # [R] 6/0
        space_after_pt=0.0,
    )

    refs_heading = typography(
        family="Times New Roman",
        size_pt=12.0,  # [C]
        bold=True,  # [C]
        alignment="center",  # [C]
        line_spacing=2.0,  # [C]
        page_break_before=True,  # [C] new page
        keep_with_next=True,
    )

    refs_entry = typography(
        family="Times New Roman",
        size_pt=12.0,  # [R]
        alignment="left",  # [R]
        line_spacing=1.0,  # [R] bibliography single-spaced — not double
        space_after_pt=12.0,  # [R] blank line between entries (0/12)
        hanging_indent_in=0.5,  # [R]
    )

    core = {
        ParagraphRole.DOC_TITLE: doc_title,
        ParagraphRole.HEADING_1: heading_1,
        ParagraphRole.HEADING_2: heading_2,
        ParagraphRole.HEADING_3: heading_3,
        ParagraphRole.BODY: body,
        ParagraphRole.BLOCK_QUOTE: block_quote,
        ParagraphRole.FOOTNOTE: footnote,
        ParagraphRole.TABLE_CAPTION: table_caption,
        ParagraphRole.FIGURE_CAPTION: figure_caption,
        ParagraphRole.REFERENCES_HEADING: refs_heading,
        ParagraphRole.REFERENCES_ENTRY: refs_entry,
        ParagraphRole.COVER_TITLE: clone(doc_title),  # [R] title page exists
        ParagraphRole.LIST_BULLET: clone(body, left_indent_in=0.5, first_line_indent_in=0.0),  # inherited
        ParagraphRole.LIST_NUMBER: clone(body, left_indent_in=0.5, first_line_indent_in=0.0),  # inherited
    }

    return StyleProfile(
        name=StyleName.CHICAGO17,
        display_name="Chicago 17",
        source_manual="Chicago Manual of Style, 17th ed.; Turabian 9th ed. (notes-bibliography)",
        date_format="day_month_year",
        page=PageSetup(
            size=PageSize.A4,  # [H]
            margins=Margins(top_in=1.0, bottom_in=1.0, left_in=1.0, right_in=1.0),  # [R] 1.0 minimum
        ),
        page_numbering=PageNumbering(
            position=PageNumberPosition.TOP_RIGHT,  # [R] top_right or bottom_center — chose top_right
            skip_first_page=True,  # [R] title page not numbered but counted
        ),
        roles=apply_inheritance(core),
        citations=CitationConfig(
            default_in_text_mode=InTextMode.FOOTNOTE,  # [R] notes-bibliography
            et_al_threshold=4,  # [R] et al. at 4+
        ),
        references=ReferencesConfig(
            heading_text="Bibliography",  # [R] notes-bibliography (not author-date «References»)
            on_new_page=True,  # [C]
            sort=ReferenceSort.ALPHABETICAL,  # [R]
            numbered=False,  # [R]
        ),
        captions=CaptionConfig(
            table_position="above",  # [R]
            figure_position="below",  # [R]
        ),
        cover_page=CoverPage(
            enabled=True,  # [R] title page present
            title="Assignment",  # placeholder until user/form fills real title
            top_spacer_lines=8,  # [H] ~1/3 down — approximate via spacers
        ),
    )
