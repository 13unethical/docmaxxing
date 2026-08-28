"""Compare structured requirements against document metrics."""

from __future__ import annotations

import re
from typing import Any

from formatter.headings import normalize_paragraph_text
from services.check_requirements import StructuredRequirements

MIN_SECTION_BODY_WORDS = 30
_SECTION_NUM_PREFIX = re.compile(r"^(?:\d+(?:\.\d+)*|[ivxlcdm]+)[.)]?\s+", re.I)

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


def heading_label_without_number(text: str) -> str:
    """'1. Introduction' / '7 References' → 'introduction' / 'references'."""
    norm = normalize_paragraph_text(text or "")
    return _SECTION_NUM_PREFIX.sub("", norm).strip(" :-")


def is_references_section_name(text: str) -> bool:
    key = heading_label_without_number(text)
    aliases = SECTION_ALIASES.get("references", {"references"})
    return key == "references" or key in aliases


def _expected_section_keys(expected: str) -> set[str]:
    key = heading_label_without_number(expected)
    aliases = SECTION_ALIASES.get(key, {key})
    return {key} | set(aliases)


def _section_has_content(expected: str, section: dict[str, Any]) -> bool:
    """A heading alone is not a section: body text or a bibliography entry is required."""
    if is_references_section_name(expected) or is_references_section_name(
        str(section.get("title") or "")
    ) or is_references_section_name(str(section.get("canonical") or "")):
        return int(section.get("reference_entries") or 0) >= 1
    return int(section.get("body_word_count") or 0) >= MIN_SECTION_BODY_WORDS


def _section_present(expected: str, detected: list[dict[str, Any]]) -> bool:
    aliases = _expected_section_keys(expected)
    for section in detected:
        title_key = heading_label_without_number(section.get("title") or "")
        canonical_key = heading_label_without_number(section.get("canonical") or "")
        if title_key in aliases or canonical_key in aliases:
            return _section_has_content(expected, section)
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
    detected = metrics.get("detected_sections") or []
    observed_titles = [str(s.get("title") or "").strip() for s in detected if str(s.get("title") or "").strip()]
    if sections_required:
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
                details={"checklist": checklist, "missing": missing, "observed": observed_titles},
                fix="Add missing sections: " + ", ".join(missing[:5]) + "." if missing else "",
            )
        )
    else:
        preview = ", ".join(observed_titles[:8]) if observed_titles else "None detected"
        results.append(
            _validation(
                req_id="sections_observed",
                label="Detected sections",
                weight=0,
                required="Not specified in the brief",
                detected=preview,
                completion=1.0,
                status="NOT_CHECKED",
                priority="low",
                category="structure",
                details={"observed": observed_titles, "from_brief": False},
                fix="",
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
    citation_match = metrics.get("citation_match") or {}
    listed = int(citation_match.get("listed") or metrics.get("reference_entries") or 0)
    cited = int(citation_match.get("cited") or metrics.get("in_text_citations") or 0)
    if cite_style or listed > 0 or req.references_required:
        uncited = list(citation_match.get("uncited") or [])
        missing = list(citation_match.get("missing") or [])
        mismatches = list(citation_match.get("mismatches") or [])
        matched = int(
            citation_match.get("matched")
            if citation_match.get("matched") is not None
            else max(0, listed - len(uncited))
        )
        summary = str(citation_match.get("summary") or f"{listed} sources listed · {cited} cited in text")
        mode = str(citation_match.get("mode") or "")
        verifiable = citation_match.get("verifiable", True)
        if verifiable is False or mode == "unknown":
            results.append(
                _validation(
                    req_id="in_text_citations",
                    label="In-text citations",
                    weight=15,
                    required="Each listed source cited in the text",
                    detected="couldn't verify",
                    completion=0.0,
                    status="CANNOT_VERIFY",
                    priority="low",
                    category="references",
                    details={
                        "citation_style": cite_style,
                        "mode": mode or "unknown",
                        "listed": listed,
                        "cited": cited,
                        "matched": matched,
                        "uncited": uncited,
                        "missing": missing,
                        "mismatches": mismatches,
                        "verifiable": False,
                    },
                    fix="Use a consistent numbered or author-year citation style so listed sources can be matched to the text.",
                )
            )
        else:
            if listed == 0 and cited == 0:
                completion = 0.0
            elif listed == 0:
                completion = 0.0
            elif not uncited and not missing:
                completion = 1.0
            else:
                denom = max(listed + len(missing), 1)
                completion = matched / denom
            status = (
                "PASS"
                if completion >= 0.85 and not missing and not uncited
                else "PARTIAL"
                if completion >= 0.4
                else "FAIL"
            )
            if uncited and missing:
                fix = "Cite every listed source in the text, and add reference entries for names cited but missing from the list."
            elif uncited:
                names = ", ".join(item.get("label") or "" for item in uncited[:5]).strip(", ")
                fix = f"Add in-text citations for: {names}."
            elif missing:
                names = ", ".join(item.get("label") or "" for item in missing[:5]).strip(", ")
                n = len(missing)
                word = "source" if n == 1 else "sources"
                fix = f"Add reference list entries for {n} {word} cited in the text: {names}."
            elif listed == 0:
                fix = f"Add {cite_style or 'required'}-style in-text citations and a matching reference list."
            else:
                fix = ""
            results.append(
                _validation(
                    req_id="in_text_citations",
                    label="In-text citations",
                    weight=15,
                    required="Each listed source cited in the text",
                    detected=summary,
                    completion=completion,
                    status=status,
                    priority="critical" if completion < 0.4 else "medium",
                    category="references",
                    details={
                        "citation_style": cite_style,
                        "mode": mode,
                        "listed": listed,
                        "cited": cited,
                        "matched": matched,
                        "uncited": uncited,
                        "missing": missing,
                        "mismatches": mismatches,
                        "verifiable": True,
                    },
                    fix=fix,
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
        if checked > 0:
            completion = hits / checked
            status = "PASS" if completion >= 0.9 else "PARTIAL" if completion >= 0.5 else "FAIL"
            results.append(
                _validation(
                    req_id="formatting",
                    label="Formatting",
                    weight=10,
                    required=f"{len(fmt_parts)} rules",
                    detected=f"{hits}/{checked} matched",
                    completion=completion,
                    status=status,
                    priority="medium" if completion < 0.85 else "low",
                    category="formatting",
                    details={"items": fmt_details},
                    fix="Fix formatting items flagged above.",
                )
            )

    heading_count = int(metrics.get("heading_count") or 0)
    body_count = int(metrics.get("body_paragraph_count") or 0)
    developed = int(metrics.get("developed_section_count") or 0)
    heading_part = min(1.0, developed / 4.0) if developed else min(0.4, heading_count / 6.0)
    body_part = min(1.0, body_count / 8.0) if body_count else 0.0
    style_completion = 0.55 * heading_part + 0.45 * body_part
    if developed < 2 or body_count < 4:
        style_completion = min(style_completion, 0.6)
    results.append(
        _validation(
            req_id="academic_style",
            label="Academic structure",
            weight=4,
            required="Several developed sections and body paragraphs",
            detected=f"{developed} developed sections, {body_count} body paragraphs",
            completion=style_completion,
            status="PASS" if style_completion >= 0.75 else "PARTIAL" if style_completion >= 0.4 else "FAIL",
            priority="low",
            category="clarity_organization",
            details={"developed_sections": developed, "heading_count": heading_count, "body_paragraphs": body_count},
            fix="Split the text into labelled sections and develop body paragraphs under each heading.",
        )
    )

    has_refs_check = any(v["id"] == "references" for v in results)
    if not has_refs_check:
        detected_refs = int(metrics.get("reference_entries") or 0)
        has_section = bool(metrics.get("has_references_section"))
        if not has_section:
            detected_refs = 0
        if detected_refs >= 5:
            completion, status = 1.0, "PASS"
        elif detected_refs >= 1:
            completion, status = 0.55, "PARTIAL"
        else:
            completion, status = 0.0, "FAIL"
        results.append(
            _validation(
                req_id="bibliography",
                label="Reference list",
                weight=8,
                required="A references section with bibliography entries",
                detected=("No references section" if not has_section else f"{detected_refs} entries"),
                completion=completion,
                status=status,
                priority="medium" if completion < 1.0 else "low",
                category="references",
                details={"has_references_section": has_section, "entries": detected_refs},
                fix="Add a References section with full bibliography entries." if completion < 1.0 else "",
            )
        )

    cite_hits = int(metrics.get("in_text_citation_hits") or metrics.get("in_text_citations") or 0)
    if cite_hits >= 5:
        completion, status = 1.0, "PASS"
    elif cite_hits >= 1:
        completion, status = 0.5, "PARTIAL"
    else:
        completion, status = 0.0, "FAIL"
    results.append(
        _validation(
            req_id="in_text_presence",
            label="In-text citations present",
            weight=8,
            required="Citations in the body text",
            detected=f"{cite_hits} in-text citations",
            completion=completion,
            status=status,
            priority="medium" if completion < 1.0 else "low",
            category="references",
            details={"hits": cite_hits},
            fix="Cite sources in the body, not only in a bibliography." if completion < 1.0 else "",
        )
    )

    share = float(metrics.get("largest_section_share") or 0.0)
    developed_n = int(metrics.get("developed_section_count") or 0)
    largest_title = str(metrics.get("largest_section_title") or "one section")
    if developed_n <= 1:
        completion, status = 0.15, "FAIL"
    elif share > 0.5:
        completion, status = max(0.0, 1.0 - (share - 0.5) * 2.0), "FAIL" if share >= 0.65 else "PARTIAL"
    elif share > 0.4:
        completion, status = 0.7, "PARTIAL"
    else:
        completion, status = 1.0, "PASS"
    share_pct = int(round(share * 100))
    results.append(
        _validation(
            req_id="section_balance",
            label="Section length balance",
            weight=7,
            required="No single section longer than half the paper",
            detected=(
                f"{developed_n} developed section"
                + ("s" if developed_n != 1 else "")
                + (f" · largest is {share_pct}% ({largest_title})" if developed_n else "")
            ),
            completion=completion,
            status=status,
            priority="medium" if completion < 0.85 else "low",
            category="structure",
            details={"largest_share": share, "developed_sections": developed_n, "largest_title": largest_title},
            fix="Break the longest section into labelled parts so no section is more than half the paper."
            if completion < 1.0
            else "",
        )
    )

    uncited_share = float(metrics.get("share_analytical_without_citation") or 0.0)
    analytical_n = int(metrics.get("analytical_paragraphs") or 0)
    if analytical_n == 0:
        completion, status = 0.35, "PARTIAL"
        detected = "No analytical paragraphs to check"
    elif uncited_share <= 0.35:
        completion, status = 1.0, "PASS"
        detected = f"{int(round((1 - uncited_share) * 100))}% of analytical paragraphs cite a source"
    elif uncited_share <= 0.7:
        completion, status = 0.55, "PARTIAL"
        detected = f"{int(round(uncited_share * 100))}% of analytical paragraphs have no citation"
    else:
        completion, status = max(0.0, 1.0 - uncited_share), "FAIL"
        detected = f"{int(round(uncited_share * 100))}% of analytical paragraphs have no citation"
    results.append(
        _validation(
            req_id="analytical_citation_coverage",
            label="Citations in analytical paragraphs",
            weight=7,
            required="Most analytical paragraphs cite a source",
            detected=detected,
            completion=completion,
            status=status,
            priority="medium" if completion < 0.85 else "low",
            category="references",
            details={
                "share_without_citation": uncited_share,
                "analytical_paragraphs": analytical_n,
            },
            fix="Add in-text citations to analytical paragraphs that currently have none." if completion < 1.0 else "",
        )
    )

    avg_para = float(metrics.get("avg_paragraph_words") or 0.0)
    share_long = float(metrics.get("share_paragraphs_over_250") or 0.0)
    n_long = int(metrics.get("paragraphs_over_250") or 0)
    if share_long <= 0.05 and avg_para <= 160:
        completion, status = 1.0, "PASS"
    elif share_long <= 0.2 and avg_para <= 220:
        completion, status = 0.6, "PARTIAL"
    else:
        completion, status = max(0.0, 1.0 - share_long - max(0.0, avg_para - 160) / 400.0), "FAIL"
    results.append(
        _validation(
            req_id="paragraph_length",
            label="Paragraph length",
            weight=6,
            required="Average under 160 words; few paragraphs over 250",
            detected=f"avg {int(round(avg_para))} words · {n_long} paragraph(s) over 250 words",
            completion=completion,
            status=status,
            priority="low",
            category="clarity_organization",
            details={"avg_paragraph_words": avg_para, "share_over_250": share_long, "over_250": n_long},
            fix="Split paragraphs longer than 250 words into one idea each." if completion < 1.0 else "",
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
