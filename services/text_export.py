"""Plain text -> .docx / .pdf downloads (humanizer results).

Humanizer output is plain text, but models (and pastes) often wrap headings in ``**bold**``
or ``##`` markdown. ``text_to_docx`` turns those into real Word bold/heading runs so
downloads are not littered with asterisks.
"""

from __future__ import annotations

import html
import re

from services.editor_export import html_to_docx

MAX_TEXT_CHARS = 200_000
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_MD_BOLD_LINE = re.compile(r"^(\*\*|__)(.+?)\1$")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_MD_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")

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


def _inline_markdown_html(text: str) -> str:
    """Escape plain text, then turn **bold** / *italic* into HTML tags for html_to_docx."""
    parts: list[str] = []
    i = 0
    # Walk with bold first, then italic on the leftover plain segments.
    for m in _MD_BOLD.finditer(text):
        parts.append(html.escape(text[i:m.start()]))
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        parts.append("<strong>" + html.escape(inner) + "</strong>")
        i = m.end()
    parts.append(html.escape(text[i:]))
    with_bold = "".join(parts)

    def _ital(m: re.Match[str]) -> str:
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        return "<em>" + inner + "</em>"

    # Italic pattern runs on already-escaped text; only match * / _ around escaped content.
    return _MD_ITALIC.sub(_ital, with_bold)


def paragraph_to_html(paragraph: str) -> str:
    """One blank-line block -> HTML paragraph or heading (markdown headings / whole-line bold)."""
    lines = paragraph.split("\n")
    if len(lines) == 1:
        stripped = lines[0].strip()
        md = _MD_HEADING.match(stripped)
        if md:
            level = min(3, len(md.group(1)))
            return f"<h{level}>{_inline_markdown_html(md.group(2))}</h{level}>"
        bold_line = _MD_BOLD_LINE.match(stripped)
        if bold_line and len(bold_line.group(2).split()) <= 12:
            # Whole-line **Stakeholder Identification** → real bold heading-like paragraph.
            return f"<p><strong>{html.escape(bold_line.group(2))}</strong></p>"
    return "<p>" + "<br>".join(_inline_markdown_html(line) for line in lines) + "</p>"


def text_to_docx(title: str, text: str) -> bytes:
    _check(text)
    body = "".join(paragraph_to_html(p) for p in paragraphs(text))
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
