"""
OCR for requirement images (JPEG/PNG) and scanned PDF pages via Tesseract.
Requires the `tesseract` binary on PATH (e.g. brew install tesseract).
"""

from __future__ import annotations

import io
from typing import BinaryIO

from PIL import Image

_PDF_TEXT_MIN_CHARS = 30
_PDF_MAX_PAGES = 25


def extract_text_from_image_stream(stream: BinaryIO) -> str:
    """Load an image from a binary stream and return UTF-8 text from OCR."""
    try:
        import pytesseract
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pytesseract is not installed.") from e

    try:
        img = Image.open(stream)
    except OSError as e:
        raise ValueError("Could not read image file. Use JPEG or PNG.") from e

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    try:
        raw = pytesseract.image_to_string(img)
    except pytesseract.TesseractNotFoundError as e:
        raise RuntimeError(
            "Tesseract OCR is not installed or not on PATH. "
            "Install it (e.g. macOS: brew install tesseract; "
            "Ubuntu: apt install tesseract-ocr) and restart the app."
        ) from e

    text = (raw or "").strip()
    return text


def _pypdf_extract_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError(
            "PDF support requires the pypdf package. Install dependencies from requirements.txt."
        ) from e
    reader = PdfReader(io.BytesIO(raw))
    pages: list[str] = []
    for page in reader.pages[:_PDF_MAX_PAGES]:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def _ocr_embedded_pdf_images(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    reader = PdfReader(io.BytesIO(raw))
    parts: list[str] = []
    for page in reader.pages[:_PDF_MAX_PAGES]:
        images = getattr(page, "images", None)
        if not images:
            continue
        for image in images:
            try:
                data = getattr(image, "data", None)
                if not data:
                    continue
                chunk = extract_text_from_image_stream(io.BytesIO(data)).strip()
                if chunk:
                    parts.append(chunk)
            except (ValueError, RuntimeError):
                continue
    return "\n\n".join(parts).strip()


def extract_text_from_pdf_bytes(raw: bytes) -> str:
    """
    Extract text from text-based PDFs; OCR embedded page images when text is sparse.
    """
    text = _pypdf_extract_text(raw)
    if len(text) >= _PDF_TEXT_MIN_CHARS:
        return text

    ocr_text = _ocr_embedded_pdf_images(raw)
    if len(ocr_text) >= _PDF_TEXT_MIN_CHARS:
        return ocr_text

    if text.strip():
        return text
    if ocr_text.strip():
        return ocr_text
    raise ValueError(
        "No readable text found in the PDF. Try a text-based PDF or a clearer scan."
    )
