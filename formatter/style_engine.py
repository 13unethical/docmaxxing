"""
Formatting Style Engine — applies FormattingProfile to documents.

Independent from structure reconstruction. No style-specific conditionals;
all rules come from the active profile.
"""

from __future__ import annotations

from dataclasses import replace

from styles.profile import FormattingProfile
from typing import Literal

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.shared import Inches, Pt, RGBColor

from styles import load_profile, normalize_style_id
from styles.profile import (
    BodyStyleSpec,
    ContextualSpacingRules,
    FormattingProfile,
    PageSpec,
    ParagraphFormatSpec,
    ReferencesStyleSpec,
)

ParagraphRole = Literal[
    "title",
    "heading1",
    "heading2",
    "heading3",
    "body",
    "references_heading",
    "references_entry",
]


def _alignment_map(alignment: str) -> WD_ALIGN_PARAGRAPH:
    return {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }.get(alignment, WD_ALIGN_PARAGRAPH.LEFT)


def _set_line_spacing(paragraph_format, spec: ParagraphFormatSpec) -> None:
    rule = spec.line_spacing_rule
    multiple = spec.line_spacing
    if rule == "single" or (rule == "auto" and abs(multiple - 1.0) < 0.001):
        paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        paragraph_format.line_spacing = None
    elif rule == "double" or (rule == "auto" and abs(multiple - 2.0) < 0.001):
        paragraph_format.line_spacing_rule = WD_LINE_SPACING.DOUBLE
        paragraph_format.line_spacing = None
    else:
        paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        paragraph_format.line_spacing = multiple


def body_line_height_pt(font_size_pt: int, line_spacing: float) -> int:
    return max(6, int(round(font_size_pt * line_spacing)))


def _heading_space_before_pt(rules: ContextualSpacingRules, body: BodyStyleSpec) -> int:
    mode = rules.heading_space_before_mode
    if mode == "zero":
        return 0
    if mode == "fixed":
        return rules.heading_space_before_fixed_pt
    body_ls = body.paragraph.line_spacing
    body_fs = body.paragraph.font.size_pt
    if body_ls >= 1.99:
        return 0
    return body_line_height_pt(body_fs, body_ls)


_HEADING_ROLES = frozenset({"title", "heading1", "heading2", "heading3", "references_heading"})


def resolve_contextual_spacing(
    profile: FormattingProfile,
    *,
    role: ParagraphRole,
    prev_level: int,
    next_level: int,
    prev_has_text: bool,
) -> tuple[int, int]:
    """Resolve space before/after from profile paragraph specs and body rules."""
    if role in _HEADING_ROLES:
        spec = profile.paragraph_spec_for_role(role)
        return spec.space_before_pt, spec.space_after_pt

    if role == "references_entry":
        rules = profile.references.contextual
        return rules.body_space_before_pt, rules.body_space_after_pt

    rules = profile.body.contextual
    space_before = rules.body_space_before_pt
    if next_level > 0:
        space_after = rules.body_space_after_when_next_is_heading_pt
    else:
        space_after = rules.body_space_after_pt
    return space_before, space_after


def role_for_paragraph(
    *,
    level: int,
    in_refs_section: bool,
    is_refs_title: bool,
) -> ParagraphRole:
    if is_refs_title:
        return "references_heading"
    if in_refs_section and level == 0:
        return "references_entry"
    if level == 1:
        return "title"
    if level == 2:
        return "heading2"
    if level == 3:
        return "heading3"
    if level > 0:
        return "heading2"
    return "body"


def build_custom_profile(job) -> FormattingProfile:
    """Build a profile from explicit FormatJob overrides (manual form settings)."""
    base = load_profile("harvard")
    align = job.alignment if job.alignment in {"left", "justify"} else "left"
    indent = 0.5 if job.first_line_indent else None

    body_para = replace(
        base.body.paragraph,
        font=replace(base.body.paragraph.font, family=job.font_family, size_pt=job.font_size_pt),
        alignment=align,
        line_spacing=job.line_spacing,
        line_spacing_rule="double" if job.line_spacing >= 1.99 else "multiple",
        first_line_indent_inches=indent,
    )
    body_ctx = replace(
        base.body.contextual,
        body_space_before_pt=job.space_before_pt,
        body_space_after_pt=job.space_after_pt,
    )
    heading_font = replace(base.heading2.font, family=job.font_family, size_pt=job.heading_size_pt)

    def _heading(spec: ParagraphFormatSpec) -> ParagraphFormatSpec:
        return replace(
            spec,
            font=heading_font,
            line_spacing=1.0,
            line_spacing_rule="single",
            keep_with_next=True,
        )

    ref_entry = replace(
        base.references.entry,
        font=replace(base.references.entry.font, family=job.font_family, size_pt=job.font_size_pt),
        alignment="justify" if job.auto_justify_refs else align,
        line_spacing=job.line_spacing,
        hanging_indent_inches=(
            job.references_hanging_indent_inches
            if getattr(job, "references_hanging_indent_inches", None) is not None
            else base.references.entry.hanging_indent_inches
        ),
    )
    ref_heading = _heading(base.references.heading)
    if getattr(job, "references_on_new_page", True):
        ref_heading = replace(ref_heading, page_break_before=True)

    return replace(
        base,
        id="custom",
        name="Custom",
        title=_heading(replace(base.title, alignment="center")),
        heading1=_heading(base.heading1),
        heading2=_heading(base.heading2),
        heading3=_heading(base.heading3),
        body=replace(base.body, paragraph=body_para, contextual=body_ctx),
        references=replace(
            base.references,
            heading=ref_heading,
            entry=ref_entry,
            contextual=replace(base.references.contextual, body_space_after_pt=job.space_after_pt),
        ),
        page=replace(base.page, page_number_position=job.page_number_position),
    )


MARGIN_PRESET_INCHES = {"normal": 1.0, "narrow": 0.5, "wide": 1.5}


def _apply_margin_preset(profile: FormattingProfile, preset: str) -> FormattingProfile:
    inches = MARGIN_PRESET_INCHES.get(preset)
    if inches is None:
        return profile
    page = replace(
        profile.page,
        margin_top_inches=inches,
        margin_bottom_inches=inches,
        margin_left_inches=inches,
        margin_right_inches=inches,
    )
    return replace(profile, page=page)


def resolve_active_profile(job) -> FormattingProfile:
    """Resolve style profile, then overlay explicit FormatJob / AssignmentSpec rules.

    Citation style (harvard/apa/mla) selects the base profile, but brief formatting
    (font, size, spacing, alignment) must always win — otherwise Learning Journal
    left-align + double-space requirements are silently replaced by style defaults.
    """
    style = normalize_style_id(job.format_style)
    if style == "custom" or job.format_style == "custom":
        profile = build_custom_profile(job)
    else:
        profile = load_profile(style)
        profile = _overlay_job_formatting(profile, job)
    profile = _apply_margin_preset(profile, job.margin_preset)
    if job.page_number_position != profile.page.page_number_position:
        profile = replace(profile, page=replace(profile.page, page_number_position=job.page_number_position))
    return profile


def _overlay_job_formatting(profile: FormattingProfile, job) -> FormattingProfile:
    align = job.alignment if job.alignment in {"left", "justify"} else profile.body.paragraph.alignment
    indent = 0.5 if job.first_line_indent else None
    body_para = replace(
        profile.body.paragraph,
        font=replace(
            profile.body.paragraph.font,
            family=job.font_family or profile.body.paragraph.font.family,
            size_pt=job.font_size_pt or profile.body.paragraph.font.size_pt,
            bold=False,
        ),
        alignment=align,
        line_spacing=job.line_spacing,
        line_spacing_rule="double" if job.line_spacing >= 1.99 else "multiple",
        first_line_indent_inches=indent,
    )
    body_ctx = replace(
        profile.body.contextual,
        body_space_before_pt=job.space_before_pt,
        body_space_after_pt=job.space_after_pt,
    )
    heading_font = replace(
        profile.heading2.font,
        family=job.font_family or profile.heading2.font.family,
        size_pt=job.heading_size_pt or profile.heading2.font.size_pt,
        bold=True,
    )

    def _heading(spec: ParagraphFormatSpec) -> ParagraphFormatSpec:
        return replace(
            spec,
            font=heading_font,
            line_spacing=1.0,
            line_spacing_rule="single",
            keep_with_next=True,
        )

    ref_entry = replace(
        profile.references.entry,
        font=replace(
            profile.references.entry.font,
            family=job.font_family or profile.references.entry.font.family,
            size_pt=job.font_size_pt or profile.references.entry.font.size_pt,
            bold=False,
        ),
        alignment="justify" if job.auto_justify_refs else align,
        line_spacing=job.line_spacing,
        hanging_indent_inches=(
            job.references_hanging_indent_inches
            if getattr(job, "references_hanging_indent_inches", None) is not None
            else profile.references.entry.hanging_indent_inches
        ),
    )
    ref_heading = _heading(profile.references.heading)
    if getattr(job, "references_on_new_page", True):
        ref_heading = replace(ref_heading, page_break_before=True)
    return replace(
        profile,
        title=_heading(replace(profile.title, alignment="center")),
        heading1=_heading(profile.heading1),
        heading2=_heading(profile.heading2),
        heading3=_heading(profile.heading3),
        body=replace(profile.body, paragraph=body_para, contextual=body_ctx),
        references=replace(
            profile.references,
            heading=ref_heading,
            entry=ref_entry,
            contextual=replace(profile.references.contextual, body_space_after_pt=job.space_after_pt),
        ),
    )


def apply_page_style(document: Document, page: PageSpec) -> None:
    for section in document.sections:
        section.top_margin = Inches(page.margin_top_inches)
        section.bottom_margin = Inches(page.margin_bottom_inches)
        section.left_margin = Inches(page.margin_left_inches)
        section.right_margin = Inches(page.margin_right_inches)


def _apply_capitalization(text: str, capitalization: str) -> str:
    if capitalization == "all_caps":
        return text.upper()
    if capitalization == "title_case":
        return " ".join(w.capitalize() if w else w for w in text.split())
    return text


def apply_paragraph_spec(
    paragraph,
    document: Document,
    spec: ParagraphFormatSpec,
    *,
    space_before_pt: int,
    space_after_pt: int,
    heading_level: int = 0,
) -> None:
    """Apply a profile paragraph spec to one Word paragraph."""
    style_name = None
    if heading_level == 1:
        style_name = "Heading 1"
    elif heading_level == 2:
        style_name = "Heading 2"
    elif heading_level == 3:
        style_name = "Heading 3"
    if style_name:
        try:
            paragraph.style = document.styles[style_name]
        except KeyError:
            pass

    pf = paragraph.paragraph_format
    _set_line_spacing(pf, spec)
    pf.alignment = _alignment_map(spec.alignment)
    pf.space_before = Pt(space_before_pt)
    pf.space_after = Pt(space_after_pt)
    pf.keep_with_next = spec.keep_with_next
    pf.keep_lines_together = spec.keep_lines_together
    pf.widow_control = spec.widow_control
    pf.page_break_before = spec.page_break_before

    if spec.first_line_indent_inches is not None:
        pf.first_line_indent = Inches(spec.first_line_indent_inches)
    else:
        pf.first_line_indent = None

    if spec.hanging_indent_inches is not None:
        pf.left_indent = Inches(spec.hanging_indent_inches)
        pf.first_line_indent = Inches(-spec.hanging_indent_inches)
    elif heading_level > 0:
        pf.first_line_indent = None

    plain = paragraph.text.strip()
    if spec.capitalization != "none" and plain:
        new_text = _apply_capitalization(plain, spec.capitalization)
        if new_text != plain:
            paragraph.text = new_text

    if not paragraph.runs and paragraph.text:
        paragraph.add_run(paragraph.text)

    for run in paragraph.runs:
        run.font.name = spec.font.family
        run.font.size = Pt(spec.font.size_pt)
        run.font.bold = spec.font.bold
        run.font.italic = spec.font.italic
        run.font.color.rgb = RGBColor(0, 0, 0)
        run.font.underline = False


def _pt(value) -> float | None:
    if value is None:
        return None
    return round(value.pt, 1)


def _paragraph_matches_spec(
    paragraph,
    spec: ParagraphFormatSpec,
    *,
    space_before_pt: int,
    space_after_pt: int,
) -> bool:
    pf = paragraph.paragraph_format
    if _pt(pf.space_before) != float(space_before_pt):
        return False
    if _pt(pf.space_after) != float(space_after_pt):
        return False
    if pf.alignment != _alignment_map(spec.alignment):
        return False
    if paragraph.runs:
        run = paragraph.runs[0]
        if run.font.name and run.font.name != spec.font.family:
            return False
        if run.font.size and _pt(run.font.size) != float(spec.font.size_pt):
            return False
        if bool(run.font.bold) != spec.font.bold:
            return False
    return True


def validate_and_correct_document(
    document: Document,
    profile: FormattingProfile,
    plans: list,
) -> int:
    """
    Verify every paragraph against the active profile; re-apply when violated.
    Returns the number of corrected paragraphs.
    """
    corrections = 0
    in_refs = False
    for idx, plan in enumerate(plans):
        paragraph = plan.paragraph
        text = paragraph.text or ""
        if not text.strip():
            continue

        from formatter.headings import is_references_heading

        refs_title = is_references_heading(text)
        if refs_title:
            in_refs = True

        prev_level = plans[idx - 1].level if idx > 0 else 0
        next_level = plans[idx + 1].level if idx + 1 < len(plans) else 0
        prev_has_text = bool((plans[idx - 1].stripped if idx > 0 else ""))

        role = role_for_paragraph(
            level=plan.level,
            in_refs_section=in_refs,
            is_refs_title=refs_title,
        )
        spec = profile.paragraph_spec_for_role(role)
        space_before, space_after = resolve_contextual_spacing(
            profile,
            role=role,
            prev_level=prev_level,
            next_level=next_level,
            prev_has_text=prev_has_text,
        )

        if not _paragraph_matches_spec(
            paragraph, spec, space_before_pt=space_before, space_after_pt=space_after
        ):
            apply_paragraph_spec(
                paragraph,
                document,
                spec,
                space_before_pt=space_before,
                space_after_pt=space_after,
                heading_level=plan.level,
            )
            corrections += 1
    return corrections
