"""Tests for the Research Engine architecture."""

from __future__ import annotations

import pytest

from services.assignment_pipeline.models import PipelineStage
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project.service import ProjectService
from services.research_engine import MockResearchEngine, ResearchEngineService
from services.research_engine.models import ParsedDocument, ResearchEngineInput
from services.research_engine.parsed_documents import build_parsed_documents
from tests.assignment_helpers import prepare_project_for_research, seed_analyzed_requirement


def _requirement() -> dict:
    return {
        "assignment_type": "Essay",
        "title": "Digital Transformation in Higher Education",
        "word_count": 2500,
        "citation_style": "APA 7",
        "required_sections": ["Introduction", "Literature Review", "Critical Analysis", "Conclusion", "References"],
        "minimum_sources": 12,
        "difficulty": "★★★★☆",
        "learning_outcomes": ["Demonstrate critical analysis of academic literature"],
        "missing_information": ["Reading materials not attached"],
    }


def _parsed_docs() -> list[ParsedDocument]:
    return [
        ParsedDocument(
            id="doc-1",
            file_id="file-1",
            file_type="assignment_brief",
            filename="brief.pdf",
            text="Critically evaluate digital transformation in universities using stakeholder theory.",
            word_count=10,
        )
    ]


def test_research_engine_only_accepts_requirement_and_parsed_documents():
    engine = MockResearchEngine()
    plan = engine.build_plan(
        ResearchEngineInput(
            requirement_json=_requirement(),
            parsed_documents=_parsed_docs(),
            project_id="proj-1",
        )
    )
    assert plan.project_id == "proj-1"
    assert plan.assignment_topic
    assert plan.main_research_question
    assert plan.section_list
    assert all(
        section.estimated_words > 0
        for section in plan.section_list
        if "reference" not in section.title.lower()
    )
    assert plan.estimated_academic_sources == 12
    assert plan.potential_risks
    assert plan.notes_for_writer
    assert "paragraph" not in " ".join(plan.notes_for_writer).lower()


def test_learning_journal_uses_explicit_section_budgets():
    requirement = {
        "assignment_type": "Learning Journal",
        "title": "Learning Journal",
        "word_count": 1200,
        "required_sections": [
            "Cover page",
            "Introduction",
            "Journal Entry 1",
            "Journal Entry 2",
            "Journal Entry 3",
            "Journal Entry 4",
            "Reflection",
            "References",
        ],
        "section_word_budgets": {
            "Introduction": 100,
            "Journal Entry 1": 200,
            "Journal Entry 2": 200,
            "Journal Entry 3": 200,
            "Journal Entry 4": 200,
            "Reflection": 300,
        },
    }
    plan = MockResearchEngine().build_plan(
        ResearchEngineInput(requirement_json=requirement, parsed_documents=_parsed_docs())
    )
    by_title = {section.title: section.estimated_words for section in plan.section_list}
    assert by_title["Cover page"] == 0
    assert by_title["References"] == 0
    assert by_title["Introduction"] == 100
    assert by_title["Journal Entry 1"] == 200
    assert by_title["Reflection"] == 300
    assert sum(by_title.values()) == 1200


def test_section_structure_has_title_purpose_and_words():
    plan = MockResearchEngine().build_plan(
        ResearchEngineInput(requirement_json=_requirement(), parsed_documents=_parsed_docs())
    )
    intro = next(section for section in plan.section_list if section.title == "Introduction")
    assert intro.purpose
    assert intro.estimated_words >= 80
    assert intro.description


def test_standalone_service_persists_plan():
    service = ResearchEngineService()
    plan = service.build_plan(requirement_json=_requirement(), parsed_documents=_parsed_docs())
    loaded = service.get_plan(plan.id)
    assert loaded.assignment_topic == plan.assignment_topic


def test_project_run_research_advances_pipeline():
    pipeline = AssignmentPipelineService()
    research = ResearchEngineService()
    projects = ProjectService(pipeline=pipeline, research=research)
    bundle = projects.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}]
    )
    prepare_project_for_research(projects, bundle.project.id)
    plan = projects.run_research(bundle.project.id)

    from services.assignment_pipeline.models import StageStatus

    pipeline_state = pipeline.get_project(bundle.project.id)
    assert pipeline_state.stage_state(PipelineStage.RESEARCH).status == StageStatus.COMPLETED
    assert plan.assignment_topic
    assert projects.get_research_plan(bundle.project.id).id == plan.id


def test_run_research_requires_analyzed_requirements():
    projects = ProjectService()
    bundle = projects.create_project()
    with pytest.raises(ValueError):
        projects.run_research(bundle.project.id)


def test_run_research_requires_payment_confirmation():
    projects = ProjectService()
    bundle = projects.create_project()
    seed_analyzed_requirement(projects, bundle.project.id)
    with pytest.raises(ValueError, match="Payment must be confirmed"):
        projects.run_research(bundle.project.id)


def test_build_parsed_documents_from_project_files():
    projects = ProjectService()
    bundle = projects.create_project(
        files=[
            {"file_type": "assignment_brief", "original_filename": "brief.pdf"},
            {"file_type": "rubric", "original_filename": "rubric.pdf"},
        ]
    )
    docs = build_parsed_documents(bundle.files)
    assert len(docs) == 2
    assert all(doc.text for doc in docs)
    assert docs[0].file_type == "assignment_brief"
