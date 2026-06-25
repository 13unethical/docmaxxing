"""
Flask entrypoint. All document logic lives under `formatter/` for clarity.
"""

from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

import io
import json
import os
from typing import Any

import requests
from docx import Document
from flask import Flask, jsonify, render_template, request, send_file

from formatter import FormatJob, format_document_full
from formatter.cover_page import CoverPageData, prepend_cover_page
from formatter.heading_plan import ParagraphHeadingAssignment
from formatter.preview_html import build_formatted_preview_html
from formatter.structure_rebuild import rebuild_document_from_recovery
from formatter.references_section import append_references_section
from formatter.document_io import (
    build_document_from_inputs,
    build_document_from_upload,
    document_has_visible_content,
    extract_text_from_document_bytes,
    is_supported_document_upload,
    upload_extension,
)
from services.reference_list_formatter import prepare_reference_section
from services.citation_engine import CITATION_STYLES as ENGINE_CITATION_STYLES
from services.citation_engine import generate_citation
from services.document_checker import MAX_TEXT_CHARS, check_document
from services.document_structure_engine import infer_assignment_title, paragraphs_from_text, recover_structure
from services.intext_citations import generate_intext
from services.requirements_ocr import extract_text_from_image_stream
from services.requirements_parser import form_autofill_from_parsed, parse_requirements

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB uploads

ALLOWED_FONTS = frozenset(
    {
        "Times New Roman",
        "Arial",
        "Calibri",
        "Cambria",
        "Georgia",
        "Verdana",
        "Tahoma",
    }
)
ALLOWED_FONT_SIZES = frozenset({10, 11, 12, 13, 14, 16, 18, 20})
LINE_SPACING_MAP = {"1.0": 1.0, "1.15": 1.15, "1.5": 1.5, "2.0": 2.0}
PAGE_POSITIONS = frozenset(
    {"none", "top_left", "top_right", "bottom_left", "bottom_right"}
)
MARGIN_PRESETS = frozenset({"normal", "narrow", "wide"})
ALIGNMENTS = frozenset({"left", "justify"})
CITATION_STYLES = frozenset({"APA", "MLA", "Harvard", "Chicago", "IEEE", "Vancouver"})
REQUIREMENTS_IMAGE_EXT = frozenset({".jpg", ".jpeg", ".png"})
REQUIREMENTS_TEXT_EXT = frozenset({".txt", ".md"})
REQUIREMENTS_DOC_EXT = frozenset({".docx", ".pdf"}) | REQUIREMENTS_TEXT_EXT | REQUIREMENTS_IMAGE_EXT

# Telegram Bot API: TELEGRAM_TOKEN + CHAT_ID (also accepts TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID).
TELEGRAM_SEND_MESSAGE_TIMEOUT_S = 12
TELEGRAM_TEXT_MAX_LEN = 4096


def _truthy(form: Any, key: str) -> bool:
    val = form.get(key, "off")
    if val is True:
        return True
    if val is False:
        return False
    return str(val).lower() in {"on", "true", "1", "yes"}


def _int_clamped(raw: str, default: int = 0, lo: int = 0, hi: int = 72) -> int:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def document_has_visible_text(doc: Document) -> bool:
    """Reject completely empty inputs with a friendly message."""
    return document_has_visible_content(doc)


def parse_job(form) -> FormatJob:
    """Validate form fields and return a FormatJob."""
    font = form.get("font_family", "Times New Roman")
    if font not in ALLOWED_FONTS:
        font = "Times New Roman"

    size = _int_clamped(str(form.get("font_size", "12")), 12, 8, 24)
    if size not in ALLOWED_FONT_SIZES:
        size = 12

    ls_key = form.get("line_spacing", "1.5")
    line_spacing = LINE_SPACING_MAP.get(ls_key, 1.5)

    alignment = form.get("alignment", "left")
    if alignment not in ALIGNMENTS:
        alignment = "left"

    page_pos = (form.get("page_number_position") or "none").lower()
    if page_pos not in PAGE_POSITIONS:
        page_pos = "none"

    margin = form.get("margin_preset", "normal")
    if margin not in MARGIN_PRESETS:
        margin = "normal"

    before_pt = _int_clamped(str(form.get("space_before_pt", "0")), 0, 0, 72)
    after_pt = _int_clamped(str(form.get("space_after_pt", "0")), 0, 0, 72)

    return FormatJob(
        font_family=font,
        font_size_pt=size,
        line_spacing=line_spacing,
        alignment=alignment,
        first_line_indent=_truthy(form, "first_line_indent"),
        space_before_pt=before_pt,
        space_after_pt=after_pt,
        margin_preset=margin,
        page_number_position=page_pos,
        auto_headings=_truthy(form, "auto_headings"),
        heading_all_caps=_truthy(form, "heading_all_caps"),
        auto_justify_refs=_truthy(form, "auto_justify_refs"),
    )


def parse_cover_page(form, *, fallback_paragraphs: list[str] | None = None) -> CoverPageData | None:
    """Build cover page data when the user enabled the title page toggle."""
    if not _truthy(form, "include_cover_page"):
        return None

    title = (form.get("cover_assignment_title") or "").strip()
    if not title and fallback_paragraphs:
        title = infer_assignment_title(fallback_paragraphs)

    cover = CoverPageData(
        assignment_title=title or "Assignment",
        student_name=(form.get("cover_student_name") or "").strip(),
        student_id=(form.get("cover_student_id") or "").strip(),
        university=(form.get("cover_university") or "").strip(),
        module=(form.get("cover_module") or "").strip(),
        lecturer=(form.get("cover_lecturer") or "").strip(),
        submission_date=(form.get("cover_submission_date") or "").strip(),
    )
    return cover


@app.route("/")
def index():
    return render_template("index.html", nav_active="home")


@app.route("/check")
def check():
    return render_template("check.html", nav_active="check")


@app.route("/templates")
def templates():
    return render_template("templates.html", nav_active="templates")


@app.route("/references")
def references():
    return render_template("references.html", nav_active="references")


def _feedback_from_request():
    """
    Parse JSON {\"message\": \"...\"}, send to Telegram if configured.
    Returns (flask Response, http_status).
    """
    try:
        raw = request.get_data(cache=True)
        payload = request.get_json(silent=True)
        if payload is None:
            if raw and request.is_json:
                return jsonify({"error": "Invalid JSON body."}), 400
            payload = {}
        if not isinstance(payload, dict):
            return jsonify({"error": "Body must be a JSON object."}), 400
        message = (payload.get("message") or "").strip()
        if not message:
            return jsonify({"error": "Message is required."}), 400

        token = (os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id = (os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
        if not token or not chat_id:
            app.logger.error("feedback: TELEGRAM_TOKEN and CHAT_ID are not both set")
            return (
                jsonify(
                    {
                        "error": "Telegram is not configured. Set TELEGRAM_TOKEN and CHAT_ID environment variables.",
                    }
                ),
                503,
            )

        if len(message) > TELEGRAM_TEXT_MAX_LEN:
            text = message[: TELEGRAM_TEXT_MAX_LEN - 1] + "…"
        else:
            text = message

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            tg_res = requests.post(
                url,
                json={"chat_id": chat_id, "text": text},
                timeout=TELEGRAM_SEND_MESSAGE_TIMEOUT_S,
            )
        except requests.Timeout:
            app.logger.warning("feedback: Telegram sendMessage timed out")
            return jsonify({"error": "Telegram did not respond in time."}), 502
        except requests.RequestException:
            app.logger.exception("feedback: Telegram request failed")
            return jsonify({"error": "Could not reach Telegram."}), 502

        try:
            tg_data = tg_res.json()
        except ValueError:
            app.logger.error("feedback: Telegram returned non-JSON (status %s)", tg_res.status_code)
            return jsonify({"error": "Unexpected response from Telegram."}), 502

        if not tg_res.ok or not tg_data.get("ok"):
            desc = tg_data.get("description") if isinstance(tg_data, dict) else None
            app.logger.warning(
                "feedback: Telegram API error %s — %s",
                tg_res.status_code,
                desc or (tg_res.text[:200] if tg_res.text else ""),
            )
            return jsonify({"error": "Could not deliver message."}), 502

        app.logger.info("feedback: delivered via Telegram")
        return jsonify({"success": True}), 200
    except Exception:  # noqa: BLE001
        app.logger.exception("feedback: unexpected error")
        return jsonify({"error": "Something went wrong processing feedback."}), 500


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """POST JSON {\"message\": \"...\"}; forwards to Telegram when env vars are set."""
    body, status = _feedback_from_request()
    return body, status


@app.post("/feedback")
def feedback():
    """Backward-compatible alias for POST /api/feedback."""
    return api_feedback()


@app.post("/parse-requirements")
def parse_requirements_view():
    """
    Extract formatting hints from free-form text (brief, OCR, etc.).
    Uses Gemini when GOOGLE_API_KEY is set; otherwise returns heuristic mock data.
    """
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Provide non-empty text in a JSON body: {\"text\": \"...\"}"}), 400

    using_local_parser = not (os.environ.get("GOOGLE_API_KEY") or "").strip()

    try:
        requirements = parse_requirements(text)
    except Exception as e:  # noqa: BLE001
        app.logger.exception("parse-requirements failed")
        return jsonify({"error": f"Could not parse requirements: {str(e)}"}), 502

    form = form_autofill_from_parsed(requirements)
    return jsonify({"requirements": requirements, "form": form, "mock": using_local_parser})


def _extract_requirement_text_from_upload(file_storage) -> str:
    """Extract text from supported assignment brief uploads."""
    filename = (file_storage.filename or "").lower()
    ext = os.path.splitext(filename)[1]
    if ext not in REQUIREMENTS_DOC_EXT:
        raise ValueError("Unsupported file type. Supported formats: PDF, DOCX, TXT, JPG, PNG.")

    raw = file_storage.read()
    if not raw:
        raise ValueError("The uploaded requirements file is empty.")

    if ext in REQUIREMENTS_TEXT_EXT:
        return raw.decode("utf-8", errors="replace")

    if ext == ".docx":
        return extract_text_from_document_bytes(raw, filename)

    if ext in REQUIREMENTS_IMAGE_EXT:
        return extract_text_from_image_stream(io.BytesIO(raw))

    if ext == ".pdf":
        return extract_text_from_document_bytes(raw, filename)

    raise ValueError("Unsupported requirements file.")


@app.post("/api/extract-brief-text")
def api_extract_brief_text():
    """
    Extract plain text from an uploaded assignment brief (.pdf, .docx, .txt, .jpg, .png).
    Multipart field name: file
    """
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": 'Upload a brief file as form field "file".'}), 400

    try:
        text = _extract_requirement_text_from_upload(f).strip()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        app.logger.warning("extract-brief-text: %s", e)
        return jsonify({"error": str(e)}), 503
    except Exception:  # noqa: BLE001
        app.logger.exception("extract-brief-text failed")
        return jsonify({"error": "Could not read the brief file."}), 400

    if len(text) > MAX_TEXT_CHARS:
        return jsonify({"error": f"Brief text is too long (max {MAX_TEXT_CHARS:,} characters)."}), 400

    return jsonify({"text": text, "filename": f.filename})


@app.post("/api/extract-requirements")
def api_extract_requirements():
    """
    Extract precise formatting requirements from pasted text and/or uploaded brief.
    Multipart: optional requirements_text, optional file (.docx, .pdf, .txt, .md, .jpg, .png)
    """
    pasted = (request.form.get("requirements_text") or "").strip()
    f = request.files.get("file")
    uploaded_text = ""

    if f and f.filename:
        try:
            uploaded_text = _extract_requirement_text_from_upload(f).strip()
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except RuntimeError as e:
            app.logger.warning("extract-requirements: %s", e)
            return jsonify({"error": str(e)}), 503
        except Exception:  # noqa: BLE001
            app.logger.exception("extract-requirements failed")
            return jsonify({"error": "Could not read the requirements file."}), 400

    text = "\n\n".join(x for x in (pasted, uploaded_text) if x).strip()
    if not text:
        return jsonify({"error": "Paste requirements or upload a supported brief."}), 400
    if len(text) > MAX_TEXT_CHARS:
        return jsonify({"error": f"Requirements text is too long (max {MAX_TEXT_CHARS:,} characters)."}), 400

    try:
        requirements = parse_requirements(text)
    except Exception as e:  # noqa: BLE001
        app.logger.exception("extract-requirements parse failed")
        return jsonify({"error": f"Could not parse requirements: {str(e)}"}), 502

    return jsonify(
        {
            "requirements": requirements,
            "form": form_autofill_from_parsed(requirements),
            "source_text": text,
            "source_text_chars": len(text),
            "mock": not (os.environ.get("GOOGLE_API_KEY") or "").strip(),
        }
    )


@app.post("/api/requirements-ocr")
def api_requirements_ocr():
    """
    OCR a JPEG/PNG and return extracted text for the requirements parser.
    Multipart field name: image
    """
    f = request.files.get("image")
    if not f or not f.filename:
        return jsonify({"error": 'Upload an image as form field "image" (JPEG or PNG).'}), 400

    name = (f.filename or "").lower()
    if not any(name.endswith(ext) for ext in REQUIREMENTS_IMAGE_EXT):
        return jsonify({"error": "Only JPEG and PNG images are supported."}), 400

    try:
        raw = f.read()
        if not raw:
            return jsonify({"error": "Empty file."}), 400
        text = extract_text_from_image_stream(io.BytesIO(raw))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        app.logger.warning("requirements-ocr: %s", e)
        return jsonify({"error": str(e)}), 503
    except Exception as e:  # noqa: BLE001
        app.logger.exception("requirements-ocr failed")
        return jsonify({"error": f"OCR failed: {str(e)}"}), 500

    if not text.strip():
        return (
            jsonify(
                {
                    "error": "No text could be read from the image. "
                    "Try a clearer photo or paste text manually."
                }
            ),
            422,
        )

    return jsonify({"text": text})


@app.post("/api/reference")
def api_reference():
    """
    Generate a reference citation.
    JSON: mode (url|doi|isbn|title|manual|paste), style, and mode-specific fields.
    Backward compatible: url and/or text without mode → url mode.
    """
    payload = request.get_json(silent=True) or {}
    mode = (payload.get("mode") or "").strip().lower()
    style = (payload.get("style") or "APA").strip()

    if not mode:
        if payload.get("doi"):
            mode = "doi"
        elif payload.get("isbn"):
            mode = "isbn"
        elif payload.get("title"):
            mode = "title"
        elif payload.get("manual"):
            mode = "manual"
        elif payload.get("paste") or payload.get("text"):
            mode = "paste" if payload.get("paste") else ("url" if payload.get("url") else "paste")
        elif payload.get("url"):
            mode = "url"
        else:
            return jsonify({"error": "Provide input fields or a mode (url, doi, isbn, title, manual, paste)."}), 400

    if style.upper() not in ENGINE_CITATION_STYLES:
        style = "APA"

    try:
        result = generate_citation(
            mode=mode,
            style=style,
            url=(payload.get("url") or "").strip() or None,
            doi=(payload.get("doi") or "").strip() or None,
            isbn=(payload.get("isbn") or "").strip() or None,
            title=(payload.get("title") or "").strip() or None,
            author=(payload.get("author") or "").strip() or None,
            manual=payload.get("manual") if isinstance(payload.get("manual"), dict) else None,
            paste=(payload.get("paste") or payload.get("text") or "").strip() or None,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except requests.RequestException as e:
        app.logger.exception("reference generation failed")
        return jsonify({"error": f"Could not retrieve metadata: {str(e)}"}), 502
    except Exception:  # noqa: BLE001
        app.logger.exception("reference generation failed")
        return jsonify({"error": "Could not generate citation."}), 500

    return jsonify(result)


@app.post("/api/intext-citation")
def api_intext_citation():
    """Generate in-text citations, footnotes, and endnotes."""
    payload = request.get_json(silent=True) or {}
    author = (payload.get("author") or "").strip()
    year = (payload.get("year") or "n.d.").strip()
    page = (payload.get("page") or "").strip() or None
    style = (payload.get("style") or "APA").strip()
    quote = bool(payload.get("direct_quote"))
    if not author:
        return jsonify({"error": "Author is required."}), 400
    return jsonify(generate_intext(author=author, year=year, page=page, style=style, quote=quote))


@app.post("/api/format-references")
def api_format_references():
    """
    Alphabetize a citation list and pick section title for APA / MLA / Harvard.
    Body: {\"citations\": [\"...\"], \"style\": \"APA\" | \"MLA\" | \"Harvard\"}
    """
    payload = request.get_json(silent=True) or {}
    cites = payload.get("citations")
    if not isinstance(cites, list):
        return jsonify({"error": "'citations' must be a JSON array of strings."}), 400
    style_raw = (payload.get("style") or "APA").strip()
    if style_raw.upper() not in CITATION_STYLES:
        style_raw = "APA"
    lines = [str(x) for x in cites if str(x).strip()]
    if not lines:
        return jsonify({"error": "Provide at least one non-empty citation string."}), 400
    heading, sorted_lines = prepare_reference_section(lines, style_raw)
    block = heading + "\n" + "\n".join(sorted_lines)
    return jsonify(
        {
            "section_title": heading,
            "citations": sorted_lines,
            "text": block,
        }
    )


@app.post("/api/extract-document")
def api_extract_document():
    """
    Extract plain text from an uploaded .docx or .pdf for the formatting workflow.
    Multipart field name: file
    """
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": 'Upload a .docx or .pdf file as form field "file".'}), 400
    if not is_supported_document_upload(f.filename, f.mimetype):
        return jsonify({"error": "Invalid file type. Upload a .docx or .pdf file."}), 400

    try:
        raw = f.read()
        text = extract_text_from_document_bytes(raw, f.filename, f.mimetype)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        app.logger.warning("extract-document: %s", e)
        return jsonify({"error": str(e)}), 503
    except Exception:  # noqa: BLE001
        app.logger.exception("extract-document failed")
        return jsonify({"error": "Could not read the uploaded file."}), 400

    if len(text) > MAX_TEXT_CHARS:
        return jsonify({"error": f"Document text is too long (max {MAX_TEXT_CHARS:,} characters)."}), 400

    return jsonify({"text": text, "filename": f.filename})


@app.post("/api/check-document")
def api_check_document():
    """
    Smart document check: requirements + text/docx/pdf → score, categories, issue cards.
    Multipart: requirements, pasted_text, document_type, optional file (.docx or .pdf).
    """
    requirements = (request.form.get("requirements") or "").strip()
    pasted = (request.form.get("pasted_text") or "").strip()
    doc_type = (request.form.get("document_type") or "other").strip()

    if len(requirements) > MAX_TEXT_CHARS:
        return jsonify({"error": f"Requirements text is too long (max {MAX_TEXT_CHARS:,} characters)."}), 400
    if len(pasted) > MAX_TEXT_CHARS:
        return jsonify({"error": f"Document text is too long (max {MAX_TEXT_CHARS:,} characters)."}), 400

    doc: Document | None = None
    f = request.files.get("file")

    if f and f.filename:
        if not is_supported_document_upload(f.filename, f.mimetype):
            return jsonify({"error": "Invalid file type. Upload a .docx or .pdf file."}), 400
        try:
            raw = f.read()
            if not raw:
                return jsonify({"error": "The uploaded file is empty."}), 400
            ext = upload_extension(f.filename, f.mimetype)
            if ext == ".docx":
                doc = Document(io.BytesIO(raw))
            doc_text = extract_text_from_document_bytes(raw, f.filename, f.mimetype)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except RuntimeError as e:
            app.logger.warning("check-document: %s", e)
            return jsonify({"error": str(e)}), 503
        except Exception:  # noqa: BLE001
            app.logger.exception("check-document: invalid upload")
            return jsonify({"error": "Could not read the uploaded file."}), 400
    else:
        doc_text = ""

    text = pasted
    if doc_text:
        if not text:
            text = doc_text
        elif text != doc_text:
            # Prefer uploaded file content when both are present.
            text = doc_text

    if not text:
        return jsonify(
            {"error": "Provide non-empty text or upload a .docx or .pdf with readable content."}
        ), 400

    try:
        result = check_document(
            text=text,
            requirements=requirements,
            doc=doc,
            document_type=doc_type,
        )
    except Exception:  # noqa: BLE001
        app.logger.exception("check-document failed")
        return jsonify({"error": "Document check failed. Please try again."}), 500

    if result.get("error"):
        return jsonify({"error": result["error"]}), 400

    return jsonify(result)


@app.post("/api/structure-recovery")
def api_structure_recovery():
    """
    Reconstruct academic document structure from pasted text or uploaded .docx / .pdf.
    Multipart: pasted_text, document_type (optional), optional file (.docx or .pdf).
    """
    pasted = (request.form.get("pasted_text") or "").strip()
    doc_type = (request.form.get("document_type") or "other").strip()

    if len(pasted) > MAX_TEXT_CHARS:
        return jsonify({"error": f"Document text is too long (max {MAX_TEXT_CHARS:,} characters)."}), 400

    doc: Document | None = None
    f = request.files.get("file")

    if f and f.filename:
        if not is_supported_document_upload(f.filename, f.mimetype):
            return jsonify({"error": "Invalid file type. Upload a .docx or .pdf file."}), 400
        try:
            raw = f.read()
            if not raw:
                return jsonify({"error": "The uploaded file is empty."}), 400
            ext = upload_extension(f.filename, f.mimetype)
            if ext == ".docx":
                doc = Document(io.BytesIO(raw))
            doc_text = extract_text_from_document_bytes(raw, f.filename, f.mimetype)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except RuntimeError as e:
            app.logger.warning("structure-recovery: %s", e)
            return jsonify({"error": str(e)}), 503
        except Exception:  # noqa: BLE001
            app.logger.exception("structure-recovery: invalid upload")
            return jsonify({"error": "Could not read the uploaded file."}), 400
    else:
        doc_text = ""

    text = pasted
    if doc_text:
        if not text:
            text = doc_text
        elif text != doc_text:
            text = doc_text

    if not text and doc is None:
        return jsonify(
            {"error": "Provide non-empty text or upload a .docx or .pdf with readable content."}
        ), 400

    try:
        result = recover_structure(text=text or None, doc=doc, document_type=doc_type)
    except Exception:  # noqa: BLE001
        app.logger.exception("structure-recovery failed")
        return jsonify({"error": "Structure recovery failed. Please try again."}), 500

    if result.get("error"):
        if result.get("ai_failure"):
            return jsonify(result), 503
        return jsonify({"error": result["error"]}), 400

    return jsonify(result)


@app.post("/api/preview-formatted")
def preview_formatted():
    """Server-side After preview — same formatting pipeline as /api/format."""
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text to preview."}), 400
    settings = payload.get("settings") or {}
    job = parse_job(settings)
    document_type = (payload.get("document_type") or settings.get("document_type") or "").strip() or None
    try:
        html = build_formatted_preview_html(text, job, document_type=document_type)
    except Exception as exc:
        app.logger.exception("preview-formatted failed")
        return jsonify({"error": str(exc)}), 500
    return jsonify({"html": html})


@app.post("/api/format")
def format_document():
    try:
        job = parse_job(request.form)

        file_storage = request.files.get("file")
        pasted_raw = request.form.get("pasted_text") or ""
        clean_spaces = _truthy(request.form, "clean_extra_spaces")
        clean_breaks = _truthy(request.form, "clean_extra_linebreaks")

        if file_storage and file_storage.filename:
            if not is_supported_document_upload(file_storage.filename, file_storage.mimetype):
                return (
                    jsonify(
                        {
                            "error": "Invalid file type. Upload a .docx or .pdf file.",
                        }
                    ),
                    400,
                )
            raw = file_storage.read()
            if not raw:
                return jsonify({"error": "The uploaded file is empty."}), 400
            try:
                doc = build_document_from_upload(
                    raw,
                    file_storage.filename,
                    mimetype=file_storage.mimetype,
                    cleaning_spaces=clean_spaces,
                    cleaning_breaks=clean_breaks,
                )
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
            except RuntimeError as e:
                app.logger.warning("format: %s", e)
                return jsonify({"error": str(e)}), 503
        elif pasted_raw.strip():
            doc = build_document_from_inputs(
                pasted_raw=pasted_raw,
                file_bytes=None,
                cleaning_spaces=clean_spaces,
                cleaning_breaks=clean_breaks,
            )
        else:
            return (
                jsonify(
                    {
                        "error": "Please upload a .docx or .pdf file, or paste some non-empty text.",
                    }
                ),
                400,
            )

        if not document_has_visible_text(doc):
            return (
                jsonify(
                    {
                        "error": "The document looks empty after loading. Add text and try again.",
                    }
                ),
                400,
            )

        fallback_paragraphs = [p.text.strip() for p in doc.paragraphs if (p.text or "").strip()]
        if not fallback_paragraphs and pasted_raw.strip():
            fallback_paragraphs = paragraphs_from_text(pasted_raw)

        paragraph_assignments: list[ParagraphHeadingAssignment] | None = None
        recovery: dict[str, Any] | None = None
        apply_result = None
        if job.auto_headings:
            doc_type = (request.form.get("document_type") or "other").strip() or None
            recovery = recover_structure(doc=doc, document_type=doc_type)
            if not recovery.get("error") and recovery.get("recovery_mode") == "ai_reconstructed":
                apply_result = rebuild_document_from_recovery(doc, recovery)
                if apply_result:
                    paragraph_assignments = apply_result.assignments

        before_cover_paragraph_count = len(doc.paragraphs)
        cover = parse_cover_page(request.form, fallback_paragraphs=fallback_paragraphs)
        if cover:
            prepend_cover_page(doc, cover, font_family=job.font_family)
            if paragraph_assignments:
                inserted = len(doc.paragraphs) - before_cover_paragraph_count
                if inserted > 0:
                    paragraph_assignments = (
                        [ParagraphHeadingAssignment()] * inserted + paragraph_assignments
                    )

        structure_debug = (
            os.environ.get("STRUCTURE_RECOVERY_DEBUG", "").strip().lower() in {"1", "true", "yes"}
            or _truthy(request.form, "structure_recovery_debug")
        )
        debug_report = format_document_full(
            doc,
            job,
            paragraph_assignments,
            structure_debug=structure_debug,
            recovery_mode=str((recovery or {}).get("recovery_mode") or ""),
            ai_powered=bool((recovery or {}).get("ai_powered")),
        )

        ref_lines = [r.strip() for r in request.form.getlist("references") if r.strip()]
        if ref_lines:
            style = (request.form.get("citation_style") or "APA").strip()
            if style.upper() not in CITATION_STYLES:
                style = "APA"
            section_heading, sorted_refs = prepare_reference_section(ref_lines, style)
            append_references_section(doc, job, sorted_refs, section_title=section_heading)

        out = io.BytesIO()
        doc.save(out)
        out.seek(0)

        response = send_file(
            out,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name="formatted_document.docx",
        )
        if debug_report:
            response.headers["X-Structure-Recovery-Debug"] = json.dumps(debug_report.to_dict())
        return response
    except Exception as e:  # noqa: BLE001
        app.logger.exception("Format failed")
        return jsonify({"error": f"Could not format document: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5001, use_reloader=False)
