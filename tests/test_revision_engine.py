"""Tests for the Revision Engine."""

from __future__ import annotations

import pytest

from services.assignment_pipeline.models import PipelineStage
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project.models import ProjectStatus
from services.assignment_project.service import ProjectService
from services.blueprint_engine import BlueprintEngineService
from services.research_engine import ResearchEngineService
from services.revision_engine import MockSectionReviser, RevisionEngineInput, RevisionEngineService
from services.revision_engine.models import MAX_REVISION_ATTEMPTS
from services.reviewer_engine import MockAcademicReviewer, ReviewerEngineService
from services.reviewer_engine.models import ReviewEngineInput
from services.writer_engine import WriterEngineService
from services.writer_engine.models import WriterSectionStatus
from tests.assignment_helpers import prepare_project_for_research


def _revision_inputs() -> dict:
    requirement = {
        "assignment_type": "Essay",
        "title": "Digital Transformation",
        "word_count": 2500,
        "citation_style": "APA 7",
        "required_sections": ["Introduction", "Literature Review", "Critical Analysis", "Discussion", "Conclusion"],
        "rubric": [{"criterion": "Critical analysis", "weight": "30%", "description": "Depth"}],
    }
    research_plan = {
        "writing_tone": "Formal academic prose",
        "critical_analysis_locations": ["Critical Analysis", "Discussion"],
    }
    blueprint = {
        "total_target_words": 2500,
        "writing_queue": ["Introduction", "Literature Review", "Critical Analysis", "Discussion", "Conclusion"],
        "sections": [
            {"id": "introduction", "title": "Introduction", "objective": "Introduce topic.", "estimated_words": 180},
            {"id": "literature-review", "title": "Literature Review", "objective": "Survey sources.", "estimated_words": 500},
            {"id": "critical-analysis", "title": "Critical Analysis", "objective": "Compare theories.", "estimated_words": 650},
            {"id": "discussion", "title": "Discussion", "objective": "Synthesise.", "estimated_words": 450},
            {"id": "conclusion", "title": "Conclusion", "objective": "Resolve question.", "estimated_words": 220},
        ],
    }
    draft = {
        "id": "draft-1",
        "project_id": "proj-1",
        "session_id": "session-1",
        "title": "Digital Transformation",
        "content": (
            "## Introduction\nEssay on digital transformation.\n\n"
            "## Literature Review\nEvidence and source coverage.\n\n"
            "## Critical Analysis\nArgument development with objective analysis.\n\n"
            "## Discussion\nHowever, implications remain.\n\n"
            "## Conclusion\nConclusion resolves the research question."
        ),
        "total_words": 120,
        "version": 1,
    }
    review_report = {
        "passed": False,
        "overall_score": 68,
        "issues": [
            {
                "issue_id": "issue-critical-analysis-1",
                "category": "Critical Analysis",
                "severity": "high",
                "section": "Discussion",
                "description": "No comparison between competing theories.",
                "suggested_fix": "Add comparison before conclusion.",
            },
            {
                "issue_id": "issue-counterargument-1",
                "category": "Counterarguments",
                "severity": "medium",
                "section": "Critical Analysis",
                "description": "Counterarguments are not explicitly evaluated.",
                "suggested_fix": "Introduce one counterargument and rebuttal.",
            },
            {
                "issue_id": "issue-evidence-1",
                "category": "Evidence Usage",
                "severity": "medium",
                "section": "Literature Review",
                "description": "Evidence weighting is uneven across themes.",
                "suggested_fix": "Balance peer-reviewed sources across themes.",
            },
        ],
    }
    return {
        "requirement_json": requirement,
        "research_plan": research_plan,
        "blueprint": blueprint,
        "draft": draft,
        "review_report": review_report,
    }


def test_revision_only_fixes_reported_sections():
    writer = WriterEngineService()
    revision = RevisionEngineService(draft_store=writer.drafts)
    payload = _revision_inputs()
    original = payload["draft"]["content"]

    result = revision.revise_draft(project_id="proj-1", **payload)

    assert result.new_version == 2
    assert result.previous_version == 1
    assert result.changes
    assert len(result.sections_revised) >= 2
    assert "comparison" in result.draft["content"].lower()
    assert original != result.draft["content"]
    assert "## Introduction" in result.draft["content"]
    assert result.draft["content"].count("## Introduction") == 1


def test_revision_never_rewrites_unrelated_sections():
    payload = _revision_inputs()
    intro = "## Introduction\nEssay on digital transformation."
    result = MockSectionReviser().revise(RevisionEngineInput(project_id="proj-1", **payload))
    assert intro in result.draft["content"]


def test_revision_creates_version_history():
    writer = WriterEngineService()
    revision = RevisionEngineService(draft_store=writer.drafts)
    payload = _revision_inputs()

    revision.revise_draft(project_id="proj-1", **payload)
    history = revision.get_history("proj-1")

    assert history.current_version == 2
    assert len(history.versions) == 2
    assert history.versions[0].version == 1
    assert history.versions[1].version == 2
    assert history.versions[0].changes


def test_revision_handles_flat_humanized_document_blob():
    payload = _revision_inputs()
    payload["draft"]["content"] = (
        "This introduction frames the assignment and explains the research focus. "
        "However, the literature remains uneven and requires stronger comparison. "
        "The analysis develops the argument with objective commentary. "
        "In conclusion, the paper summarises implications for practice."
    )
    payload["blueprint"]["sections"] = [
        {"id": "intro", "title": "Introduction", "objective": "Open.", "estimated_words": 120},
        {"id": "body-1", "title": "Body Paragraph 1", "objective": "Develop.", "estimated_words": 180},
        {"id": "conclusion", "title": "Conclusion", "objective": "Close.", "estimated_words": 100},
    ]

    result = MockSectionReviser().revise(RevisionEngineInput(project_id="proj-1", **payload))

    assert result.sections_revised
    assert result.draft["content"] != payload["draft"]["content"]


def test_revision_resolves_nonstandard_section_titles():
    payload = _revision_inputs()
    payload["blueprint"]["sections"] = [
        {"id": "entry-1", "title": "Journal Entry 1", "objective": "Reflect.", "estimated_words": 400},
        {"id": "entry-2", "title": "Journal Entry 2", "objective": "Analyse.", "estimated_words": 400},
    ]
    payload["draft"]["content"] = (
        "## Journal Entry 1\nInitial reflection on the module themes.\n\n"
        "## Journal Entry 2\nHowever, the evidence remains limited."
    )
    payload["review_report"]["issues"] = [
        {
            "issue_id": "issue-critical-analysis-1",
            "category": "Critical Analysis",
            "severity": "high",
            "section": "Discussion",
            "description": "No comparison between competing theories.",
            "suggested_fix": "Add comparison before conclusion.",
        }
    ]

    result = MockSectionReviser().revise(RevisionEngineInput(project_id="proj-1", **payload))

    assert result.sections_revised
    assert "comparison" in result.draft["content"].lower() or "[Revision:" in result.draft["content"]


def test_revision_rejects_passed_review():
    revision = RevisionEngineService()
    payload = _revision_inputs()
    payload["review_report"]["passed"] = True
    with pytest.raises(ValueError, match="revision is not required"):
        revision.revise_draft(**payload)


class _AlwaysFailReviewer:
    def review(self, payload: ReviewEngineInput):
        report = MockAcademicReviewer().review(payload)
        report.passed = False
        return report


def test_project_revision_loop_and_manual_review():
    pipeline = AssignmentPipelineService()
    writer = WriterEngineService()
    revision = RevisionEngineService(draft_store=writer.drafts)
    reviewer = ReviewerEngineService(reviewer=_AlwaysFailReviewer())
    projects = ProjectService(
        pipeline=pipeline,
        research=ResearchEngineService(),
        blueprint=BlueprintEngineService(),
        writer=writer,
        reviewer=reviewer,
        revision=revision,
    )
    bundle = projects.create_project(files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}])
    prepare_project_for_research(projects, bundle.project.id)
    projects.run_research(bundle.project.id)
    projects.run_blueprint(bundle.project.id)
    session = projects.start_writer(bundle.project.id)
    while session.status.value == "active":
        if session.current_section_id and session.section_by_id(session.current_section_id).status == WriterSectionStatus.REVISION:
            session = projects.revise_writer_section(bundle.project.id, session.current_section_id)
        else:
            session = projects.advance_writer(bundle.project.id)
    projects.merge_writer_draft(bundle.project.id)

    report = projects.run_academic_review(bundle.project.id)
    assert not report.passed

    result = projects.run_revision(bundle.project.id)
    assert result.new_version == 2
    history = projects.get_revision_history(bundle.project.id)
    assert history.revision_attempts == 1

    pipeline_project = pipeline.get_project(bundle.project.id)
    assert pipeline_project.stage_state(PipelineStage.REVISION).status.value == "completed"

    for _ in range(MAX_REVISION_ATTEMPTS - 1):
        projects.run_revision(bundle.project.id)

    with pytest.raises(ValueError, match="Maximum automatic revision attempts"):
        projects.run_revision(bundle.project.id)

    projects.run_academic_review(bundle.project.id)
    project = projects.get_project(bundle.project.id).project
    assert project.status == ProjectStatus.NEEDS_MANUAL_REVIEW
    history = projects.get_revision_history(bundle.project.id)
    assert history.needs_manual_review
