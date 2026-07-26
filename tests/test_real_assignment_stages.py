"""Tests for real post-writing assignment pipeline stages."""

from __future__ import annotations

from services.assignment_citations import AssignmentCitationEngine
from services.assignment_formatting import AssignmentFormatEngine
from services.assignment_pipeline.models import PipelineStage, StageProvider, StageStatus
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_pipeline.stages import PIPELINE_STAGE_SPECS, PIPELINE_STAGES, stage_after
from services.ai_detection_engine.zerogpt_detector import ZeroGPTAIDetector
from services.requirement_validation import GeminiRequirementValidator
from services.reviewer_engine.gemini_reviewer import GeminiAcademicReviewer
from services.reviewer_engine.models import ReviewEngineInput
from services.revision_engine.gemini_reviser import GeminiSectionReviser
from services.revision_engine.models import RevisionEngineInput


def test_pipeline_order_matches_plan_a():
    assert len(PIPELINE_STAGES) == 16
    assert PIPELINE_STAGES[8] == PipelineStage.CITATION_GENERATION
    assert PIPELINE_STAGES[9] == PipelineStage.HUMANIZATION
    assert PIPELINE_STAGES[10] == PipelineStage.FORMATTING
    assert PIPELINE_STAGES[11] == PipelineStage.STYLE_REVIEW
    assert PIPELINE_STAGES[12] == PipelineStage.REVISION
    assert PIPELINE_STAGES[13] == PipelineStage.REQUIREMENT_VALIDATION
    assert PIPELINE_STAGES[14] == PipelineStage.AI_DETECTION
    assert PIPELINE_STAGES[-1] == PipelineStage.DELIVERY
    assert stage_after(PipelineStage.FORMATTING) == PipelineStage.STYLE_REVIEW
    assert stage_after(PipelineStage.STYLE_REVIEW) == PipelineStage.REVISION


def test_stage_providers_are_real():
    providers = {spec.stage: spec.provider for spec in PIPELINE_STAGE_SPECS}
    assert providers[PipelineStage.STYLE_REVIEW] == StageProvider.GEMINI
    assert providers[PipelineStage.REVISION] == StageProvider.GEMINI
    assert providers[PipelineStage.CITATION_GENERATION] == StageProvider.CITATION_ENGINE
    assert providers[PipelineStage.FORMATTING] == StageProvider.FORMAT_ENGINE
    assert providers[PipelineStage.REQUIREMENT_VALIDATION] == StageProvider.GEMINI
    assert providers[PipelineStage.AI_DETECTION] == StageProvider.ZEROGPT


def test_failed_stage_retry_does_not_reset_prior_stages():
    service = AssignmentPipelineService()
    project = service.create_project()
    pid = project.id
    service.complete_stage(pid, PipelineStage.REQUIREMENT_ANALYSIS)
    service.complete_stage(pid, PipelineStage.PRICING)
    service.start_stage(pid, PipelineStage.WAITING_FOR_PAYMENT)
    service.fail_stage(pid, PipelineStage.WAITING_FOR_PAYMENT, "payment failed")

    service.reset_stage(pid, PipelineStage.WAITING_FOR_PAYMENT)
    service.start_stage(pid, PipelineStage.WAITING_FOR_PAYMENT, force=True)
    project = service.get_project(pid)

    assert project.stage_state(PipelineStage.REQUIREMENT_ANALYSIS).status == StageStatus.COMPLETED
    assert project.stage_state(PipelineStage.PRICING).status == StageStatus.COMPLETED
    assert project.stage_state(PipelineStage.WAITING_FOR_PAYMENT).status == StageStatus.RUNNING


def test_gemini_reviewer_falls_back_without_llm(monkeypatch):
    monkeypatch.setattr(
        "services.reviewer_engine.gemini_reviewer.assignment_llm_configured",
        lambda stage=None: False,
    )
    reviewer = GeminiAcademicReviewer()
    report = reviewer.review(
        ReviewEngineInput(
            requirement_json={"assignment_type": "Essay", "word_count": 500},
            research_plan={"sources": []},
            blueprint={"sections": [{"title": "Introduction"}]},
            draft={
                "content": "## Introduction\n\nThis essay examines digital learning with critical comparison.",
                "total_words": 120,
            },
            project_id="p1",
        )
    )
    assert report.overall_score >= 0
    assert report.engine_version


def test_gemini_reviser_uses_fallback(monkeypatch):
    monkeypatch.setattr(
        "services.revision_engine.gemini_reviser.assignment_llm_configured",
        lambda stage=None: False,
    )
    reviser = GeminiSectionReviser()
    result = reviser.revise(
        RevisionEngineInput(
            requirement_json={"assignment_type": "Essay"},
            research_plan={},
            blueprint={"sections": [{"title": "Introduction"}]},
            draft={"content": "## Introduction\n\nBody text for revision.", "version": 1},
            review_report={
                "passed": False,
                "issues": [
                    {
                        "issue_id": "i1",
                        "category": "critical",
                        "section": "Introduction",
                        "suggested_fix": "Add comparison.",
                    }
                ],
            },
            project_id="p1",
        )
    )
    assert result.new_version == 2
    assert "Introduction" in result.draft["content"]


def test_citation_engine_with_mock_lookup():
    class FakeCitations:
        def search(self, query, *, style="APA 7", limit=3):
            return {
                "results": [
                    {
                        "title": "Sample Paper",
                        "reference": "Smith, J. (2020). Sample Paper.",
                        "label": "Smith, 2020",
                        "intext": "(Smith, 2020)",
                    }
                ]
            }

    engine = AssignmentCitationEngine(citation_service=FakeCitations())
    pack, draft = engine.generate(
        draft={"content": "## Intro\n\nClaim (Smith, 2020) supports this.", "version": 1},
        requirement_json={"citation_style": "APA 7", "title": "Digital Learning"},
        project_id="p1",
    )
    assert pack.references
    assert "## References" in draft["content"]
    assert "Smith, J. (2020)" in draft["content"]


def test_requirement_validator_heuristic(monkeypatch):
    monkeypatch.setattr(
        "services.requirement_validation.assignment_llm_configured",
        lambda stage=None: False,
    )
    report = GeminiRequirementValidator().validate(
        document_text="## Introduction\nEnough text " + ("word " * 200),
        requirement_json={"word_count": 50, "required_sections": ["Introduction"]},
        project_id="p1",
    )
    assert report["passed"] is True
    assert "validation" in report["engine_version"] or "gemini" in report["engine_version"]


def test_format_engine_writes_docx(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_STORAGE_DIR", str(tmp_path))
    formatted = AssignmentFormatEngine().format_draft(
        draft={"id": "d1", "title": "Essay", "content": "## Intro\n\nHello world.", "total_words": 2},
        requirement_json={"citation_style": "APA", "formatting": {"line_spacing": "Double"}},
        project_id="proj-format",
    )
    assert formatted["path"]
    assert formatted["profile_summary"]["line_spacing"] == 2.0
    assert (tmp_path / "proj-format" / "formatted" / "formatted.docx").exists()


def test_parse_line_spacing_labels():
    from services.assignment_formatting import _parse_line_spacing

    assert _parse_line_spacing("Double") == 2.0
    assert _parse_line_spacing("single") == 1.0
    assert _parse_line_spacing("1.5") == 1.5
    assert _parse_line_spacing(None) == 2.0


def test_zerogpt_detector_maps_score(monkeypatch):
    class FakeProvider:
        def detect(self, text):
            from services.ai_provider_interfaces import DetectionResult

            return DetectionResult(
                provider="zerogpt-business",
                ai_score=12.5,
                passed=True,
                paragraphs=[],
                raw={},
            )

    detector = ZeroGPTAIDetector.__new__(ZeroGPTAIDetector)
    detector._provider = FakeProvider()
    assert detector.detect("Some academic paragraph about methodology.") == 12.5
