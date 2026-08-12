"""Shared builders for StyleProfile role maps (reference-driven)."""

from __future__ import annotations

from formatter_v2.spec import (
    Alignment,
    FontFamily,
    ParagraphRole,
    TextCase,
    TypographySpec,
)

_CAP_MAP = {
    "none": TextCase.PRESERVE,
    "preserve": TextCase.PRESERVE,
    "title_case": TextCase.TITLE_CASE,
    "sentence_case": TextCase.SENTENCE_CASE,
    "all_caps": TextCase.UPPER,
    "upper": TextCase.UPPER,
}


def typography(
    *,
    family: str = "Times New Roman",
    size_pt: float = 12.0,
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    text_case: str | TextCase = "preserve",
    small_caps: bool = False,
    alignment: str = "left",
    line_spacing: float = 1.5,
    space_before_pt: float = 0.0,
    space_after_pt: float = 0.0,
    first_line_indent_in: float = 0.0,
    left_indent_in: float = 0.0,
    right_indent_in: float = 0.0,
    hanging_indent_in: float = 0.0,
    keep_with_next: bool = False,
    page_break_before: bool = False,
    widow_control: bool = True,
) -> TypographySpec:
    case = text_case if isinstance(text_case, TextCase) else _CAP_MAP.get(text_case, TextCase.PRESERVE)
    return TypographySpec(
        font_family=FontFamily(family),
        font_size_pt=size_pt,
        bold=bold,
        italic=italic,
        underline=underline,
        text_case=case,
        small_caps=small_caps,
        alignment=Alignment(alignment),
        line_spacing=line_spacing,
        space_before_pt=space_before_pt,
        space_after_pt=space_after_pt,
        first_line_indent_in=first_line_indent_in,
        left_indent_in=left_indent_in,
        right_indent_in=right_indent_in,
        hanging_indent_in=hanging_indent_in,
        keep_with_next=keep_with_next,
        page_break_before=page_break_before,
        widow_control=widow_control,
    )


def clone(spec: TypographySpec, **overrides: object) -> TypographySpec:
    data = spec.model_dump()
    data.update(overrides)
    return TypographySpec.model_validate(data)


def apply_inheritance(core: dict[ParagraphRole, TypographySpec]) -> dict[ParagraphRole, TypographySpec]:
    """
    Fill roles missing from the style table using FORMATTER_V2_STYLE_REFERENCE.md rules:

    BODY_FIRST ← BODY
    TOC_ENTRY ← BODY
    ABBREVIATION_ENTRY ← BODY
    TOC_HEADING ← HEADING_1
    APPENDIX_HEADING ← HEADING_1
    TABLE_CELL ← BODY (line_spacing 1.0)
    TABLE_HEADER ← TABLE_CELL + bold
    SUBTITLE ← DOC_TITLE without bold
    COVER_FIELD ← BODY centered
    """
    if ParagraphRole.BODY not in core:
        raise ValueError("BODY is required")
    if ParagraphRole.DOC_TITLE not in core:
        raise ValueError("DOC_TITLE is required")
    if ParagraphRole.HEADING_1 not in core:
        raise ValueError("HEADING_1 is required")

    body = core[ParagraphRole.BODY]
    doc_title = core[ParagraphRole.DOC_TITLE]
    h1 = core[ParagraphRole.HEADING_1]
    out = dict(core)

    def put(role: ParagraphRole, spec: TypographySpec) -> None:
        if role not in out:
            out[role] = spec

    # inherited — see reference header
    put(ParagraphRole.BODY_FIRST, clone(body))
    put(ParagraphRole.TOC_ENTRY, clone(body))
    put(ParagraphRole.ABBREVIATION_ENTRY, clone(body))
    put(ParagraphRole.TOC_HEADING, clone(h1))
    put(ParagraphRole.APPENDIX_HEADING, clone(h1))

    table_cell = out.get(ParagraphRole.TABLE_CELL) or clone(body, line_spacing=1.0)
    put(ParagraphRole.TABLE_CELL, table_cell)
    put(ParagraphRole.TABLE_HEADER, clone(out[ParagraphRole.TABLE_CELL], bold=True))

    put(ParagraphRole.SUBTITLE, clone(doc_title, bold=False))
    put(
        ParagraphRole.COVER_FIELD,
        clone(body, alignment=Alignment.CENTER, first_line_indent_in=0.0),
    )

    # Remaining roles without a table row: inherit BODY
    for role in ParagraphRole:
        if role not in out:
            out[role] = clone(body)

    return out
