"""Create documents from pasted text or uploaded .docx / .pdf files."""

from __future__ import annotations

import io
import os
import re

from docx import Document

from formatter.text_cleaning import clean_pasted_raw, paragraphs_snapshot_apply_cleaning

UPLOAD_DOCUMENT_EXTENSIONS = frozenset({".docx", ".pdf"})


def upload_extension(filename: str, mimetype: str | None = None) -> str:
    """Resolve .docx / .pdf from filename or MIME type."""
    ext = os.path.splitext((filename or "").lower())[1]
    if ext in UPLOAD_DOCUMENT_EXTENSIONS:
        return ext
    mt = (mimetype or "").lower()
    if "pdf" in mt:
        return ".pdf"
    if "wordprocessingml" in mt or mt == "application/msword":
        return ".docx"
    return ext


def is_supported_document_upload(filename: str, mimetype: str | None = None) -> bool:
    return upload_extension(filename, mimetype) in UPLOAD_DOCUMENT_EXTENSIONS


def extract_text_from_docx_bytes(raw: bytes) -> str:
    """Extract body text; each paragraph (including headings) stays a separate block."""
    doc = Document(io.BytesIO(raw))
    parts: list[str] = []
    for paragraph in doc.paragraphs:
        text = (paragraph.text or "").strip()
        if text:
            parts.append(text)
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n\n".join(parts).strip()


def _run_to_html(run) -> str:
    """One python-docx run → inline HTML (bold/italic/underline/color/font)."""
    import html as html_lib

    text = run.text or ""
    if not text:
        return ""
    esc = html_lib.escape(text)
    styles: list[str] = []
    if run.font and run.font.color and run.font.color.rgb:
        styles.append(f"color: #{run.font.color.rgb}")
    if run.font and run.font.name:
        styles.append(f"font-family: {run.font.name}")
    if run.font and run.font.size:
        try:
            styles.append(f"font-size: {int(run.font.size.pt)}pt")
        except Exception:  # noqa: BLE001
            pass
    inner = esc
    if styles:
        inner = f'<span style="{html_lib.escape("; ".join(styles), quote=True)}">{inner}</span>'
    if run.underline:
        inner = f"<u>{inner}</u>"
    if run.italic:
        inner = f"<i>{inner}</i>"
    if run.bold:
        inner = f"<b>{inner}</b>"
    return inner


def _paragraph_to_html(paragraph) -> str:
    import html as html_lib

    text = (paragraph.text or "").strip()
    if not text:
        return ""
    style_name = (paragraph.style.name or "") if paragraph.style else ""
    inner = "".join(_run_to_html(run) for run in paragraph.runs) or html_lib.escape(text)
    if style_name.startswith("Heading"):
        level = "".join(ch for ch in style_name if ch.isdigit()) or "2"
        level = str(min(6, max(1, int(level))))
        return f"<h{level}>{inner}</h{level}>"
    if style_name.startswith("List Number"):
        return f"<ol><li>{inner}</li></ol>"
    if style_name.startswith("List Bullet"):
        return f"<ul><li>{inner}</li></ul>"
    return f"<p>{inner}</p>"


def _table_to_html(table) -> str:
    import html as html_lib

    rows = []
    for row in table.rows:
        cells = "".join(f"<td>{html_lib.escape((cell.text or '').strip())}</td>" for cell in row.cells)
        rows.append(f"<tr>{cells}</tr>")
    return "<table>" + "".join(rows) + "</table>"


def extract_html_from_docx_bytes(raw: bytes) -> str:
    """DOCX → HTML preserving bold/italic/underline/color/font and tables."""
    doc = Document(io.BytesIO(raw))
    parts: list[str] = []
    # Walk body elements in order (paragraphs and tables interleaved).
    body = doc.element.body
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            html = _paragraph_to_html(Paragraph(child, doc))
            if html:
                parts.append(html)
        elif child.tag == qn("w:tbl"):
            parts.append(_table_to_html(Table(child, doc)))
    return "\n".join(parts).strip()


def extract_html_from_document_bytes(raw: bytes, filename: str, mimetype: str | None = None) -> str:
    """HTML when possible (.docx); PDF falls back to escaped paragraphs."""
    import html as html_lib

    if not raw:
        raise ValueError("The uploaded file is empty.")
    ext = upload_extension(filename, mimetype)
    if ext == ".docx":
        html = extract_html_from_docx_bytes(raw)
    elif ext == ".pdf":
        text = extract_text_from_pdf_bytes(raw)
        html = "\n".join(f"<p>{html_lib.escape(p)}</p>" for p in re.split(r"\n\s*\n", text) if p.strip())
    else:
        raise ValueError("Unsupported file type. Upload a .docx or .pdf file.")
    if not html.strip():
        raise ValueError("No readable text found in the uploaded file.")
    return html


def extract_text_from_pdf_bytes(raw: bytes) -> str:
    from services.requirements_ocr import extract_text_from_pdf_bytes as _pdf_extract

    return _pdf_extract(raw)


def extract_text_from_document_bytes(raw: bytes, filename: str, mimetype: str | None = None) -> str:
    if not raw:
        raise ValueError("The uploaded file is empty.")
    ext = upload_extension(filename, mimetype)
    if ext == ".docx":
        text = extract_text_from_docx_bytes(raw)
    elif ext == ".pdf":
        text = extract_text_from_pdf_bytes(raw)
    else:
        raise ValueError("Unsupported file type. Upload a .docx or .pdf file.")
    if not text.strip():
        raise ValueError("No readable text found in the uploaded file.")
    return text


def document_has_visible_content(doc: Document) -> bool:
    if any((p.text or "").strip() for p in doc.paragraphs):
        return True
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if (cell.text or "").strip():
                    return True
    return False


def document_from_pasted_text(pasted: str) -> Document:
    """One Word paragraph per blank-line-separated block (\\n\\n)."""
    doc = Document()
    if doc.paragraphs:
        body = doc.paragraphs[0]._element
        body.getparent().remove(body)

    if not pasted.strip():
        doc.add_paragraph("")
        return doc

    blocks = re.split(r"\n\s*\n", pasted)
    for block in blocks:
        text = block.strip("\n")
        doc.add_paragraph(text)
    return doc


def build_document_from_inputs(
    *,
    pasted_raw: str | None,
    file_bytes: bytes | None,
    cleaning_spaces: bool,
    cleaning_breaks: bool,
) -> Document:
    """
    Load from upload or paste. Cleaning (optional) runs on paste as a whole string,
    or per-paragraph after load for .docx uploads.
    """
    if file_bytes is not None:
        doc = Document(io.BytesIO(file_bytes))
        if cleaning_spaces or cleaning_breaks:
            paragraphs_snapshot_apply_cleaning(
                doc,
                extra_spaces=cleaning_spaces,
                extra_linebreaks=cleaning_breaks,
            )
        return doc

    # Paste path
    text = pasted_raw or ""
    text = clean_pasted_raw(
        text,
        extra_spaces=cleaning_spaces,
        extra_linebreaks=cleaning_breaks,
    )
    return document_from_pasted_text(text)


def build_document_from_upload(
    file_bytes: bytes,
    filename: str,
    *,
    mimetype: str | None = None,
    cleaning_spaces: bool,
    cleaning_breaks: bool,
) -> Document:
    """Load .docx directly; convert PDF text into a new Word document."""
    ext = upload_extension(filename, mimetype)
    if ext == ".docx":
        return build_document_from_inputs(
            pasted_raw=None,
            file_bytes=file_bytes,
            cleaning_spaces=cleaning_spaces,
            cleaning_breaks=cleaning_breaks,
        )
    if ext == ".pdf":
        text = extract_text_from_pdf_bytes(file_bytes)
        return build_document_from_inputs(
            pasted_raw=text,
            file_bytes=None,
            cleaning_spaces=cleaning_spaces,
            cleaning_breaks=cleaning_breaks,
        )
    raise ValueError("Unsupported file type. Upload a .docx or .pdf file.")
