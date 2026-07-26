"""Build AssignmentSpec from RequirementJSON — grade-driven unified contract."""

from __future__ import annotations

import re
from typing import Any

from services.assignment_spec.models import (
    AssignmentSpec,
    FormatSpec,
    RubricCriterionSpec,
    SectionSpec,
    WORD_TOLERANCE,
)

_STRUCTURAL_ZERO_WORDS = {
    "cover page",
    "cover",
    "title page",
    "references",
    "reference list",
    "bibliography",
    "works cited",
    "table of contents",
    "toc",
    "appendix",
    "appendices",
}

_DEFAULT_SIGNALS = {
    "lo1": [
        "historical concept",
        "marketing",
        "digital innovation",
        "international business",
        "origin",
        "development",
    ],
    "lo2": ["historical stage", "business evolution", "stage", "evolution", "shaped"],
    "lo4": ["entrepreneur", "entrepreneurial", "responded", "change", "innovation"],
    "lo5": ["reflection", "personal interest", "major", "choice", "decision"],
    "paper-quality": [
        "lecture",
        "seminar",
        "reference",
        "academic",
        "organised",
        "organized",
    ],
}


def build_assignment_spec(requirement: dict[str, Any], *, project_id: str | None = None) -> AssignmentSpec:
    """Derive the canonical AssignmentSpec from analyzed RequirementJSON + rubric."""
    req = dict(requirement or {})
    pid = str(project_id or req.get("project_id") or "")
    title = str(req.get("title") or req.get("assignment_type") or "Assignment")
    assignment_type = str(req.get("assignment_type") or title)
    total = int(req.get("word_count") or 0)
    budgets = {
        str(k).strip(): int(v)
        for k, v in dict(req.get("section_word_budgets") or {}).items()
        if str(k).strip() and int(v) >= 0
    }
    required = [str(s).strip() for s in (req.get("required_sections") or []) if str(s).strip()]
    if not required and budgets:
        required = list(budgets.keys())

    learning_outcomes = [str(v) for v in (req.get("learning_outcomes") or []) if str(v).strip()]
    rubric_criteria = _build_rubric_criteria(req.get("rubric") or [], learning_outcomes)

    sections: list[SectionSpec] = []
    for index, raw_title in enumerate(required):
        clean = raw_title.split("(", 1)[0].strip() or raw_title
        structural = _is_structural(clean)
        target = budgets.get(raw_title, budgets.get(clean, 0))
        if structural:
            target = 0
        sections.append(
            SectionSpec(
                id=_slug(clean),
                title=clean,
                target_words=target,
                writable=not structural and target > 0,
                mandatory=True,
                order=index,
                notes=raw_title if raw_title != clean else "",
                linked_criteria=_link_section_to_criteria(clean, rubric_criteria),
            )
        )

    writable_sum = sum(s.target_words for s in sections if s.writable)
    if total <= 0 and writable_sum > 0:
        total = writable_sum
    if writable_sum > 0 and abs(writable_sum - total) > max(20, int(total * 0.15)):
        total = writable_sum

    formatting = _format_spec(req.get("formatting") if isinstance(req.get("formatting"), dict) else {})
    formatting.cover_page_required = any(_is_cover(s.title) for s in sections)
    formatting.references_on_new_page = any(_is_references(s.title) for s in sections) or formatting.references_on_new_page

    brief_blob = " ".join(
        [
            title,
            assignment_type,
            " ".join(required),
            " ".join(learning_outcomes),
            " ".join(str(c.get("description") or "") for c in (req.get("rubric") or []) if isinstance(c, dict)),
            str(req.get("raw_brief") or ""),
        ]
    ).lower()

    required_lecture = bool(
        re.search(r"lecture|seminar", brief_blob)
        or any("lecture" in r.lower() or "seminar" in r.lower() for r in required)
    )
    has_reflection = any(s.title.lower() == "reflection" for s in sections)
    has_compare = bool(re.search(r"compar|two historical concepts|different fields", brief_blob))

    rules: list[str] = []
    required_evidence: list[str] = []
    citation_requirements: list[str] = []
    mandatory_comparisons: list[str] = []
    mandatory_reflections: list[str] = []
    forbidden: list[str] = []

    if required_lecture:
        rules.append("Each journal entry / body section must refer to at least one lecture or seminar.")
        required_evidence.append("Explicit lecture or seminar reference in each entry section")
    if has_reflection:
        rules.append("Reflection must connect journal materials to personal major choice / decision-making.")
        mandatory_reflections.append(
            "Connect journal entry materials to personal interest in a major and explain the choice"
        )
    if has_compare:
        mandatory_comparisons.append(
            "Compare two historical concepts from two different fields and discuss current/future influence"
        )
        rules.append("Include a comparison of two historical concepts across different fields.")
    if formatting.cover_page_required:
        rules.append("Include required university cover page.")
    if formatting.references_on_new_page:
        rules.append("References must begin on a new page.")
    citation_requirements.append("Use academic sources with proper in-text citations and a reference list")
    if req.get("citation_style"):
        citation_requirements.append(f"Follow citation style: {req.get('citation_style')}")
    if re.search(r"week\s*1|excluding week 1", brief_blob):
        forbidden.append("Do not base journal entries on Week 1 materials")

    # Normalize rubric weights to 100 when present but unscaled.
    _normalize_weights(rubric_criteria)

    return AssignmentSpec(
        project_id=pid,
        title=title,
        assignment_type=assignment_type,
        total_word_target=total,
        word_tolerance=WORD_TOLERANCE,
        citation_style=req.get("citation_style"),
        sections=sections,
        formatting=formatting,
        learning_outcomes=learning_outcomes,
        rubric_criteria=rubric_criteria,
        rubric=[c.to_dict() for c in rubric_criteria],
        minimum_sources=req.get("minimum_sources"),
        mandatory_content_rules=rules,
        required_lecture_seminar_refs=required_lecture,
        required_evidence=required_evidence,
        citation_requirements=citation_requirements,
        mandatory_comparisons=mandatory_comparisons,
        mandatory_reflections=mandatory_reflections,
        forbidden_content=forbidden,
        source_requirement_id=str(req.get("id") or "") or None,
    )


def _build_rubric_criteria(raw: list[Any], learning_outcomes: list[str]) -> list[RubricCriterionSpec]:
    criteria: list[RubricCriterionSpec] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        label = str(item.get("criterion") or item.get("label") or f"Criterion {index + 1}").strip()
        if not label:
            continue
        cid = str(item.get("id") or _slug(label))
        weight = _parse_weight(item.get("weight") or item.get("weight_percent"))
        description = str(item.get("description") or "")
        lo_links = _match_learning_outcomes(label, description, learning_outcomes)
        signals = list(item.get("signals") or []) or _default_signals_for(label, description)
        criteria.append(
            RubricCriterionSpec(
                id=cid,
                label=label,
                weight_percent=weight,
                description=description,
                top_band_guidance=str(item.get("top_band_guidance") or description),
                signals=signals,
                linked_learning_outcomes=lo_links,
                linked_sections=list(item.get("linked_sections") or []),
            )
        )
    if criteria:
        return criteria
    # Synthesize criteria from learning outcomes when rubric array is empty.
    if learning_outcomes:
        weight = round(100.0 / len(learning_outcomes), 2)
        for lo in learning_outcomes:
            criteria.append(
                RubricCriterionSpec(
                    id=_slug(lo[:40]),
                    label=lo,
                    weight_percent=weight,
                    description=lo,
                    top_band_guidance=lo,
                    signals=_default_signals_for(lo, lo),
                    linked_learning_outcomes=[lo],
                )
            )
    return criteria


def _normalize_weights(criteria: list[RubricCriterionSpec]) -> None:
    total = sum(c.weight_percent for c in criteria)
    if not criteria:
        return
    if total <= 0:
        equal = round(100.0 / len(criteria), 2)
        for c in criteria:
            c.weight_percent = equal
        return
    if abs(total - 100.0) > 1.0:
        for c in criteria:
            c.weight_percent = round(c.weight_percent * 100.0 / total, 2)


def _match_learning_outcomes(label: str, description: str, outcomes: list[str]) -> list[str]:
    blob = f"{label} {description}".lower()
    matched: list[str] = []
    for lo in outcomes:
        key = lo.lower()
        short = re.sub(r"^lo\s*\d+[\.\):\s-]*", "", key).strip()
        lo_id = re.match(r"(lo\s*\d+)", key)
        if lo_id and lo_id.group(1).replace(" ", "") in blob.replace(" ", ""):
            matched.append(lo)
            continue
        if short and short[:24] in blob:
            matched.append(lo)
    return matched


def _default_signals_for(label: str, description: str) -> list[str]:
    blob = f"{label} {description}".lower()
    if re.search(r"\blo\s*1\b|historical concepts|define key", blob):
        return list(_DEFAULT_SIGNALS["lo1"])
    if re.search(r"\blo\s*2\b|historical stages|recognize", blob):
        return list(_DEFAULT_SIGNALS["lo2"])
    if re.search(r"\blo\s*4\b|entrepreneur", blob):
        return list(_DEFAULT_SIGNALS["lo4"])
    if re.search(r"\blo\s*5\b|personal interest|informed decision|reflect", blob):
        return list(_DEFAULT_SIGNALS["lo5"])
    if re.search(r"paper quality|organisation|organization|referencing", blob):
        return list(_DEFAULT_SIGNALS["paper-quality"])
    words = [w for w in re.findall(r"[a-zA-Z]{5,}", blob) if w.lower() not in {"student", "demonstrates"}]
    return words[:8]


def _link_section_to_criteria(title: str, criteria: list[RubricCriterionSpec]) -> list[str]:
    t = title.lower()
    linked: list[str] = []
    for c in criteria:
        label = c.label.lower()
        if "reflection" in t and ("lo5" in label or "personal" in label or "reflect" in label):
            linked.append(c.id)
        elif "journal entry" in t or "body" in t:
            if any(x in label for x in ("lo1", "lo2", "lo4", "historical", "entrepreneur")):
                linked.append(c.id)
        elif "introduction" in t and "paper quality" in label:
            linked.append(c.id)
        elif "reference" in t and "paper quality" in label:
            linked.append(c.id)
    return linked


def _format_spec(fmt: dict[str, Any]) -> FormatSpec:
    spacing = _parse_spacing(fmt.get("line_spacing"))
    font_size = _parse_int(fmt.get("font_size_pt") if fmt.get("font_size_pt") is not None else fmt.get("font_size"), 12)
    margins = _parse_margins(fmt.get("margins") or fmt.get("margins_inches"))
    alignment = str(fmt.get("alignment") or "left").strip().lower()
    if alignment not in {"left", "justify", "centre", "center"}:
        alignment = "left"
    if alignment in {"centre", "center"}:
        alignment = "left"
    return FormatSpec(
        font_family=str(fmt.get("font_family") or "Times New Roman"),
        font_size_pt=font_size,
        line_spacing=spacing,
        alignment=alignment,
        margins_inches=margins,
        first_line_indent=bool(fmt.get("first_line_indent", False)),
        heading_size_pt=_parse_int(fmt.get("heading_size_pt"), 14),
    )


def _parse_spacing(value: Any) -> float:
    if value is None or value == "":
        return 2.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace("-", " ").replace("_", " ")
    aliases = {
        "single": 1.0,
        "1.5": 1.5,
        "double": 2.0,
        "double spaced": 2.0,
        "double spacing": 2.0,
    }
    for key, num in aliases.items():
        if key in text:
            return num
    try:
        return float(text.split()[0])
    except (TypeError, ValueError, IndexError):
        return 2.0


def _parse_margins(value: Any) -> float:
    if value is None or value == "":
        return 1.0
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"(\d+(?:\.\d+)?)", str(value))
    if match:
        return float(match.group(1))
    return 1.0


def _parse_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).strip().split()[0]))
    except (TypeError, ValueError, IndexError):
        return default


def _parse_weight(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"(\d+(?:\.\d+)?)", str(value))
    return float(match.group(1)) if match else 0.0


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "section"


def _is_structural(title: str) -> bool:
    return title.strip().lower() in _STRUCTURAL_ZERO_WORDS or _is_cover(title) or _is_references(title)


def _is_cover(title: str) -> bool:
    t = title.strip().lower()
    return t in {"cover page", "cover", "title page"} or t.startswith("cover")


def _is_references(title: str) -> bool:
    t = title.strip().lower()
    return t in {"references", "reference list", "bibliography", "works cited"} or t.startswith("reference")
