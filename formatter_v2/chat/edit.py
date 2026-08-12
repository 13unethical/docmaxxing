"""Gemini translation of post-format chat messages into UserOverrides patches.

PROMPT_VERSION and the system instruction share one source of truth:
``docs/prompts/format_chat_prompt.md``. ``PROMPT_VERSION`` below must match
the version declared in that file.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Protocol

from formatter_v2.smartform.extract import parse_prompt_version_from_markdown
from formatter_v2.spec import (
    Alignment,
    FontFamily,
    PageNumberPosition,
    PageSize,
    StyleName,
    UserOverrides,
)

PROMPT_VERSION = "1.1.0"

_PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "prompts"
    / "format_chat_prompt.md"
)

_TIMEOUT_S = 15.0
_MAX_ATTEMPTS = 2

USER_MESSAGE_TEMPLATE = """The document is formatted in style: {style_name}.

Current user overrides (JSON, only fields the user already changed):
{current_overrides_json}

User request:
{message}
"""


def assert_prompt_version_in_sync(
    *,
    code_version: str | None = None,
    prompt_path: Path | None = None,
) -> None:
    code_ver = PROMPT_VERSION if code_version is None else code_version
    path = _PROMPT_PATH if prompt_path is None else prompt_path
    code_path = Path(__file__).resolve()
    doc_text = path.read_text(encoding="utf-8")
    doc_ver = parse_prompt_version_from_markdown(doc_text)
    if doc_ver != code_ver:
        raise RuntimeError(
            "Format chat prompt version mismatch: "
            f"code PROMPT_VERSION={code_ver!r} in {code_path}, "
            f"document PROMPT_VERSION={doc_ver!r} in {path.resolve()}. "
            "Bump both together when editing the prompt."
        )


assert_prompt_version_in_sync()


class ChatLLMClient(Protocol):
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
        """Return a JSON object. Raise ``TimeoutError`` on timeout."""


def load_system_instruction() -> str:
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
    out = dict(schema)
    out["nullable"] = True
    return out


def _enum_schema(values: list[str]) -> dict[str, Any]:
    return _nullable({"type": "string", "enum": values})


def build_response_schema() -> dict[str, Any]:
    """Flat JSON Schema for Gemini ``response_schema``."""
    style_values = [s.value for s in StyleName if s != StyleName.CUSTOM]
    font_values = [f.value for f in FontFamily]
    align_values = [a.value for a in Alignment]
    page_values = [p.value for p in PageSize]
    pos_values = [p.value for p in PageNumberPosition]

    properties: dict[str, Any] = {
        "summary": {"type": "string"},
        "rejected": {
            "type": "array",
            "items": {"type": "string"},
        },
        "relative": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["margins", "font_size_pt", "line_spacing"],
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["increase", "decrease"],
                    },
                },
            },
        },
        "changes_style": _enum_schema(style_values),
        "changes_font_family": _enum_schema(font_values),
        "changes_font_size_pt": _nullable({"type": "number"}),
        "changes_line_spacing": _nullable({"type": "number"}),
        "changes_alignment": _enum_schema(align_values),
        "changes_first_line_indent": _nullable({"type": "boolean"}),
        "changes_margins_top_in": _nullable({"type": "number"}),
        "changes_margins_bottom_in": _nullable({"type": "number"}),
        "changes_margins_left_in": _nullable({"type": "number"}),
        "changes_margins_right_in": _nullable({"type": "number"}),
        "changes_page_size": _enum_schema(page_values),
        "changes_page_number_position": _enum_schema(pos_values),
        "changes_heading_size_pt": _nullable({"type": "number"}),
        "changes_cover_page_enabled": _nullable({"type": "boolean"}),
        "changes_cover_page_title": _nullable({"type": "string"}),
        "changes_table_of_contents_enabled": _nullable({"type": "boolean"}),
        "changes_references_enabled": _nullable({"type": "boolean"}),
        "changes_citations_style_override": _enum_schema(style_values),
    }

    return {
        "type": "object",
        "properties": properties,
    }


_RELATIVE_FIELDS = frozenset({"margins", "font_size_pt", "line_spacing"})
_RELATIVE_DIRECTIONS = frozenset({"increase", "decrease"})


def _parse_relative(raw: Any) -> list[dict[str, str]]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        direction = str(item.get("direction") or "").strip()
        if field in _RELATIVE_FIELDS and direction in _RELATIVE_DIRECTIONS:
            out.append({"field": field, "direction": direction})
    return out


def _empty_chat_response() -> dict[str, Any]:
    return {"changes": {}, "relative": [], "summary": "", "rejected": []}


def _timeout_chat_response() -> dict[str, Any]:
    return {
        "changes": {},
        "relative": [],
        "summary": "",
        "rejected": ["запрос — превышено время ожидания модели (15 с)"],
    }


def _generate_with_timeout(
    client: ChatLLMClient,
    *,
    system_instruction: str,
    user_message: str,
    temperature: float,
    response_mime_type: str,
    response_schema: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    """Hard wall-clock limit so a hung client cannot block the chat route."""
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        client.generate,
        system_instruction=system_instruction,
        user_message=user_message,
        temperature=temperature,
        response_mime_type=response_mime_type,
        response_schema=response_schema,
        timeout_s=timeout_s,
    )
    try:
        return future.result(timeout=timeout_s)
    except FuturesTimeoutError as exc:
        raise TimeoutError(f"Chat edit timed out after {timeout_s:g}s") from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def chat_edit(
    message: str,
    current_overrides: UserOverrides,
    style: StyleName | str,
    client: ChatLLMClient,
) -> dict[str, Any]:
    """Call the LLM and return ``{changes, summary, rejected}``.

    Timeouts and persistent invalid JSON yield empty changes — never an
    exception to the caller.
    """
    from formatter_v2.pipeline import resolve_style_name

    style_name = resolve_style_name(style)
    system = load_system_instruction()
    overrides_json = json.dumps(
        current_overrides.model_dump(exclude_none=True, mode="json"),
        ensure_ascii=False,
    )
    user = USER_MESSAGE_TEMPLATE.format(
        style_name=style_name.value,
        current_overrides_json=overrides_json or "{}",
        message=message or "",
    )
    schema = build_response_schema()

    last_error = "invalid response"
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            raw = _generate_with_timeout(
                client,
                system_instruction=system,
                user_message=user,
                temperature=0,
                response_mime_type="application/json",
                response_schema=schema,
                timeout_s=_TIMEOUT_S,
            )
        except TimeoutError:
            return _timeout_chat_response()
        except (ValueError, json.JSONDecodeError, TypeError) as exc:
            last_error = str(exc) or last_error
            continue
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc) or last_error
            continue

        if not isinstance(raw, dict):
            last_error = "response is not a JSON object"
            continue

        summary = str(raw.get("summary") or "").strip()
        rejected_raw = raw.get("rejected") or []
        rejected: list[str] = []
        if isinstance(rejected_raw, list):
            rejected = [str(item).strip() for item in rejected_raw if str(item).strip()]

        changes: dict[str, Any] = {}
        for key, value in raw.items():
            if not key.startswith("changes_") or value is None:
                continue
            field = key[len("changes_") :]
            changes[field] = value

        return {
            "changes": changes,
            "relative": _parse_relative(raw.get("relative")),
            "summary": summary,
            "rejected": rejected,
        }

    del last_error
    return _empty_chat_response()
