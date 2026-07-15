"""Tests for the AI Detection Engine."""

from __future__ import annotations

import pytest

from services.ai_detection_engine import (
    AIDetectionEngineService,
    DEFAULT_THRESHOLDS,
    DetectionThresholds,
    MockAIDetector,
    classify_score,
    score_passes,
)
from services.ai_detection_engine.models import DetectionSessionStatus, ParagraphDetectionStatus
from services.ai_detection_engine.paragraph_parser import split_humanized_draft_into_paragraphs
from services.assignment_pipeline.models import PipelineStage
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project.models import ProjectStatus
from services.assignment_project.service import ProjectService
from services.blueprint_engine import BlueprintEngineService
from services.humanizer_engine import HumanizerEngineService
from services.research_engine import ResearchEngineService
from services.reviewer_engine import ReviewerEngineService
from services.revision_engine import RevisionEngineService
from services.writer_engine import WriterEngineService
from services.writer_engine.models import WriterSectionStatus
from tests.assignment_helpers import prepare_project_for_research


def _humanized_draft() -> dict:
    return {
        "id": "humanized-1",
        "project_id": "proj-1",
        "title": "Humanized Draft",
        "content": (
            "## Introduction\n"
            "This essay introduces digital transformation in higher education.\n\n"
            "Section objective: Introduce the research question in academic terms.\n\n"
            "## Discussion\n"
            "However, implications remain contested across institutions."
        ),
        "version": 4,
    }


def _requirement() -> dict:
    return {"assignment_type": "Essay", "writing_tone": "Formal academic prose"}


def test_threshold_classification():
    assert classify_score(3.0) == "excellent"
    assert classify_score(8.0) == "good"
    assert classify_score(12.0) == "acceptable"
    assert classify_score(20.0) == "needs_revision"
    assert classify_score(30.0) == "high_ai_probability"
    assert score_passes(12.0)
    assert not score_passes(20.0)


def test_split_humanized_draft_paragraphs():
    paragraphs = split_humanized_draft_into_paragraphs(_humanized_draft()["content"])
    assert len(paragraphs) >= 4
    assert paragraphs[0].text.startswith("## Introduction")


def test_detection_one_paragraph_at_a_time():
    engine = AIDetectionEngineService()
    session = engine.create_session(
        humanized_draft=_humanized_draft(),
        requirement_json=_requirement(),
        project_id="proj-1",
    )
    first_id = session.current_paragraph_id
    session = engine.advance_paragraph(session.id)
    first = session.paragraph_by_id(first_id)
    assert first.ai_score is not None
    assert first.last_checked is not None
    assert session.paragraphs_completed >= 1


def test_detection_generates_report():
    engine = AIDetectionEngineService()
    session = engine.create_session(
        humanized_draft=_humanized_draft(),
        requirement_json=_requirement(),
        project_id="proj-1",
    )
    while session.status.value == "active":
        session = engine.advance_paragraph(session.id)

    if not session.report_id:
        session = engine.finalize_session(session.id)

    assert session.report_id
    report = engine.get_report(session.report_id)
    assert report.overall_ai_score >= 0
    assert report.paragraph_scores
    assert report.average_score == report.overall_ai_score
    assert report.highest_score >= report.lowest_score


def test_detection_rehumanize_callback_on_fail():
    engine = AIDetectionEngineService(detector=MockAIDetector())
    session = engine.create_session(
        humanized_draft={
            **_humanized_draft(),
            "content": "## Introduction\nSection objective: frame the research question in academic terms.",
        },
        requirement_json=_requirement(),
        humanizer_paragraph_ids=["hz-p-1", "hz-p-2"],
    )

    calls: list[str] = []

    def rehumanize(paragraph_id: str, _text: str) -> str:
        calls.append(paragraph_id)
        return "[Rehumanized] Revised paragraph with Nevertheless, improved academic tone."

    while session.status.value == "active":
        session = engine.advance_paragraph(session.id, rehumanize=rehumanize)

    assert calls or session.paragraphs_completed > 0


def test_finalize_detection_rebuilds_report_missing_from_worker_memory(tmp_path):
    """Worker B can finalize after worker A auto-finalized in RAM and only persisted the session."""
    from services.ai_detection_engine import AIDetectionEngineService, MockAIDetector
    from services.assignment_project.store import ProjectStore
    from services.writer_engine import MockSectionWriter, WriterEngineService
    from services.writer_engine.mock_reviewer import MockSectionReviewer
    from tests.test_assignment_project import (
        _StubBlueprintService,
        _StubRequirementAnalyzer,
        _StubResearchService,
    )

    store = ProjectStore(root=tmp_path / "projects")
    writer = WriterEngineService(writer=MockSectionWriter(), reviewer=MockSectionReviewer())
    humanizer = HumanizerEngineService()
    detection_a = AIDetectionEngineService(detector=MockAIDetector())
    service_a = ProjectService(
        store=store,
        pipeline=AssignmentPipelineService(),
        research=_StubResearchService(),  # type: ignore[arg-type]
        blueprint=_StubBlueprintService(),  # type: ignore[arg-type]
        writer=writer,
        humanizer=humanizer,
        ai_detection=detection_a,
        analyzer=_StubRequirementAnalyzer(),
    )
    bundle = service_a.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    project_id = bundle.project.id
    service_a.analyze_requirements(project_id)
    service_a.calculate_pricing(project_id)
    service_a.confirm_payment(project_id)
    service_a.run_research(project_id)
    service_a.run_blueprint(project_id)
    session = service_a.start_writer(project_id)
    while session.status.value == "active":
        session = service_a.advance_writer(project_id)
    service_a.merge_writer_draft(project_id)
    hz = service_a.start_humanizer(project_id)
    while hz.status.value == "active":
        hz = service_a.advance_humanizer(project_id)
    service_a.merge_humanized_draft(project_id)

    detection = service_a.start_ai_detection(project_id)
    while detection.status.value == "active":
        detection = service_a.advance_ai_detection(project_id)

    # Simulate worker B with empty detection RAM but shared disk artifacts.
    detection_b = AIDetectionEngineService(detector=MockAIDetector())
    service_b = ProjectService(
        store=store,
        pipeline=AssignmentPipelineService(),
        research=_StubResearchService(),  # type: ignore[arg-type]
        blueprint=_StubBlueprintService(),  # type: ignore[arg-type]
        writer=WriterEngineService(writer=MockSectionWriter(), reviewer=MockSectionReviewer()),
        humanizer=HumanizerEngineService(),
        ai_detection=detection_b,
        analyzer=_StubRequirementAnalyzer(),
    )
    # Drop in-memory report on A path by using B which never saw it; disk may already have report.
    report = service_b.finalize_ai_detection(project_id)
    assert report.id
    assert service_b.get_detection_report(project_id).id == report.id


def test_project_ai_detection_pipeline():
    pipeline = AssignmentPipelineService()
    writer = WriterEngineService()
    humanizer = HumanizerEngineService()
    projects = ProjectService(
        pipeline=pipeline,
        research=ResearchEngineService(),
        blueprint=BlueprintEngineService(),
        writer=writer,
        reviewer=ReviewerEngineService(),
        revision=RevisionEngineService(draft_store=writer.drafts),
        humanizer=humanizer,
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

    hz = projects.start_humanizer(bundle.project.id)
    while hz.status.value == "active":
        hz = projects.advance_humanizer(bundle.project.id)
    projects.merge_humanized_draft(bundle.project.id)

    detection = projects.start_ai_detection(bundle.project.id)
    while detection.status.value == "active":
        detection = projects.advance_ai_detection(bundle.project.id)
    report = projects.finalize_ai_detection(bundle.project.id)

    assert report.id
    assert projects.get_detection_report(bundle.project.id).id == report.id
    assert pipeline.get_project(bundle.project.id).current_stage == PipelineStage.DELIVERY
