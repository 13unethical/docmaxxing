"""User-selected formatting options from the HTTP form."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FormatJob:
    """Formatting and structure-recovery toggles (structure flags are not style rules)."""

    font_family: str
    font_size_pt: int
    line_spacing: float
    alignment: str  # "left" | "justify"
    first_line_indent: bool
    space_before_pt: int
    space_after_pt: int
    margin_preset: str
    page_number_position: str
    auto_headings: bool
    heading_all_caps: bool
    auto_justify_refs: bool
    format_style: str = "harvard"
    requirement_headings: bool = False
    heading_size_pt: int = 16
    references_hanging_indent_inches: float | None = 0.5
    references_on_new_page: bool = True
