"""Helpers for building parsed document inputs to the Research Engine."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from formatter.document_io import extract_text_from_document_bytes
from services.assignment_pipeline.models import utc_now
from services.research_engine.models import ParsedDocument

# Cap per file so research prompts stay bounded.
_MAX_CHARS_PER_FILE = 14000


def build_parsed_documents(files: list[Any], parsed_payload: list[dict] | None = None) -> list[ParsedDocument]:
    """Prefer explicit parsed payloads; otherwise extract real text from stored files."""
    if parsed_payload:
        return [ParsedDocument.from_dict(item) for item in parsed_payload]

    documents: list[ParsedDocument] = []
    for file_record in files:
        text = _extract_project_file_text(file_record)
        file_type = file_record.file_type
        file_type_value = file_type.value if hasattr(file_type, "value") else str(file_type)
        documents.append(
            ParsedDocument(
                id=str(uuid.uuid4()),
                file_id=file_record.id,
                file_type=file_type_value,
                filename=file_record.original_filename,
                text=text,
                word_count=len(text.split()),
                parsed_at=utc_now(),
            )
        )
    return documents


def _extract_project_file_text(file_record: Any) -> str:
    path = Path(getattr(file_record, "storage_path", "") or "")
    file_type = getattr(file_record, "file_type", "")
    file_type_value = file_type.value if hasattr(file_type, "value") else str(file_type)
    original = getattr(file_record, "original_filename", "") or path.name
    header = f"[{file_type_value}] {original}"
    if not path.exists() or not path.is_file():
        return f"{header}\n(file content unavailable in storage)"
    try:
        raw = path.read_bytes()
    except OSError:
        return f"{header}\n(unable to read file content)"
    if not raw:
        return f"{header}\n(empty file)"

    suffix = path.suffix.lower()
    try:
        if suffix in {".txt", ".md"}:
            text = raw.decode("utf-8", errors="replace")
        elif suffix in {".docx", ".pdf"}:
            text = extract_text_from_document_bytes(raw, original)
        elif suffix == ".zip":
            text = _extract_zip_text(raw, original)
        else:
            text = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return f"{header}\n(failed to parse file content)"

    normalized = " ".join((text or "").replace("\r", "\n").split())
    if not normalized:
        return f"{header}\n(empty file content)"
    return f"{header}\n{normalized[:_MAX_CHARS_PER_FILE]}"


def _extract_zip_text(raw: bytes, original_filename: str) -> str:
    import io
    import zipfile

    chunks: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")][:12]
            for name in names:
                lower = name.lower()
                if not lower.endswith((".txt", ".md", ".docx", ".pdf")):
                    chunks.append(f"[zip member skipped] {name}")
                    continue
                data = zf.read(name)
                if lower.endswith((".txt", ".md")):
                    body = data.decode("utf-8", errors="replace")
                else:
                    body = extract_text_from_document_bytes(data, name)
                body = " ".join((body or "").replace("\r", "\n").split())[:4000]
                chunks.append(f"[zip:{name}]\n{body or '(empty)'}")
    except Exception as exc:  # noqa: BLE001
        return f"(failed to read zip {original_filename}: {exc})"
    return "\n\n".join(chunks) if chunks else "(empty zip archive)"
