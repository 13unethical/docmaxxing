"""Hard word-budget gates and structure validation for AssignmentSpec."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from services.assignment_spec.models import AssignmentSpec, WORD_TOLERANCE


@dataclass
class SectionWordResult:
    title: str
    target: int
    actual: int
    passed: bool
    min_allowed: int
    max_allowed: int


@dataclass
class SpecValidationResult:
    passed: bool
    total_words: int
    total_target: int
    total_passed: bool
    missing_sections: list[str] = field(default_factory=list)
    section_results: list[SectionWordResult] = field(default_factory=list)
    formatting_issues: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total_words": self.total_words,
            "total_target": self.total_target,
            "total_passed": self.total_passed,
            "missing_sections": list(self.missing_sections),
            "section_results": [
                {
                    "title": s.title,
                    "target": s.target,
                    "actual": s.actual,
                    "passed": s.passed,
                    "min_allowed": s.min_allowed,
                    "max_allowed": s.max_allowed,
                }
                for s in self.section_results
            ],
            "formatting_issues": list(self.formatting_issues),
            "blocking_issues": list(self.blocking_issues),
            "repairs": list(self.repairs),
        }


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text or ""))


def section_bounds(target: int, *, tolerance: float = WORD_TOLERANCE) -> tuple[int, int]:
    if target <= 0:
        return 0, 0
    lo = max(1, int(round(target * (1.0 - tolerance))))
    hi = max(lo, int(round(target * (1.0 + tolerance))))
    return lo, hi


def words_within_tolerance(actual: int, target: int, *, tolerance: float = WORD_TOLERANCE) -> bool:
    if target <= 0:
        return True
    lo, hi = section_bounds(target, tolerance=tolerance)
    return lo <= actual <= hi


def needs_expansion(actual: int, target: int, *, tolerance: float = WORD_TOLERANCE) -> bool:
    if target <= 0:
        return False
    lo, _hi = section_bounds(target, tolerance=tolerance)
    return actual < lo


def parse_markdown_sections(content: str) -> list[dict[str, str]]:
    """Split markdown-style draft into ordered sections (no cross-package deps)."""
    text = (content or "").strip()
    if not text:
        return []
    pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return [{"title": "Document", "body": text}]
    sections: list[dict[str, str]] = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append({"title": "Preamble", "body": preamble})
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append({"title": title, "body": body})
    return sections


def validate_draft_against_spec(
    *,
    content: str,
    spec: AssignmentSpec,
    formatted_profile: dict[str, Any] | None = None,
) -> SpecValidationResult:
    """Deterministic pre-delivery validation. No LLM guessing."""
    sections = parse_markdown_sections(content or "")
    by_title = {s["title"].strip().lower(): s for s in sections}
    total = count_words(content or "")
    total_passed = words_within_tolerance(total, spec.total_word_target, tolerance=spec.word_tolerance)

    missing: list[str] = []
    section_results: list[SectionWordResult] = []
    blocking: list[str] = []
    repairs: list[str] = []

    for section in spec.sections:
        if not section.mandatory:
            continue
        if _is_cover(section.title):
            continue
        key = section.title.strip().lower()
        found = by_title.get(key)
        if found is None and not _is_references(section.title):
            found = next((s for t, s in by_title.items() if key in t or t in key), None)
        if found is None:
            missing.append(section.title)
            blocking.append(f"Missing required section: {section.title}")
            repairs.append(f"restore_section:{section.title}")
            continue
        actual = count_words(found.get("body") or "")
        if section.writable and section.target_words > 0:
            lo, hi = section_bounds(section.target_words, tolerance=spec.word_tolerance)
            ok = lo <= actual <= hi
            section_results.append(
                SectionWordResult(
                    title=section.title,
                    target=section.target_words,
                    actual=actual,
                    passed=ok,
                    min_allowed=lo,
                    max_allowed=hi,
                )
            )
            if actual < lo:
                blocking.append(
                    f"{section.title} is too short ({actual}/{section.target_words} words; min {lo})"
                )
                repairs.append(f"expand_section:{section.title}")
            elif actual > hi:
                blocking.append(
                    f"{section.title} is too long ({actual}/{section.target_words} words; max {hi})"
                )
                repairs.append(f"trim_section:{section.title}")

    if not total_passed and spec.total_word_target > 0:
        blocking.append(
            f"Total word count {total} outside ±{int(spec.word_tolerance * 100)}% of "
            f"{spec.total_word_target} (allowed {spec.min_total_words}-{spec.max_total_words})"
        )
        if total < spec.min_total_words:
            repairs.append("expand_total")
        else:
            repairs.append("trim_total")

    formatting_issues = _check_formatting(spec, formatted_profile)
    blocking.extend(formatting_issues)

    passed = not missing and not blocking and total_passed and all(s.passed for s in section_results)
    return SpecValidationResult(
        passed=passed,
        total_words=total,
        total_target=spec.total_word_target,
        total_passed=total_passed,
        missing_sections=missing,
        section_results=section_results,
        formatting_issues=formatting_issues,
        blocking_issues=blocking,
        repairs=repairs,
    )


def _check_formatting(spec: AssignmentSpec, profile: dict[str, Any] | None) -> list[str]:
    if not profile:
        return []
    issues: list[str] = []
    fmt = spec.formatting
    family = str(profile.get("font_family") or "")
    if family and family.lower() != fmt.font_family.lower():
        issues.append(f"Font family mismatch: expected {fmt.font_family}, got {family}")
    size = profile.get("font_size_pt")
    if size is not None and int(size) != int(fmt.font_size_pt):
        issues.append(f"Font size mismatch: expected {fmt.font_size_pt}, got {size}")
    spacing = profile.get("line_spacing")
    if spacing is not None and abs(float(spacing) - float(fmt.line_spacing)) > 0.05:
        issues.append(f"Line spacing mismatch: expected {fmt.line_spacing}, got {spacing}")
    align = str(profile.get("alignment") or "").lower()
    if align and align != fmt.alignment.lower():
        issues.append(f"Alignment mismatch: expected {fmt.alignment}, got {align}")
    return issues


def _is_cover(title: str) -> bool:
    t = title.strip().lower()
    return t in {"cover page", "cover", "title page"} or t.startswith("cover")


def _is_references(title: str) -> bool:
    t = title.strip().lower()
    return t in {"references", "reference list", "bibliography", "works cited"} or t.startswith("reference")


def render_structured_markdown(sections: list[dict[str, str]]) -> str:
    """Render sections with blank line after each heading (required for DOCX heading/body split)."""
    parts: list[str] = []
    for section in sections:
        title = (section.get("title") or "").strip()
        body = (section.get("body") or "").strip()
        if title in {"Preamble", "Document"}:
            if body:
                parts.append(body)
            continue
        if not title:
            if body:
                parts.append(body)
            continue
        if body:
            parts.append(f"## {title}\n\n{body}")
        else:
            parts.append(f"## {title}")
    return "\n\n".join(parts)
