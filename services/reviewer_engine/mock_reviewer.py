"""Mock Academic Reviewer — replace with professor-grade AI reviewer later."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from services.assignment_pipeline.models import utc_now
from services.reviewer_engine.models import (
    ChecklistItem,
    IssueSeverity,
    QualityScores,
    ReviewEngineInput,
    ReviewIssue,
    ReviewReport,
)


class AcademicReviewer(Protocol):
    def review(self, payload: ReviewEngineInput) -> ReviewReport:
        ...


class MockAcademicReviewer:
    VERSION = "mock-1.0"

    def review(self, payload: ReviewEngineInput) -> ReviewReport:
        req = payload.requirement_json
        plan = payload.research_plan
        blueprint = payload.blueprint
        draft = payload.draft

        content = str(draft.get("content") or "")
        draft_words = int(draft.get("total_words") or len(content.split()))
        target_words = int(req.get("word_count") or req.get("estimatedWordCount") or blueprint.get("total_target_words") or 2500)
        assignment_type = str(req.get("assignment_type") or req.get("assignmentType") or "Essay")
        required_sections = list(req.get("required_sections") or req.get("requiredSections") or [])
        blueprint_sections = [s.get("title") for s in (blueprint.get("sections") or []) if s.get("title")]

        requirement_checklist = _requirement_checklist(
            assignment_type=assignment_type,
            draft_words=draft_words,
            target_words=target_words,
            required_sections=required_sections,
            blueprint_sections=blueprint_sections,
            content=content,
            plan=plan,
            req=req,
            blueprint=blueprint,
        )
        rubric_checklist = _rubric_checklist(req)
        issues = _issues(content, blueprint, plan)
        quality_scores = _quality_scores(requirement_checklist, rubric_checklist, issues)
        overall = quality_scores.overall
        passed = overall >= 75

        return ReviewReport(
            id=str(uuid.uuid4()),
            project_id=payload.project_id,
            overall_score=overall,
            passed=passed,
            requirement_checklist=requirement_checklist,
            rubric_checklist=rubric_checklist,
            issues=issues,
            recommendations=_recommendations(issues, passed),
            quality_scores=quality_scores,
            engine_version=self.VERSION,
            reviewed_at=utc_now(),
        )


def _requirement_checklist(
    *,
    assignment_type: str,
    draft_words: int,
    target_words: int,
    required_sections: list[str],
    blueprint_sections: list[str],
    content: str,
    plan: dict[str, Any],
    req: dict[str, Any],
    blueprint: dict[str, Any],
) -> list[ChecklistItem]:
    word_ratio = draft_words / target_words if target_words else 0
    word_pass = 0.85 <= word_ratio <= 1.15
    sections = required_sections or blueprint_sections
    structure_pass = all(_section_present(content, title) for title in sections if title.lower() != "references")
    tone = str(plan.get("writing_tone") or "Formal academic prose")

    checks = [
        ("assignment_type", "Assignment Type", assignment_type.lower() in content.lower() or bool(assignment_type), 90, f"Expected: {assignment_type}"),
        ("word_count", "Word Count", word_pass, 88 if word_pass else 62, f"{draft_words}/{target_words} words"),
        ("structure", "Structure", structure_pass, 86 if structure_pass else 58, "Blueprint section coverage"),
        ("required_sections", "Required Sections", structure_pass, 84 if structure_pass else 55, ", ".join(sections) or "—"),
        ("learning_outcomes", "Learning Outcomes", True, 82, "Outcomes addressed in analytical sections"),
        ("critical_analysis", "Critical Analysis", "analysis" in content.lower() or "compare" in content.lower(), 78, "Evaluative depth"),
        ("logical_flow", "Logical Flow", bool(blueprint.get("writing_queue")), 85, "Queue-aligned progression"),
        ("argument_quality", "Argument Quality", "argument" in content.lower() or "objective" in content.lower(), 80, "Argument development"),
        ("counterarguments", "Counterarguments", "counter" in content.lower() or "however" in content.lower(), 72, "Opposing views"),
        ("evidence_usage", "Evidence Usage", "evidence" in content.lower() or "source" in content.lower(), 79, "Evidence integration"),
        ("citation_placement", "Citation Placement", "citation" in content.lower() or "apa" in content.lower(), 76, str(req.get("citation_style") or "APA 7")),
        ("formatting", "Formatting Requirements", True, 88, "Formatting profile from requirements"),
        ("writing_tone", "Writing Tone", bool(tone), 87, tone),
        ("conclusion_quality", "Conclusion Quality", _section_present(content, "Conclusion"), 81, "Conclusion resolves research question"),
    ]
    return [
        ChecklistItem(id=item_id, label=label, passed=passed, score=score, notes=notes)
        for item_id, label, passed, score, notes in checks
    ]


def _rubric_checklist(req: dict[str, Any]) -> list[ChecklistItem]:
    rubric = req.get("rubric") or []
    if not rubric:
        return [
            ChecklistItem("structure", "Structure & coherence", True, 84, "Inferred from brief"),
            ChecklistItem("analysis", "Critical analysis", True, 78, "Needs stronger comparison"),
            ChecklistItem("sources", "Use of sources", True, 80, "Citation density acceptable"),
            ChecklistItem("writing", "Academic writing", True, 86, "Tone is formal"),
            ChecklistItem("referencing", "Referencing", True, 82, str(req.get("citation_style") or "APA 7")),
        ]
    items: list[ChecklistItem] = []
    for index, criterion in enumerate(rubric):
        label = str(criterion.get("criterion") or f"Criterion {index + 1}")
        score = 85 if index % 2 == 0 else 76
        items.append(
            ChecklistItem(
                id=f"rubric-{index + 1}",
                label=label,
                passed=score >= 75,
                score=score,
                notes=str(criterion.get("description") or ""),
            )
        )
    return items


def _issues(content: str, blueprint: dict[str, Any], plan: dict[str, Any]) -> list[ReviewIssue]:
    titles = section_titles(blueprint)
    discussion = _pick_section_title(titles, ("discussion", "analysis", "critical", "evaluation"))
    literature = _pick_section_title(titles, ("literature", "review", "thematic", "background"))
    issues: list[ReviewIssue] = []
    if "compare" not in content.lower() and "comparison" not in content.lower():
        issues.append(
            ReviewIssue(
                issue_id="issue-critical-analysis-1",
                category="Critical Analysis",
                severity=IssueSeverity.HIGH,
                section=discussion,
                description="No comparison between competing theories.",
                suggested_fix="Add comparison before conclusion.",
            )
        )
    if "counter" not in content.lower():
        issues.append(
            ReviewIssue(
                issue_id="issue-counterargument-1",
                category="Counterarguments",
                severity=IssueSeverity.MEDIUM,
                section=discussion,
                description="Counterarguments are not explicitly evaluated.",
                suggested_fix="Introduce one counterargument and rebuttal in the analysis section.",
            )
        )
    if not any(loc.lower() in content.lower() for loc in (plan.get("critical_analysis_locations") or [])):
        issues.append(
            ReviewIssue(
                issue_id="issue-evidence-1",
                category="Evidence Usage",
                severity=IssueSeverity.MEDIUM,
                section=literature,
                description="Evidence weighting is uneven across themes.",
                suggested_fix="Balance peer-reviewed sources across all major themes.",
            )
        )
    return issues


def _quality_scores(
    requirement_checklist: list[ChecklistItem],
    rubric_checklist: list[ChecklistItem],
    issues: list[ReviewIssue],
) -> QualityScores:
    def avg(items: list[ChecklistItem]) -> int:
        if not items:
            return 0
        return int(round(sum(item.score for item in items) / len(items)))

    structure = _score_for_labels(requirement_checklist, {"Structure", "Required Sections", "Logical Flow"})
    research = _score_for_labels(requirement_checklist, {"Evidence Usage", "Learning Outcomes"})
    critical = _score_for_labels(requirement_checklist, {"Critical Analysis", "Argument Quality", "Counterarguments"})
    evidence = _score_for_labels(requirement_checklist, {"Evidence Usage", "Citation Placement"})
    formatting = _score_for_labels(requirement_checklist, {"Formatting Requirements"})
    language = _score_for_labels(requirement_checklist, {"Writing Tone", "Conclusion Quality"})
    tone = _score_for_labels(requirement_checklist, {"Writing Tone"})
    rubric_avg = avg(rubric_checklist)
    penalty = sum(4 for issue in issues if issue.severity == IssueSeverity.HIGH)
    penalty += sum(2 for issue in issues if issue.severity == IssueSeverity.MEDIUM)
    overall = max(0, int(round((structure + research + critical + evidence + formatting + language + tone + rubric_avg) / 8 - penalty)))
    return QualityScores(
        structure=structure,
        research=research,
        critical_thinking=critical,
        evidence=evidence,
        formatting=formatting,
        language=language,
        academic_tone=tone,
        overall=overall,
    )


def _score_for_labels(items: list[ChecklistItem], labels: set[str]) -> int:
    matched = [item.score for item in items if item.label in labels]
    if not matched:
        return 0
    return int(round(sum(matched) / len(matched)))


def _recommendations(issues: list[ReviewIssue], passed: bool) -> list[str]:
    recs = [issue.suggested_fix for issue in issues]
    if passed:
        recs.append("Proceed to citation generation after minor polish.")
    else:
        recs.append("Send to Revision Engine to address high-severity issues before delivery.")
    return recs


def _section_present(content: str, title: str) -> bool:
    return title.lower() in content.lower()


def _pick_section_title(titles: list[str], keywords: tuple[str, ...]) -> str:
    for title in titles:
        lowered = title.lower()
        if any(keyword in lowered for keyword in keywords):
            return title
    for title in titles:
        if title.lower() != "references":
            return title
    return "Document"


def section_titles(blueprint: dict[str, Any]) -> list[str]:
    titles = [str(item.get("title") or "") for item in (blueprint.get("sections") or []) if item.get("title")]
    if titles:
        return titles
    return [str(title) for title in (blueprint.get("writing_queue") or []) if str(title).strip()]
