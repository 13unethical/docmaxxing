"""Tests for the Blueprint Engine architecture."""

from __future__ import annotations

import pytest

from services.assignment_pipeline.models import PipelineStage
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project.service import ProjectService
from services.blueprint_engine import BlueprintEngineService, MockBlueprintEngine
from services.blueprint_engine.models import BlueprintEngineInput, SectionCompletionStatus
from services.research_engine import ResearchEngineService
from tests.assignment_helpers import prepare_project_for_research


def _requirement() -> dict:
    return {
        "assignment_type": "Essay",
        "title": "Digital Transformation in Higher Education",
        "word_count": 2500,
        "citation_style": "APA 7",
        "required_sections": ["Introduction", "Literature Review", "Critical Analysis", "Conclusion", "References"],
        "minimum_sources": 12,
        "difficulty": "★★★★☆",
    }


def _research_plan() -> dict:
    return {
        "assignment_topic": "Digital Transformation in Higher Education",
        "writing_objective": "Critically evaluate digital transformation in universities.",
        "main_research_question": "To what extent does evidence support current understanding?",
        "writing_tone": "Formal, objective, and evidence-led academic prose",
        "estimated_academic_sources": 12,
        "estimated_completion_time": "10–13 hours",
        "required_theories": ["Stakeholder theory", "Institutional theory"],
        "section_list": [
            {"title": "Introduction", "purpose": "Introduce the research question.", "estimated_words": 180},
            {"title": "Literature Review", "purpose": "Map scholarship.", "estimated_words": 450},
            {"title": "Critical Analysis", "purpose": "Compare theories.", "estimated_words": 650},
            {"title": "Discussion", "purpose": "Synthesise implications.", "estimated_words": 450},
            {"title": "Conclusion", "purpose": "Answer the research question.", "estimated_words": 220},
            {"title": "References", "purpose": "Document sources.", "estimated_words": 120},
        ],
    }


def test_blueprint_engine_only_accepts_requirement_and_research_plan():
    engine = MockBlueprintEngine()
    blueprint = engine.build_blueprint(
        BlueprintEngineInput(
            requirement_json=_requirement(),
            research_plan=_research_plan(),
            project_id="proj-1",
        )
    )
    assert blueprint.project_id == "proj-1"
    assert blueprint.total_target_sections == 6
    assert blueprint.total_target_words > 0
    assert blueprint.writing_queue == [
        "Introduction",
        "Literature Review",
        "Critical Analysis",
        "Discussion",
        "Conclusion",
    ]
    assert blueprint.word_distribution
    assert blueprint.citation_strategy
    assert blueprint.critical_analysis_locations
    assert blueprint.conclusion_goals


def test_section_blueprint_fields():
    blueprint = MockBlueprintEngine().build_blueprint(
        BlueprintEngineInput(requirement_json=_requirement(), research_plan=_research_plan())
    )
    intro = next(section for section in blueprint.sections if section.title == "Introduction")
    assert intro.id == "introduction"
    assert intro.objective
    assert intro.key_points
    assert intro.required_arguments
    assert intro.required_evidence
    assert intro.citation_target > 0
    assert intro.completion_status == SectionCompletionStatus.PENDING

    analysis = next(section for section in blueprint.sections if section.title == "Critical Analysis")
    assert "Advantages" in analysis.key_points
    assert "Counterargument" in analysis.key_points


def test_word_distribution_matches_sections():
    blueprint = MockBlueprintEngine().build_blueprint(
        BlueprintEngineInput(requirement_json=_requirement(), research_plan=_research_plan())
    )
    assert {entry.title: entry.estimated_words for entry in blueprint.word_distribution} == {
        section.title: section.estimated_words for section in blueprint.sections
    }


def test_project_run_blueprint_advances_pipeline():
    pipeline = AssignmentPipelineService()
    research = ResearchEngineService()
    blueprint = BlueprintEngineService()
    projects = ProjectService(pipeline=pipeline, research=research, blueprint=blueprint)
    bundle = projects.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}]
    )
    prepare_project_for_research(projects, bundle.project.id)
    projects.run_research(bundle.project.id)
    result = projects.run_blueprint(bundle.project.id)

    pipeline_state = pipeline.get_project(bundle.project.id)
    assert pipeline_state.current_stage == PipelineStage.WRITING
    assert result.writing_queue
    assert projects.get_blueprint(bundle.project.id).id == result.id


def test_run_blueprint_requires_research_plan():
    projects = ProjectService()
    bundle = projects.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}]
    )
    prepare_project_for_research(projects, bundle.project.id)
    with pytest.raises(ValueError):
        projects.run_blueprint(bundle.project.id)
