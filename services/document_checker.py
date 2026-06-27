"""
Heuristic academic document checker: requirements + text → score, categories, issue cards.

Local-only analysis — no paid APIs. Does not rewrite content.
"""

from __future__ import annotations

import re
from typing import Any

from docx import Document

from formatter.headings import COMMON_HEADINGS, REFS_HEADINGS, normalize_paragraph_text
from services.document_analyzer import analyze_document, normalize_expected
from services.document_structure_engine import (
    is_heading_like,
    recover_structure,
    structure_tree_to_detected_sections,
)
from services.gemini_client import generate_json, gemini_enabled, gemini_model

MAX_TEXT_CHARS = 200_000

CATEGORIES = (
    ("requirements_match", "Requirements match"),
    ("structure", "Structure"),
    ("headings", "Headings"),
    ("paragraphing", "Paragraphing"),
    ("formatting", "Formatting"),
    ("references", "References / citations"),
    ("spacing_layout", "Spacing / layout"),
    ("clarity_organization", "Clarity of organization"),
)

CATEGORY_WEIGHTS = {
    "requirements_match": 1.2,
    "structure": 1.0,
    "headings": 0.9,
    "paragraphing": 0.8,
    "formatting": 1.0,
    "references": 1.1,
    "spacing_layout": 0.7,
    "clarity_organization": 0.9,
}

DOC_TYPES = frozenset(
    {
        "essay",
        "report",
        "literature_review",
        "research_paper",
        "case_study",
        "reflection",
        "learning_journal",
        "dissertation_chapter",
        "thesis_chapter",
        "other",
    }
)

_IN_TEXT_CITATION = re.compile(
    r"\([A-Za-z][^)]{0,80}\d{4}[a-z]?\)|\([A-Za-z][^)]{0,80}n\.d\.\)|\[\d+\]"
)
_DOUBLE_SPACE = re.compile(r"  +")
_EXTRA_BLANKS = re.compile(r"\n{3,}")
_WORD_COUNT = re.compile(r"\b(\d{1,5})\s*(?:words?|word\s*count)\b", re.I)
_WORD_RANGE = re.compile(
    r"(?:between|from)\s+(\d{1,5})\s+(?:and|to|-)\s+(\d{1,5})\s*words?", re.I
)
_MAX_WORDS = re.compile(r"(?:max(?:imum)?|no more than|up to|at most)\s+(\d{1,5})\s*words?", re.I)
_MIN_WORDS = re.compile(r"(?:min(?:imum)?|at least|no fewer than)\s+(\d{1,5})\s*words?", re.I)
SECTION_ALIASES: dict[str, set[str]] = {
    "abstract": {"abstract"},
    "executive summary": {"executive summary", "summary"},
    "introduction": {"introduction", "intro"},
    "background": {"background", "context"},
    "literature review": {"literature review", "literature", "review of literature"},
    "methodology": {"methodology", "methods", "method"},
    "analysis": {"analysis", "findings"},
    "results": {"results", "findings"},
    "discussion": {"discussion"},
    "recommendations": {"recommendations", "recommendation"},
    "conclusion": {"conclusion", "conclusions"},
    "references": {"references", "reference list", "bibliography", "works cited"},
    "appendix": {"appendix", "appendices"},
}
DEFAULT_REQUIRED_SECTIONS: dict[str, list[str]] = {
    "essay": ["Introduction", "Conclusion"],
    "report": ["Introduction", "Conclusion", "References"],
    "literature_review": ["Introduction", "Literature Review", "Conclusion", "References"],
    "research_paper": ["Introduction", "Methodology", "Results", "Discussion", "Conclusion", "References"],
    "case_study": ["Introduction", "Analysis", "Conclusion", "References"],
    "reflection": ["Introduction", "Conclusion"],
    "learning_journal": ["Introduction", "Reflection", "Conclusion"],
    "dissertation_chapter": ["Introduction", "Conclusion", "References"],
    "thesis_chapter": ["Introduction", "Conclusion", "References"],
}
RUBRIC_SECTION_WORDS = frozenset(
    {
        "knowledge",
        "analysis",
        "critical thinking",
        "presentation",
        "referencing",
        "grammar",
        "clarity",
        "argument",
        "evidence",
    }
)


def _gemini_insights(
    *,
    text: str,
    requirements: str,
    issues: list[dict[str, Any]],
    structure_analysis: dict[str, Any],
    document_type: str,
) -> dict[str, Any]:
    diagnostics = {
        "enabled": gemini_enabled(),
        "model": gemini_model(),
        "api_call_success": False,
        "token_usage_estimate": 0,
    }
    if not diagnostics["enabled"]:
        return {
            "document_classification": {
                "document_type": document_type,
                "confidence": 0.0,
                "source": "local",
            },
            "compliance_analysis": None,
            "formatting_recommendations": [],
            "gemini_diagnostics": diagnostics,
        }

    system_prompt = """You analyze academic document quality and return strict JSON.

Return keys exactly:
- document_classification: object with document_type (essay|report|literature_review|research_paper|case_study|reflection|learning_journal|dissertation_chapter|thesis_chapter|other), confidence (0-1), rationale (short string)
- compliance_analysis: object with summary (short string), alignment_level (high|medium|low), major_risks (array of short strings)
- formatting_recommendations: array of concise actionable strings (max 6)

Use the supplied local analyzer context; do not invent unsupported facts."""
    user_prompt = (
        "Requirements:\n"
        f"{(requirements or '').strip()[:6000]}\n\n"
        "Document excerpt:\n"
        f"{(text or '').strip()[:9000]}\n\n"
        "Local structure analysis:\n"
        f"{structure_analysis}\n\n"
        "Local issues:\n"
        f"{issues[:12]}"
    )
    payload, diagnostics = generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.1,
    )
    if not payload:
        return {
            "document_classification": {
                "document_type": document_type,
                "confidence": 0.0,
                "source": "local",
            },
            "compliance_analysis": None,
            "formatting_recommendations": [],
            "gemini_diagnostics": diagnostics,
        }

    cls = payload.get("document_classification")
    comp = payload.get("compliance_analysis")
    recs = payload.get("formatting_recommendations")

    if not isinstance(cls, dict):
        cls = {
            "document_type": document_type,
            "confidence": 0.0,
            "source": "local",
        }
    else:
        cls = {
            "document_type": str(cls.get("document_type") or document_type),
            "confidence": float(cls.get("confidence") or 0.0),
            "rationale": str(cls.get("rationale") or "").strip(),
            "source": "gemini",
        }

    if not isinstance(comp, dict):
        comp = None
    else:
        comp = {
            "summary": str(comp.get("summary") or "").strip(),
            "alignment_level": str(comp.get("alignment_level") or "").strip().lower() or "medium",
            "major_risks": [str(x).strip() for x in (comp.get("major_risks") or []) if str(x).strip()][:6],
        }

    if not isinstance(recs, list):
        recs = []
    recs_out = [str(x).strip() for x in recs if str(x).strip()][:6]

    return {
        "document_classification": cls,
        "compliance_analysis": comp,
        "formatting_recommendations": recs_out,
        "gemini_diagnostics": diagnostics,
    }


def _paragraphs_from_text(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", (text or "").strip())
    return [b.strip() for b in blocks if b.strip()]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _doc_position(idx: int, total: int) -> str:
    if total <= 1:
        return "document"
    ratio = idx / max(total - 1, 1)
    if ratio < 0.33:
        return "first part of document"
    if ratio > 0.66:
        return "last part of document"
    return "middle of document"


def _snippet(text: str, max_len: int = 90) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _make_location(
    *,
    paragraph_number: int | None = None,
    heading: str | None = None,
    section: str | None = None,
    position: str | None = None,
    snippet: str | None = None,
) -> dict[str, Any]:
    loc: dict[str, Any] = {}
    if paragraph_number is not None:
        loc["paragraph_number"] = paragraph_number
    if heading:
        loc["heading"] = heading
    if section:
        loc["section"] = section
    if position:
        loc["position"] = position
    if snippet:
        loc["snippet"] = snippet
    if not loc:
        loc["position"] = "throughout document"
    return loc


def _issue(
    *,
    category: str,
    severity: str,
    title: str,
    message: str,
    fix: str,
    location: dict[str, Any] | None = None,
    penalty: int = 8,
) -> dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "title": title,
        "message": message,
        "fix": fix,
        "location": location or {"position": "throughout document"},
        "penalty": penalty,
    }


def parse_requirements_for_check(text: str) -> dict[str, Any]:
    """Extract assignment rules from free-form requirements (local heuristics only)."""
    low = (text or "").strip().lower()
    out: dict[str, Any] = {
        "font_family": None,
        "font_size": None,
        "line_spacing": None,
        "margins": None,
        "alignment": None,
        "page_numbers": None,
        "title_page": None,
        "headings_required": None,
        "citation_style": None,
        "reference_list_required": None,
        "first_line_indent": None,
        "paragraph_spacing": None,
        "word_limit_min": None,
        "word_limit_max": None,
        "required_sections": [],
    }
    if not low:
        return out

    if "double" in low or "double-space" in low or "double space" in low:
        out["line_spacing"] = 2.0
    elif "single space" in low or "single-spaced" in low:
        out["line_spacing"] = 1.0
    elif "1.15" in low:
        out["line_spacing"] = 1.15
    elif "1.5" in low and "margin" not in low:
        out["line_spacing"] = 1.5

    for style in ("apa", "mla", "harvard", "chicago", "ieee"):
        if style in low:
            out["citation_style"] = style.upper() if style != "ieee" else "IEEE"
            break

    if "times new roman" in low:
        out["font_family"] = "Times New Roman"
    elif "arial" in low:
        out["font_family"] = "Arial"
    elif "calibri" in low:
        out["font_family"] = "Calibri"

    if re.search(r"\b(10|11|12|13|14|16|18|20)\s*(?:pt|point)", low):
        m = re.search(r"\b(10|11|12|13|14|16|18|20)\s*(?:pt|point)", low)
        if m:
            out["font_size"] = int(m.group(1))

    if "justify" in low or "justified" in low:
        out["alignment"] = "justify"
    elif "left align" in low or "flush left" in low:
        out["alignment"] = "left"

    if "no page number" in low:
        out["page_numbers"] = False
    elif "page number" in low or "paginate" in low:
        out["page_numbers"] = True

    if "title page" in low or "cover page" in low:
        out["title_page"] = True

    if "no heading" in low or "without headings" in low:
        out["headings_required"] = False
    elif "heading" in low or "subheading" in low:
        out["headings_required"] = True

    if any(x in low for x in ("reference list", "bibliography", "works cited", "references section")):
        out["reference_list_required"] = True
    if "no references" in low or "without references" in low:
        out["reference_list_required"] = False

    if "first line indent" in low or "first-line indent" in low or "paragraph indent" in low:
        out["first_line_indent"] = True

    if "space after paragraph" in low or "paragraph spacing" in low:
        out["paragraph_spacing"] = True

    out["required_sections"] = _extract_required_sections_for_check(text)

    wr = _WORD_RANGE.search(text)
    if wr:
        out["word_limit_min"] = int(wr.group(1))
        out["word_limit_max"] = int(wr.group(2))
    else:
        mx = _MAX_WORDS.search(text)
        if mx:
            out["word_limit_max"] = int(mx.group(1))
        mn = _MIN_WORDS.search(text)
        if mn:
            out["word_limit_min"] = int(mn.group(1))
        if out["word_limit_min"] is None and out["word_limit_max"] is None:
            wm = _WORD_COUNT.search(text)
            if wm and any(x in low for x in ("limit", "maximum", "minimum", "exactly", "approximately", "around")):
                n = int(wm.group(1))
                out["word_limit_min"] = n
                out["word_limit_max"] = n

    if "1 inch" in low or '1"' in low:
        out["margins"] = "1 inch"
    elif "narrow margin" in low:
        out["margins"] = "narrow"

    return out


def _extract_required_sections_for_check(text: str) -> list[str]:
    """Extract explicitly required document sections without treating rubric criteria as sections."""
    found: list[str] = []
    relevant_lines = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if any(x in low for x in ("required section", "include section", "section heading", "must include", "structure")):
            relevant_lines.append(line)
    relevant = "\n".join(relevant_lines)
    if not relevant:
        return []

    low = relevant.lower()
    for canonical, aliases in SECTION_ALIASES.items():
        if canonical == "references":
            continue
        if any(re.search(rf"\b{re.escape(alias)}\b", low) for alias in aliases):
            found.append(canonical.title())

    for m in re.finditer(r"(?:required sections?|include sections?|section headings?|structure)\s*:?\s*([A-Za-z0-9,;/ &-]{8,180})", relevant, re.I):
        chunk = re.split(r"\.|\n", m.group(1))[0]
        for part in re.split(r",|;|/|\band\b", chunk):
            label = re.sub(r"^\d+[\).]\s*", "", part.strip(" -:"))
            norm = normalize_paragraph_text(label)
            if not norm or norm in RUBRIC_SECTION_WORDS:
                continue
            if 1 <= len(label.split()) <= 4 and len(label) <= 40:
                found.append(label.title())

    deduped: list[str] = []
    seen: set[str] = set()
    for item in found:
        key = normalize_paragraph_text(item)
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:12]


def _track_sections(paragraphs: list[str]) -> list[str | None]:
    current: str | None = None
    sections: list[str | None] = []
    for p in paragraphs:
        if is_heading_like(p):
            current = p.strip()[:80]
        sections.append(current)
    return sections


def _has_section(paragraphs: list[str], labels: set[str]) -> bool:
    for p in paragraphs:
        if normalize_paragraph_text(p) in labels:
            return True
    return False


def _canonical_section_name(label: str) -> str:
    norm = normalize_paragraph_text(label)
    for canonical, aliases in SECTION_ALIASES.items():
        if norm == canonical or norm in aliases:
            return canonical.title()
    return label.strip()[:80]


def _expected_sections(parsed: dict[str, Any], doc_type: str) -> list[str]:
    sections: list[str] = []
    explicit = parsed.get("required_sections")
    if isinstance(explicit, list):
        sections.extend(str(x) for x in explicit if str(x).strip())
    if not sections:
        sections.extend(DEFAULT_REQUIRED_SECTIONS.get(doc_type, []))
    if parsed.get("reference_list_required") is True and not any(
        normalize_paragraph_text(x) in SECTION_ALIASES["references"] for x in sections
    ):
        sections.append("References")

    deduped: list[str] = []
    seen: set[str] = set()
    for section in sections:
        clean = str(section).strip()
        key = normalize_paragraph_text(clean)
        if clean and key not in seen:
            seen.add(key)
            deduped.append(clean)
    return deduped


def _section_present(expected: str, detected: list[dict[str, Any]]) -> bool:
    exp_norm = normalize_paragraph_text(expected)
    aliases = SECTION_ALIASES.get(exp_norm, {exp_norm})
    aliases = set(aliases) | {exp_norm}
    for section in detected:
        title_norm = normalize_paragraph_text(section.get("title") or "")
        canonical_norm = normalize_paragraph_text(section.get("canonical") or "")
        if title_norm in aliases or canonical_norm in aliases:
            return True
    return False


def _sentence_count(text: str) -> int:
    return len(re.findall(r"[.!?](?:\s+|$)", text or ""))


def analyze_structure_recovery(
    *,
    text: str,
    paragraphs: list[str],
    parsed: dict[str, Any],
    doc_type: str,
    doc: Document | None = None,
) -> dict[str, Any]:
    """Structure recovery: preserve existing headings or reconstruct lost academic structure."""
    recovery = recover_structure(
        text=text,
        paragraphs=paragraphs,
        doc=doc,
        document_type=doc_type,
    )
    if recovery.get("error"):
        return {
            "health_score": 0,
            "detected_sections": [],
            "expected_sections": [],
            "missing_sections": [],
            "paragraph_issues": [],
            "heading_issues": [],
            "suggestions": [recovery["error"]],
            "structure_tree": [],
            "headings_present": False,
            "recovery_mode": "none",
        }

    structure_tree = recovery.get("structure_tree") or []
    detected = structure_tree_to_detected_sections(structure_tree)
    inferred_type = recovery.get("inferred_document_type") or doc_type
    expected = _expected_sections(parsed, inferred_type)
    missing = [section for section in expected if not _section_present(section, detected)]

    paragraph_issues: list[dict[str, Any]] = []
    heading_issues: list[dict[str, Any]] = []
    suggestions: list[str] = []
    total = len(paragraphs)

    body_paras = [(i, p) for i, p in enumerate(paragraphs, start=1) if not is_heading_like(p)]
    for idx, p in body_paras:
        words = len(p.split())
        sentences = _sentence_count(p)
        if words > 260:
            target = max(2, min(5, round(words / 120)))
            paragraph_issues.append(
                {
                    "paragraph_number": idx,
                    "type": "large_text_block",
                    "message": f"Paragraph {idx} is unusually large ({words} words).",
                    "suggestion": f"Split paragraph {idx} into about {target} paragraphs.",
                    "word_count": words,
                    "snippet": _snippet(p),
                }
            )
        elif words > 140 and sentences >= 6:
            paragraph_issues.append(
                {
                    "paragraph_number": idx,
                    "type": "possible_missing_breaks",
                    "message": f"Paragraph {idx} has {sentences} sentences and may contain multiple ideas.",
                    "suggestion": f"Check paragraph {idx} for missing paragraph breaks.",
                    "word_count": words,
                    "snippet": _snippet(p),
                }
            )

    if total <= 2 and _word_count(text) > 350:
        paragraph_issues.append(
            {
                "paragraph_number": 1,
                "type": "merged_paragraphs",
                "message": "The document is long but has very few paragraph breaks.",
                "suggestion": "Restore paragraph breaks around each main idea and section transition.",
                "word_count": _word_count(text),
                "snippet": _snippet(paragraphs[0] if paragraphs else text),
            }
        )

    style_counts: dict[str, int] = {}
    for section in detected:
        style = section.get("style") or "unknown"
        style_counts[style] = style_counts.get(style, 0) + 1
    if len([s for s, count in style_counts.items() if count > 0]) >= 2 and len(detected) >= 3:
        heading_issues.append(
            {
                "type": "mixed_heading_styles",
                "message": "Detected headings use mixed styles: " + ", ".join(sorted(style_counts)),
                "suggestion": "Normalize heading style across all section headings.",
            }
        )

    if len(detected) == 0 and _word_count(text) > 300 and not recovery.get("headings_present"):
        heading_issues.append(
            {
                "type": "missing_headings",
                "message": "No section headings were detected in a substantive document.",
                "suggestion": "Recovered structure below — add headings for each major section.",
            }
        )
    elif len(detected) < 2 and _word_count(text) > 800:
        heading_issues.append(
            {
                "type": "too_few_headings",
                "message": "Only a small number of headings were detected for a longer document.",
                "suggestion": "Add headings for major themes or assignment sections.",
            }
        )

    if doc is not None:
        styled_heading_like = 0
        unstyled_heading_like = 0
        for p in doc.paragraphs:
            t = (p.text or "").strip()
            if not t or not is_heading_like(t):
                continue
            style_name = (getattr(p.style, "name", "") or "").lower()
            if "heading" in style_name or "title" in style_name:
                styled_heading_like += 1
            else:
                unstyled_heading_like += 1
        if styled_heading_like and unstyled_heading_like:
            heading_issues.append(
                {
                    "type": "word_heading_style_inconsistent",
                    "message": "Some heading-like lines use Word heading styles while others do not.",
                    "suggestion": "Apply Word Heading styles consistently to all section headings.",
                }
            )

    for section in missing:
        suggestions.append(f"Add {section} heading")
    for issue in paragraph_issues:
        suggestions.append(issue["suggestion"])
    for issue in heading_issues:
        suggestions.append(issue["suggestion"])

    score = 100
    score -= min(45, len(missing) * 12)
    score -= min(35, len(paragraph_issues) * 10)
    score -= min(25, len(heading_issues) * 10)
    if detected and missing:
        score -= 4
    health_score = max(0, min(100, score))

    return {
        "health_score": health_score,
        "detected_sections": detected,
        "expected_sections": expected,
        "missing_sections": missing,
        "paragraph_issues": paragraph_issues,
        "heading_issues": heading_issues,
        "suggestions": suggestions[:10],
        "structure_tree": structure_tree,
        "headings_present": recovery.get("headings_present", False),
        "recovery_mode": recovery.get("recovery_mode"),
        "inferred_document_type": inferred_type,
        "document_type_confidence": recovery.get("document_type_confidence"),
        "overall_confidence": recovery.get("overall_confidence"),
        "paragraph_count": recovery.get("paragraph_count"),
    }


def _verdict(score: int) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 55:
        return "Needs improvement"
    return "Major issues"


def _category_scores(issues: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    scores: dict[str, int] = {c[0]: 100 for c in CATEGORIES}
    for iss in issues:
        cat = iss.get("category") or "structure"
        if cat not in scores:
            scores[cat] = 100
        sev = (iss.get("severity") or "medium").lower()
        pen = iss.get("penalty")
        if pen is None:
            pen = {"high": 18, "medium": 10, "low": 5}.get(sev, 8)
        scores[cat] = max(0, scores[cat] - int(pen))

    out: dict[str, dict[str, Any]] = {}
    for key, label in CATEGORIES:
        out[key] = {"score": scores.get(key, 100), "label": label}
    return out


def _overall_score(categories: dict[str, dict[str, Any]]) -> int:
    total_w = 0.0
    weighted = 0.0
    for key, _ in CATEGORIES:
        w = CATEGORY_WEIGHTS.get(key, 1.0)
        s = categories[key]["score"]
        weighted += s * w
        total_w += w
    return int(round(weighted / total_w)) if total_w else 0


def _positives_and_needs(
    paragraphs: list[str],
    issues: list[dict[str, Any]],
    wc: int,
    has_refs: bool,
    heading_count: int,
) -> tuple[list[str], list[str]]:
    positives: list[str] = []
    needs: list[str] = []

    if len(paragraphs) >= 5:
        positives.append("The document has a reasonable number of body paragraphs.")
    if heading_count >= 2:
        positives.append("Section headings help readers navigate your work.")
    if has_refs:
        positives.append("A references or bibliography section was detected.")
    if wc >= 300:
        positives.append(f"Word count ({wc:,}) suggests substantive content.")
    if not issues:
        positives.append("No common structural or formatting problems were flagged.")

    high_cats = {i["category"] for i in issues if i.get("severity") == "high"}
    for iss in issues[:6]:
        needs.append(iss.get("title") or iss.get("message", "")[:80])

    if "references" in high_cats:
        needs.insert(0, "Fix references and in-text citations first — graders often penalize these heavily.")
    if "requirements_match" in high_cats:
        needs.insert(0, "Re-read the assignment brief and align word count, style, and layout requirements.")

    return positives[:5], needs[:6]


def _next_steps(issues: list[dict[str, Any]]) -> list[str]:
    ranked = sorted(
        issues,
        key=lambda i: (
            {"high": 0, "medium": 1, "low": 2}.get((i.get("severity") or "medium").lower(), 1),
            -int(i.get("penalty") or 8),
        ),
    )
    steps: list[str] = []
    for iss in ranked:
        fix = (iss.get("fix") or "").strip()
        if fix and fix not in steps:
            steps.append(fix)
        if len(steps) >= 3:
            break
    return steps


def _run_content_checks(
    *,
    text: str,
    paragraphs: list[str],
    requirements: str,
    parsed: dict[str, Any],
    doc_type: str,
    sections: list[str | None],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    total = len(paragraphs)
    wc = _word_count(text)

    # --- Requirements match ---
    if not requirements.strip():
        issues.append(
            _issue(
                category="requirements_match",
                severity="low",
                title="No requirements pasted",
                message="Paste your assignment brief or rubric so the checker can compare against specific rules.",
                fix="Add the assignment requirements in the first box, then run Check again.",
                penalty=5,
            )
        )
    else:
        wmin = parsed.get("word_limit_min")
        wmax = parsed.get("word_limit_max")
        if wmin is not None and wc < wmin:
            issues.append(
                _issue(
                    category="requirements_match",
                    severity="high",
                    title="Below word limit",
                    message=f"About {wc:,} words detected; assignment asks for at least {wmin:,}.",
                    fix=f"Expand key sections until you reach at least {wmin:,} words (without padding).",
                    location=_make_location(position="throughout document", snippet=f"~{wc:,} words total"),
                    penalty=20,
                )
            )
        if wmax is not None and wc > wmax * 1.05:
            issues.append(
                _issue(
                    category="requirements_match",
                    severity="high",
                    title="Over word limit",
                    message=f"About {wc:,} words detected; limit appears to be {wmax:,}.",
                    fix="Trim repetition in the discussion and tighten introductions and conclusions.",
                    location=_make_location(position="throughout document", snippet=f"~{wc:,} words total"),
                    penalty=20,
                )
            )
        elif wmax is not None and wc > wmax:
            issues.append(
                _issue(
                    category="requirements_match",
                    severity="medium",
                    title="Slightly over word limit",
                    message=f"About {wc:,} words — just above the stated {wmax:,} word limit.",
                    fix="Cut a few sentences from less essential paragraphs.",
                    location=_make_location(position="throughout document"),
                    penalty=10,
                )
            )

        cite = parsed.get("citation_style")
        if cite and cite.upper() in ("APA", "MLA", "HARVARD"):
            style_in_text = cite.upper() in text.upper() or cite.lower() in requirements.lower()
            has_paren_cites = bool(_IN_TEXT_CITATION.search(text))
            has_refs = _has_section(paragraphs, REFS_HEADINGS)
            if has_refs and not has_paren_cites:
                issues.append(
                    _issue(
                        category="requirements_match",
                        severity="high",
                        title=f"Missing in-text {cite} citations",
                        message=f"Requirements mention {cite}, but few parenthetical or bracket citations were found in the body.",
                        fix=f"Add {cite}-style in-text citations wherever you use a source from your reference list.",
                        location=_make_location(position="middle of document"),
                        penalty=18,
                    )
                )

        if parsed.get("title_page") and total > 0:
            first = paragraphs[0]
            if len(first.split()) < 3 or first.endswith("."):
                issues.append(
                    _issue(
                        category="requirements_match",
                        severity="medium",
                        title="Title page may be missing",
                        message="Requirements mention a title page, but the opening does not look like a standalone title block.",
                        fix="Add a separate title page with assignment title, your name, course, and date before the main text.",
                        location=_make_location(
                            paragraph_number=1,
                            position="first part of document",
                            snippet=_snippet(first),
                        ),
                        penalty=12,
                    )
                )

    # --- Structure ---
    expect_intro = doc_type in ("essay", "report", "research_paper", "literature_review", "thesis_chapter")
    if expect_intro and total >= 4:
        if not _has_section(paragraphs, frozenset({"introduction", "intro"})):
            issues.append(
                _issue(
                    category="structure",
                    severity="medium",
                    title="No Introduction section",
                    message="For this document type, a clear Introduction heading is usually expected.",
                    fix='Add an "Introduction" heading and open with context, aim, and structure overview.',
                    location=_make_location(position="first part of document"),
                    penalty=12,
                )
            )
        if doc_type in ("essay", "report", "research_paper") and not _has_section(
            paragraphs, frozenset({"conclusion"})
        ):
            issues.append(
                _issue(
                    category="structure",
                    severity="medium",
                    title="No Conclusion section",
                    message="A Conclusion heading helps show you answered the assignment question.",
                    fix='Add a "Conclusion" section that summarises findings and links back to the brief.',
                    location=_make_location(position="last part of document"),
                    penalty=12,
                )
            )

    if total < 3:
        issues.append(
            _issue(
                category="structure",
                severity="high",
                title="Very thin document",
                message="Only a few paragraphs were found — the work may be incomplete.",
                fix="Develop each required section with multiple paragraphs before submitting.",
                location=_make_location(position="throughout document"),
                penalty=25,
            )
        )

    # Section order: references should be last major section
    ref_idx = None
    for i, p in enumerate(paragraphs):
        if normalize_paragraph_text(p) in REFS_HEADINGS:
            ref_idx = i
            break
    if ref_idx is not None and ref_idx < total - 3:
        tail = paragraphs[ref_idx + 1 :]
        if any(is_heading_like(t) and normalize_paragraph_text(t) not in REFS_HEADINGS for t in tail):
            issues.append(
                _issue(
                    category="structure",
                    severity="medium",
                    title="Content after references",
                    message="Headings or sections appear after the References block — unusual for academic work.",
                    fix="Move the References section to the end, after all body content and appendices.",
                    location=_make_location(
                        paragraph_number=ref_idx + 1,
                        heading=paragraphs[ref_idx][:60],
                        position="last part of document",
                    ),
                    penalty=10,
                )
            )

    # --- Headings ---
    heading_indices = [i for i, p in enumerate(paragraphs) if is_heading_like(p)]
    heading_count = len(heading_indices)
    headings_required = parsed.get("headings_required")

    if headings_required and heading_count == 0 and total >= 4:
        issues.append(
            _issue(
                category="headings",
                severity="high",
                title="No headings detected",
                message="Requirements expect headings, but the text looks like one continuous block.",
                fix="Break the work into labelled sections (Introduction, main parts, Conclusion, References).",
                location=_make_location(position="throughout document"),
                penalty=18,
            )
        )
    elif total >= 8 and heading_count < 2:
        issues.append(
            _issue(
                category="headings",
                severity="medium",
                title="Few section headings",
                message="Longer papers usually need more visible section headings.",
                fix="Add headings for major parts so markers can scan structure quickly.",
                location=_make_location(position="middle of document"),
                penalty=10,
            )
        )

    caps_headings = [p for p in paragraphs if is_heading_like(p) and p.strip().isupper()]
    title_headings = [p for p in paragraphs if is_heading_like(p) and not p.strip().isupper()]
    if caps_headings and title_headings and len(caps_headings) >= 2 and len(title_headings) >= 2:
        issues.append(
            _issue(
                category="headings",
                severity="low",
                title="Mixed heading styles",
                message="Some headings are ALL CAPS and others use title case — style is inconsistent.",
                fix="Pick one heading style (title case or ALL CAPS) and apply it to all section titles.",
                location=_make_location(
                    heading=_snippet(caps_headings[0], 40),
                    snippet=_snippet(title_headings[0], 40),
                ),
                penalty=6,
            )
        )

    if total > 0:
        first = paragraphs[0]
        if len(first.split()) < 4 and not is_heading_like(first):
            issues.append(
                _issue(
                    category="headings",
                    severity="low",
                    title="Missing or weak title",
                    message="The first line does not read like a document title.",
                    fix="Start with a clear, standalone title line before the first section.",
                    location=_make_location(
                        paragraph_number=1,
                        position="first part of document",
                        snippet=_snippet(first),
                    ),
                    penalty=6,
                )
            )

    # --- Paragraphing ---
    if total >= 2:
        lens = [len(p.split()) for p in paragraphs if not is_heading_like(p)]
        if lens:
            avg = sum(lens) / len(lens)
            short = sum(1 for n in lens if n < 40)
            long = sum(1 for n in lens if n > 220)
            if short > len(lens) * 0.45:
                idx = next(
                    (i + 1 for i, p in enumerate(paragraphs) if not is_heading_like(p) and len(p.split()) < 40),
                    1,
                )
                issues.append(
                    _issue(
                        category="paragraphing",
                        severity="medium",
                        title="Many very short paragraphs",
                        message="Several body paragraphs are under ~40 words — ideas may feel fragmented.",
                        fix="Combine related short paragraphs or expand each with evidence and explanation.",
                        location=_make_location(
                            paragraph_number=idx,
                            section=sections[idx - 1] if idx <= len(sections) else None,
                            position=_doc_position(idx - 1, total),
                            snippet=_snippet(paragraphs[idx - 1]),
                        ),
                        penalty=10,
                    )
                )
            if long > 0:
                idx = next(
                    (
                        i + 1
                        for i, p in enumerate(paragraphs)
                        if not is_heading_like(p) and len(p.split()) > 220
                    ),
                    1,
                )
                issues.append(
                    _issue(
                        category="paragraphing",
                        severity="medium",
                        title="Very long paragraph(s)",
                        message="At least one paragraph exceeds ~220 words — hard to follow on one screen.",
                        fix="Split long blocks at natural topic shifts; one main idea per paragraph.",
                        location=_make_location(
                            paragraph_number=idx,
                            section=sections[idx - 1] if idx <= len(sections) else None,
                            position=_doc_position(idx - 1, total),
                            snippet=_snippet(paragraphs[idx - 1]),
                        ),
                        penalty=10,
                    )
                )
            if avg < 55 and total > 6:
                issues.append(
                    _issue(
                        category="paragraphing",
                        severity="low",
                        title="Paragraphs run short on average",
                        message=f"Average body paragraph is about {int(avg)} words — may look under-developed.",
                        fix="Add analysis, examples, or citations to strengthen each paragraph.",
                        location=_make_location(position="throughout document"),
                        penalty=5,
                    )
                )

    # --- References ---
    ref_required = parsed.get("reference_list_required")
    if ref_required is None:
        ref_required = doc_type in ("research_paper", "literature_review", "report", "thesis_chapter", "case_study")

    has_refs_heading = _has_section(paragraphs, REFS_HEADINGS)
    if ref_required and not has_refs_heading:
        issues.append(
            _issue(
                category="references",
                severity="high",
                title="Missing references section",
                message="No References, Bibliography, or Works Cited heading was found.",
                fix="Add a reference list on a new page at the end, formatted in the required citation style.",
                location=_make_location(position="last part of document"),
                penalty=22,
            )
        )
    elif has_refs_heading:
        ref_i = next(
            i for i, p in enumerate(paragraphs) if normalize_paragraph_text(p) in REFS_HEADINGS
        )
        tail = paragraphs[ref_i + 1 : ref_i + 4]
        yearish = re.compile(r"\(?(19|20)\d{2}[a-z]?\)?|n\.d\.")
        if not tail or not any(yearish.search(t) for t in tail):
            issues.append(
                _issue(
                    category="references",
                    severity="medium",
                    title="References list looks empty",
                    message="A references heading exists, but following lines do not look like dated citations.",
                    fix="Add full reference entries (author, year, title, source) under the heading.",
                    location=_make_location(
                        paragraph_number=ref_i + 1,
                        heading=paragraphs[ref_i][:60],
                        position="last part of document",
                    ),
                    penalty=14,
                )
            )

    cite_style = (parsed.get("citation_style") or "").upper()
    if cite_style == "APA" and text:
        if has_refs_heading and not re.search(r"\(\d{4}\)", text):
            issues.append(
                _issue(
                    category="references",
                    severity="medium",
                    title="APA-style citations not obvious",
                    message="APA usually uses (Author, Year) in the body — few were detected.",
                    fix="Use parenthetical APA citations: (Smith, 2020) or narrative: Smith (2020).",
                    location=_make_location(position="middle of document"),
                    penalty=10,
                )
            )

    # --- Spacing / layout (text signals) ---
    if _DOUBLE_SPACE.search(text):
        m = _DOUBLE_SPACE.search(text)
        pos = text[: m.start()].count("\n\n") + 1 if m else 1
        issues.append(
            _issue(
                category="spacing_layout",
                severity="low",
                title="Double spaces in text",
                message="Extra spaces between words were found — often left over from manual formatting.",
                fix="Find and replace double spaces with single spaces (or run Format on Home).",
                location=_make_location(
                    paragraph_number=min(pos, total) if total else 1,
                    snippet=_snippet(text[max(0, m.start() - 20) : m.end() + 20]) if m else None,
                ),
                penalty=4,
            )
        )

    if _EXTRA_BLANKS.search(text):
        issues.append(
            _issue(
                category="spacing_layout",
                severity="low",
                title="Extra blank lines",
                message="Multiple consecutive blank lines may create uneven vertical spacing.",
                fix="Remove extra empty lines so sections are separated by a single blank line.",
                location=_make_location(position="throughout document"),
                penalty=4,
            )
        )

    # --- Clarity / organization ---
    if doc_type == "literature_review" and not _has_section(
        paragraphs, frozenset({"literature review", "literature", "background"})
    ):
        issues.append(
            _issue(
                category="clarity_organization",
                severity="medium",
                title="Literature review structure unclear",
                message="For a literature review, a labelled literature or background section helps orientation.",
                fix='Use a clear heading such as "Literature Review" or thematic subheadings.',
                location=_make_location(position="first part of document"),
                penalty=10,
            )
        )

    if doc_type == "reflection" and total >= 5 and heading_count == 0:
        issues.append(
            _issue(
                category="clarity_organization",
                severity="low",
                title="Reflection could use structure",
                message="Reflections read better with short labelled parts (e.g. experience, analysis, learning).",
                fix="Add 2–3 short headings to guide the reader through your reflection.",
                location=_make_location(position="throughout document"),
                penalty=6,
            )
        )

    body_before_refs = paragraphs[: ref_idx if ref_idx is not None else total]
    if len(body_before_refs) >= 10 and heading_count < 3:
        issues.append(
            _issue(
                category="clarity_organization",
                severity="medium",
                title="Hard to scan",
                message="A long body with few headings makes organization harder to follow.",
                fix="Introduce subheadings for each major theme or assignment criterion.",
                location=_make_location(position="middle of document"),
                penalty=10,
            )
        )

    return issues


def check_document(
    *,
    text: str,
    requirements: str = "",
    doc: Document | None = None,
    document_type: str = "other",
    parsed_requirements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Full check: requirements → metrics → per-requirement validation → weighted score.
    """
    doc_type = (document_type or "other").lower().replace(" ", "_")
    if doc_type not in DOC_TYPES:
        doc_type = "other"

    paragraphs = _paragraphs_from_text(text)
    if not paragraphs and doc:
        paragraphs = [p.text.strip() for p in doc.paragraphs if (p.text or "").strip()]

    if not paragraphs:
        return {
            "error": "No readable text found. Paste your document or upload a .docx with content.",
        }

    parsed = parse_requirements_for_check(requirements)
    wc = _word_count(text)
    structure_analysis = analyze_structure_recovery(
        text=text,
        paragraphs=paragraphs,
        parsed=parsed,
        doc_type=doc_type,
        doc=doc,
    )

    from services.check_pipeline import run_check_pipeline

    pipeline = run_check_pipeline(
        text=text,
        requirements=requirements,
        paragraphs=paragraphs,
        doc=doc,
        document_type=doc_type,
        structure_tree=structure_analysis.get("structure_tree"),
        parsed_requirements=parsed_requirements,
    )

    score = pipeline["score"]
    verdict = pipeline["verdict"]
    categories = pipeline["categories"]
    issues = pipeline["issues"]
    explanation = pipeline["explanation"]
    validations = pipeline["validations"]
    action_plan = pipeline["action_plan"]
    structured = pipeline["structured_requirements"]
    metrics = pipeline["metrics"]

    has_refs = bool(metrics.get("has_references_section"))
    heading_count = int(metrics.get("heading_count") or 0)
    positives, needs_work = _positives_and_needs(paragraphs, issues, wc, has_refs, heading_count)

    next_steps = [
        f"Step {s['step_number']}: {s['action']} (est. +{s['estimated_improvement']} pts)"
        for s in action_plan
    ]
    if not next_steps:
        next_steps = _next_steps(issues)
    for rec in explanation.get("action_plan_narrative") or []:
        if rec and rec not in next_steps:
            next_steps.append(rec)
        if len(next_steps) >= 6:
            break

    summary = explanation.get("summary") or (
        f"Readiness score: {score}/100 ({verdict}). About {wc:,} words in {len(paragraphs)} paragraphs."
    )

    if doc is None and any(structured.get(k) for k in ("font_family", "font_size", "line_spacing", "page_numbers_required")):
        issues.append(
            _issue(
                category="formatting",
                severity="low",
                title="Upload .docx for layout checks",
                message="Font, margins, and page numbers can only be verified from a Word file.",
                fix="Upload your .docx copy to validate formatting against the brief.",
                penalty=0,
            )
        )

    return {
        "score": score,
        "verdict": verdict,
        "summary": summary,
        "categories": categories,
        "positives": positives,
        "needs_work": needs_work,
        "issues": issues,
        "next_steps": next_steps,
        "structure_analysis": structure_analysis,
        "validations": validations,
        "action_plan": action_plan,
        "priorities": pipeline["priorities"],
        "gemini_diagnostics": explanation.get("gemini_diagnostics"),
        "meta": {
            "word_count": wc,
            "paragraph_count": len(paragraphs),
            "document_type": doc_type,
            "document_classification": {
                "document_type": doc_type,
                "confidence": 0.0,
                "source": explanation.get("source") or "local",
            },
            "compliance_analysis": explanation.get("compliance_analysis"),
            "formatting_recommendations": explanation.get("formatting_recommendations"),
            "parsed_requirements": structured,
            "structured_requirements": structured,
            "metrics": metrics,
            "notes": [],
        },
    }
