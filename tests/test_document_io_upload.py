"""Upload sniffing: legacy .doc must not be treated as .docx."""

from __future__ import annotations

import io
import pytest
from docx import Document

from formatter.document_io import (
    build_document_from_upload,
    is_supported_document_upload,
    upload_extension,
)


def test_msword_mime_is_not_docx():
    assert upload_extension("essay.doc", "application/msword") == ".doc"
    assert is_supported_document_upload("essay.doc", "application/msword") is False


def test_wordprocessingml_still_docx():
    assert (
        upload_extension(
            "essay",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        == ".docx"
    )


def test_ole_bytes_rejected_as_docx():
    # OLE Compound File magic (legacy .doc), not ZIP.
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64
    with pytest.raises(ValueError, match="not a valid .docx"):
        build_document_from_upload(ole, "paper.docx", cleaning_spaces=False, cleaning_breaks=False)


def test_valid_docx_still_loads():
    buf = io.BytesIO()
    Document().save(buf)
    doc = build_document_from_upload(
        buf.getvalue(), "ok.docx", cleaning_spaces=False, cleaning_breaks=False
    )
    assert doc is not None
