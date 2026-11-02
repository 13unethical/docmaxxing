"""Plain text -> .docx / .pdf downloads (humanizer results)."""

from __future__ import annotations

import html
import re

from services.editor_export import html_to_docx

MAX_TEXT_CHARS = 200_000

# Helvetica advance widths (Adobe AFM, 1/1000 em) for ASCII 32..126
_HELVETICA = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
_WIDE = {"\u2014": 1000, "\u2026": 1000, "\u2122": 1000, "\u2030": 1000}

PAGE_W, PAGE_H, MARGIN = 595.0, 842.0, 72.0   # A4, 1 inch margins
FONT_SIZE, LEADING = 11.0, 16.0


class TextExportError(ValueError):
    pass


def paragraphs(text: str) -> list[str]:
    """Blank lines split paragraphs; single line breaks inside a paragraph are kept."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _check(text: str) -> None:
    if not str(text or "").strip():
        raise TextExportError("There is no text to download.")
    if len(text) > MAX_TEXT_CHARS:
        raise TextExportError("This text is too long to download.")


def text_to_docx(title: str, text: str) -> bytes:
    _check(text)
    body = "".join(
        "<p>" + "<br>".join(html.escape(line) for line in p.split("\n")) + "</p>" for p in paragraphs(text)
    )
    return html_to_docx(title, body)


def _char_width(ch: str) -> float:
    code = ord(ch)
    if 32 <= code <= 126:
        return _HELVETICA[code - 32]
    return _WIDE.get(ch, 556)


def _width(s: str) -> float:
    return sum(_char_width(c) for c in s) * FONT_SIZE / 1000


def _wrap(line: str, max_w: float) -> list[str]:
    out, cur = [], ""
    for word in line.split(" "):
        cand = f"{cur} {word}" if cur else word
        if _width(cand) <= max_w:
            cur = cand
            continue
        if cur:
            out.append(cur)
        while _width(word) > max_w:   # one very long token: hard split
            cut = len(word)
            while cut > 1 and _width(word[:cut]) > max_w:
                cut -= 1
            out.append(word[:cut])
            word = word[cut:]
        cur = word
    out.append(cur)
    return out


def _pdf_string(s: str) -> bytes:
    raw = s.encode("cp1252", errors="replace")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def text_to_pdf(title: str, text: str) -> bytes:
    """A text-only PDF in Helvetica (WinAnsi); characters outside it become '?'."""
    _check(text)
    max_w = PAGE_W - 2 * MARGIN
    lines_per_page = int((PAGE_H - 2 * MARGIN) // LEADING)
    rows: list[str | None] = []   # None = paragraph gap
    for p in paragraphs(text):
        if rows:
            rows.append(None)
        for line in p.split("\n"):
            rows.extend(_wrap(line.strip(), max_w))
    pages: list[list[str | None]] = []
    for row in rows:
        if not pages or len(pages[-1]) >= lines_per_page:
            if row is None:
                continue
            pages.append([])
        pages[-1].append(row)

    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")
    pages_id = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    kids = []
    for page in pages:
        ops = [b"BT", f"/F1 {FONT_SIZE:g} Tf {LEADING:g} TL {MARGIN:g} {PAGE_H - MARGIN - FONT_SIZE:g} Td".encode()]
        for row in page:
            ops.append(b"T*" if row is None else _pdf_string(row) + b" Tj T*")
        ops.append(b"ET")
        stream = b"\n".join(ops)
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W:g} {PAGE_H:g}] "
            f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>".encode()
        ))
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    objects[pages_id - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    )
    info = add(b"<< /Title " + _pdf_string(str(title or "")[:200]) + b" /Producer (DocMaxxing) >>")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, catalog, info, xref,
    )
    return bytes(out)
