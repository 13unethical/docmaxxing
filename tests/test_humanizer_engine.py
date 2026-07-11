"""Tests for the Humanizer Engine."""

from __future__ import annotations

import pytest

from services.assignment_pipeline.models import PipelineStage
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project.service import ProjectService
from services.blueprint_engine import BlueprintEngineService
from services.humanizer_engine import HumanizerEngineService
from services.humanizer_engine.mock_humanizer import MockTextHumanizer
from services.humanizer_engine.mock_validator import MockParagraphValidator
from services.humanizer_engine.models import HumanizerParagraph, HumanizerParagraphStatus
from services.humanizer_engine.paragraph_parser import split_draft_into_paragraphs
from services.research_engine import ResearchEngineService
from services.reviewer_engine import ReviewerEngineService
from services.revision_engine import RevisionEngineService
from services.writer_engine import WriterEngineService
from services.writer_engine.models import WriterSectionStatus
from tests.assignment_helpers import prepare_project_for_research


def _draft() -> dict:
    return {
        "id": "draft-1",
        "project_id": "proj-1",
        "session_id": "session-1",
        "title": "Assignment Draft",
        "content": (
            "## Introduction\n"
            "This essay introduces digital transformation in higher education.\n\n"
            "Section objective: Introduce the research question.\n\n"
            "## Literature Review\n"
            "Evidence from peer-reviewed sources (Smith, 2021) supports the argument.\n\n"
            "## Discussion\n"
            "However, implications remain contested across institutions."
        ),
        "total_words": 40,
        "version": 3,
    }


def _requirement() -> dict:
    return {
        "assignment_type": "Essay",
        "title": "Digital Transformation",
        "citation_style": "APA 7",
        "writing_tone": "Formal academic prose",
    }


def _blueprint() -> dict:
    return {
        "academic_tone": "Formal academic prose",
        "sections": [
            {"id": "introduction", "title": "Introduction"},
            {"id": "literature-review", "title": "Literature Review"},
            {"id": "discussion", "title": "Discussion"},
        ],
    }


def test_split_draft_into_paragraphs():
    paragraphs = split_draft_into_paragraphs(_draft()["content"], _blueprint())
    assert 3 <= len(paragraphs) <= 10
    assert any(p.original_text.startswith("## Introduction") for p in paragraphs)
    assert any(p.section == "Literature Review" for p in paragraphs)


def test_group_paragraphs_into_batches_merges_small_chunks():
    from services.humanizer_engine.paragraph_parser import group_paragraphs_into_batches

    raw = [
        HumanizerParagraph(paragraph_id="p-1", section="Intro", original_text="## Introduction"),
        HumanizerParagraph(paragraph_id="p-2", section="Intro", original_text="Short line."),
        HumanizerParagraph(
            paragraph_id="p-3",
            section="Intro",
            original_text=" ".join(["word"] * 120),
        ),
    ]
    batches = group_paragraphs_into_batches(raw)
    body_batches = [batch for batch in batches if not batch.original_text.startswith("## ")]
    assert len(body_batches) == 1
    assert "Short line." in body_batches[0].original_text


def test_humanizer_processes_one_paragraph_at_a_time():
    engine = HumanizerEngineService()
    session = engine.create_session(
        draft=_draft(),
        requirement_json=_requirement(),
        blueprint=_blueprint(),
        project_id="proj-1",
    )
    assert session.current_paragraph_id
    first_id = session.current_paragraph_id

    session = engine.advance_paragraph(session.id)
    first = session.paragraph_by_id(first_id)
    assert first.status == HumanizerParagraphStatus.COMPLETED
    assert first.humanized_text
    assert first.ai_score_before is not None
    assert first.ai_score_after is not None
    assert session.progress > 0


def test_humanizer_creates_new_draft_version_without_overwriting_source():
    engine = HumanizerEngineService()
    session = engine.create_session(
        draft=_draft(),
        requirement_json=_requirement(),
        blueprint=_blueprint(),
        project_id="proj-1",
    )
    while session.status.value == "active":
        session = engine.advance_paragraph(session.id)

    humanized = engine.merge_humanized_draft(session.id, title="Humanized Draft")
    assert humanized.version == 4
    assert humanized.source_version == 3
    assert humanized.content != _draft()["content"]
    assert humanized.paragraphs_processed == len(session.paragraphs)


def test_paragraph_validation_retries_up_to_three_times():
    engine = HumanizerEngineService()
    session = engine.create_session(
        draft={
            **_draft(),
            "content": "## Introduction\nSection objective: frame the research question in academic terms.",
        },
        requirement_json=_requirement(),
        blueprint=_blueprint(),
    )
    while session.status.value == "active":
        session = engine.advance_paragraph(session.id)
        paragraph = session.paragraph_by_id(session.current_paragraph_id) if session.current_paragraph_id else session.paragraphs[-1]
        if "objective" in paragraph.original_text.lower() and paragraph.attempts > 0:
            break
    paragraph = next(p for p in session.paragraphs if "objective" in p.original_text.lower())
    assert paragraph.attempts >= 1
    assert paragraph.status in {
        HumanizerParagraphStatus.COMPLETED,
        HumanizerParagraphStatus.REVISION,
        HumanizerParagraphStatus.VALIDATING,
    }


def test_humanizer_session_completes_after_max_validation_attempts():
    engine = HumanizerEngineService(
        humanizer=MockTextHumanizer(),
        validator=MockParagraphValidator(),
    )
    session = engine.create_session(
        draft={
            **_draft(),
            "content": "## Introduction\nSection objective: frame the research question in academic terms.",
        },
        requirement_json=_requirement(),
        blueprint=_blueprint(),
    )
    guard = 0
    while session.status.value == "active" and guard < 50:
        session = engine.advance_paragraph(session.id)
        guard += 1
    assert session.status.value == "completed"
    assert all(p.status == HumanizerParagraphStatus.COMPLETED for p in session.paragraphs)


def test_project_humanization_advances_pipeline():
    pipeline = AssignmentPipelineService()
    writer = WriterEngineService()
    projects = ProjectService(
        pipeline=pipeline,
        research=ResearchEngineService(),
        blueprint=BlueprintEngineService(),
        writer=writer,
        reviewer=ReviewerEngineService(),
        revision=RevisionEngineService(draft_store=writer.drafts),
        humanizer=HumanizerEngineService(),
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

    hz_session = projects.start_humanizer(bundle.project.id)
    while hz_session.status.value == "active":
        hz_session = projects.advance_humanizer(bundle.project.id)
    humanized = projects.merge_humanized_draft(bundle.project.id)

    assert humanized.version >= 2
    assert projects.get_humanized_draft(bundle.project.id).id == humanized.id
    assert pipeline.get_project(bundle.project.id).current_stage == PipelineStage.AI_DETECTION
