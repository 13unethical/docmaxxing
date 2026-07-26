"""Rubric Coverage Analysis — estimate grade criterion by criterion."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from services.assignment_spec.models import AssignmentSpec, RubricCriterionSpec
from services.assignment_spec.validate import count_words, parse_markdown_sections

CoverageStatus = Literal["covered", "partially_covered", "missing"]


@dataclass
class CriterionCoverage:
    criterion_id: str
    label: str
    weight_percent: float
    coverage_percent: float
    status: CoverageStatus
    evidence: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    repair_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "label": self.label,
            "weight_percent": self.weight_percent,
            "coverage_percent": self.coverage_percent,
            "status": self.status,
            "evidence": list(self.evidence),
            "gaps": list(self.gaps),
            "repair_hint": self.repair_hint,
        }


@dataclass
class RubricCoverageReport:
    criteria: list[CriterionCoverage]
    overall_predicted_grade: float
    passed: bool
    min_coverage: float
    min_overall: float
    learning_outcomes_covered: list[str] = field(default_factory=list)
    lecture_seminar_ok: bool = True
    references_quality_ok: bool = True
    blocking_issues: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "criteria": [c.to_dict() for c in self.criteria],
            "overall_predicted_grade": self.overall_predicted_grade,
            "passed": self.passed,
            "min_coverage": self.min_coverage,
            "min_overall": self.min_overall,
            "learning_outcomes_covered": list(self.learning_outcomes_covered),
            "lecture_seminar_ok": self.lecture_seminar_ok,
            "references_quality_ok": self.references_quality_ok,
            "blocking_issues": list(self.blocking_issues),
            "repairs": list(self.repairs),
            "per_criterion": {
                c.label: {"coverage": c.coverage_percent, "status": c.status} for c in self.criteria
            },
        }


def analyze_rubric_coverage(*, content: str, spec: AssignmentSpec) -> RubricCoverageReport:
    """Score how well the draft maximises each uploaded rubric criterion."""
    text = content or ""
    low = text.lower()
    sections = parse_markdown_sections(text)
    criteria_out: list[CriterionCoverage] = []
    blocking: list[str] = []
    repairs: list[str] = []

    for criterion in spec.rubric_criteria:
        cov = _score_criterion(criterion, text=text, low=low, sections=sections, spec=spec)
        criteria_out.append(cov)
        if cov.coverage_percent < spec.min_rubric_coverage:
            blocking.append(
                f"{cov.label}: coverage {cov.coverage_percent:.0f}% below minimum "
                f"{spec.min_rubric_coverage:.0f}%"
            )
            repairs.append(f"strengthen_criterion:{cov.criterion_id}")

    overall = _weighted_overall(criteria_out)
    if overall < spec.min_overall_predicted_grade:
        blocking.append(
            f"Overall predicted grade {overall:.1f}% below minimum "
            f"{spec.min_overall_predicted_grade:.0f}%"
        )
        repairs.append("raise_overall_grade")

    lecture_ok = _lecture_seminar_ok(low, sections, spec)
    if spec.required_lecture_seminar_refs and not lecture_ok:
        blocking.append("Missing required lecture/seminar references in entry sections")
        repairs.append("add_lecture_seminar_refs")

    refs_ok = _references_quality_ok(low, sections, spec)
    if not refs_ok:
        blocking.append("References quality insufficient (missing reference list or academic citations)")
        repairs.append("improve_references")

    los_covered = []
    for lo in spec.learning_outcomes:
        if _lo_present(lo, low, criteria_out):
            los_covered.append(lo)
        else:
            blocking.append(f"Learning outcome under-covered: {lo}")
            repairs.append(f"cover_learning_outcome:{lo[:48]}")

    for item in spec.mandatory_reflections:
        if not _reflection_ok(low, item):
            blocking.append(f"Mandatory reflection missing: {item}")
            repairs.append("strengthen_reflection")

    for item in spec.mandatory_comparisons:
        if not re.search(r"compar|whereas|in contrast|unlike", low):
            blocking.append(f"Mandatory comparison missing: {item}")
            repairs.append("add_comparison")

    for item in spec.forbidden_content:
        if "week 1" in item.lower() and re.search(r"week\s*1", low):
            blocking.append(f"Forbidden content present: {item}")
            repairs.append("remove_forbidden_content")

    passed = (
        not blocking
        and all(c.coverage_percent >= spec.min_rubric_coverage for c in criteria_out)
        and overall >= spec.min_overall_predicted_grade
    )
    return RubricCoverageReport(
        criteria=criteria_out,
        overall_predicted_grade=overall,
        passed=passed if criteria_out else True,
        min_coverage=spec.min_rubric_coverage,
        min_overall=spec.min_overall_predicted_grade,
        learning_outcomes_covered=los_covered,
        lecture_seminar_ok=lecture_ok,
        references_quality_ok=refs_ok,
        blocking_issues=blocking,
        repairs=list(dict.fromkeys(repairs)),
    )


def _score_criterion(
    criterion: RubricCriterionSpec,
    *,
    text: str,
    low: str,
    sections: list[dict[str, str]],
    spec: AssignmentSpec,
) -> CriterionCoverage:
    signals = criterion.signals or [w for w in re.findall(r"[a-zA-Z]{5,}", criterion.label.lower())]
    hits = 0
    evidence: list[str] = []
    for signal in signals:
        if signal.lower() in low:
            hits += 1
            evidence.append(signal)
    if signals:
        # Non-linear: 2+ hits already implies strong coverage for short academic sections.
        ratio = hits / len(signals)
        if hits >= max(2, len(signals) // 2):
            signal_score = max(80.0, ratio * 100.0)
        else:
            signal_score = ratio * 100.0
    else:
        signal_score = 0.0

    label = criterion.label.lower()
    boost = 0.0
    gaps: list[str] = []

    if "paper quality" in label or label.strip() == "paper quality":
        required_titles = [
            s.title for s in spec.sections if s.mandatory and not _is_cover_title(s.title)
        ]
        present = 0
        for title in required_titles:
            if any(title.lower() in s["title"].lower() or s["title"].lower() in title.lower() for s in sections):
                present += 1
        structure_ratio = present / max(1, len(required_titles))
        boost += structure_ratio * 40
        if structure_ratio < 1:
            gaps.append("missing required sections")
        if re.search(r"\([A-Z][A-Za-z\-']+,?\s*\d{4}\)|\[\w+[^\]]*\d{4}\]", text):
            boost += 20
            evidence.append("in-text citations")
        else:
            gaps.append("academic in-text citations")
        if any("reference" in s["title"].lower() for s in sections):
            boost += 15
            evidence.append("references section")
        else:
            gaps.append("references section")
        if count_words(text) >= spec.min_total_words if spec.total_word_target else True:
            boost += 15
        else:
            gaps.append("word count")
        if re.search(r"lecture|seminar", low):
            boost += 10
            evidence.append("lecture/seminar refs")
        elif spec.required_lecture_seminar_refs:
            gaps.append("lecture/seminar references")

    if any(x in label for x in ("lo5", "personal")) or "informed decision" in label:
        if re.search(r"personal|interest|major|choice|decision|reflect", low):
            boost += 25
            evidence.append("personal decision reflection")
        else:
            gaps.append("personal major choice reflection")

    if any(x in label for x in ("lo4",)) or "entrepreneur" in label:
        if re.search(r"entrepreneur", low):
            boost += 20
            evidence.append("entrepreneurial perspective")
        else:
            gaps.append("entrepreneurial perspective")

    if any(x in label for x in ("lo1",)) or "historical concept" in (criterion.description or "").lower():
        if re.search(r"historical concept|marketing|digital innovation|international business|origin|development", low):
            boost += 20
        else:
            gaps.append("historical concepts across fields")

    if any(x in label for x in ("lo2",)) or "historical stage" in (criterion.description or "").lower():
        if re.search(r"historical stage|business evolution|evolution|shaped", low):
            boost += 20
        else:
            gaps.append("historical stages of evolution")

    if "paper quality" in label:
        coverage = min(100.0, round(boost, 1))
    else:
        coverage = min(100.0, round(signal_score * 0.55 + boost, 1))
        if hits >= 1 and coverage < 70:
            coverage = max(coverage, 70.0)
        if hits >= 2 and coverage < 85:
            coverage = max(coverage, 85.0)

    if not signals and criterion.description:
        desc_words = [w for w in re.findall(r"[a-zA-Z]{5,}", criterion.description.lower())][:6]
        hit = sum(1 for w in desc_words if w in low)
        coverage = max(coverage, round((hit / max(1, len(desc_words))) * 100.0, 1))

    if coverage >= 85:
        status: CoverageStatus = "covered"
    elif coverage >= 55:
        status = "partially_covered"
    else:
        status = "missing"
        if not gaps:
            gaps.append("insufficient evidence for top-band performance")

    hint = ""
    if status != "covered":
        hint = (
            f"Strengthen {criterion.label}: address {', '.join(gaps[:3]) or 'top-band descriptors'} "
            f"with explicit evidence and analysis."
        )
    return CriterionCoverage(
        criterion_id=criterion.id,
        label=criterion.label,
        weight_percent=criterion.weight_percent,
        coverage_percent=coverage,
        status=status,
        evidence=evidence[:8],
        gaps=gaps,
        repair_hint=hint,
    )


def _is_cover_title(title: str) -> bool:
    t = title.strip().lower()
    return t in {"cover page", "cover", "title page"} or t.startswith("cover")


def _weighted_overall(criteria: list[CriterionCoverage]) -> float:
    if not criteria:
        return 100.0
    total_w = sum(c.weight_percent for c in criteria) or 100.0
    score = sum(c.coverage_percent * c.weight_percent for c in criteria) / total_w
    return round(score, 1)


def _lecture_seminar_ok(low: str, sections: list[dict[str, str]], spec: AssignmentSpec) -> bool:
    if not spec.required_lecture_seminar_refs:
        return True
    entry_sections = [
        s
        for s in sections
        if re.search(r"journal\s*entry|\bentry\s*\d|\bbody\b", s["title"], re.I)
    ]
    if not entry_sections:
        return bool(re.search(r"lecture|seminar", low))
    missing = 0
    for section in entry_sections:
        if not re.search(r"lecture|seminar", (section.get("body") or "").lower()):
            missing += 1
    return missing == 0


def _references_quality_ok(low: str, sections: list[dict[str, str]], spec: AssignmentSpec) -> bool:
    has_refs_heading = any("reference" in s["title"].lower() for s in sections)
    has_citations = bool(re.search(r"\([A-Z][A-Za-z\-']+,?\s*\d{4}\)|\[\w+[^\]]*\d{4}\]", low))
    has_ref_entries = bool(re.search(r"https?://|doi\.org|\(\d{4}\)\.", low))
    if any(_is_references(s.title) for s in spec.sections):
        return has_refs_heading and (has_citations or has_ref_entries)
    return has_citations or has_ref_entries or not spec.citation_requirements


def _is_references(title: str) -> bool:
    t = title.strip().lower()
    return t.startswith("reference") or t in {"bibliography", "works cited"}


def _lo_present(lo: str, low: str, criteria: list[CriterionCoverage]) -> bool:
    # Covered if linked criterion is covered/partial, or LO keywords appear.
    key = lo.lower()
    for c in criteria:
        if any(key[:20] in x.lower() or x.lower()[:20] in key for x in [c.label, *c.evidence]):
            if c.coverage_percent >= 55:
                return True
    tokens = [t for t in re.findall(r"[a-zA-Z]{5,}", key) if t not in {"define", "recognize", "interpret", "relate"}]
    hits = sum(1 for t in tokens[:6] if t in low)
    return hits >= max(1, min(2, len(tokens) // 3))


def _reflection_ok(low: str, requirement: str) -> bool:
    return bool(re.search(r"personal|interest|major|choice|decision|reflect", low))
