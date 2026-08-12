"""HTTP helpers for Formatter V2 UI routes (not the formatting pipeline itself)."""

from __future__ import annotations

import base64
import json
from typing import Any

from formatter_v2.profiles import load_profile
from formatter_v2.resolve import ResolutionNotice
from formatter_v2.spec import (
    Margins,
    ParagraphRole,
    StyleName,
    StyleProfile,
    UserOverrides,
)

_STYLE_VALUES = {s.value for s in StyleName if s != StyleName.CUSTOM}


def encode_notices_header(notices: list[ResolutionNotice]) -> str:
    """Encode notices as base64(JSON) for ``X-Format-Notices``.

    Binary DOCX responses cannot carry a JSON body, and raw JSON in a header
    breaks on non-ASCII notice text (Russian deviation messages). Base64 keeps
    the download path unchanged while remaining safe for HTTP headers.
    """
    payload = json.dumps(
        [n.model_dump(mode="json") for n in notices],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.b64encode(payload).decode("ascii")


def decode_notices_header(value: str | None) -> list[dict[str, Any]]:
    """Inverse of :func:`encode_notices_header` (used by the browser and tests)."""
    if not value:
        return []
    raw = base64.b64decode(value.encode("ascii"))
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("notices payload must be a JSON array")
    return data


def encode_json_header(payload: Any) -> str:
    """Base64(JSON) for header-safe metadata on DOCX download responses."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(body).decode("ascii")


def decode_json_header(value: str | None) -> Any:
    if not value:
        return None
    raw = base64.b64decode(value.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def encode_overrides_header(overrides: UserOverrides) -> str:
    return encode_json_header(overrides.model_dump(exclude_none=True, mode="json"))


def decode_overrides_header(value: str | None) -> dict[str, Any]:
    data = decode_json_header(value)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("overrides payload must be a JSON object")
    return data


def encode_rejected_header(rejected: list[dict[str, str]]) -> str:
    return encode_json_header(rejected)


def encode_chat_summary_header(summary: str) -> str:
    """Base64(JSON string) so Cyrillic summaries survive HTTP headers."""
    text = (summary or "").strip()
    if not text:
        return ""
    return encode_json_header(text)


def decode_chat_summary_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        decoded = decode_json_header(value)
        if isinstance(decoded, str):
            return decoded
    except (ValueError, json.JSONDecodeError):
        pass
    return value


def parse_user_overrides_from_form(form: Any) -> UserOverrides:
    """Build ``UserOverrides`` from multipart form.

    Expects optional ``overrides`` JSON object. Absent / empty / ``{}`` means
    no overrides — profile defaults apply. Keys with JSON ``null`` are dropped
    so the client can omit untouched fields entirely.
    """
    raw = (form.get("overrides") if form is not None else None) or ""
    raw = str(raw).strip()
    if not raw:
        return UserOverrides()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("overrides must be valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("overrides must be a JSON object")
    cleaned = {k: v for k, v in data.items() if v is not None}
    return UserOverrides.model_validate(cleaned)


def _margin_preset_name(margins: Margins) -> str:
    for name in ("normal", "narrow", "wide"):
        preset = Margins.preset(name)  # type: ignore[arg-type]
        if (
            preset.top_in == margins.top_in
            and preset.bottom_in == margins.bottom_in
            and preset.left_in == margins.left_in
            and preset.right_in == margins.right_in
        ):
            return name
    return "custom"


def _cover_page_form_defaults(cover_page) -> dict[str, Any]:
    data = cover_page.model_dump(mode="json")
    if data.get("title") in ("Assignment", "assignment"):
        data["title"] = ""
    return data


def profile_form_defaults(profile: StyleProfile) -> dict[str, Any]:
    """Flatten profile values the V2 form displays as defaults."""
    body = profile.roles[ParagraphRole.BODY]
    return {
        "font_family": body.font_family.value,
        "font_size_pt": float(body.font_size_pt),
        "line_spacing": float(body.line_spacing),
        "alignment": body.alignment.value,
        "first_line_indent": body.first_line_indent_in > 0,
        "page_size": profile.page.size.value,
        "margin_preset": _margin_preset_name(profile.page.margins),
        "margins": profile.page.margins.model_dump(mode="json"),
        "page_number_position": profile.page_numbering.position.value,
        "cover_page": _cover_page_form_defaults(profile.cover_page),
        "table_of_contents": {
            "enabled": False,
            "max_depth": 3,
            "field_based": False,
            "heading_text": "Table of Contents",
        },
        "abbreviations": {
            "enabled": False,
            "heading_text": "List of Abbreviations",
            "entries": {},
        },
        "appendices": {
            "enabled": False,
            "lettered": True,
            "page_break_before_each": True,
        },
        "captions": profile.captions.model_dump(mode="json"),
        "references": profile.references.model_dump(mode="json"),
        "structure": {
            "expected_sections": [],
        },
        "citations": {
            "style_override": profile.citations.style_override.value
            if profile.citations.style_override
            else None,
        },
    }


def profile_payload(style: StyleName | str) -> dict[str, Any]:
    key = str(style).strip().casefold()
    if key not in _STYLE_VALUES:
        raise ValueError(f"Unknown style: {style!r}")
    style_name = StyleName(key)
    profile = load_profile(style_name)
    return {
        "name": profile.name.value,
        "display_name": profile.display_name,
        "source_manual": profile.source_manual,
        "date_format": profile.date_format,
        "form": profile_form_defaults(profile),
        "profile": profile.model_dump(mode="json"),
    }


def resolve_style_param(value: str | None) -> StyleName:
    from formatter_v2.pipeline import resolve_style_name

    return resolve_style_name(value or "harvard")


def format_v2_response_payload(
    *,
    document_id: str,
    overrides: UserOverrides,
    notices: list[ResolutionNotice],
    summary: str = "",
    rejected: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """JSON body for ``POST /api/format-v2`` and ``POST /api/format-v2/chat``."""
    return {
        "document_id": document_id,
        "summary": summary,
        "rejected": rejected or [],
        "notices": [n.model_dump(mode="json") for n in notices],
        "overrides": overrides.model_dump(exclude_none=True, mode="json"),
    }


def load_format_v2_source_from_form(
    form: Any,
    files: Any,
    *,
    build_document_from_upload: Any,
    is_supported_document_upload: Any,
) -> object:
    """Return document source (docx Document or list of lines) from multipart form."""
    file_storage = files.get("file") if files is not None else None
    pasted_raw = (form.get("pasted_text") if form is not None else None) or ""
    clean_spaces = str(form.get("clean_extra_spaces", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    clean_breaks = str(form.get("clean_extra_linebreaks", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if file_storage and file_storage.filename:
        if not is_supported_document_upload(file_storage.filename, file_storage.mimetype):
            raise ValueError("Invalid file type. Upload a .docx or .pdf file.")
        raw = file_storage.read()
        if not raw:
            raise ValueError("The uploaded file is empty.")
        return build_document_from_upload(
            raw,
            file_storage.filename,
            mimetype=file_storage.mimetype,
            cleaning_spaces=clean_spaces,
            cleaning_breaks=clean_breaks,
        )
    if pasted_raw.strip():
        return [line for line in pasted_raw.replace("\r\n", "\n").split("\n")]
    raise ValueError("Please upload a .docx or .pdf file, or paste some non-empty text.")


FORMAT_V2_EXPOSE_HEADERS = (
    "Content-Disposition",
    "X-Format-Overrides",
    "X-Format-Chat-Summary",
    "X-Format-Chat-Rejected",
    "X-Format-Notices",
    "X-Format-Extractor",
)


def apply_format_v2_response_headers(response: Any) -> Any:
    """Expose custom metadata headers to browser ``fetch()`` (CORS)."""
    response.headers["Access-Control-Expose-Headers"] = ", ".join(
        FORMAT_V2_EXPOSE_HEADERS
    )
    return response
