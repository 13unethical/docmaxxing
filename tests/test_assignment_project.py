"""Tests for assignment project data architecture."""

from __future__ import annotations

import pytest

from services.assignment_pipeline.models import PipelineStage, utc_now
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project import ProjectFileType, ProjectService, ProjectStatus
from services.assignment_project.models import RequirementFormatting
from services.assignment_project.store import ProjectStore


class _StubRequirementAnalyzer:
    VERSION = "mock-v1"

    def analyze(self, payload):
        req = payload.requirement
        req.assignment_type = "Literature Review"
        req.word_count = 3000
        req.citation_style = "APA 7"
        req.required_sections = ["Introduction", "Conclusion"]
        req.rubric = []
        req.learning_outcomes = []
        req.minimum_sources = 15
        req.formatting = RequirementFormatting(font_family="Times New Roman")
        req.analyzer_version = self.VERSION
        req.analyzed_at = utc_now()
        return req


def test_create_project_initializes_models():
    pipeline = AssignmentPipelineService()
    service = ProjectService(pipeline=pipeline)
    bundle = service.create_project(
        title="Ethics Essay",
        university="Example University",
        deadline="2026-03-15T23:59:00+00:00",
        files=[
            {
                "file_type": "assignment_brief",
                "original_filename": "brief.pdf",
            }
        ],
    )

    project = bundle.project
    assert project.title == "Ethics Essay"
    assert project.university == "Example University"
    assert project.status == ProjectStatus.DRAFT
    assert project.current_stage == PipelineStage.REQUIREMENT_ANALYSIS
    assert len(bundle.files) == 1
    assert bundle.files[0].file_type == ProjectFileType.ASSIGNMENT_BRIEF
    assert bundle.requirement.project_id == project.id
    assert bundle.requirement.word_count is None


def test_every_project_has_exactly_one_requirement_json():
    service = ProjectService()
    bundle = service.create_project()
    store = service.store
    assert store.get_requirement(bundle.project.id) is not None
    with pytest.raises(KeyError):
        store.require_requirement("missing")


def test_analyze_requirements_populates_mock_json_and_project_fields():
    service = ProjectService(analyzer=_StubRequirementAnalyzer())
    bundle = service.create_project(
        title="Literature Review",
        note="literature review on climate policy",
        files=[
            {"file_type": "assignment_brief", "original_filename": "brief.pdf"},
            {"file_type": "rubric", "original_filename": "rubric.pdf"},
        ],
    )
    analyzed = service.analyze_requirements(bundle.project.id)

    req = analyzed.requirement
    assert req.assignment_type == "Literature Review"
    assert req.word_count == 3000
    assert req.citation_style == "APA 7"
    assert req.required_sections
    assert req.minimum_sources == 15
    assert req.formatting.font_family == "Times New Roman"
    assert req.analyzer_version == _StubRequirementAnalyzer.VERSION
    assert req.analyzed_at is not None

    project = analyzed.project
    assert project.assignment_type == "Literature Review"
    assert project.estimated_word_count == 3000
    assert project.citation_style == "APA 7"
    assert project.status == ProjectStatus.ACTIVE
    assert project.current_stage == PipelineStage.PRICING


def test_add_file_supports_all_file_types():
    service = ProjectService()
    bundle = service.create_project()
    project_id = bundle.project.id

    for file_type in ProjectFileType:
        service.add_file(
            project_id,
            file_type=file_type.value,
            original_filename=f"{file_type.value}.pdf",
        )

    updated = service.get_project(project_id)
    assert len(updated.files) == len(ProjectFileType)


def test_bundle_to_dict_shape():
    service = ProjectService()
    bundle = service.create_project(files=[{"file_type": "assignment_brief", "original_filename": "a.pdf"}])
    payload = bundle.to_dict()
    assert set(payload.keys()) == {"project", "files", "requirement"}
    assert payload["requirement"]["project_id"] == payload["project"]["id"]


def test_create_project_shares_id_with_pipeline():
    pipeline = AssignmentPipelineService()
    service = ProjectService(pipeline=pipeline)
    bundle = service.create_project()
    pipeline_state = pipeline.get_project(bundle.project.id)
    assert pipeline_state.id == bundle.project.id


def test_store_reload_from_disk_after_external_write(tmp_path):
    """Simulate another gunicorn worker saving pricing while this worker holds stale cache."""
    store_a = ProjectStore(root=tmp_path / "projects")
    store_b = ProjectStore(root=tmp_path / "projects")
    pipeline = AssignmentPipelineService()
    service_a = ProjectService(store=store_a, pipeline=pipeline, analyzer=_StubRequirementAnalyzer())

    bundle = service_a.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    project_id = bundle.project.id
    service_a.analyze_requirements(project_id)

    # Worker B loads project into its cache before pricing runs.
    store_b.require_bundle(project_id)
    assert store_b.require_bundle(project_id).project.price is None

    service_a.calculate_pricing(project_id)

    # Worker B must see the price written by worker A, not its stale cache.
    assert store_b.require_bundle(project_id).project.price is not None


def test_confirm_payment_restores_pipeline_from_disk(tmp_path):
    """Simulate a new gunicorn worker that has no in-memory pipeline state."""
    store = ProjectStore(root=tmp_path / "projects")
    pipeline_a = AssignmentPipelineService()
    service_a = ProjectService(store=store, pipeline=pipeline_a, analyzer=_StubRequirementAnalyzer())

    bundle = service_a.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    service_a.analyze_requirements(bundle.project.id)
    service_a.calculate_pricing(bundle.project.id)

    pipeline_b = AssignmentPipelineService()
    service_b = ProjectService(store=store, pipeline=pipeline_b, analyzer=_StubRequirementAnalyzer())

    confirmed = service_b.confirm_payment(bundle.project.id)
    assert confirmed.project.artifacts.get("payment_confirmed") is True


def test_calculate_pricing_restores_pipeline_from_disk(tmp_path):
    store = ProjectStore(root=tmp_path / "projects")
    pipeline_a = AssignmentPipelineService()
    service_a = ProjectService(store=store, pipeline=pipeline_a, analyzer=_StubRequirementAnalyzer())

    bundle = service_a.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    service_a.analyze_requirements(bundle.project.id)

    pipeline_b = AssignmentPipelineService()
    service_b = ProjectService(store=store, pipeline=pipeline_b, analyzer=_StubRequirementAnalyzer())

    priced = service_b.calculate_pricing(bundle.project.id)
    assert priced.project.price is not None
    pricing_state = pipeline_b.get_project(bundle.project.id).stage_state(PipelineStage.PRICING)
    assert pricing_state.status.value == "completed"


class _StubResearchEngine:
    VERSION = "stub-research"

    def build_plan(self, payload):
        from services.research_engine.models import ResearchPlan, ResearchSection

        return ResearchPlan(
            id="plan-disk-1",
            project_id=payload.project_id,
            assignment_topic="Disk persistence topic",
            writing_objective="Test objective",
            main_research_question="Test question?",
            section_list=[
                ResearchSection(
                    title="Introduction",
                    description="Intro",
                    purpose="Open",
                    estimated_words=200,
                )
            ],
            engine_version=self.VERSION,
        )


class _StubResearchService:
    def __init__(self) -> None:
        from services.research_engine.service import ResearchEngineService

        self.store = ResearchEngineService().store
        self.engine = _StubResearchEngine()

    def build_plan(self, *, requirement_json, parsed_documents, project_id=None):
        from services.research_engine.models import ResearchEngineInput

        plan = self.engine.build_plan(
            ResearchEngineInput(
                requirement_json=requirement_json,
                parsed_documents=parsed_documents,
                project_id=project_id,
            )
        )
        return self.store.save(plan)


class _StubBlueprintEngine:
    VERSION = "stub-blueprint"

    def build_blueprint(self, payload):
        from services.blueprint_engine.models import Blueprint, BlueprintSection, WordDistributionEntry

        section = BlueprintSection(
            id="introduction",
            title="Introduction",
            objective="Introduce the topic.",
            estimated_words=200,
            key_points=["Background", "Thesis"],
        )
        return Blueprint(
            id="blueprint-disk-1",
            project_id=payload.project_id,
            total_target_words=200,
            total_target_sections=1,
            writing_order=["introduction"],
            transition_rules=[],
            citation_strategy="APA 7",
            academic_tone="Formal academic prose",
            critical_analysis_locations=[],
            comparison_locations=[],
            counterargument_locations=[],
            conclusion_goals=[],
            sections=[section],
            word_distribution=[WordDistributionEntry(title="Introduction", estimated_words=200)],
            writing_queue=["Introduction"],
            estimated_completion_time="1 hour",
            engine_version=self.VERSION,
        )


class _StubBlueprintService:
    def __init__(self) -> None:
        from services.blueprint_engine.service import BlueprintEngineService

        self.store = BlueprintEngineService().store
        self.engine = _StubBlueprintEngine()

    def build_blueprint(self, *, requirement_json, research_plan, project_id=None):
        from services.blueprint_engine.models import BlueprintEngineInput

        blueprint = self.engine.build_blueprint(
            BlueprintEngineInput(
                requirement_json=requirement_json,
                research_plan=research_plan,
                project_id=project_id,
            )
        )
        return self.store.save(blueprint)


def test_run_research_restores_plan_from_disk(tmp_path):
    """Simulate a new gunicorn worker loading research plan from bundle artifacts."""
    from services.research_engine.service import ResearchEngineService

    store = ProjectStore(root=tmp_path / "projects")
    pipeline_a = AssignmentPipelineService()
    research_a = _StubResearchService()
    service_a = ProjectService(
        store=store,
        pipeline=pipeline_a,
        research=research_a,  # type: ignore[arg-type]
        analyzer=_StubRequirementAnalyzer(),
    )

    bundle = service_a.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    project_id = bundle.project.id
    service_a.analyze_requirements(project_id)
    service_a.calculate_pricing(project_id)
    service_a.confirm_payment(project_id)
    plan = service_a.run_research(project_id)

    research_b = ResearchEngineService()
    pipeline_b = AssignmentPipelineService()
    service_b = ProjectService(store=store, pipeline=pipeline_b, research=research_b)

    loaded = service_b.get_research_plan(project_id)
    assert loaded.id == plan.id
    assert loaded.assignment_topic == plan.assignment_topic
    assert store.require_bundle(project_id).project.artifacts.get("research_plan")


def test_seed_research_plan_from_client_snapshot(tmp_path):
    """Fresh worker can adopt research plan JSON sent from the browser."""
    from services.research_engine.service import ResearchEngineService

    store = ProjectStore(root=tmp_path / "projects")
    pipeline_a = AssignmentPipelineService()
    research_a = _StubResearchService()
    service_a = ProjectService(
        store=store,
        pipeline=pipeline_a,
        research=research_a,  # type: ignore[arg-type]
        analyzer=_StubRequirementAnalyzer(),
    )

    bundle = service_a.create_project(
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    project_id = bundle.project.id
    service_a.analyze_requirements(project_id)
    service_a.calculate_pricing(project_id)
    service_a.confirm_payment(project_id)
    plan = service_a.run_research(project_id)
    plan_snapshot = plan.to_dict()

    project = store.require_project(project_id)
    project.artifacts.pop("research_plan", None)
    store.save_project(project)

    service_b = ProjectService(store=store, research=ResearchEngineService())
    with pytest.raises(KeyError):
        service_b._load_research_plan(project_id)

    loaded = service_b._load_research_plan(project_id, seed=plan_snapshot)
    assert loaded.id == plan.id
    assert store.require_bundle(project_id).project.artifacts.get("research_plan")


def test_start_writer_restores_session_from_disk(tmp_path):
    """Simulate a new gunicorn worker loading writer session from bundle artifacts."""
    from services.research_engine.service import ResearchEngineService
    from services.writer_engine import MockSectionWriter, WriterEngineService

    store = ProjectStore(root=tmp_path / "projects")
    pipeline_a = AssignmentPipelineService()
    research_a = _StubResearchService()
    blueprint_a = _StubBlueprintService()
    writer_a = WriterEngineService(writer=MockSectionWriter())
    service_a = ProjectService(
        store=store,
        pipeline=pipeline_a,
        research=research_a,  # type: ignore[arg-type]
        blueprint=blueprint_a,  # type: ignore[arg-type]
        writer=writer_a,
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

    service_b = ProjectService(
        store=store,
        pipeline=AssignmentPipelineService(),
        research=ResearchEngineService(),
        blueprint=_StubBlueprintService(),  # type: ignore[arg-type]
        writer=WriterEngineService(writer=MockSectionWriter()),
    )

    loaded = service_b.get_writer_session(project_id)
    assert loaded.id == session.id
    assert loaded.sections[0].id == session.sections[0].id
    assert store.require_bundle(project_id).project.artifacts.get("writer_session")


def test_advance_writer_prefers_disk_over_stale_worker_memory(tmp_path):
    """A worker with stale RAM must not rewind progress persisted by another worker."""
    from services.writer_engine import MockSectionWriter, WriterEngineService
    from services.writer_engine.mock_reviewer import MockSectionReviewer
    from services.writer_engine.models import WriterSession

    store = ProjectStore(root=tmp_path / "projects")
    writer_a = WriterEngineService(writer=MockSectionWriter(), reviewer=MockSectionReviewer())
    service_a = ProjectService(
        store=store,
        pipeline=AssignmentPipelineService(),
        research=_StubResearchService(),  # type: ignore[arg-type]
        blueprint=_StubBlueprintService(),  # type: ignore[arg-type]
        writer=writer_a,
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
    started = service_a.start_writer(project_id)
    latest = service_a.advance_writer(project_id)
    assert len(latest.completed_section_ids) >= 1

    # Simulate worker B that still has the older in-memory session (pre-advance).
    writer_b = WriterEngineService(writer=MockSectionWriter(), reviewer=MockSectionReviewer())
    writer_b.sessions.save(WriterSession.from_dict(started.to_dict()))
    service_b = ProjectService(
        store=store,
        pipeline=AssignmentPipelineService(),
        research=_StubResearchService(),  # type: ignore[arg-type]
        blueprint=_StubBlueprintService(),  # type: ignore[arg-type]
        writer=writer_b,
        analyzer=_StubRequirementAnalyzer(),
    )
    loaded = service_b.get_writer_session(project_id)
    assert len(loaded.completed_section_ids) == len(latest.completed_section_ids)
    assert loaded.progress == latest.progress


def test_advance_writer_restores_session_from_disk(tmp_path):
    """Fresh worker can advance a writer session persisted by another worker."""
    from services.research_engine.service import ResearchEngineService
    from services.writer_engine import MockSectionWriter, WriterEngineService

    store = ProjectStore(root=tmp_path / "projects")
    pipeline_a = AssignmentPipelineService()
    research_a = _StubResearchService()
    blueprint_a = _StubBlueprintService()
    writer_a = WriterEngineService(writer=MockSectionWriter())
    service_a = ProjectService(
        store=store,
        pipeline=pipeline_a,
        research=research_a,  # type: ignore[arg-type]
        blueprint=blueprint_a,  # type: ignore[arg-type]
        writer=writer_a,
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
    service_a.start_writer(project_id)

    service_b = ProjectService(
        store=store,
        pipeline=AssignmentPipelineService(),
        research=ResearchEngineService(),
        blueprint=_StubBlueprintService(),  # type: ignore[arg-type]
        writer=WriterEngineService(writer=MockSectionWriter()),
    )

    advanced = service_b.advance_writer(project_id)
    assert advanced.progress > 0
    assert store.require_bundle(project_id).project.artifacts.get("writer_session")
    assert advanced.sections[0].generated_text


def test_start_humanizer_restores_session_from_disk(tmp_path):
    """Fresh gunicorn worker can load humanizer session from bundle artifacts."""
    from services.research_engine.service import ResearchEngineService
    from services.writer_engine import MockSectionWriter, WriterEngineService
    from services.writer_engine.models import WriterSectionStatus
    from services.humanizer_engine import HumanizerEngineService

    store = ProjectStore(root=tmp_path / "projects")
    research_a = _StubResearchService()
    blueprint_a = _StubBlueprintService()
    writer_a = WriterEngineService(writer=MockSectionWriter())
    service_a = ProjectService(
        store=store,
        pipeline=AssignmentPipelineService(),
        research=research_a,  # type: ignore[arg-type]
        blueprint=blueprint_a,  # type: ignore[arg-type]
        writer=writer_a,
        humanizer=HumanizerEngineService(),
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
        current = session.current_section()
        if current and current.status == WriterSectionStatus.REVISION:
            session = service_a.revise_writer_section(project_id, session.current_section_id)
        else:
            session = service_a.advance_writer(project_id)
    service_a.merge_writer_draft(project_id)
    humanizer_session = service_a.start_humanizer(project_id)

    service_b = ProjectService(
        store=store,
        pipeline=AssignmentPipelineService(),
        research=ResearchEngineService(),
        blueprint=_StubBlueprintService(),  # type: ignore[arg-type]
        writer=WriterEngineService(writer=MockSectionWriter()),
        humanizer=HumanizerEngineService(),
    )

    loaded = service_b.get_humanizer_session(project_id)
    assert loaded.id == humanizer_session.id
    assert store.require_bundle(project_id).project.artifacts.get("humanizer_session")

    advanced = service_b.advance_humanizer(project_id)
    assert advanced.paragraphs_processed >= 0
    assert store.require_bundle(project_id).project.artifacts.get("humanizer_session")
