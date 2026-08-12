"""Post-process raw Gemini JSON into a trusted ExtractedRequirements.

Step order is fixed (see docs/prompts/requirements_extraction_prompt.md):
1. evidence quotes must appear in the brief
2. non-null fields without an evidence key are cleared
3. numeric ranges are checked
4. style strings are normalized (unknown → unsupported)
5. fully empty payloads collapse to ExtractedRequirements()
"""

from __future__ import annotations

import re
from typing import Any

from formatter_v2.spec import ExtractedRequirements, StyleName

# Value fields subject to evidence checks (not meta lists).
_VALUE_FIELDS: tuple[str, ...] = (
    "style",
    "document_type",
    "font_family",
    "font_size_pt",
    "line_spacing",
    "alignment",
    "first_line_indent",
    "margins_in",
    "page_size",
    "page_number_position",
    "word_count_min",
    "word_count_max",
    "deadline",
    "required_sections",
    "min_references",
    "max_references",
    "requires_cover_page",
    "requires_toc",
    "requires_abstract",
    "requires_appendices",
)

_INSTRUCTION_RE = re.compile(
    r"("
    r"ignore\s+(all\s+)?(previous\s+|above\s+|prior\s+)?instructions"
    r"|disregard\s+(the\s+)?(system|above|previous)"
    r"|you\s+are\s+now\s+"
    r"|system\s*prompt"
    r"|do\s+not\s+follow\s+(your\s+)?(rules|instructions)"
    r")",
    re.IGNORECASE,
)

_STYLE_ALIASES: dict[str, StyleName] = {
    "harvard": StyleName.HARVARD,
    "cite them right": StyleName.HARVARD,
    "harvard cite them right": StyleName.HARVARD,
    "apa": StyleName.APA7,
    "apa7": StyleName.APA7,
    "apa 7": StyleName.APA7,
    "apa7th": StyleName.APA7,
    "apa 7th": StyleName.APA7,
    "apa 7th edition": StyleName.APA7,
    "apa style": StyleName.APA7,
    "apa style 7th edition": StyleName.APA7,
    "mla": StyleName.MLA9,
    "mla9": StyleName.MLA9,
    "mla 9": StyleName.MLA9,
    "mla 9th": StyleName.MLA9,
    "mla 9th edition": StyleName.MLA9,
    "chicago": StyleName.CHICAGO17,
    "chicago17": StyleName.CHICAGO17,
    "chicago 17": StyleName.CHICAGO17,
    "chicago 17th": StyleName.CHICAGO17,
    "chicago manual of style": StyleName.CHICAGO17,
    "turabian": StyleName.CHICAGO17,
    "ieee": StyleName.IEEE,
}


def normalize_evidence_text(text: str) -> str:
    """Normalize a string for evidence↔brief comparison.

    Collapse whitespace, lowercase, curly quotes → straight,
    em/en dashes → hyphen.
    """
    if not text:
        return ""
    result = str(text)
    for src, dst in (
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u00ab", '"'),
        ("\u00bb", '"'),
        ("\u2014", "-"),
        ("\u2013", "-"),
        ("\u2212", "-"),
    ):
        result = result.replace(src, dst)
    result = result.casefold()
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _field_is_present(data: dict[str, Any], field: str) -> bool:
    value = data.get(field)
    if value is None:
        return False
    if field == "required_sections":
        return isinstance(value, list) and len(value) > 0
    if field == "margins_in":
        return isinstance(value, dict) and any(v is not None for v in value.values())
    return True


def _evidence_for_field(evidence: dict[str, str], field: str) -> str | None:
    if field in evidence and evidence[field]:
        return str(evidence[field])
    if field == "margins_in":
        for key in (
            "margins_in",
            "margins_top_in",
            "margins_bottom_in",
            "margins_left_in",
            "margins_right_in",
        ):
            if evidence.get(key):
                return str(evidence[key])
    if field in {"word_count_min", "word_count_max"}:
        for key in ("word_count_min", "word_count_max", "word_count"):
            if evidence.get(key):
                return str(evidence[key])
    return None


def _clear_field(data: dict[str, Any], field: str) -> None:
    if field == "required_sections":
        data[field] = []
    else:
        data[field] = None


def verify_evidence_quotes(data: dict[str, Any], brief_text: str) -> dict[str, Any]:
    """Step 1: drop fields whose evidence quote is missing from the brief."""
    out = dict(data)
    evidence = {
        str(k): str(v) for k, v in dict(out.get("evidence") or {}).items() if v is not None
    }
    warnings = list(out.get("warnings") or [])
    brief_norm = normalize_evidence_text(brief_text)

    for field in _VALUE_FIELDS:
        if not _field_is_present(out, field):
            continue
        quote = _evidence_for_field(evidence, field)
        if not quote:
            continue  # step 2 handles missing keys
        if _INSTRUCTION_RE.search(quote):
            _clear_field(out, field)
            warnings.append(
                f"Ignored instruction-like text in brief for field '{field}'."
            )
            continue
        quote_norm = normalize_evidence_text(quote)
        if not quote_norm or quote_norm not in brief_norm:
            _clear_field(out, field)
            warnings.append(
                f"Evidence for '{field}' was not found in the brief; field cleared."
            )

    out["evidence"] = evidence
    out["warnings"] = warnings
    return out


def clear_fields_without_evidence(data: dict[str, Any]) -> dict[str, Any]:
    """Step 2: non-null field without an evidence key is cleared. No exceptions."""
    out = dict(data)
    evidence = dict(out.get("evidence") or {})
    warnings = list(out.get("warnings") or [])

    for field in _VALUE_FIELDS:
        if not _field_is_present(out, field):
            continue
        quote = _evidence_for_field(evidence, field)
        if quote:
            continue
        _clear_field(out, field)
        warnings.append(f"Field '{field}' had no evidence key; cleared.")

    out["warnings"] = warnings
    return out


def validate_ranges(data: dict[str, Any]) -> dict[str, Any]:
    """Step 3: word/reference counts and physical bounds."""
    out = dict(data)
    warnings = list(out.get("warnings") or [])

    wmin = out.get("word_count_min")
    wmax = out.get("word_count_max")
    if wmin is not None and wmax is not None:
        try:
            if int(wmin) > int(wmax):
                out["word_count_min"] = None
                out["word_count_max"] = None
                warnings.append("word_count_min > word_count_max; both cleared.")
        except (TypeError, ValueError):
            out["word_count_min"] = None
            out["word_count_max"] = None
            warnings.append("Invalid word count values; both cleared.")

    rmin = out.get("min_references")
    rmax = out.get("max_references")
    if rmin is not None and rmax is not None:
        try:
            if int(rmin) > int(rmax):
                out["min_references"] = None
                out["max_references"] = None
                warnings.append("min_references > max_references; both cleared.")
        except (TypeError, ValueError):
            out["min_references"] = None
            out["max_references"] = None
            warnings.append("Invalid reference count values; both cleared.")

    margins = out.get("margins_in")
    if isinstance(margins, dict):
        bad = False
        cleaned: dict[str, float] = {}
        for key, value in margins.items():
            try:
                number = float(value)
            except (TypeError, ValueError):
                bad = True
                break
            if number < 0.0 or number > 3.0:
                bad = True
                break
            cleaned[key] = number
        if bad or not cleaned:
            out["margins_in"] = None
            if bad:
                warnings.append("Margin values out of range 0–3 in; margins cleared.")
        else:
            # Margins requires all four sides — fill from any known value.
            fill = next(iter(cleaned.values()))
            out["margins_in"] = {
                "top_in": cleaned.get("top_in", fill),
                "bottom_in": cleaned.get("bottom_in", fill),
                "left_in": cleaned.get("left_in", fill),
                "right_in": cleaned.get("right_in", fill),
            }

    size = out.get("font_size_pt")
    if size is not None:
        try:
            number = float(size)
            if number < 6.0 or number > 48.0:
                out["font_size_pt"] = None
                warnings.append("font_size_pt out of range 6–48; cleared.")
            else:
                out["font_size_pt"] = number
        except (TypeError, ValueError):
            out["font_size_pt"] = None
            warnings.append("Invalid font_size_pt; cleared.")

    spacing = out.get("line_spacing")
    if spacing is not None:
        try:
            number = float(spacing)
            if number < 1.0 or number > 3.0:
                out["line_spacing"] = None
                warnings.append("line_spacing out of range; cleared.")
            else:
                out["line_spacing"] = number
        except (TypeError, ValueError):
            out["line_spacing"] = None
            warnings.append("Invalid line_spacing; cleared.")

    out["warnings"] = warnings
    return out


def normalize_style(data: dict[str, Any]) -> dict[str, Any]:
    """Step 4: map style aliases; unknown names go to ``unsupported``."""
    out = dict(data)
    unsupported = list(out.get("unsupported") or [])
    raw = out.get("style")

    if raw is None or raw == "":
        out["style"] = None
        out["unsupported"] = unsupported
        return out

    if isinstance(raw, StyleName):
        out["style"] = raw
        out["unsupported"] = unsupported
        return out

    text = str(raw).strip()
    key = re.sub(r"\s+", " ", text).casefold()
    key = key.replace(".", "").replace(",", "")
    # Strip trailing "edition" noise already handled by aliases; also try compact.
    compact = key.replace(" ", "")
    mapped = _STYLE_ALIASES.get(key) or _STYLE_ALIASES.get(compact)

    if mapped is None:
        # Try soft contains for phrases like "use APA 7th edition referencing"
        for alias, style in _STYLE_ALIASES.items():
            if alias in key:
                mapped = style
                break

    if mapped is None:
        # Known enum value string?
        try:
            mapped = StyleName(text)
            if mapped == StyleName.CUSTOM:
                mapped = None
        except ValueError:
            mapped = None

    if mapped is None:
        label = text.strip()
        if label and label not in unsupported:
            unsupported.append(label)
        out["style"] = None
    else:
        out["style"] = mapped.value  # let pydantic coerce

    out["unsupported"] = unsupported
    return out


def ensure_not_vacuous(data: dict[str, Any]) -> ExtractedRequirements:
    """Step 5: build the model; collapse to empty if no real values remain."""
    payload = {
        k: v
        for k, v in data.items()
        if k in ExtractedRequirements.model_fields
    }
    # Drop keys that would fail enum coercion if left as junk — already cleaned.
    try:
        result = ExtractedRequirements.model_validate(payload)
    except Exception:
        # Last resort: keep warnings/unsupported only.
        result = ExtractedRequirements(
            unsupported=list(payload.get("unsupported") or []),
            warnings=list(payload.get("warnings") or [])
            + ["Post-process could not validate extraction; cleared values."],
        )

    if result.is_empty():
        # Preserve unsupported / warnings so the UI can still show notes,
        # but treat as empty prefill (is_empty ignores those fields).
        return ExtractedRequirements(
            unsupported=list(result.unsupported),
            warnings=list(result.warnings),
        )
    return result


def postprocess_extraction(data: dict[str, Any], brief_text: str) -> ExtractedRequirements:
    """Run the five mandatory post-process steps in order."""
    step1 = verify_evidence_quotes(data, brief_text)
    step2 = clear_fields_without_evidence(step1)
    step3 = validate_ranges(step2)
    step4 = normalize_style(step3)
    return ensure_not_vacuous(step4)
