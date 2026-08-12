"""Map ExtractedRequirements → UserOverrides for form prefill only.

Nothing here is applied automatically: the UI shows the values, the user
confirms or edits them, and only then does ``resolve_format_spec`` see
``UserOverrides``.
"""

from __future__ import annotations

from dataclasses import dataclass

from formatter_v2.spec import (
    AppendixConfig,
    CoverPage,
    ExtractedRequirements,
    PageNumbering,
    StructureConfig,
    StyleProfile,
    TableOfContents,
    UserOverrides,
)


@dataclass(frozen=True)
class PrefillResult:
    """Prefill payload for the smart form UI."""

    overrides: UserOverrides
    evidence_by_field: dict[str, str]
    """UserOverrides field name → verbatim brief quote (when available)."""


def to_user_overrides(
    extracted: ExtractedRequirements,
    profile: StyleProfile,
) -> PrefillResult:
    """Build form prefill from extraction.

    ``profile`` is accepted for call-site symmetry with the resolver; prefill
    does not copy profile defaults into overrides (absent brief values stay
    unset so the form keeps showing profile defaults on its own).
    """
    del profile  # explicit: do not merge profile into overrides

    if extracted.is_empty():
        return PrefillResult(overrides=UserOverrides(), evidence_by_field={})

    evidence = dict(extracted.evidence)
    overrides_data: dict = {}
    evidence_by_field: dict[str, str] = {}

    def take(override_key: str, value, *evidence_keys: str) -> None:
        if value is None:
            return
        overrides_data[override_key] = value
        for key in (override_key, *evidence_keys):
            quote = evidence.get(key)
            if quote:
                evidence_by_field[override_key] = quote
                break

    take("style", extracted.style, "style")
    take("font_family", extracted.font_family, "font_family")
    take("font_size_pt", extracted.font_size_pt, "font_size_pt")
    take("line_spacing", extracted.line_spacing, "line_spacing")
    take("alignment", extracted.alignment, "alignment")
    take("first_line_indent", extracted.first_line_indent, "first_line_indent")
    take("margins", extracted.margins_in, "margins_in", "margins_top_in")
    take("page_size", extracted.page_size, "page_size")

    if extracted.page_number_position is not None:
        overrides_data["page_numbering"] = PageNumbering(
            position=extracted.page_number_position
        )
        quote = evidence.get("page_number_position")
        if quote:
            evidence_by_field["page_numbering"] = quote

    if extracted.requires_cover_page is not None:
        # Title is unknown at prefill time; placeholder satisfies CoverPage validation.
        overrides_data["cover_page"] = CoverPage(
            enabled=extracted.requires_cover_page,
            title="Assignment" if extracted.requires_cover_page else "",
        )
        quote = evidence.get("requires_cover_page")
        if quote:
            evidence_by_field["cover_page"] = quote

    if extracted.requires_toc is not None:
        overrides_data["table_of_contents"] = TableOfContents(
            enabled=extracted.requires_toc
        )
        quote = evidence.get("requires_toc")
        if quote:
            evidence_by_field["table_of_contents"] = quote

    if extracted.requires_appendices is not None:
        overrides_data["appendices"] = AppendixConfig(
            enabled=extracted.requires_appendices
        )
        quote = evidence.get("requires_appendices")
        if quote:
            evidence_by_field["appendices"] = quote

    structure_kwargs: dict = {}
    if extracted.document_type is not None:
        structure_kwargs["document_type"] = extracted.document_type
    if extracted.required_sections:
        structure_kwargs["expected_sections"] = list(extracted.required_sections)
    if structure_kwargs:
        overrides_data["structure"] = StructureConfig(**structure_kwargs)
        quote = evidence.get("required_sections") or evidence.get("document_type")
        if quote:
            evidence_by_field["structure"] = quote

    overrides = UserOverrides.model_validate(overrides_data)
    return PrefillResult(overrides=overrides, evidence_by_field=evidence_by_field)
