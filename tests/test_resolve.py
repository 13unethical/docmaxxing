"""Tests for Formatter V2 resolve_format_spec."""

from __future__ import annotations

import pytest

from formatter_v2.profiles import load_profile
from formatter_v2.resolve import resolve_format_spec
from formatter_v2.spec import (
    Alignment,
    CoverPage,
    FontFamily,
    Margins,
    ParagraphRole,
    StyleName,
    StyleProfile,
    UserOverrides,
)


def _profile(name: StyleName) -> StyleProfile:
    return load_profile(name)


# ---------------------------------------------------------------------------
# Пропорциональное масштабирование
# ---------------------------------------------------------------------------


def test_harvard_body_12_to_11_scales_h1_from_14_to_13() -> None:
    profile = _profile(StyleName.HARVARD)
    assert profile.roles[ParagraphRole.BODY].font_size_pt == 12.0
    assert profile.roles[ParagraphRole.HEADING_1].font_size_pt == 14.0

    result = resolve_format_spec(profile, UserOverrides(font_size_pt=11.0))
    assert result.spec.roles[ParagraphRole.BODY].font_size_pt == 11.0
    # 14 * (11/12) = 12.833… → half-point round → 13.0
    assert result.spec.roles[ParagraphRole.HEADING_1].font_size_pt == 13.0


def test_apa_uniform_sizes_stay_uniform_after_scaling() -> None:
    profile = _profile(StyleName.APA7)
    result = resolve_format_spec(profile, UserOverrides(font_size_pt=11.0))
    body = result.spec.roles[ParagraphRole.BODY].font_size_pt
    assert body == 11.0
    assert result.spec.roles[ParagraphRole.HEADING_1].font_size_pt == body
    assert result.spec.roles[ParagraphRole.HEADING_2].font_size_pt == body
    assert result.spec.roles[ParagraphRole.DOC_TITLE].font_size_pt == body


def test_ieee_body_10_to_12_scales_title_proportionally() -> None:
    profile = _profile(StyleName.IEEE)
    assert profile.roles[ParagraphRole.BODY].font_size_pt == 10.0
    assert profile.roles[ParagraphRole.DOC_TITLE].font_size_pt == 24.0

    result = resolve_format_spec(profile, UserOverrides(font_size_pt=12.0))
    assert result.spec.roles[ParagraphRole.BODY].font_size_pt == 12.0
    # 24 * (12/10) = 28.8 → 29.0
    assert result.spec.roles[ParagraphRole.DOC_TITLE].font_size_pt == 29.0


def test_font_size_clamped_to_valid_range() -> None:
    profile = _profile(StyleName.HARVARD)
    result = resolve_format_spec(profile, UserOverrides(font_size_pt=48.0))
    for role, spec in result.spec.roles.items():
        assert 6.0 <= spec.font_size_pt <= 48.0, role
    # Extreme upscale still clamps (title would otherwise exceed 48)
    huge = resolve_format_spec(profile, UserOverrides(font_size_pt=48.0))
    assert huge.spec.roles[ParagraphRole.DOC_TITLE].font_size_pt <= 48.0


# ---------------------------------------------------------------------------
# Распространение по совпадению с телом
# ---------------------------------------------------------------------------


def test_chicago_bibliography_stays_single_spaced_when_body_changes() -> None:
    profile = _profile(StyleName.CHICAGO17)
    assert profile.roles[ParagraphRole.BODY].line_spacing == 2.0
    assert profile.roles[ParagraphRole.REFERENCES_ENTRY].line_spacing == 1.0

    result = resolve_format_spec(profile, UserOverrides(line_spacing=1.5))
    assert result.spec.roles[ParagraphRole.BODY].line_spacing == 1.5
    assert result.spec.roles[ParagraphRole.REFERENCES_ENTRY].line_spacing == 1.0


def test_chicago_block_quote_stays_single_spaced() -> None:
    profile = _profile(StyleName.CHICAGO17)
    assert profile.roles[ParagraphRole.BLOCK_QUOTE].line_spacing == 1.0

    result = resolve_format_spec(profile, UserOverrides(line_spacing=1.5))
    assert result.spec.roles[ParagraphRole.BLOCK_QUOTE].line_spacing == 1.0


def test_apa_headings_follow_body_spacing_because_they_match() -> None:
    profile = _profile(StyleName.APA7)
    assert profile.roles[ParagraphRole.BODY].line_spacing == 2.0
    assert profile.roles[ParagraphRole.HEADING_1].line_spacing == 2.0

    result = resolve_format_spec(profile, UserOverrides(line_spacing=1.5))
    assert result.spec.roles[ParagraphRole.BODY].line_spacing == 1.5
    assert result.spec.roles[ParagraphRole.HEADING_1].line_spacing == 1.5
    assert result.spec.roles[ParagraphRole.HEADING_2].line_spacing == 1.5


def test_ieee_body_alignment_override_does_not_touch_captions() -> None:
    profile = _profile(StyleName.IEEE)
    assert profile.roles[ParagraphRole.BODY].alignment == Alignment.JUSTIFY
    assert profile.roles[ParagraphRole.TABLE_CAPTION].alignment == Alignment.CENTER
    assert profile.roles[ParagraphRole.FIGURE_CAPTION].alignment == Alignment.LEFT

    result = resolve_format_spec(profile, UserOverrides(alignment=Alignment.LEFT))
    assert result.spec.roles[ParagraphRole.BODY].alignment == Alignment.LEFT
    assert result.spec.roles[ParagraphRole.TABLE_CAPTION].alignment == Alignment.CENTER
    assert result.spec.roles[ParagraphRole.FIGURE_CAPTION].alignment == Alignment.LEFT


# ---------------------------------------------------------------------------
# Предупреждения
# ---------------------------------------------------------------------------


def test_justify_on_apa_produces_deviation_notice() -> None:
    profile = _profile(StyleName.APA7)
    result = resolve_format_spec(profile, UserOverrides(alignment=Alignment.JUSTIFY))
    assert result.has_deviations
    assert any(n.field == "alignment" and n.severity == "deviation" for n in result.notices)


def test_cover_page_on_mla_produces_deviation_notice() -> None:
    profile = _profile(StyleName.MLA9)
    assert profile.cover_page.enabled is False
    result = resolve_format_spec(
        profile,
        UserOverrides(cover_page=CoverPage(enabled=True, title="My Essay")),
    )
    assert result.has_deviations
    assert any(n.field == "cover_page" for n in result.notices)


def test_margin_change_on_ieee_produces_deviation_notice() -> None:
    profile = _profile(StyleName.IEEE)
    result = resolve_format_spec(
        profile,
        UserOverrides(margins=Margins(top_in=1.0, bottom_in=1.0, left_in=1.0, right_in=1.0)),
    )
    assert result.has_deviations
    assert any(n.field == "margins" for n in result.notices)


def test_heading_size_override_on_apa_produces_deviation_notice() -> None:
    profile = _profile(StyleName.APA7)
    result = resolve_format_spec(profile, UserOverrides(heading_size_pt=16.0))
    assert result.has_deviations
    assert any(n.field == "heading_size_pt" for n in result.notices)
    assert result.spec.roles[ParagraphRole.HEADING_1].font_size_pt == 16.0


def test_no_overrides_produces_no_deviations() -> None:
    for style in StyleName:
        if style == StyleName.CUSTOM:
            continue
        result = resolve_format_spec(_profile(style), UserOverrides())
        assert result.notices == []
        assert result.has_deviations is False


# ---------------------------------------------------------------------------
# Общее
# ---------------------------------------------------------------------------


def test_empty_overrides_returns_profile_values_unchanged() -> None:
    profile = _profile(StyleName.HARVARD)
    result = resolve_format_spec(profile, UserOverrides())
    body = result.spec.roles[ParagraphRole.BODY]
    assert body.font_size_pt == profile.roles[ParagraphRole.BODY].font_size_pt
    assert body.line_spacing == profile.roles[ParagraphRole.BODY].line_spacing
    assert body.alignment == profile.roles[ParagraphRole.BODY].alignment
    assert result.spec.style == StyleName.HARVARD
    assert result.spec.page.margins == profile.page.margins
    assert result.spec.references.heading_text == profile.references.heading_text


def test_resolver_does_not_mutate_the_profile() -> None:
    """Same profile object, two override sets — second must not inherit the first."""
    profile = _profile(StyleName.APA7)
    original_body_size = profile.roles[ParagraphRole.BODY].font_size_pt
    original_align = profile.roles[ParagraphRole.BODY].alignment
    original_h1 = profile.roles[ParagraphRole.HEADING_1].font_size_pt

    first = resolve_format_spec(
        profile,
        UserOverrides(font_size_pt=11.0, alignment=Alignment.JUSTIFY),
    )
    assert first.spec.roles[ParagraphRole.BODY].font_size_pt == 11.0

    # Profile must still hold original values
    assert profile.roles[ParagraphRole.BODY].font_size_pt == original_body_size
    assert profile.roles[ParagraphRole.BODY].alignment == original_align
    assert profile.roles[ParagraphRole.HEADING_1].font_size_pt == original_h1

    second = resolve_format_spec(profile, UserOverrides())
    assert second.spec.roles[ParagraphRole.BODY].font_size_pt == original_body_size
    assert second.spec.roles[ParagraphRole.BODY].alignment == original_align
    assert second.spec.roles[ParagraphRole.HEADING_1].font_size_pt == original_h1
    assert second.spec.roles[ParagraphRole.BODY].font_size_pt != 11.0


def test_style_mismatch_raises() -> None:
    profile = _profile(StyleName.APA7)
    with pytest.raises(ValueError, match="does not match"):
        resolve_format_spec(profile, UserOverrides(style=StyleName.MLA9))


def test_first_line_indent_clears_conflicting_hanging_indent() -> None:
    profile = _profile(StyleName.HARVARD)
    # Put a hanging indent on BODY (valid alone) so enable-indent must clear it.
    body = profile.roles[ParagraphRole.BODY].model_copy(
        update={"hanging_indent_in": 0.5, "first_line_indent_in": 0.0}
    )
    roles = {**profile.roles, ParagraphRole.BODY: body, ParagraphRole.BODY_FIRST: body.model_copy(deep=True)}
    mutated = profile.model_copy(update={"roles": roles})

    result = resolve_format_spec(mutated, UserOverrides(first_line_indent=True))
    resolved_body = result.spec.roles[ParagraphRole.BODY]
    assert resolved_body.hanging_indent_in == 0.0
    assert resolved_body.first_line_indent_in == 0.5


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
def test_resolved_spec_passes_full_role_validation(style: StyleName) -> None:
    profile = _profile(style)
    result = resolve_format_spec(
        profile,
        UserOverrides(font_family=FontFamily.GEORGIA, font_size_pt=11.0),
    )
    assert set(result.spec.roles.keys()) == set(ParagraphRole)
    # Round-trip validates FormatSpec (including all-roles rule)
    assert result.spec.style == style
