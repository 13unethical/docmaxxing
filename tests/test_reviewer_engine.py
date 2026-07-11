"""Tests for the Academic Reviewer Engine."""

from __future__ import annotations

import pytest

from services.assignment_pipeline.models import PipelineStage
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project.service import ProjectService
from services.blueprint_engine import BlueprintEngineService
from services.research_engine import ResearchEngineService
from services.reviewer_engine import MockAcademicReviewer, ReviewerEngineService
from services.reviewer_engine.models import ReviewEngineInput
from services.writer_engine import WriterEngineService
from services.writer_engine.models import WriterSectionStatus
from tests.assignment_helpers import prepare_project_for_research


def _inputs() -> dict:
    requirement = {
        "assignment_type": "Essay",
        "title": "Digital Transformation in Higher Education",
        "word_count": 2500,
        "citation_style": "APA 7",
        "required_sections": ["Introduction", "Literature Review", "Critical Analysis", "Discussion", "Conclusion"],
        "rubric": [{"criterion": "Critical analysis", "weight": "30%", "description": "Depth of argument"}],
        "learning_outcomes": ["Demonstrate critical analysis"],
    }
    research_plan = {
        "writing_tone": "Formal academic prose",
        "critical_analysis_locations": ["Critical Analysis", "Discussion"],
        "main_research_question": "To what extent does evidence support current understanding?",
    }
    blueprint = {
        "total_target_words": 2500,
        "writing_queue": ["Introduction", "Literature Review", "Critical Analysis", "Discussion", "Conclusion"],
        "sections": [
            {"id": "introduction", "title": "Introduction", "objective": "Introduce the research question.", "estimated_words": 180},
            {"id": "critical-analysis", "title": "Critical Analysis", "objective": "Compare theories.", "estimated_words": 650},
            {"id": "discussion", "title": "Discussion", "objective": "Synthesise implications.", "estimated_words": 450},
            {"id": "conclusion", "title": "Conclusion", "objective": "Answer the research question.", "estimated_words": 220},
        ],
    }
    draft = {
        "title": "Digital Transformation in Higher Education",
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
    return {
        "requirement_json": requirement,
        "research_plan": research_plan,
        "blueprint": blueprint,
        "draft": draft,
    }


def test_reviewer_only_accepts_required_inputs():
    report = MockAcademicReviewer().review(ReviewEngineInput(project_id="proj-1", **_inputs()))
    assert report.project_id == "proj-1"
    assert report.overall_score >= 0
    assert report.requirement_checklist
    assert report.rubric_checklist
    assert report.quality_scores.overall == report.overall_score
    assert report.issues
    assert report.issues[0].issue_id
    assert report.issues[0].suggested_fix
    assert report.recommendations


def test_reviewer_never_modifies_draft_content():
    payload = _inputs()
    original = payload["draft"]["content"]
    MockAcademicReviewer().review(ReviewEngineInput(**payload))
    assert payload["draft"]["content"] == original


def test_issue_structure():
    report = MockAcademicReviewer().review(ReviewEngineInput(**_inputs()))
    issue = report.issues[0]
    assert issue.category
    assert issue.severity.value in {"low", "medium", "high", "critical"}
    assert issue.section
    assert issue.description
    assert issue.suggested_fix


def test_project_academic_review_advances_pipeline():
    pipeline = AssignmentPipelineService()
    projects = ProjectService(
        pipeline=pipeline,
        research=ResearchEngineService(),
        blueprint=BlueprintEngineService(),
        writer=WriterEngineService(),
        reviewer=ReviewerEngineService(),
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

    assert report.overall_score > 0
    assert projects.get_review_report(bundle.project.id).id == report.id
    assert pipeline.get_project(bundle.project.id).current_stage == PipelineStage.CITATION_GENERATION


def test_review_requires_draft():
    projects = ProjectService(reviewer=ReviewerEngineService())
    bundle = projects.create_project(files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}])
    with pytest.raises(KeyError):
        projects.run_academic_review(bundle.project.id)
