"""Tests for Formatter V2 schema and style profiles (reference-driven)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from formatter_v2.profiles import all_profiles, load_profile
from formatter_v2.spec import (
    ExtractedRequirements,
    FontFamily,
    FormatSpec,
    ParagraphRole,
    ReferenceSort,
    StyleName,
    StyleProfile,
    TypographySpec,
)


@pytest.fixture(scope="module")
def profiles() -> dict[StyleName, StyleProfile]:
    return all_profiles()


@pytest.mark.parametrize(
    "style",
    [
        StyleName.HARVARD,
        StyleName.APA7,
        StyleName.MLA9,
        StyleName.CHICAGO17,
        StyleName.IEEE,
    ],
)
def test_each_profile_validates_as_style_profile(style: StyleName, profiles) -> None:
    profile = profiles[style]
    assert isinstance(profile, StyleProfile)
    assert profile.name == style
    StyleProfile.model_validate(profile.model_dump())


@pytest.mark.parametrize(
    "style",
    [
        StyleName.HARVARD,
        StyleName.APA7,
        StyleName.MLA9,
        StyleName.CHICAGO17,
        StyleName.IEEE,
    ],
)
def test_each_profile_covers_all_paragraph_roles(style: StyleName, profiles) -> None:
    profile = profiles[style]
    missing = [r for r in ParagraphRole if r not in profile.roles]
    assert missing == [], f"{style}: missing roles {[m.value for m in missing]}"
    assert set(profile.roles.keys()) == set(ParagraphRole)


def test_format_spec_rejects_missing_roles() -> None:
    incomplete = {
        ParagraphRole.BODY: TypographySpec(),
        ParagraphRole.HEADING_1: TypographySpec(),
    }
    with pytest.raises(ValidationError) as exc_info:
        FormatSpec(roles=incomplete)
    message = str(exc_info.value)
    assert "FormatSpec must cover every paragraph role" in message or "Missing:" in message
    assert ParagraphRole.DOC_TITLE.value in message


def test_typography_forbids_first_line_and_hanging_together() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TypographySpec(first_line_indent_in=0.5, hanging_indent_in=0.5)
    assert "mutually exclusive" in str(exc_info.value)


def test_extracted_requirements_partial_json() -> None:
    req = ExtractedRequirements.model_validate(
        {
            "style": "apa7",
            "font_family": "Times New Roman",
            "font_size_pt": 12,
            "evidence": {"style": "Use APA 7th edition"},
        }
    )
    assert req.style == StyleName.APA7
    assert req.font_family == FontFamily.TIMES_NEW_ROMAN
    assert req.font_size_pt == 12.0
    assert req.line_spacing is None
    assert req.alignment is None


def test_extracted_requirements_forbid_unknown_key() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ExtractedRequirements.model_validate({"style": "harvard", "made_up_field": 1})
    assert "made_up_field" in str(exc_info.value)


def test_extracted_requirements_is_empty_on_blank_brief() -> None:
    assert ExtractedRequirements().is_empty() is True
    assert ExtractedRequirements(warnings=["note"]).is_empty() is True
    assert ExtractedRequirements(style=StyleName.HARVARD).is_empty() is False


def test_load_profile_helper() -> None:
    assert load_profile("harvard").name == StyleName.HARVARD
    assert load_profile(StyleName.IEEE).page.margins.left_in == 0.625


# ---------------------------------------------------------------------------
# Regression: сводная матрица FORMATTER_V2_STYLE_REFERENCE.md
# ---------------------------------------------------------------------------


def test_apa_headings_are_double_spaced(profiles) -> None:
    """Catches V1 bug: style_engine forced heading line_spacing=1.0."""
    apa = profiles[StyleName.APA7]
    assert apa.roles[ParagraphRole.BODY].line_spacing == 2.0
    assert apa.roles[ParagraphRole.HEADING_1].line_spacing == 2.0
    assert apa.roles[ParagraphRole.HEADING_2].line_spacing == 2.0
    assert apa.roles[ParagraphRole.HEADING_3].line_spacing == 2.0


def test_apa_headings_are_12pt_not_16pt(profiles) -> None:
    """Catches V1 bug: APA headings inflated to 16pt."""
    apa = profiles[StyleName.APA7]
    assert apa.roles[ParagraphRole.DOC_TITLE].font_size_pt == 12.0
    assert apa.roles[ParagraphRole.HEADING_1].font_size_pt == 12.0
    assert apa.roles[ParagraphRole.HEADING_2].font_size_pt == 12.0
    assert apa.roles[ParagraphRole.HEADING_3].font_size_pt == 12.0


def test_apa_body_is_left_aligned_not_justified(profiles) -> None:
    """Catches V1 default justify applied to APA body."""
    apa = profiles[StyleName.APA7]
    assert apa.roles[ParagraphRole.BODY].alignment.value == "left"


def test_apa_title_page_is_numbered(profiles) -> None:
    """Catches common APA error: skipping page number on title page."""
    apa = profiles[StyleName.APA7]
    assert apa.page_numbering.skip_first_page is False
    assert apa.page_numbering.position.value == "top_right"
    assert apa.cover_page.enabled is True


def test_mla_works_cited_heading_is_not_bold(profiles) -> None:
    """Catches V1 bug: Works Cited was bold flush-left."""
    mla = profiles[StyleName.MLA9]
    heading = mla.roles[ParagraphRole.REFERENCES_HEADING]
    assert heading.bold is False
    assert heading.alignment.value == "center"
    assert mla.references.heading_text == "Works Cited"


def test_mla_has_no_cover_page_by_default(profiles) -> None:
    """Catches inventing an MLA title page — MLA has none."""
    mla = profiles[StyleName.MLA9]
    assert mla.cover_page.enabled is False


def test_chicago_bibliography_is_single_spaced(profiles) -> None:
    """Catches V1 treating Chicago bibliography as double-spaced like APA."""
    chi = profiles[StyleName.CHICAGO17]
    entry = chi.roles[ParagraphRole.REFERENCES_ENTRY]
    assert entry.line_spacing == 1.0
    assert entry.space_after_pt == 12.0  # blank line between entries
    assert chi.references.heading_text == "Bibliography"


def test_ieee_margins_are_not_overwritten_by_preset(profiles) -> None:
    """Catches V1 bug: margin_preset overwrote IEEE 0.625\" sides."""
    ieee = profiles[StyleName.IEEE]
    assert ieee.page.margins.top_in == 0.75
    assert ieee.page.margins.bottom_in == 1.0
    assert ieee.page.margins.left_in == 0.625
    assert ieee.page.margins.right_in == 0.625


def test_ieee_references_sorted_by_appearance(profiles) -> None:
    """Catches alphabetical sort applied to IEEE numbered refs."""
    ieee = profiles[StyleName.IEEE]
    assert ieee.references.sort == ReferenceSort.ORDER_OF_APPEARANCE
    assert ieee.references.numbered is True


def test_ieee_body_is_10pt(profiles) -> None:
    """Catches body font inflated to 12pt for IEEE."""
    ieee = profiles[StyleName.IEEE]
    assert ieee.roles[ParagraphRole.BODY].font_size_pt == 10.0


def test_apa_figure_caption_is_above(profiles) -> None:
    """Catches defaulting figure captions below for APA (APA puts both above)."""
    apa = profiles[StyleName.APA7]
    assert apa.captions.table_position == "above"
    assert apa.captions.figure_position == "above"


def test_mla_figure_caption_is_below(profiles) -> None:
    """Catches APA-style figure-above applied to MLA."""
    mla = profiles[StyleName.MLA9]
    assert mla.captions.table_position == "above"
    assert mla.captions.figure_position == "below"


def test_hanging_indent_comes_from_profile_not_hardcoded(profiles) -> None:
    """Catches FormatJob unconditional hanging 0.5\" applied to every style."""
    assert profiles[StyleName.APA7].roles[ParagraphRole.REFERENCES_ENTRY].hanging_indent_in == 0.5
    assert profiles[StyleName.MLA9].roles[ParagraphRole.REFERENCES_ENTRY].hanging_indent_in == 0.5
    assert profiles[StyleName.CHICAGO17].roles[ParagraphRole.REFERENCES_ENTRY].hanging_indent_in == 0.5
    assert profiles[StyleName.HARVARD].roles[ParagraphRole.REFERENCES_ENTRY].hanging_indent_in == 0.5
    assert profiles[StyleName.IEEE].roles[ParagraphRole.REFERENCES_ENTRY].hanging_indent_in == 0.25


def test_harvard_body_is_justify_without_first_line_indent(profiles) -> None:
    """Matrix: Harvard body justify + no first-line indent (UK house style)."""
    har = profiles[StyleName.HARVARD]
    body = har.roles[ParagraphRole.BODY]
    assert body.alignment.value == "justify"
    assert body.first_line_indent_in == 0.0
    assert body.line_spacing == 1.5


def test_ieee_in_text_mode_is_numeric_not_literal_one(profiles) -> None:
    """Catches V1 hard-coded in-text '[1]' for every IEEE citation."""
    ieee = profiles[StyleName.IEEE]
    assert ieee.citations.default_in_text_mode.value == "numeric"


def test_et_al_thresholds_match_matrix(profiles) -> None:
    """Matrix: APA/MLA 3+, Chicago/Harvard 4+."""
    assert profiles[StyleName.APA7].citations.et_al_threshold == 3
    assert profiles[StyleName.MLA9].citations.et_al_threshold == 3
    assert profiles[StyleName.CHICAGO17].citations.et_al_threshold == 4
    assert profiles[StyleName.HARVARD].citations.et_al_threshold == 4
