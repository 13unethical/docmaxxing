"""Format Engine stage for assignment projects."""

from __future__ import annotations

import io
import os
import uuid
from pathlib import Path
from typing import Any

from docx import Document

from formatter.format_job import FormatJob
from formatter.pipeline import format_document_full
from services.assignment_pipeline.models import utc_now
from services.assignment_spec.validate import count_body_words, count_words

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _storage_root() -> Path:
    override = (os.environ.get("PROJECT_STORAGE_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (_REPO_ROOT / "data" / "projects").resolve()


def _parse_line_spacing(value: Any, *, default: float = 2.0) -> float:
    """Accept numeric or Word-style labels like Double / Single / 1.5."""
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace("-", " ").replace("_", " ")
    aliases = {
        "single": 1.0,
        "single spacing": 1.0,
        "1.0": 1.0,
        "1": 1.0,
        "1.15": 1.15,
        "1.5": 1.5,
        "1.5 lines": 1.5,
        "one and a half": 1.5,
        "double": 2.0,
        "double spacing": 2.0,
        "2.0": 2.0,
        "2": 2.0,
        "2.0 lines": 2.0,
        "triple": 3.0,
    }
    if text in aliases:
        return aliases[text]
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _parse_int(value: Any, *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _job_from_requirement(requirement_json: dict[str, Any]) -> FormatJob:
    from services.assignment_spec import build_assignment_spec

    fmt = requirement_json.get("formatting") if isinstance(requirement_json.get("formatting"), dict) else {}
    # Prefer AssignmentSpec so analyzer field names (font_size, margins, double-spaced)
    # are normalized once for every downstream consumer.
    try:
        spec = build_assignment_spec(requirement_json)
        fmt_spec = spec.formatting.to_dict()
    except Exception:  # noqa: BLE001
        fmt_spec = {}
        spec = None

    raw_spacing = (
        fmt_spec.get("line_spacing")
        if fmt_spec.get("line_spacing") is not None
        else fmt.get("line_spacing")
    )
    if raw_spacing is None:
        raw_spacing = requirement_json.get("line_spacing")

    style = str(
        fmt.get("style")
        or requirement_json.get("format_style")
        or requirement_json.get("citation_style")
        or (spec.citation_style if spec else None)
        or "harvard"
    ).lower()
    if "apa" in style:
        style_id = "apa"
    elif "mla" in style:
        style_id = "mla"
    else:
        style_id = "harvard"

    font_size = fmt_spec.get("font_size_pt")
    if font_size is None:
        font_size = fmt.get("font_size_pt", fmt.get("font_size"))
    alignment = str(fmt_spec.get("alignment") or fmt.get("alignment") or "left").lower()
    if alignment not in {"left", "justify"}:
        alignment = "left"
    margin_preset = str(
        fmt_spec.get("margin_preset")
        or fmt.get("margin_preset")
        or "normal"
    )

    return FormatJob(
        font_family=str(fmt_spec.get("font_family") or fmt.get("font_family") or "Times New Roman"),
        font_size_pt=_parse_int(font_size, default=12),
        line_spacing=_parse_line_spacing(raw_spacing, default=2.0),
        alignment=alignment,
        first_line_indent=bool(fmt.get("first_line_indent", False)),
        space_before_pt=_parse_int(fmt.get("space_before_pt"), default=0),
        space_after_pt=_parse_int(fmt.get("space_after_pt"), default=0),
        margin_preset=margin_preset,
        page_number_position=str(fmt.get("page_number_position") or "bottom_center"),
        auto_headings=bool(fmt.get("auto_headings", True)),
        heading_all_caps=bool(fmt.get("heading_all_caps", False)),
        auto_justify_refs=bool(fmt.get("auto_justify_refs", False)),
        format_style=style_id,
        requirement_headings=bool(fmt.get("requirement_headings", True)),
        heading_size_pt=_parse_int(fmt.get("heading_size_pt") or fmt_spec.get("heading_size_pt"), default=14),
    )


def _docx_from_markdown(title: str, content: str) -> Document:
    """Build a docx from draft text.

    Paragraph boundaries are blank lines (\\n\\n). Single newlines are soft wraps
    and must stay inside one paragraph — never create a paragraph per wrapped line.

    Critical: a block that starts with ``## Heading`` followed by body on the next
    line must become Heading + Normal — never one giant Heading paragraph.
    """
    import re

    doc = Document()
    if title.strip():
        doc.add_heading(title.strip(), level=1)

    blocks = re.split(r"\n\s*\n", content or "")
    for block in blocks:
        raw = (block or "").strip()
        if not raw:
            continue
        lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
        if not lines:
            continue

        # Heading-only line.
        if len(lines) == 1 and lines[0].startswith("## "):
            doc.add_heading(lines[0][3:].strip(), level=2)
            continue
        if len(lines) == 1 and lines[0].startswith("# "):
            doc.add_heading(lines[0][2:].strip(), level=1)
            continue

        # Heading + body in the same block (single newline after ## Title).
        if lines[0].startswith("## "):
            doc.add_heading(lines[0][3:].strip(), level=2)
            body = " ".join(lines[1:]).strip()
            if body:
                doc.add_paragraph(body)
            continue
        if lines[0].startswith("# "):
            doc.add_heading(lines[0][2:].strip(), level=1)
            body = " ".join(lines[1:]).strip()
            if body:
                doc.add_paragraph(body)
            continue

        # Soft-wrapped prose → one Normal paragraph.
        text = " ".join(lines)
        doc.add_paragraph(text)
    return doc


class AssignmentFormatEngine:
    VERSION = "format-engine-1.0"

    def format_draft(
        self,
        *,
        draft: dict[str, Any],
        requirement_json: dict[str, Any],
        project_id: str,
        citation_pack: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del citation_pack  # references already embedded in draft content when available
        title = str(draft.get("title") or requirement_json.get("title") or "Assignment")
        content = str(draft.get("content") or "")
        job = _job_from_requirement(requirement_json)
        document = _docx_from_markdown(title, content)
        from formatter.document_reconstruction import reconstruct_document_before_format
        from formatter.requirement_headings import extract_format_section_labels

        required = requirement_json.get("required_sections") or requirement_json.get("requiredSections") or []
        if isinstance(required, list):
            required_sections = [str(s).strip() for s in required if str(s).strip()]
        else:
            required_sections = []
        # Strip parenthetical brief notes: "Introduction (article title…)" → "Introduction"
        cleaned_sections: list[str] = []
        for label in required_sections:
            base = label.split("(", 1)[0].strip() or label
            cleaned_sections.append(base)
        if not cleaned_sections:
            cleaned_sections = extract_format_section_labels(str(requirement_json.get("raw_brief") or ""))

        recon = reconstruct_document_before_format(
            document,
            document_type=str(requirement_json.get("document_type") or "other"),
            required_sections=cleaned_sections or None,
            prefer_ai=False,
        )
        format_document_full(document, job, recon.assignments)

        out_dir = _storage_root() / project_id / "formatted"
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = "formatted.docx"
        path = out_dir / filename
        buf = io.BytesIO()
        document.save(buf)
        path.write_bytes(buf.getvalue())

        return {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "path": str(path),
            "filename": filename,
            "style_id": job.format_style,
            "word_count": int(draft.get("total_words") or count_body_words(content)),
            "body_word_count": int(draft.get("total_words") or count_body_words(content)),
            "document_word_count": count_words(content),
            "profile_summary": {
                "font_family": job.font_family,
                "font_size_pt": job.font_size_pt,
                "line_spacing": job.line_spacing,
                "alignment": job.alignment,
                "margin_preset": job.margin_preset,
                "page_number_position": job.page_number_position,
            },
            "applied_rules": [
                "page_style",
                "page_numbers",
                "paragraph_styles",
                "headings",
                "references_justify" if job.auto_justify_refs else "references",
            ],
            "engine_version": self.VERSION,
            "formatted_at": utc_now().isoformat(),
            "source_draft_id": str(draft.get("id") or ""),
            "plain_text": content,
        }
