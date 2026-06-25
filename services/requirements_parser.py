"""
Extract formatting requirements from free-form text.

Uses Gemini when GOOGLE_API_KEY is set; otherwise returns deterministic
data derived from strict keyword heuristics.
Optional: GEMINI_MODEL (default gemini-2.5-flash).
"""

from __future__ import annotations

import re
from typing import Any

from services.gemini_client import generate_json

# Must stay in sync with the formatter UI / app.py validation
ALLOWED_FONTS = (
    "Times New Roman",
    "Arial",
    "Calibri",
    "Cambria",
    "Georgia",
    "Verdana",
    "Tahoma",
)
ALLOWED_FONT_SIZES = (10, 11, 12, 13, 14, 16, 18, 20)
LINE_SPACING_CHOICES = (1.0, 1.15, 1.5, 2.0)

STYLE_NAMES = ("APA", "MLA", "Harvard", "Chicago", "IEEE", "Vancouver", "OSCOLA")
IGNORE_SECTION_HEADINGS = re.compile(
    r"^\s*(learning outcomes?|assessment criteria|marking rubric|rubric|"
    r"academic integrity|plagiarism|university regulations?|late submission|"
    r"feedback criteria|grading criteria)\s*:?\s*$",
    re.I,
)
FORMAT_SIGNAL = re.compile(
    r"\b(font|typeface|pt|point|size|spacing|spaced|margin|word count|words?|"
    r"reference(?:s| list)?|bibliograph|works cited|citation|cite|apa|mla|"
    r"harvard|chicago|ieee|vancouver|oscola|cover page|title page|page number|"
    r"section|heading|submit|submission|format|pdf|docx|word document)\b",
    re.I,
)


def _relevant_lines(text: str) -> list[str]:
    """Keep lines likely to contain formatting instructions; drop rubric/policy blocks."""
    lines: list[str] = []
    skip_block = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            skip_block = False
            continue
        if IGNORE_SECTION_HEADINGS.match(line):
            skip_block = True
            continue
        if skip_block:
            if FORMAT_SIGNAL.search(line):
                skip_block = False
            elif re.match(r"^[A-Z][A-Za-z /&-]{2,60}:?\s*$", line):
                skip_block = False
            else:
                continue
        if FORMAT_SIGNAL.search(line):
            lines.append(line)
    return lines


def _strict_requirements_from_text(text: str) -> dict[str, Any]:
    """
    Lightweight precision-first keyword pass.
    It intentionally leaves fields null unless formatting wording is explicit.
    """
    relevant = "\n".join(_relevant_lines(text))
    low = relevant.lower()
    raw: dict[str, Any] = {k: None for k in _payload_keys()}
    raw["required_sections"] = []

    if not low:
        raw["confidence_score"] = 0.0
        return raw

    if re.search(r"\bdouble[-\s]?spaced?\b|\bdouble\s+line\s+spacing\b", low):
        raw["spacing"] = 2.0
    elif re.search(r"\bsingle[-\s]?spaced?\b|\bsingle\s+line\s+spacing\b", low):
        raw["spacing"] = 1.0
    elif re.search(r"\b1\.15\b.*\b(spacing|spaced)\b|\b(spacing|spaced)\b.*\b1\.15\b", low):
        raw["spacing"] = 1.15
    elif re.search(r"\b1\.5\b.*\b(spacing|spaced)\b|\b(spacing|spaced)\b.*\b1\.5\b", low):
        raw["spacing"] = 1.5

    for style in STYLE_NAMES:
        if re.search(rf"\b{re.escape(style.lower())}\b", low):
            raw["citation_style"] = style
            break

    if re.search(r"\btimes new roman\b", low):
        raw["font_family"] = "Times New Roman"
    elif re.search(r"\barial\b", low):
        raw["font_family"] = "Arial"
    elif re.search(r"\bcalibri\b", low):
        raw["font_family"] = "Calibri"
    elif re.search(r"\bcambria\b", low):
        raw["font_family"] = "Cambria"
    elif re.search(r"\bgeorgia\b", low):
        raw["font_family"] = "Georgia"
    elif re.search(r"\bverdana\b", low):
        raw["font_family"] = "Verdana"
    elif re.search(r"\btahoma\b", low):
        raw["font_family"] = "Tahoma"

    size_match = re.search(r"\b(10|11|12|13|14|16|18|20)\s*(?:pt|point(?:s)?)\b", low)
    if not size_match:
        size_match = re.search(r"\bfont\s+size\s*:?\s*(10|11|12|13|14|16|18|20)\b", low)
    if size_match:
        raw["font_size"] = int(size_match.group(1))

    if re.search(r"\bjustif(?:y|ied)\b", low):
        raw["alignment"] = "justify"
    elif re.search(r"\bleft[-\s]?align(?:ed)?\b|\bflush left\b", low):
        raw["alignment"] = "left"

    if re.search(r"\bmargin", low) and re.search(r"\b0\.5\s*(?:inch|in|\"|cm)?\b|\bhalf[-\s]?inch\b|\b1\.27\s*cm\b", low):
        raw["margins"] = "0.5 inch (narrow)"
    elif re.search(r"\bmargin", low) and re.search(r"\b1\.5\s*(?:inch|in|\")\b|\b3\.81\s*cm\b", low):
        raw["margins"] = "1.5 inch (wide)"
    elif re.search(r"\bmargin", low) and re.search(r"\b1\s*(?:inch|in|\")\b|\b2\.54\s*cm\b|\bnormal margins?\b", low):
        raw["margins"] = "1 inch all sides"

    raw["word_count"] = _extract_word_count(relevant)
    raw["required_sections"] = _extract_required_sections(relevant)

    if re.search(r"\b(no|without)\s+(?:cover|title)\s+page\b", low):
        raw["cover_page_required"] = False
    elif re.search(r"\b(?:cover|title)\s+page\s+(?:is\s+)?(?:required|must|needed)|\binclude\s+(?:a\s+)?(?:cover|title)\s+page\b", low):
        raw["cover_page_required"] = True

    if re.search(r"\b(no|without)\s+page\s+numbers?\b|\bpage\s+numbers?\s+(?:are\s+)?not\s+required\b", low):
        raw["page_numbers_required"] = False
    elif re.search(r"\bpage\s+numbers?\s+(?:are\s+)?(?:required|must|needed)|\binclude\s+page\s+numbers?\b|\bnumber(?:ed)?\s+pages\b|\bpaginate\b", low) or (
        re.search(r"\bpage\s+numbers?\b", low) and re.search(r"\binclude|required|must\b", low)
    ):
        raw["page_numbers_required"] = True

    if re.search(r"\b(no|without)\s+(?:reference list|references|bibliography|works cited)\b", low):
        raw["references_required"] = False
    elif re.search(r"\b(?:reference list|references section|bibliography|works cited)\s+(?:is\s+)?(?:required|must|needed)|\binclude\s+(?:a\s+)?(?:reference list|references|bibliography|works cited)\b", low):
        raw["references_required"] = True
    elif raw["citation_style"]:
        raw["references_required"] = True

    raw["submission_format"] = _extract_submission_format(relevant)
    raw["line_spacing"] = raw["spacing"]
    raw["page_numbers"] = raw["page_numbers_required"]
    raw["headings"] = bool(raw["required_sections"]) if raw["required_sections"] else None
    raw["confidence_score"] = _confidence_score(raw)
    return raw


def parse_requirements(text: str) -> dict[str, Any]:
    """
    Extract structured requirements from user text via OpenAI, or mock data if no API key.

    Returns a dict with keys: font_family, font_size, line_spacing, citation_style,
    margins, alignment, headings, page_numbers (values may be None).
    """
    # System prompt: instructs the model to emit a single JSON object with fixed keys.
    system_prompt = """You are an assistant that extracts only academic document formatting and submission requirements from raw assignment briefs, OCR, emails, rubrics, or assessment guides.

Return ONE JSON object only, no markdown. Use these keys exactly:
- citation_style: string or null — one of: "APA", "MLA", "Harvard", "Chicago", "IEEE", "Vancouver", "OSCOLA", or another named style if explicitly given
- font_family: string or null — a common font name if stated or clearly implied, else null
- font_size: integer or null — point size (e.g. 12), else null
- spacing: number or string or null — use 2.0 for "double spaced", 1.5 for 1.5, 1.15 for 1.15, 1.0 for single; null if not stated
- margins: string or null — short description (e.g. "1 inch all sides", "2.54 cm", "normal"); null if not stated
- word_count: string or null — exact word count/range/limit only if explicitly stated
- required_sections: array of strings — document sections explicitly required for the submitted document, not rubric criteria
- cover_page_required: boolean or null — true/false only if explicitly stated
- page_numbers_required: boolean or null — true/false only if explicitly stated
- references_required: boolean or null — true/false only if explicitly stated
- submission_format: string or null — file/output format only if explicitly stated, such as PDF or DOCX
- confidence_score: number — 0 to 1 for confidence in extracted formatting requirements

You may also include these backwards-compatible keys when explicitly stated: line_spacing, alignment, headings, page_numbers.

Rules:
- Prioritize precision over recall. Leave fields null/empty if unsure.
- Do not guess numbers or styles that are not stated or strongly implied by context.
- Ignore learning outcomes, assessment criteria, marking rubrics, academic integrity policies, plagiarism warnings, university regulations, and general academic advice.
- Do not treat rubric headings like "knowledge", "analysis", "argument", or grade-band descriptors as required document sections.
- Phrases like "double-spacing", "double spaced", "double-spaced" → spacing 2.0
- "Times New Roman, 12 pt" → font_family "Times New Roman", font_size 12
- If only a citation style is named, set citation_style and references_required true only when references/citations are requested.
- Output valid JSON only."""

    user_content = (
        "Extract formatting requirements from the following text. "
        "Respond with the JSON object only.\n\n---\n"
        f"{text.strip()}\n---"
    )

    data, diag = generate_json(
        system_prompt=system_prompt,
        user_prompt=user_content,
        temperature=0.2,
    )
    if not data:
        payload = _normalize_requirements_payload(_strict_requirements_from_text(text))
        payload["gemini_diagnostics"] = diag
        payload["ai_provider"] = "local"
        return payload

    payload = _normalize_requirements_payload(data)
    payload["gemini_diagnostics"] = diag
    payload["ai_provider"] = "gemini"
    return payload


def _payload_keys() -> tuple[str, ...]:
    return (
        "citation_style",
        "font_family",
        "font_size",
        "spacing",
        "line_spacing",
        "margins",
        "word_count",
        "required_sections",
        "cover_page_required",
        "page_numbers_required",
        "references_required",
        "submission_format",
        "confidence_score",
        "alignment",
        "headings",
        "page_numbers",
    )


def _normalize_requirements_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure all expected keys exist and coerce types so the API surface is stable."""
    keys = _payload_keys()
    out: dict[str, Any] = {k: None for k in keys}
    out["required_sections"] = []
    for k in keys:
        if k not in data:
            continue
        v = data[k]
        if v == "" or v == "null":
            out[k] = None
            continue
        if k == "font_family" and isinstance(v, str):
            out[k] = v.strip() or None
        elif k == "font_size":
            out[k] = _coerce_int_or_none(v)
        elif k in ("spacing", "line_spacing"):
            out[k] = _coerce_float_or_none(v)
        elif k == "citation_style" and isinstance(v, str):
            s = v.strip()
            out[k] = s or None
        elif k in ("margins", "word_count", "submission_format") and isinstance(v, str):
            out[k] = v.strip() or None
        elif k == "required_sections":
            out[k] = _coerce_string_list(v)
        elif k == "alignment" and isinstance(v, str):
            out[k] = _normalize_alignment_string(v)
        elif k in ("cover_page_required", "page_numbers_required", "references_required", "headings", "page_numbers"):
            out[k] = _coerce_bool_or_none(v)
        elif k == "confidence_score":
            out[k] = _coerce_confidence(v)
        else:
            out[k] = v
    if out["spacing"] is None and out["line_spacing"] is not None:
        out["spacing"] = out["line_spacing"]
    if out["line_spacing"] is None and out["spacing"] is not None:
        out["line_spacing"] = out["spacing"]
    if out["page_numbers_required"] is None and out["page_numbers"] is not None:
        out["page_numbers_required"] = out["page_numbers"]
    if out["page_numbers"] is None and out["page_numbers_required"] is not None:
        out["page_numbers"] = out["page_numbers_required"]
    if out["headings"] is None and out["required_sections"]:
        out["headings"] = True
    if out["confidence_score"] is None:
        out["confidence_score"] = _confidence_score(out)
    return out


def _extract_word_count(text: str) -> str | None:
    patterns = (
        r"\b(?:between|from)\s+(\d{2,5})\s+(?:and|to|-)\s+(\d{2,5})\s*words?\b",
        r"\b(\d{2,5})\s*[-–]\s*(\d{2,5})\s*words?\b",
        r"\b(?:max(?:imum)?|no more than|up to|at most)\s+(\d{2,5})\s*words?\b",
        r"\b(?:min(?:imum)?|at least|no fewer than)\s+(\d{2,5})\s*words?\b",
        r"\b(?:word count|length)\s*:?\s*(?:approximately|around|about)?\s*(\d{2,5})\s*words?\b",
        r"\b(\d{2,5})\s*words?\s*(?:maximum|max|minimum|min|limit|required)?\b",
    )
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        groups = [g for g in m.groups() if g]
        if len(groups) == 2:
            return f"{groups[0]}-{groups[1]} words"
        prefix = m.group(0).lower()
        if "max" in prefix or "no more" in prefix or "up to" in prefix or "at most" in prefix:
            return f"maximum {groups[0]} words"
        if "min" in prefix or "at least" in prefix or "no fewer" in prefix:
            return f"minimum {groups[0]} words"
        return f"{groups[0]} words"
    return None


def _extract_required_sections(text: str) -> list[str]:
    found: list[str] = []
    known = (
        "abstract",
        "introduction",
        "literature review",
        "methodology",
        "methods",
        "results",
        "discussion",
        "conclusion",
        "recommendations",
        "appendix",
        "appendices",
        "executive summary",
    )
    low = text.lower()
    if re.search(r"\b(required sections?|include sections?|must include)\b", low):
        for section in known:
            if re.search(rf"\b{re.escape(section)}\b", low):
                found.append(section.title())
    for m in re.finditer(r"\b(?:section headings?|headings?)\s*:?\s*([A-Za-z,;/ &-]{8,160})", text, re.I):
        chunk = re.split(r"\.|\n", m.group(1))[0]
        for part in re.split(r",|;|/|\band\b", chunk):
            label = part.strip(" -:")
            if 2 <= len(label.split()) <= 4 and not IGNORE_SECTION_HEADINGS.match(label):
                found.append(label.title())
    deduped: list[str] = []
    for item in found:
        if item and item.lower() not in {x.lower() for x in deduped}:
            deduped.append(item)
    return deduped[:12]


def _extract_submission_format(text: str) -> str | None:
    low = text.lower()
    formats: list[str] = []
    if re.search(r"\bpdf\b", low):
        formats.append("PDF")
    if re.search(r"\bdocx\b|\bword document\b|\bmicrosoft word\b", low):
        formats.append("DOCX")
    if formats and re.search(r"\bsubmit|submission|upload|file format|format\b", low):
        return " or ".join(formats)
    return None


def _coerce_string_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()][:20]
    if isinstance(v, str):
        return [x.strip() for x in re.split(r",|;|\n", v) if x.strip()][:20]
    return []


def _coerce_confidence(v: Any) -> float | None:
    f = _coerce_float_or_none(v)
    if f is None:
        return None
    if f > 1:
        f = f / 100.0
    return round(max(0.0, min(1.0, f)), 2)


def _confidence_score(data: dict[str, Any]) -> float:
    fields = (
        "citation_style",
        "font_family",
        "font_size",
        "spacing",
        "margins",
        "word_count",
        "cover_page_required",
        "page_numbers_required",
        "references_required",
        "submission_format",
    )
    hits = sum(1 for k in fields if data.get(k) not in (None, "", []))
    if data.get("required_sections"):
        hits += 1
    if hits == 0:
        return 0.0
    return round(min(0.95, 0.35 + hits * 0.08), 2)


def _coerce_int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(round(v))
    if isinstance(v, str):
        m = re.search(r"-?\d+", v)
        if m:
            return int(m.group(0))
    return None


def _coerce_float_or_none(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"-?\d+(\.\d+)?", v.replace(",", "."))
        if m:
            return float(m.group(0))
    return None


def _coerce_bool_or_none(v: Any) -> bool | None:
    if v is None or v == "null":
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        low = v.strip().lower()
        if low in ("true", "yes", "required", "1"):
            return True
        if low in ("false", "no", "0", "not required"):
            return False
    return None


def _normalize_alignment_string(v: str) -> str | None:
    low = v.strip().lower()
    mapping = {
        "left": "left",
        "left-aligned": "left",
        "justify": "justify",
        "justified": "justify",
        "full": "justify",
        "full justify": "justify",
        "right": "right",
        "center": "center",
        "centre": "center",
    }
    return mapping.get(low, low if low in ("left", "justify", "right", "center") else None)


def _nearest_allowed_font(name: str | None) -> str | None:
    if not name:
        return None
    n = name.strip().lower()
    for f in ALLOWED_FONTS:
        if f.lower() == n:
            return f
    for f in ALLOWED_FONTS:
        if n in f.lower() or f.lower().split()[0] in n:
            return f
    return None


def _nearest_font_size(size: int | None) -> int | None:
    if size is None:
        return None
    return min(ALLOWED_FONT_SIZES, key=lambda s: abs(s - size))


def _nearest_line_spacing(value: float | None) -> float | None:
    if value is None:
        return None
    return min(LINE_SPACING_CHOICES, key=lambda s: abs(s - value))


def margins_to_preset(margins: str | None) -> str | None:
    """
    Map free-text margins to margin_preset: normal | narrow | wide, or None.
    """
    if not margins:
        return None
    low = margins.lower()
    if any(x in low for x in ("narrow", "0.5", "half inch", "half-inch", "1.27")):
        return "narrow"
    if any(x in low for x in ("wide", "1.5", "1.5 inch", "1.5-inch", "38.1")):
        return "wide"
    if any(
        x in low
        for x in (
            "1 inch",
            "1-inch",
            "1in",
            "2.54",
            "normal",
            "default",
            "standard",
        )
    ):
        return "normal"
    if re.search(r"\b1\b", low) and "margin" in low:
        return "normal"
    return None


def alignment_to_form(alignment: str | None) -> str | None:
    """UI only supports left | justify."""
    if alignment is None:
        return None
    if alignment == "justify":
        return "justify"
    if alignment == "left":
        return "left"
    # center / right → default to left for this formatter
    if alignment in ("center", "right"):
        return "left"
    return None


def page_numbers_to_position(page_numbers: bool | None) -> str | None:
    """If boolean known, map to our page_number_position select."""
    if page_numbers is True:
        return "top_right"
    if page_numbers is False:
        return "none"
    return None


def form_autofill_from_parsed(parsed: dict[str, Any]) -> dict[str, Any]:
    """
    Map parsed requirements to frontend / Format form field names.
    Only includes keys where we have a value to apply (omit unknowns).
    """
    form: dict[str, Any] = {}

    font = _nearest_allowed_font(parsed.get("font_family") if isinstance(parsed.get("font_family"), str) else None)
    if font:
        form["font_family"] = font

    raw_size = _coerce_int_or_none(parsed.get("font_size"))
    if raw_size is not None:
        form["font_size"] = str(_nearest_font_size(raw_size))

    raw_ls = _coerce_float_or_none(parsed.get("line_spacing"))
    nearest_ls = _nearest_line_spacing(raw_ls)
    if nearest_ls is not None:
        form["line_spacing"] = {
            1.0: "1.0",
            1.15: "1.15",
            1.5: "1.5",
            2.0: "2.0",
        }[nearest_ls]

    preset = margins_to_preset(parsed.get("margins") if isinstance(parsed.get("margins"), str) else None)
    if preset:
        form["margin_preset"] = preset

    align = alignment_to_form(
        parsed.get("alignment") if isinstance(parsed.get("alignment"), str) else None
    )
    if align:
        form["alignment"] = align

    pos = page_numbers_to_position(parsed.get("page_numbers"))
    if pos is not None:
        form["page_number_position"] = pos

    headings = parsed.get("headings")
    if isinstance(headings, bool):
        form["auto_headings"] = headings

    if parsed.get("cover_page_required") is True:
        form["include_cover_page"] = True
    elif parsed.get("cover_page_required") is False:
        form["include_cover_page"] = False

    return form
