"""DOCX → HTML keeps bold runs and tables."""

from __future__ import annotations

import io

from docx import Document
from docx.shared import Pt, RGBColor

from formatter.document_io import extract_html_from_docx_bytes, extract_text_from_docx_bytes


def _docx_bytes() -> bytes:
    doc = Document()
    p = doc.add_paragraph()
    run = p.add_run("Hello ")
    bold = p.add_run("world")
    bold.bold = True
    ital = p.add_run(" now")
    ital.italic = True
    colored = p.add_run("!")
    colored.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
    colored.font.size = Pt(14)
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "A"
    table.rows[0].cells[1].text = "B"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extract_html_keeps_bold_italic_color_and_table():
    raw = _docx_bytes()
    html = extract_html_from_docx_bytes(raw)
    assert "<b>world</b>" in html or "<b>" in html
    assert "<i>now</i>" in html or "<i>" in html
    assert "color: #CC0000" in html or "color: #cc0000" in html.lower()
    assert "<table>" in html and "A" in html and "B" in html
    plain = extract_text_from_docx_bytes(raw)
    assert "Hello" in plain and "world" in plain


def test_student_restores_list_marker_after_ordinal_rewrite():
    from services.humanizer_engine.student_humanizer import StudentTextHumanizer
    from tests.test_student_humanizer import PARA, _config, _rewrite

    item = (
        "1. Ministry of Employment and Poverty Reduction handles programmes across the country "
        "and coordinates decent working conditions for many people today."
    )

    def rewrite(text: str) -> str:
        if text.startswith("Ministry") or "Ministry" in text[:40]:
            assert not text.strip().startswith("1.")
            return "First, " + _rewrite(text)
        return _rewrite(text)

    out = StudentTextHumanizer(_config(chunk_words=1), complete_fn=rewrite).humanize(f"{PARA}\n\n{item}")
    assert "\n\n1. " in out or out.startswith("1.")
    after = out.split("1.", 1)[-1].lstrip()
    assert not after.lower().startswith("first")
