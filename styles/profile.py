"""
Formatting profile data model — every visual rule for an academic style.

Structure recovery never imports this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Alignment = Literal["left", "center", "right", "justify"]
LineSpacingRule = Literal["single", "double", "multiple", "auto"]
Capitalization = Literal["none", "all_caps", "title_case", "sentence_case"]
HeadingSpaceBeforeMode = Literal["zero", "one_body_line", "fixed"]

# Fixed academic heading spacing (Word paragraph space_before / space_after in pt).
ACADEMIC_TITLE_SPACE_BEFORE_PT = 0
ACADEMIC_TITLE_SPACE_AFTER_PT = 24
ACADEMIC_HEADING2_SPACE_BEFORE_PT = 18
ACADEMIC_HEADING2_SPACE_AFTER_PT = 6
ACADEMIC_HEADING3_SPACE_BEFORE_PT = 12
ACADEMIC_HEADING3_SPACE_AFTER_PT = 4


@dataclass(frozen=True)
class FontSpec:
    family: str = "Times New Roman"
    size_pt: int = 12
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class ParagraphFormatSpec:
    """Complete paragraph-level formatting rules."""

    font: FontSpec = field(default_factory=FontSpec)
    alignment: Alignment = "left"
    line_spacing: float = 1.5
    line_spacing_rule: LineSpacingRule = "multiple"
    space_before_pt: int = 0
    space_after_pt: int = 0
    first_line_indent_inches: float | None = None
    hanging_indent_inches: float | None = None
    keep_with_next: bool = False
    keep_lines_together: bool = False
    widow_control: bool = True
    page_break_before: bool = False
    capitalization: Capitalization = "none"


@dataclass(frozen=True)
class ContextualSpacingRules:
    """Spacing resolved from paragraph context (neighbour levels)."""

    body_space_before_pt: int = 0
    body_space_after_pt: int = 0
    body_space_after_when_next_is_heading_pt: int = 0
    heading_space_after_pt: int = 0
    heading_space_before_mode: HeadingSpaceBeforeMode = "one_body_line"
    heading_space_before_fixed_pt: int = 0


@dataclass(frozen=True)
class BodyStyleSpec:
    paragraph: ParagraphFormatSpec = field(default_factory=ParagraphFormatSpec)
    contextual: ContextualSpacingRules = field(default_factory=ContextualSpacingRules)


@dataclass(frozen=True)
class ReferencesStyleSpec:
    heading: ParagraphFormatSpec = field(default_factory=ParagraphFormatSpec)
    entry: ParagraphFormatSpec = field(default_factory=ParagraphFormatSpec)
    contextual: ContextualSpacingRules = field(default_factory=ContextualSpacingRules)


@dataclass(frozen=True)
class PageSpec:
    margin_top_inches: float = 1.0
    margin_bottom_inches: float = 1.0
    margin_left_inches: float = 1.0
    margin_right_inches: float = 1.0
    page_number_position: str = "none"


@dataclass(frozen=True)
class CoverPageSpec:
    title_font: FontSpec = field(default_factory=lambda: FontSpec(size_pt=16, bold=True))
    body_font: FontSpec = field(default_factory=FontSpec)
    alignment: Alignment = "center"
    line_spacing: float = 1.0
    space_after_pt: int = 8
    top_spacer_lines: int = 5


@dataclass(frozen=True)
class FormattingProfile:
    """Complete academic formatting style."""

    id: str
    name: str
    title: ParagraphFormatSpec
    heading1: ParagraphFormatSpec
    heading2: ParagraphFormatSpec
    heading3: ParagraphFormatSpec
    body: BodyStyleSpec
    references: ReferencesStyleSpec
    lists: ParagraphFormatSpec = field(default_factory=ParagraphFormatSpec)
    quotes: ParagraphFormatSpec = field(default_factory=ParagraphFormatSpec)
    tables: ParagraphFormatSpec = field(default_factory=ParagraphFormatSpec)
    captions: ParagraphFormatSpec = field(default_factory=ParagraphFormatSpec)
    page: PageSpec = field(default_factory=PageSpec)
    cover_page: CoverPageSpec = field(default_factory=CoverPageSpec)

    def paragraph_spec_for_role(self, role: str) -> ParagraphFormatSpec:
        return {
            "title": self.title,
            "heading1": self.heading1,
            "heading2": self.heading2,
            "heading3": self.heading3,
            "body": self.body.paragraph,
            "references_heading": self.references.heading,
            "references_entry": self.references.entry,
            "list": self.lists,
            "quote": self.quotes,
            "table": self.tables,
            "caption": self.captions,
        }.get(role, self.body.paragraph)
