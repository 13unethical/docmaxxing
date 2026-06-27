"""Compare structured requirements against document metrics."""

from __future__ import annotations

from typing import Any

from formatter.headings import normalize_paragraph_text
from services.check_requirements import StructuredRequirements

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
    "counterargument": {"counterargument", "counter-argument", "counter argument"},
}


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


def _validation(
    *,
    req_id: str,
    label: str,
    weight: float,
    required: str,
    detected: str,
    completion: float,
    status: str,
    priority: str,
    confidence: float = 1.0,
    category: str = "requirements_match",
    details: dict[str, Any] | None = None,
    fix: str = "",
) -> dict[str, Any]:
    completion = max(0.0, min(1.0, completion))
    pct = int(round(completion * 100))
    return {
        "id": req_id,
        "label": label,
        "weight": weight,
        "required": required,
        "detected": detected,
        "completion": completion,
        "completion_pct": pct,
        "status": status,
        "priority": priority,
        "confidence": confidence,
        "category": category,
        "details": details or {},
        "fix": fix,
        "points_earned": round(weight * completion, 2),
        "points_possible": weight,
    }


def _word_count_completion(wc: int, req: StructuredRequirements) -> tuple[float, str]:
    wmin, wmax = req.word_min, req.word_max
    if wmin is None and wmax is None:
        return 1.0, "PASS"
    if wmin is not None and wmax is not None:
        if wmin <= wc <= wmax:
            return 1.0, "PASS"
        if wc < wmin:
            return wc / wmin if wmin else 0.0, "FAIL"
        over = wc - wmax
        penalty = min(1.0, over / max(wmax, 1))
        return max(0.0, 1.0 - penalty * 0.5), "PARTIAL" if penalty < 0.5 else "FAIL"
    if wmin is not None:
        if wc >= wmin:
            return 1.0, "PASS"
        return wc / wmin if wmin else 0.0, "FAIL"
    if wmax is not None:
        if wc <= wmax:
            return 1.0, "PASS"
        over = wc - wmax
        return max(0.0, 1.0 - over / max(wmax, 1)), "FAIL"
    return 1.0, "PASS"


def _format_required_range(req: StructuredRequirements) -> str:
    if req.word_min is not None and req.word_max is not None:
        return f"{req.word_min:,}–{req.word_max:,}"
    if req.word_min is not None:
        return f"minimum {req.word_min:,}"
    if req.word_max is not None:
        return f"maximum {req.word_max:,}"
    return "Not specified"


def validate_all_requirements(
    req: StructuredRequirements,
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run independent validators; each returns required/detected/completion/status."""
    results: list[dict[str, Any]] = []
    wc = int(metrics.get("word_count") or 0)

    if req.word_min is not None or req.word_max is not None:
        completion, status = _word_count_completion(wc, req)
        conf = req.word_count_confidence or 0.85
        priority = "critical" if completion < 0.5 else "medium" if completion < 0.85 else "low"
        results.append(
            _validation(
                req_id="word_count",
                label="Word count",
                weight=25,
                required=_format_required_range(req),
                detected=f"{wc:,}",
                completion=completion,
                status=status,
                priority=priority,
                confidence=conf,
                category="requirements_match",
                fix=f"Increase word count to at least {req.word_min or req.word_max:,}."
                if completion < 1.0 and req.word_min
                else "Trim content to meet the word limit.",
            )
        )
    elif req.word_count_confidence and req.word_count_confidence < 0.5:
        results.append(
            _validation(
                req_id="word_count",
                label="Word count",
                weight=25,
                required="Ambiguous (needs confirmation)",
                detected=f"{wc:,}",
                completion=1.0,
                status="NEEDS_CONFIRMATION",
                priority="medium",
                confidence=req.word_count_confidence,
                category="requirements_match",
                fix="Confirm the required word count with your instructor.",
            )
        )

    sections_required = req.required_sections or []
    if sections_required:
        detected = metrics.get("detected_sections") or []
        checklist: list[dict[str, Any]] = []
        present = 0
        for section in sections_required:
            ok = _section_present(section, detected)
            if ok:
                present += 1
            checklist.append({"section": section, "present": ok})
        total = len(sections_required)
        completion = present / total if total else 1.0
        status = "PASS" if completion >= 1.0 else "PARTIAL" if completion >= 0.5 else "FAIL"
        missing = [c["section"] for c in checklist if not c["present"]]
        results.append(
            _validation(
                req_id="sections",
                label="Required sections",
                weight=20,
                required=f"{total} sections",
                detected=f"{present}/{total}",
                completion=completion,
                status=status,
                priority="critical" if completion < 0.5 else "medium",
                category="structure",
                details={"checklist": checklist, "missing": missing},
                fix="Add missing sections: " + ", ".join(missing[:5]) + "." if missing else "",
            )
        )

    ref_target = req.peer_reviewed_refs
    if ref_target is None and req.references_required:
        ref_target = 1
    if ref_target is not None:
        detected_refs = int(metrics.get("reference_entries") or 0)
        has_section = bool(metrics.get("has_references_section"))
        if not has_section:
            detected_refs = 0
        completion = min(1.0, detected_refs / ref_target) if ref_target else 1.0
        status = "PASS" if completion >= 1.0 else "PARTIAL" if completion >= 0.3 else "FAIL"
        results.append(
            _validation(
                req_id="references",
                label="References",
                weight=15,
                required=str(ref_target),
                detected=str(detected_refs),
                completion=completion,
                status=status,
                priority="critical" if completion < 0.5 else "medium",
                confidence=req.peer_reviewed_confidence or 0.85,
                category="references",
                fix=f"Add {ref_target - detected_refs} more reference entries."
                if detected_refs < ref_target
                else "Add a References section with full citations.",
            )
        )

    cite_style = (req.citation_style or "").upper()
    in_text = int(metrics.get("in_text_citations") or 0)
    ref_entries = int(metrics.get("reference_entries") or 0)
    if cite_style or ref_entries > 0 or req.references_required:
        if ref_entries > 0:
            expected_cites = max(3, min(ref_entries, ref_entries))
            completion = min(1.0, in_text / expected_cites) if expected_cites else 0.0
        elif cite_style:
            completion = 1.0 if in_text >= 2 else (in_text / 2.0 if in_text else 0.0)
        else:
            completion = 1.0 if in_text else 0.0
        apa_refs = bool(metrics.get("apa_reference_format_ok"))
        apa_parts = []
        if cite_style == "APA":
            apa_parts.append(f"References: {'APA ✔' if apa_refs else 'APA ✘'}")
        apa_parts.append(f"In-text citations: {in_text}")
        overall_apa = completion
        if cite_style == "APA" and ref_entries:
            overall_apa = (completion + (1.0 if apa_refs else 0.0)) / 2.0
        status = "PASS" if overall_apa >= 0.85 else "PARTIAL" if overall_apa >= 0.4 else "FAIL"
        results.append(
            _validation(
                req_id="in_text_citations",
                label="In-text citations",
                weight=15,
                required=cite_style or "Required",
                detected=" · ".join(apa_parts),
                completion=overall_apa,
                status=status,
                priority="critical" if overall_apa < 0.4 else "medium",
                category="references",
                details={"citation_style": cite_style, "in_text_count": in_text, "apa_compliance_pct": int(round(overall_apa * 100))},
                fix=f"Add {cite_style or 'required'}-style in-text citations throughout the body.",
            )
        )

    fmt_parts: list[tuple[str, Any, Any, str]] = []
    if req.font_family:
        fmt_parts.append(("font", req.font_family, metrics.get("font_family"), "Apply the required font throughout."))
    if req.font_size:
        fmt_parts.append(("font size", f"{req.font_size} pt", metrics.get("font_size"), "Set body text to the required point size."))
    if req.line_spacing:
        fmt_parts.append(("line spacing", str(req.line_spacing), metrics.get("line_spacing"), "Set line spacing to match the brief."))
    if req.page_numbers_required:
        fmt_parts.append(("page numbers", "Required", metrics.get("has_page_numbers"), "Insert page numbers."))

    if fmt_parts:
        hits = 0
        checked = 0
        fmt_details: list[dict[str, Any]] = []
        for name, required, detected, fix_hint in fmt_parts:
            if detected is None:
                fmt_details.append({"item": name, "required": str(required), "detected": "Unknown (upload .docx)", "ok": None})
                continue
            checked += 1
            ok = False
            if name == "font":
                ok = detected and str(required).lower() in str(detected).lower()
            elif name == "font size":
                ok = detected == required or str(detected) == str(required).replace(" pt", "")
            elif name == "line spacing":
                try:
                    ok = abs(float(detected) - float(required)) < 0.11
                except (TypeError, ValueError):
                    ok = False
            elif name == "page numbers":
                ok = bool(detected)
            if ok:
                hits += 1
            fmt_details.append({"item": name, "required": str(required), "detected": str(detected), "ok": ok})
        if checked == 0:
            completion = 0.5
            status = "NEEDS_CONFIRMATION"
        else:
            completion = hits / checked
            status = "PASS" if completion >= 0.9 else "PARTIAL" if completion >= 0.5 else "FAIL"
        results.append(
            _validation(
                req_id="formatting",
                label="Formatting",
                weight=10,
                required=f"{len(fmt_parts)} rules",
                detected=f"{hits}/{checked or len(fmt_parts)} matched" if checked else "Upload .docx",
                completion=completion,
                status=status,
                priority="medium" if completion < 0.85 else "low",
                category="formatting",
                details={"items": fmt_details},
                fix="Fix formatting items flagged above.",
            )
        )

    grammar_signals = int(metrics.get("grammar_signal_count") or 0)
    grammar_completion = max(0.0, 1.0 - grammar_signals * 0.15)
    results.append(
        _validation(
            req_id="grammar",
            label="Grammar & clarity",
            weight=10,
            required="Clear academic prose",
            detected=f"{100 - int((1 - grammar_completion) * 100)}% estimated",
            completion=grammar_completion,
            status="PASS" if grammar_completion >= 0.85 else "PARTIAL" if grammar_completion >= 0.6 else "FAIL",
            priority="low",
            category="clarity_organization",
            fix="Review spacing, sentence length, and paragraph development.",
        )
    )

    heading_count = int(metrics.get("heading_count") or 0)
    body_count = int(metrics.get("body_paragraph_count") or 0)
    style_completion = min(1.0, (heading_count / 3.0) * 0.5 + min(1.0, body_count / 5.0) * 0.5) if body_count else 0.3
    results.append(
        _validation(
            req_id="academic_style",
            label="Academic structure",
            weight=5,
            required="Headings + body development",
            detected=f"{heading_count} headings, {body_count} body paragraphs",
            completion=style_completion,
            status="PASS" if style_completion >= 0.75 else "PARTIAL" if style_completion >= 0.4 else "FAIL",
            priority="low",
            category="clarity_organization",
            fix="Develop body paragraphs and add section headings.",
        )
    )

    if req.body_paragraphs is not None:
        detected_body = int(metrics.get("body_paragraph_count") or 0)
        completion = min(1.0, detected_body / req.body_paragraphs) if req.body_paragraphs else 1.0
        results.append(
            _validation(
                req_id="body_paragraphs",
                label="Body paragraphs",
                weight=0,
                required=str(req.body_paragraphs),
                detected=str(detected_body),
                completion=completion,
                status="PASS" if completion >= 1.0 else "FAIL",
                priority="medium",
                category="structure",
                fix=f"Write at least {req.body_paragraphs} substantive body paragraphs.",
            )
        )

    return results
