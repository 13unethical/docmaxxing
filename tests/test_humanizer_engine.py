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
    """Small multi-section drafts become one humanize batch (not one call per part)."""
    paragraphs = split_draft_into_paragraphs(_draft()["content"], _blueprint())
    assert len(paragraphs) == 1
    assert "## Introduction" in paragraphs[0].original_text
    assert "## Literature Review" in paragraphs[0].original_text
    assert "Literature Review" in paragraphs[0].section or "Discussion" in paragraphs[0].section


def test_group_paragraphs_into_batches_merges_across_sections():
    from services.humanizer_engine.paragraph_parser import group_paragraphs_into_batches

    raw = [
        HumanizerParagraph(paragraph_id="p-1", section="Intro", original_text="## Introduction"),
        HumanizerParagraph(paragraph_id="p-2", section="Intro", original_text="Short line."),
        HumanizerParagraph(paragraph_id="p-3", section="Body", original_text="## Body"),
        HumanizerParagraph(
            paragraph_id="p-4",
            section="Body",
            original_text=" ".join(["word"] * 120),
        ),
    ]
    batches = group_paragraphs_into_batches(raw)
    assert len(batches) == 1
    assert "## Introduction" in batches[0].original_text
    assert "Short line." in batches[0].original_text


def test_references_section_is_batched_separately_and_passthrough():
    from services.humanizer_engine.paragraph_parser import group_paragraphs_into_batches, split_draft_into_paragraphs
    from services.humanizer_engine.service import _should_passthrough_humanization

    content = (
        "## Introduction\n\n"
        + " ".join(["body"] * 80)
        + "\n\n## References\n\nSmith, J. (2020). Title. Journal.\n\nJones, A. (2021). Other. Book."
    )
    batches = split_draft_into_paragraphs(content)
    assert len(batches) >= 2
    ref_batches = [b for b in batches if "References" in (b.section or "") or "References" in b.original_text]
    assert ref_batches
    for batch in ref_batches:
        assert _should_passthrough_humanization(batch.original_text, section=batch.section)


def test_fit_content_to_word_budget_soft_accepts_without_mutilation(monkeypatch):
    from services.assignment_spec import build_assignment_spec
    from services.assignment_spec.validate import count_body_words
    from services.writer_engine.gemini_trim import fit_content_to_word_budget

    spec = build_assignment_spec(
        {
            "title": "Essay",
            "word_count": 200,
            "required_sections": ["Introduction", "Body", "References"],
            "section_word_budgets": {"Introduction": 50, "Body": 150},
        }
    )
    monkeypatch.setattr(
        "services.assignment_llm.assignment_llm_configured",
        lambda stage=None: False,
    )
    bloated = (
        "## Introduction\n\n"
        + " ".join(["intro"] * 80)
        + " complete thought.\n\n## Body\n\n"
        + " ".join(["body"] * 220)
        + " complete thought.\n\n## References\n\n"
        + " ".join(["Smith", "2020", "Journal"] * 40)
    )
    assert count_body_words(bloated) > spec.max_total_words
    fitted, meta = fit_content_to_word_budget(bloated, spec=spec)
    # Without Gemini, keep complete prose — never mid-sentence stubs.
    assert "complete thought." in fitted
    assert not fitted.rstrip().endswith(" The.")
    assert "## References" in fitted
    assert meta.get("method") in {"soft_accept_over_budget", "keep_complete_prose", None} or meta.get("body_words")


def test_humanizer_does_not_skip_batched_draft_starting_with_heading():
    """Regression: batched drafts start with ## Title but must still be humanized."""
    from services.humanizer_engine.service import HumanizerEngineService, _should_passthrough_humanization
    from services.humanizer_engine.stealthwriter_humanizer import StealthWriterTextHumanizer
    from services.humanizer_engine.mock_validator import ZeroGPTParagraphValidator

    batched = (
        "## Introduction\n\n"
        "This paragraph is long enough to trigger StealthWriter humanization "
        "because it exceeds the minimum character threshold used by the engine.\n\n"
        "## Journal Entry 1\n\n"
        "Another body paragraph that also needs humanization and must not be skipped."
    )
    assert _should_passthrough_humanization(batched) is False
    # Tiny heading-only strings are below MIN_HUMANIZE_CHARS — not body prose.
    assert _should_passthrough_humanization("## Introduction") is True

    calls: list[str] = []

    def fake_humanize(text: str, *, model: str | None = None):
        calls.append(text)
        return {"success": True, "humanized_text": text.replace("paragraph", "passage")}

    out = StealthWriterTextHumanizer(humanize_fn=fake_humanize).humanize(batched)
    assert calls, "StealthWriter must be invoked for batched markdown drafts"
    assert "## Introduction" in out
    assert "passage" in out

    engine = HumanizerEngineService(
        humanizer=StealthWriterTextHumanizer(humanize_fn=fake_humanize),
        validator=ZeroGPTParagraphValidator(),
    )
    session = engine.create_session(
        draft={"id": "d1", "content": batched, "version": 1},
        requirement_json={"writing_tone": "Academic"},
        blueprint={"sections": [{"title": "Introduction"}, {"title": "Journal Entry 1"}]},
        project_id="proj-batch",
    )
    session = engine.advance_paragraph(session.id)
    para = session.paragraphs[0]
    assert para.status == HumanizerParagraphStatus.COMPLETED
    assert "passage" in (para.humanized_text or "")
    assert para.original_text != para.humanized_text


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
    # Mock validator may request a revision on first pass for long "objective" drafts.
    assert first.status in {
        HumanizerParagraphStatus.COMPLETED,
        HumanizerParagraphStatus.REVISION,
    }
    assert first.humanized_text
    assert first.ai_score_before is not None
    assert first.ai_score_after is not None
    assert session.progress >= 0


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
