"""Validate and merge chat-derived setting changes into UserOverrides."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from formatter_v2.chat.edit import ChatLLMClient, chat_edit
from formatter_v2.chat.summary import profile_defaults_as_overrides, summarize_override_changes
from formatter_v2.profiles import load_profile
from formatter_v2.spec import (
    Margins,
    ParagraphRole,
    StyleName,
    StyleProfile,
    UserOverrides,
)

_OVERRIDE_FIELDS = frozenset(UserOverrides.model_fields.keys())

_MARGIN_FLAT = (
    ("margins_top_in", "top_in"),
    ("margins_bottom_in", "bottom_in"),
    ("margins_left_in", "left_in"),
    ("margins_right_in", "right_in"),
)

_RELATIVE_FIELDS = frozenset({"margins", "font_size_pt", "line_spacing"})
_RELATIVE_DIRECTIONS = frozenset({"increase", "decrease"})
_SPACING_STEPS = (1.0, 1.15, 1.5, 2.0)
_MARGIN_STEP_IN = 0.25
_FONT_SIZE_STEP_PT = 1.0
_MARGIN_MIN, _MARGIN_MAX = 0.0, 3.0
_FONT_MIN, _FONT_MAX = 6.0, 48.0


@dataclass(frozen=True)
class RejectedItem:
    request: str
    reason: str

    def as_string(self) -> str:
        return f"{self.request} — {self.reason}"


def deep_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = deep_merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def merge_user_overrides(
    base: UserOverrides,
    patch: UserOverrides,
) -> UserOverrides:
    """Merge ``patch`` onto ``base``; nested objects are deep-merged."""
    base_dict = base.model_dump(exclude_none=True, mode="json")
    patch_dict = patch.model_dump(exclude_none=True, exclude_unset=True, mode="json")
    merged = deep_merge_dict(base_dict, patch_dict)
    return UserOverrides.model_validate(merged)


def inflate_chat_changes(data: dict[str, Any]) -> dict[str, Any]:
    """Convert flat ``changes_*`` payload into UserOverrides-shaped dict."""
    out: dict[str, Any] = dict(data)

    margin_vals: dict[str, float] = {}
    for flat_key, nested_key in _MARGIN_FLAT:
        if flat_key in out:
            value = out.pop(flat_key)
            if value is not None:
                margin_vals[nested_key] = float(value)
    if margin_vals:
        fill = next(iter(margin_vals.values()))
        out["margins"] = {
            "top_in": margin_vals.get("top_in", fill),
            "bottom_in": margin_vals.get("bottom_in", fill),
            "left_in": margin_vals.get("left_in", fill),
            "right_in": margin_vals.get("right_in", fill),
        }

    if "page_number_position" in out:
        pos = out.pop("page_number_position")
        if pos is not None:
            out["page_numbering"] = {"position": pos}

    if "cover_page_enabled" in out or "cover_page_title" in out:
        cover: dict[str, Any] = {}
        if "cover_page_enabled" in out:
            cover["enabled"] = out.pop("cover_page_enabled")
        if "cover_page_title" in out:
            cover["title"] = out.pop("cover_page_title")
        if cover:
            out["cover_page"] = cover

    if "table_of_contents_enabled" in out:
        enabled = out.pop("table_of_contents_enabled")
        if enabled is not None:
            out["table_of_contents"] = {"enabled": enabled}

    if "references_enabled" in out:
        enabled = out.pop("references_enabled")
        if enabled is not None:
            out["references"] = {"enabled": enabled}

    if "citations_style_override" in out:
        override = out.pop("citations_style_override")
        if override is not None:
            out["citations"] = {"style_override": override}

    return out


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _next_spacing(current: float, direction: str) -> float:
    if direction == "increase":
        for value in _SPACING_STEPS:
            if value > current + 1e-9:
                return value
        return _SPACING_STEPS[-1]
    for value in reversed(_SPACING_STEPS):
        if value < current - 1e-9:
            return value
    return _SPACING_STEPS[0]


def _step_margins(current: Margins, direction: str) -> Margins:
    delta = _MARGIN_STEP_IN if direction == "increase" else -_MARGIN_STEP_IN

    def side(value: float) -> float:
        return _clamp(round(value + delta, 4), _MARGIN_MIN, _MARGIN_MAX)

    return Margins(
        top_in=side(current.top_in),
        bottom_in=side(current.bottom_in),
        left_in=side(current.left_in),
        right_in=side(current.right_in),
    )


def _effective_numeric(
    current: UserOverrides,
    profile: StyleProfile,
) -> tuple[float, float, Margins]:
    body = profile.roles[ParagraphRole.BODY]
    font = current.font_size_pt if current.font_size_pt is not None else body.font_size_pt
    spacing = current.line_spacing if current.line_spacing is not None else body.line_spacing
    margins = current.margins if current.margins is not None else profile.page.margins
    return float(font), float(spacing), margins


def apply_relative_changes(
    current: UserOverrides,
    relative: list[dict[str, str]],
    profile: StyleProfile,
) -> tuple[dict[str, Any], list[RejectedItem]]:
    """Turn {field, direction} items into a UserOverrides-shaped patch."""
    patch: dict[str, Any] = {}
    rejected: list[RejectedItem] = []
    font, spacing, margins = _effective_numeric(current, profile)
    for item in relative:
        field = item.get("field", "")
        direction = item.get("direction", "")
        if field not in _RELATIVE_FIELDS or direction not in _RELATIVE_DIRECTIONS:
            rejected.append(
                RejectedItem(
                    request=str(item),
                    reason="invalid relative change",
                )
            )
            continue
        if field == "margins":
            margins = _step_margins(margins, direction)
            patch["margins"] = margins
        elif field == "font_size_pt":
            delta = _FONT_SIZE_STEP_PT if direction == "increase" else -_FONT_SIZE_STEP_PT
            font = _clamp(font + delta, _FONT_MIN, _FONT_MAX)
            patch["font_size_pt"] = font
        elif field == "line_spacing":
            spacing = _next_spacing(spacing, direction)
            patch["line_spacing"] = spacing
    return patch, rejected


def _validate_field_patch(field: str, value: Any) -> Any:
    """Validate a single override field; raise ``ValidationError`` on failure."""
    UserOverrides.model_validate({field: value})
    return value


def _apply_validated_changes(
    current: UserOverrides,
    changes: dict[str, Any],
    llm_rejected: list[str],
) -> tuple[UserOverrides, str, list[RejectedItem]]:
    inflated = inflate_chat_changes(changes)
    rejected: list[RejectedItem] = []
    for item in llm_rejected:
        if " — " in item:
            request, reason = item.split(" — ", 1)
            rejected.append(RejectedItem(request=request.strip(), reason=reason.strip()))
        else:
            rejected.append(RejectedItem(request=item, reason=""))

    valid_patch: dict[str, Any] = {}
    for key, value in inflated.items():
        if key not in _OVERRIDE_FIELDS:
            rejected.append(
                RejectedItem(
                    request=key,
                    reason="Unknown formatting setting",
                )
            )
            continue
        try:
            _validate_field_patch(key, value)
            valid_patch[key] = value
        except ValidationError as exc:
            reason = "; ".join(
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                for err in exc.errors()
            )
            rejected.append(
                RejectedItem(
                    request=key,
                    reason=reason or "Invalid value",
                )
            )

    base_dict = current.model_dump(exclude_none=True, mode="json")
    merged_dict = deep_merge_dict(base_dict, valid_patch)
    merged = UserOverrides.model_validate(merged_dict)
    return merged, "", rejected


def apply_chat_edit(
    message: str,
    current_overrides: UserOverrides,
    style: StyleName | str,
    client: ChatLLMClient,
) -> tuple[UserOverrides, str, list[RejectedItem]]:
    """Translate ``message`` via LLM and merge validated changes.

    Returns ``(new_overrides, summary, rejected)``. New changes merge on top
    of ``current_overrides``; they do not replace unrelated fields.
  """
    raw = chat_edit(message, current_overrides, style, client)
    profile = load_profile(style)
    relative_patch, relative_rejected = apply_relative_changes(
        current_overrides,
        raw.get("relative") or [],
        profile,
    )
    after_relative = current_overrides
    if relative_patch:
        after_relative = merge_user_overrides(
            current_overrides,
            UserOverrides.model_validate(relative_patch),
        )
    merged, _, rejected = _apply_validated_changes(
        after_relative,
        raw.get("changes") or {},
        raw.get("rejected") or [],
    )
    rejected = [*relative_rejected, *rejected]
    baseline = profile_defaults_as_overrides(profile)
    summary = summarize_override_changes(
        merge_user_overrides(baseline, current_overrides),
        merge_user_overrides(baseline, merged),
    )
    return merged, summary, rejected


def push_override_undo(
    stack: list[UserOverrides],
    snapshot: UserOverrides,
) -> list[UserOverrides]:
    """Return a new stack with ``snapshot`` pushed (immutable pattern)."""
    return [*stack, snapshot]


def pop_override_undo(stack: list[UserOverrides]) -> tuple[UserOverrides, list[UserOverrides]]:
    """Pop the latest snapshot; return previous overrides and shortened stack."""
    if len(stack) < 2:
        current = stack[0] if stack else UserOverrides()
        return current, stack[:1] if stack else []
    new_stack = stack[:-1]
    return new_stack[-1], new_stack
