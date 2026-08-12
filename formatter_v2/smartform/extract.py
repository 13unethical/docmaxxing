"""Gemini extraction of formatting requirements from assignment briefs.

PROMPT_VERSION and the system instruction share one source of truth:
``docs/prompts/requirements_extraction_prompt.md``. The markdown file is
loaded at runtime (not copied into this module) so prompt edits and the
version bump stay in one place, as the prompt document itself requires.
``PROMPT_VERSION`` below must match the version declared in that file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from formatter_v2.smartform.postprocess import postprocess_extraction
from formatter_v2.spec import (
    Alignment,
    DocumentType,
    ExtractedRequirements,
    FontFamily,
    PageNumberPosition,
    PageSize,
    StyleName,
)

PROMPT_VERSION = "1.0.0"

_PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "prompts"
    / "requirements_extraction_prompt.md"
)

_PROMPT_VERSION_RE = re.compile(
    r"""PROMPT_VERSION\s*=\s*["']([^"']+)["']""",
)

_TIMEOUT_S = 20.0
_MAX_ATTEMPTS = 2

USER_MESSAGE_TEMPLATE = """Extract the formatting and submission requirements from the assignment brief
below. Return null for anything the brief does not state.

--- BEGIN BRIEF ---
{brief_text}
--- END BRIEF ---
"""


def parse_prompt_version_from_markdown(text: str) -> str:
    """Extract ``PROMPT_VERSION = "…"`` from the prompt markdown document."""
    match = _PROMPT_VERSION_RE.search(text)
    if not match:
        raise RuntimeError(
            f"PROMPT_VERSION declaration not found in prompt markdown "
            f"({_PROMPT_PATH})"
        )
    return match.group(1)


def assert_prompt_version_in_sync(
    *,
    code_version: str | None = None,
    prompt_path: Path | None = None,
) -> None:
    """Ensure the markdown prompt version matches ``PROMPT_VERSION`` in code.

    Raises ``RuntimeError`` naming both versions and both file paths when they
    diverge — called at import time so the app refuses to start out of sync.
    """
    code_ver = PROMPT_VERSION if code_version is None else code_version
    path = _PROMPT_PATH if prompt_path is None else prompt_path
    code_path = Path(__file__).resolve()
    doc_text = path.read_text(encoding="utf-8")
    doc_ver = parse_prompt_version_from_markdown(doc_text)
    if doc_ver != code_ver:
        raise RuntimeError(
            "Smartform prompt version mismatch: "
            f"code PROMPT_VERSION={code_ver!r} in {code_path}, "
            f"document PROMPT_VERSION={doc_ver!r} in {path.resolve()}. "
            "Bump both together when editing the prompt."
        )


# Fail fast on import if markdown and code drift apart.
assert_prompt_version_in_sync()


class SmartformLLMClient(Protocol):
    """Minimal client contract. Tests supply a mock; production wraps Gemini."""

    def generate(
        self,
        *,
        system_instruction: str,
        user_message: str,
        temperature: float,
        response_mime_type: str,
        response_schema: dict[str, Any],
        timeout_s: float,
    ) -> dict[str, Any]:
        """Return a JSON object.

        Raise ``TimeoutError`` on timeout / deadline.
        Raise ``ValueError`` (or ``json.JSONDecodeError``) if the body is not
        valid JSON / not an object — the caller will retry.
        """


def load_system_instruction() -> str:
    """Parse the fenced System instruction block from the prompt markdown."""
    text = _PROMPT_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"## System instruction\s*```\s*(.*?)\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        raise FileNotFoundError(
            f"System instruction block not found in {_PROMPT_PATH}"
        )
    return match.group(1).strip()


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    """Gemini-friendly nullability without anyOf/$ref."""
    out = dict(schema)
    out["nullable"] = True
    return out


def _enum_schema(values: list[str]) -> dict[str, Any]:
    return _nullable({"type": "string", "enum": values})


def build_response_schema() -> dict[str, Any]:
    """Flat JSON Schema for Gemini ``response_schema``.

    Nested ``Margins`` becomes four top-level number fields. No ``$ref``,
    no nested objects with their own ``properties`` (``evidence`` uses
    ``additionalProperties`` only).
    """
    style_values = [s.value for s in StyleName if s != StyleName.CUSTOM]
    font_values = [f.value for f in FontFamily]
    align_values = [a.value for a in Alignment]
    page_values = [p.value for p in PageSize]
    pos_values = [p.value for p in PageNumberPosition]
    doc_values = [d.value for d in DocumentType]

    properties: dict[str, Any] = {
        "style": _enum_schema(style_values),
        "document_type": _enum_schema(doc_values),
        "font_family": _enum_schema(font_values),
        "font_size_pt": _nullable({"type": "number"}),
        "line_spacing": _nullable({"type": "number"}),
        "alignment": _enum_schema(align_values),
        "first_line_indent": _nullable({"type": "boolean"}),
        "margins_top_in": _nullable({"type": "number"}),
        "margins_bottom_in": _nullable({"type": "number"}),
        "margins_left_in": _nullable({"type": "number"}),
        "margins_right_in": _nullable({"type": "number"}),
        "page_size": _enum_schema(page_values),
        "page_number_position": _enum_schema(pos_values),
        "word_count_min": _nullable({"type": "integer"}),
        "word_count_max": _nullable({"type": "integer"}),
        "deadline": _nullable({"type": "string"}),
        "required_sections": {
            "type": "array",
            "items": {"type": "string"},
        },
        "min_references": _nullable({"type": "integer"}),
        "max_references": _nullable({"type": "integer"}),
        "requires_cover_page": _nullable({"type": "boolean"}),
        "requires_toc": _nullable({"type": "boolean"}),
        "requires_abstract": _nullable({"type": "boolean"}),
        "requires_appendices": _nullable({"type": "boolean"}),
        "evidence": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "unsupported": {
            "type": "array",
            "items": {"type": "string"},
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
        },
    }

    return {
        "type": "object",
        "properties": properties,
    }


_MARGIN_FLAT = (
    ("margins_top_in", "top_in"),
    ("margins_bottom_in", "bottom_in"),
    ("margins_left_in", "left_in"),
    ("margins_right_in", "right_in"),
)


def inflate_flat_response(data: dict[str, Any]) -> dict[str, Any]:
    """Convert Gemini flat margin fields into ``margins_in`` for the model."""
    out = dict(data)
    margin_vals: dict[str, float] = {}
    for flat_key, nested_key in _MARGIN_FLAT:
        if flat_key in out:
            value = out.pop(flat_key)
            if value is not None:
                margin_vals[nested_key] = float(value)
    if margin_vals:
        fill = next(iter(margin_vals.values()))
        out["margins_in"] = {
            "top_in": margin_vals.get("top_in", fill),
            "bottom_in": margin_vals.get("bottom_in", fill),
            "left_in": margin_vals.get("left_in", fill),
            "right_in": margin_vals.get("right_in", fill),
        }
    return out


def _empty_with_warning(message: str) -> ExtractedRequirements:
    return ExtractedRequirements(warnings=[message])


def extract_requirements(
    brief_text: str,
    client: SmartformLLMClient,
) -> ExtractedRequirements:
    """Call Gemini (via ``client``) and post-process into ExtractedRequirements.

    Timeouts and persistent invalid JSON yield an empty extraction with a
    warning — never an exception to the caller.
    """
    system = load_system_instruction()
    user = USER_MESSAGE_TEMPLATE.format(brief_text=brief_text or "")
    schema = build_response_schema()

    last_error = "invalid response"
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            raw = client.generate(
                system_instruction=system,
                user_message=user,
                temperature=0,
                response_mime_type="application/json",
                response_schema=schema,
                timeout_s=_TIMEOUT_S,
            )
        except TimeoutError:
            return _empty_with_warning(
                "Brief analysis timed out; showing style defaults."
            )
        except (ValueError, json.JSONDecodeError, TypeError) as exc:
            last_error = str(exc) or last_error
            continue
        except Exception as exc:  # noqa: BLE001 — never crash the form
            # Network / unexpected: treat like soft failure after attempts.
            last_error = str(exc) or last_error
            continue

        if not isinstance(raw, dict):
            last_error = "response is not a JSON object"
            continue

        inflated = inflate_flat_response(raw)
        return postprocess_extraction(inflated, brief_text)

    return _empty_with_warning(
        f"Brief analysis failed after {_MAX_ATTEMPTS} attempts ({last_error}); "
        "showing style defaults."
    )
