import io

import pytest
from docx import Document
from pypdf import PdfReader

from app import app
from services.text_export import TextExportError, paragraphs, text_to_docx, text_to_pdf

ESSAY = "Intro line\n\n" + "A humanized sentence with “quotes” — and (parens). " * 80 + "\n\nLast part\nwith a line break."


def test_paragraphs_split_on_blank_lines_and_keep_line_breaks():
    assert paragraphs("One\r\n\r\nTwo\nstill two\n\n\n") == ["One", "Two\nstill two"]


def test_pdf_has_all_text_wrapped_over_pages():
    reader = PdfReader(io.BytesIO(text_to_pdf("My essay-humanized", ESSAY)))
    assert len(reader.pages) >= 2
    text = " ".join(p.extract_text() for p in reader.pages)
    assert "Intro line" in text and "“quotes” — and (parens)" in text and "with a line break." in text
    assert reader.metadata.title == "My essay-humanized"


def test_docx_keeps_paragraphs():
    doc = Document(io.BytesIO(text_to_docx("Essay", ESSAY)))
    texts = [p.text for p in doc.paragraphs]
    assert texts[0] == "Intro line"
    assert texts[-1] == "Last part\nwith a line break."


def test_docx_turns_markdown_bold_headings_into_real_bold():
    text = "**2. Stakeholder Identification**\n\nBody with **important** word and plain end."
    doc = Document(io.BytesIO(text_to_docx("Essay", text)))
    assert [p.text for p in doc.paragraphs] == [
        "2. Stakeholder Identification",
        "Body with important word and plain end.",
    ]
    heading_runs = list(doc.paragraphs[0].runs)
    assert heading_runs and all(r.bold for r in heading_runs if r.text.strip())
    body_runs = doc.paragraphs[1].runs
    bold_bits = [r.text for r in body_runs if r.bold]
    assert bold_bits == ["important"]
    assert "**" not in "".join(p.text for p in doc.paragraphs)


def test_docx_turns_hash_markdown_headings_into_heading_style():
    doc = Document(io.BytesIO(text_to_docx("Essay", "## Power Analysis\n\nStakeholders exert power.")))
    assert doc.paragraphs[0].text == "Power Analysis"
    assert "Heading" in (doc.paragraphs[0].style.name or "")


@pytest.mark.parametrize("fn", [text_to_pdf, text_to_docx])
def test_empty_text_is_rejected(fn):
    with pytest.raises(TextExportError):
        fn("x", "   ")


def test_export_endpoint_works_without_an_account():
    client = app.test_client()
    res = client.post("/api/text/export", json={"text": ESSAY, "title": "My essay-humanized", "format": "pdf"})
    assert res.status_code == 200
    assert res.mimetype == "application/pdf"
    assert res.data.startswith(b"%PDF-")
    assert 'filename="My essay-humanized.pdf"' in res.headers["Content-Disposition"]

    res = client.post("/api/text/export", json={"text": ESSAY, "title": "x", "format": "docx"})
    assert res.status_code == 200 and res.data[:2] == b"PK"

    res = client.post("/api/text/export", json={"text": ESSAY, "format": "exe"})
    assert res.status_code == 400 and res.get_json()["error"] == "FORMAT_INVALID"
