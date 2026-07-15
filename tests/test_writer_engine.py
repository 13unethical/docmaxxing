"""Tests for the Writer Engine architecture."""

from __future__ import annotations

import pytest

from services.assignment_pipeline.models import PipelineStage
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project.service import ProjectService
from services.blueprint_engine import BlueprintEngineService
from services.research_engine import ResearchEngineService
from services.writer_engine import MockSectionWriter, WriterEngineService
from services.writer_engine.mock_reviewer import MockSectionReviewer
from services.writer_engine.models import WriterEngineInput, WriterSectionStatus, WriterSessionStatus
from tests.assignment_helpers import prepare_project_for_research


def _writer_service() -> WriterEngineService:
    return WriterEngineService(writer=MockSectionWriter(), reviewer=MockSectionReviewer())


def _inputs() -> dict:
    requirement = {
        "assignment_type": "Essay",
        "title": "Digital Transformation in Higher Education",
        "word_count": 2500,
        "citation_style": "APA 7",
    }
    research_plan = {
        "assignment_topic": "Digital Transformation in Higher Education",
        "writing_tone": "Formal academic prose",
        "section_list": [
            {"title": "Introduction", "purpose": "Introduce the research question.", "estimated_words": 180},
            {"title": "Literature Review", "purpose": "Map scholarship.", "estimated_words": 450},
            {"title": "Critical Analysis", "purpose": "Compare theories.", "estimated_words": 650},
            {"title": "Discussion", "purpose": "Synthesise implications.", "estimated_words": 450},
            {"title": "Conclusion", "purpose": "Answer the research question.", "estimated_words": 220},
        ],
    }
    blueprint = {
        "writing_order": ["introduction", "literature-review", "critical-analysis", "discussion", "conclusion"],
        "sections": [
            {"id": "introduction", "title": "Introduction", "objective": "Introduce the research question.", "estimated_words": 180, "key_points": ["Background", "Thesis Statement", "Scope"]},
            {"id": "literature-review", "title": "Literature Review", "objective": "Map scholarship.", "estimated_words": 450, "key_points": ["Theme mapping"]},
            {"id": "critical-analysis", "title": "Critical Analysis", "objective": "Compare theories.", "estimated_words": 650, "key_points": ["Advantages", "Disadvantages", "Evidence", "Counterargument"]},
            {"id": "discussion", "title": "Discussion", "objective": "Synthesise implications.", "estimated_words": 450, "key_points": ["Synthesis"]},
            {"id": "conclusion", "title": "Conclusion", "objective": "Answer the research question.", "estimated_words": 220, "key_points": ["Direct answer"]},
        ],
    }
    return {"requirement_json": requirement, "research_plan": research_plan, "blueprint": blueprint}


def test_writer_engine_only_accepts_required_inputs():
    service = _writer_service()
    session = service.create_session(project_id="proj-1", **_inputs())
    assert session.project_id == "proj-1"
    assert len(session.sections) == 5
    assert session.current_section_id == "introduction"
    assert session.remaining_section_ids[0] == "introduction"


def test_writer_processes_one_section_per_advance():
    service = _writer_service()
    session = service.create_session(**_inputs())

    session = service.advance_section(session.id)
    intro = session.section_by_id("introduction")
    assert intro.status == WriterSectionStatus.COMPLETED
    assert intro.generated_text
    assert intro.last_review is not None
    assert intro.last_review.passed is True
    assert session.current_section_id == "literature-review"
    assert session.progress == 20


def test_revision_only_regenerates_failed_section():
    service = _writer_service()
    session = service.create_session(**_inputs())

    service.advance_section(session.id)  # Introduction
    session = service.advance_section(session.id)  # Literature Review
    session = service.advance_section(session.id)  # Critical Analysis fails then auto-revises

    analysis = session.section_by_id("critical-analysis")
    assert analysis.status == WriterSectionStatus.COMPLETED
    assert analysis.revision_count >= 1
    assert "[REVISED]" in analysis.generated_text
    assert analysis.last_review is not None
    assert analysis.last_review.passed is True

    intro = session.section_by_id("introduction")
    assert intro.generated_text
    assert intro.status == WriterSectionStatus.COMPLETED


def test_merge_creates_draft_after_all_sections_complete():
    service = _writer_service()
    session = service.create_session(**_inputs())

    while session.status.value == "active":
        if session.section_by_id(session.current_section_id or "").status == WriterSectionStatus.REVISION:
            session = service.revise_section(session.id, session.current_section_id)
        else:
            session = service.advance_section(session.id)

    draft = service.merge_draft(session.id, title="Test Draft")
    assert draft.title == "Test Draft"
    assert draft.content
    assert draft.total_words > 0
    assert "Introduction" in draft.content
    assert session.status == WriterSessionStatus.MERGED


def test_project_writer_flow_advances_pipeline():
    pipeline = AssignmentPipelineService()
    projects = ProjectService(
        pipeline=pipeline,
        research=ResearchEngineService(),
        blueprint=BlueprintEngineService(),
        writer=_writer_service(),
    )
    bundle = projects.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}]
    )
    prepare_project_for_research(projects, bundle.project.id)
    projects.run_research(bundle.project.id)
    projects.run_blueprint(bundle.project.id)
    session = projects.start_writer(bundle.project.id)

    while session.status.value == "active":
        if session.current_section_id and session.section_by_id(session.current_section_id).status == WriterSectionStatus.REVISION:
            session = projects.revise_writer_section(bundle.project.id, session.current_section_id)
        else:
            session = projects.advance_writer(bundle.project.id)

    draft = projects.merge_writer_draft(bundle.project.id)
    assert draft.content
    assert session.status.value in {"completed", "merged"}


def test_create_session_requires_blueprint_queue():
    service = _writer_service()
    with pytest.raises(ValueError):
        service.create_session(
            requirement_json={},
            research_plan={},
            blueprint={"sections": [], "writing_order": []},
        )


def test_parse_section_json_recovers_unescaped_draft_quotes():
    from services.writer_engine.llm_writer import _parse_section_json

    fenced = (
        '```json\n'
        '{"title":"Intro","purpose":"P","target_words":10,'
        '"draft":"Hello","citations_used":[],"warnings":[],'
        '"generation_time":0,"model_used":"x"}\n```'
    )
    assert _parse_section_json(fenced)["draft"] == "Hello"

    broken = (
        '{\n'
        '  "title": "Intro",\n'
        '  "purpose": "Set context",\n'
        '  "target_words": 200,\n'
        '  "draft": "Said "hello" then continued.",\n'
        '  "citations_used": ["[Smith, 2021]"],\n'
        '  "warnings": [],\n'
        '  "generation_time": 0,\n'
        '  "model_used": "claude"\n'
        '}'
    )
    parsed = _parse_section_json(broken)
    assert 'hello' in parsed["draft"]
    assert parsed["citations_used"] == ["[Smith, 2021]"]
    assert any("Recovered malformed" in w for w in parsed["warnings"])


def test_parse_section_json_trims_overlong_draft_to_target_words():
    from services.writer_engine.llm_writer import _parse_section_json

    draft = " ".join(f"word{i}" for i in range(200))
    parsed = _parse_section_json(
        '{"title":"Body","purpose":"P","target_words":80,'
        f'"draft":"{draft}","citations_used":[],"warnings":[],'
        '"generation_time":0,"model_used":"x"}'
    )
    assert len(parsed["draft"].split()) <= 93
    assert any("Trimmed section" in warning for warning in parsed["warnings"])
