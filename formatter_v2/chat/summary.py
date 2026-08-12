"""Deterministic chat-edit summaries from applied UserOverrides diffs."""

from __future__ import annotations

from typing import Any

from formatter_v2.spec import (
    Margins,
    ParagraphRole,
    StyleProfile,
    UserOverrides,
)

_LABELS: dict[str, str] = {
    "line_spacing": "line spacing",
    "font_size_pt": "font size",
    "font_family": "font",
    "alignment": "alignment",
    "first_line_indent": "first-line indent",
    "page_size": "page size",
    "style": "style",
    "heading_size_pt": "heading size",
    "heading_case": "heading case",
    "page_numbering.position": "page numbers",
    "cover_page.enabled": "cover page",
    "cover_page.title": "cover title",
    "table_of_contents.enabled": "table of contents",
    "references.enabled": "references",
    "citations.style_override": "citation style",
}


def _format_number(value: Any) -> str:
    number = float(value)
    if abs(number - round(number)) < 1e-6 and number <= 10:
        return f"{number:.1f}"
    if abs(number - round(number)) < 1e-6:
        return str(int(round(number)))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _format_inches(value: Any) -> str:
    number = float(value)
    if abs(number - round(number)) < 1e-6:
        return f'{int(round(number))}"'
    return f'{_format_number(value)}"'


def _format_value(path: str, value: Any) -> str:
    if value is None:
        return "—"
    if path == "line_spacing" or path.endswith("_pt"):
        return _format_number(value)
    if path.endswith("_in"):
        return _format_inches(value)
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        else:
            out[path] = value
    return out


def _margins_line(before: Margins | None, after: Margins | None) -> str | None:
    left = before or Margins()
    right = after or Margins()
    if left.model_dump() == right.model_dump():
        return None
    before_vals = (left.top_in, left.bottom_in, left.left_in, left.right_in)
    after_vals = (right.top_in, right.bottom_in, right.left_in, right.right_in)
    if len(set(before_vals)) == 1 and len(set(after_vals)) == 1:
        return f"margins {_format_inches(before_vals[0])} → {_format_inches(after_vals[0])}"
    side_labels = ("top", "bottom", "left", "right")
    parts = [
        f"margin {label} {_format_inches(old)} → {_format_inches(new)}"
        for label, old, new in zip(side_labels, before_vals, after_vals, strict=True)
        if old != new
    ]
    return ", ".join(parts) if parts else None


def profile_defaults_as_overrides(profile: StyleProfile) -> UserOverrides:
    """UserOverrides filled with the values the document actually uses before any chat edit."""
    body = profile.roles[ParagraphRole.BODY]
    return UserOverrides(
        font_family=body.font_family,
        font_size_pt=body.font_size_pt,
        line_spacing=body.line_spacing,
        alignment=body.alignment,
        first_line_indent=body.first_line_indent_in > 0,
        margins=profile.page.margins.model_copy(deep=True),
        page_size=profile.page.size,
    )


def summarize_override_changes(before: UserOverrides, after: UserOverrides) -> str:
    """Build a human-readable summary from overrides that actually changed."""
    if before.model_dump(exclude_none=True) == after.model_dump(exclude_none=True):
        return ""

    parts: list[str] = []
    margin_line = _margins_line(before.margins, after.margins)
    if margin_line:
        parts.append(margin_line)

    before_data = before.model_dump(exclude_none=True, mode="json")
    after_data = after.model_dump(exclude_none=True, mode="json")
    before_data.pop("margins", None)
    after_data.pop("margins", None)

    before_flat = _flatten(before_data)
    after_flat = _flatten(after_data)
    for path in sorted(set(before_flat) | set(after_flat)):
        old = before_flat.get(path)
        new = after_flat.get(path)
        if old == new:
            continue
        label = _LABELS.get(path, path)
        parts.append(f"{label} {_format_value(path, old)} → {_format_value(path, new)}")

    return ", ".join(parts)
