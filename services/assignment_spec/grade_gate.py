"""Grade gate: unified validation + automatic repair loop before export."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from services.assignment_spec.models import AssignmentSpec
from services.assignment_spec.rubric_coverage import RubricCoverageReport, analyze_rubric_coverage
from services.assignment_spec.validate import (
    SpecValidationResult,
    count_body_words,
    count_words,
    parse_markdown_sections,
    render_structured_markdown,
    section_bounds,
    validate_draft_against_spec,
)

MAX_REPAIR_ITERATIONS = 5


@dataclass
class GradeGateResult:
    passed: bool
    content: str
    iterations: int
    spec_validation: SpecValidationResult
    rubric_coverage: RubricCoverageReport
    blocking_issues: list[str] = field(default_factory=list)
    repair_log: list[str] = field(default_factory=list)
    export_blocked: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "iterations": self.iterations,
            "export_blocked": self.export_blocked,
            "blocking_issues": list(self.blocking_issues),
            "repair_log": list(self.repair_log),
            "spec_validation": self.spec_validation.to_dict(),
            "rubric_coverage": self.rubric_coverage.to_dict(),
            "overall_predicted_grade": self.rubric_coverage.overall_predicted_grade,
            "per_criterion_coverage": {
                c.label: c.coverage_percent for c in self.rubric_coverage.criteria
            },
            "content": self.content,
            "total_words": count_words(self.content),
        }


def run_grade_gate(
    *,
    content: str,
    spec: AssignmentSpec,
    formatted_profile: dict[str, Any] | None = None,
    max_iterations: int = MAX_REPAIR_ITERATIONS,
    llm_repair: Callable[[str, AssignmentSpec, list[str]], str] | None = None,
) -> GradeGateResult:
    """Validate → Repair → Validate loop. Export only when all checks pass."""
    current = content or ""
    repair_log: list[str] = []
    iterations = 0

    for iteration in range(max_iterations + 1):
        iterations = iteration
        spec_result = validate_draft_against_spec(
            content=current,
            spec=spec,
            formatted_profile=formatted_profile,
        )
        rubric_result = analyze_rubric_coverage(content=current, spec=spec)
        blocking = list(
            dict.fromkeys(list(spec_result.blocking_issues) + list(rubric_result.blocking_issues))
        )
        if spec_result.passed and rubric_result.passed:
            return GradeGateResult(
                passed=True,
                content=current,
                iterations=iterations,
                spec_validation=spec_result,
                rubric_coverage=rubric_result,
                blocking_issues=[],
                repair_log=repair_log,
                export_blocked=False,
            )

        if iteration >= max_iterations:
            break

        repairs = list(
            dict.fromkeys(list(spec_result.repairs) + list(rubric_result.repairs))
        )
        repaired = apply_repairs(
            content=current,
            spec=spec,
            repairs=repairs,
            rubric=rubric_result,
            llm_repair=llm_repair,
        )
        if repaired == current:
            repair_log.append(f"iteration={iteration + 1}: no-op repair; stopping")
            break
        repair_log.append(f"iteration={iteration + 1}: applied {', '.join(repairs[:6]) or 'repairs'}")
        current = repaired

    spec_result = validate_draft_against_spec(
        content=current, spec=spec, formatted_profile=formatted_profile
    )
    rubric_result = analyze_rubric_coverage(content=current, spec=spec)
    blocking = list(
        dict.fromkeys(list(spec_result.blocking_issues) + list(rubric_result.blocking_issues))
    )
    return GradeGateResult(
        passed=False,
        content=current,
        iterations=iterations,
        spec_validation=spec_result,
        rubric_coverage=rubric_result,
        blocking_issues=blocking,
        repair_log=repair_log,
        export_blocked=True,
    )


def apply_repairs(
    *,
    content: str,
    spec: AssignmentSpec,
    repairs: list[str],
    rubric: RubricCoverageReport,
    llm_repair: Callable[[str, AssignmentSpec, list[str]], str] | None = None,
) -> str:
    """Trim over-long sections at sentence boundaries; content gaps go to the LLM repair.

    No canned sentences are ever appended: template filler reads as nonsense on
    any brief other than the one it was written for.
    """
    sections = parse_markdown_sections(content)
    by_title = {s["title"].strip().lower(): s for s in sections}
    changed = False

    def find(title: str) -> dict[str, str] | None:
        key = title.strip().lower()
        return by_title.get(key) or next((s for t, s in by_title.items() if key in t or t in key), None)

    limits: dict[str, int] = {}
    for repair in repairs:
        if repair.startswith("trim_section:"):
            title = repair.split(":", 1)[1]
            target_spec = spec.section_by_title(title)
            if target_spec and target_spec.target_words:
                limits[title] = section_bounds(target_spec.target_words, tolerance=spec.word_tolerance)[1]
    if "trim_total" in repairs:
        excess = count_body_words(content) - spec.max_total_words
        over = sorted(
            (
                (count_words(found["body"]) - s.target_words, s, found)
                for s in spec.writable_sections
                if s.target_words and (found := find(s.title))
            ),
            key=lambda row: row[0],
            reverse=True,
        )
        for surplus, section_spec, found in over:
            if excess <= 0 or surplus <= 0:
                break
            cut = min(surplus, excess)
            actual = count_words(found["body"])
            limits[section_spec.title] = min(limits.get(section_spec.title, actual), actual - cut)
            excess -= cut
    for title, max_words in limits.items():
        section = find(title)
        if not section:
            continue
        new_body = _trim_to_sentences(section.get("body") or "", max_words)
        if new_body != (section.get("body") or ""):
            section["body"] = new_body
            changed = True

    text = render_structured_markdown(sections) if (sections and changed) else content
    if llm_repair is not None:
        weak = [c for c in rubric.criteria if c.coverage_percent < spec.min_rubric_coverage]
        content_repairs = [r for r in repairs if not r.startswith("trim_")]
        if weak or content_repairs:
            try:
                improved = llm_repair(text, spec, repairs)
                if improved and count_words(improved) >= count_words(text) * 0.9:
                    return improved
            except Exception:  # noqa: BLE001
                pass
    return text


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"“\[])")
_SIGNPOST_RE = re.compile(
    r"\b(?:in the (?:next|following) section|(?:the )?(?:next|following) section|section that follows"
    r"|this (?:section|report|part) (?:will|aims to|sets out)|as (?:discussed|mentioned|noted|shown) "
    r"(?:above|earlier|previously)|will be (?:summari[sz]ed|discussed|examined|addressed|explored)"
    r"|the conclusion will|is (?:examined|discussed) (?:next|below))\b",
    re.I,
)
_PROTECTED_RE = re.compile(r"\(\D{0,80}\d{4}[a-z]?\)|\bAppendix\b|\d")


def _significant(sentence: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{5,}", sentence.lower())}


def _trim_to_sentences(body: str, max_words: int) -> str:
    """Delete whole sentences until the body fits: signposting first, then the most redundant.

    The first sentence of each paragraph, its closing sentence (unless it is only a
    signpost) and any sentence carrying a citation, a figure or an appendix pointer are
    kept: cutting from the end used to drop whole PESTLE factors and section conclusions.
    """
    if count_words(body) <= max_words:
        return body
    paragraphs = [_SENTENCE_SPLIT_RE.split(p.strip()) for p in re.split(r"\n\s*\n", body or "") if p.strip()]
    candidates: list[tuple[int, float, int, int]] = []
    for pi, sentences in enumerate(paragraphs):
        for si, sentence in enumerate(sentences):
            signpost = bool(_SIGNPOST_RE.search(sentence))
            if si == 0 or (si == len(sentences) - 1 and not signpost) or _PROTECTED_RE.search(sentence):
                continue
            words = _significant(sentence)
            others = set().union(*(_significant(s) for j, s in enumerate(sentences) if j != si))
            redundancy = len(words & others) / len(words) if words else 1.0
            candidates.append((0 if signpost else 1, -redundancy, pi, si))
    removed: set[tuple[int, int]] = set()
    for _kind, _redundancy, pi, si in sorted(candidates):
        if count_words(_render_paragraphs(paragraphs, removed)) <= max_words:
            break
        removed.add((pi, si))
    return _render_paragraphs(paragraphs, removed)


def _render_paragraphs(paragraphs: list[list[str]], removed: set[tuple[int, int]]) -> str:
    return "\n\n".join(
        " ".join(s for si, s in enumerate(sentences) if (pi, si) not in removed)
        for pi, sentences in enumerate(paragraphs)
    )
