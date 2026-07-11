"""Project lifecycle service — coordinates data models and pipeline state."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from services.assignment_pipeline.handlers import StageResult
from services.assignment_pipeline.models import PipelineStage, StageStatus, utc_now
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project.models import (
    Project,
    ProjectBundle,
    ProjectFile,
    ProjectFileType,
    ProjectStatus,
    RequirementJSON,
)
from services.assignment_project.requirement_analyzer import (
    AnalyzerInput,
    GeminiRequirementAnalyzer,
    RequirementAnalyzer,
    normalize_file_type,
)
from services.assignment_project.pricing import calculate_project_price
from services.assignment_project.store import ProjectStore
from services.research_engine.parsed_documents import build_parsed_documents
from services.research_engine.service import ResearchEngineService
from services.blueprint_engine.service import BlueprintEngineService
from services.writer_engine.service import WriterEngineService
from services.reviewer_engine.service import ReviewerEngineService
from services.revision_engine.service import RevisionEngineService
from services.revision_engine.models import MAX_REVISION_ATTEMPTS
from services.humanizer_engine.service import HumanizerEngineService
from services.ai_detection_engine.service import AIDetectionEngineService
from services.delivery_engine.service import DeliveryEngineService
from services.project_engine import ProjectEngine, ProjectLifecycleStatus


def _parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _storage_path(project_id: str, file_id: str, original_filename: str) -> str:
    safe_name = Path(original_filename).name
    return f"data/projects/{project_id}/files/{file_id}_{safe_name}"


class ProjectService:
    """Create and manage assignment projects with files and requirement JSON."""

    def __init__(
        self,
        store: ProjectStore | None = None,
        pipeline: AssignmentPipelineService | None = None,
        analyzer: RequirementAnalyzer | None = None,
        research: ResearchEngineService | None = None,
        blueprint: BlueprintEngineService | None = None,
        writer: WriterEngineService | None = None,
        reviewer: ReviewerEngineService | None = None,
        revision: RevisionEngineService | None = None,
        humanizer: HumanizerEngineService | None = None,
        ai_detection: AIDetectionEngineService | None = None,
        delivery: DeliveryEngineService | None = None,
        project_engine: ProjectEngine | None = None,
    ) -> None:
        self.store = store or ProjectStore()
        self.pipeline = pipeline or AssignmentPipelineService()
        self.analyzer = analyzer or GeminiRequirementAnalyzer()
        self.research = research or ResearchEngineService()
        self.blueprint = blueprint or BlueprintEngineService()
        self.writer = writer or WriterEngineService()
        self.reviewer = reviewer or ReviewerEngineService()
        self.revision = revision or RevisionEngineService(draft_store=self.writer.drafts)
        self.humanizer = humanizer or HumanizerEngineService()
        self.ai_detection = ai_detection or AIDetectionEngineService()
        self.delivery = delivery or DeliveryEngineService()
        self.project_engine = project_engine or ProjectEngine()

    def create_project(
        self,
        *,
        user_id: str | None = None,
        title: str | None = None,
        university: str | None = None,
        deadline: str | None = None,
        note: str | None = None,
        files: list[dict[str, Any]] | None = None,
        upload_manifest: dict[str, Any] | None = None,
    ) -> ProjectBundle:
        project_id = str(uuid.uuid4())
        now = utc_now()
        deadline_dt = _parse_deadline(deadline)

        project = Project(
            id=project_id,
            user_id=user_id,
            title=title or "Untitled Assignment",
            assignment_type=None,
            university=university,
            status=ProjectStatus.DRAFT,
            current_stage=PipelineStage.UPLOAD,
            progress=0,
            price=None,
            credits=None,
            estimated_word_count=None,
            citation_style=None,
            deadline=deadline_dt,
            created_at=now,
            updated_at=now,
            note=note,
        )
        requirement = RequirementJSON(
            id=str(uuid.uuid4()),
            project_id=project_id,
        )

        self.store.save_project(project)
        self.store.save_requirement(requirement)
        self.project_engine.init_project(project_id)

        manifest_files = list((upload_manifest or {}).get("files") or [])
        payload_files = list(files or [])
        merged_files = payload_files or _files_from_manifest(manifest_files)

        for entry in merged_files:
            self._add_file_record(project_id, entry)

        self.pipeline.create_project(upload_manifest=upload_manifest, project_id=project_id)
        self._sync_pipeline_state(project_id)

        return self.store.require_bundle(project_id)

    def get_project(self, project_id: str) -> ProjectBundle:
        self._sync_pipeline_state(project_id)
        return self.store.require_bundle(project_id)

    def add_file(
        self,
        project_id: str,
        *,
        file_type: str,
        original_filename: str,
        storage_path: str | None = None,
        parsed: bool = False,
    ) -> ProjectFile:
        self.store.require_project(project_id)
        file_record = self._add_file_record(
            project_id,
            {
                "file_type": file_type,
                "original_filename": original_filename,
                "storage_path": storage_path,
                "parsed": parsed,
            },
        )
        self._touch_project(project_id)
        return file_record

    def analyze_requirements(self, project_id: str) -> ProjectBundle:
        bundle = self.store.require_bundle(project_id)
        self.project_engine.stage_start(project_id, ProjectLifecycleStatus.REQUIREMENTS_READY)
        self.pipeline.start_stage(project_id, PipelineStage.REQUIREMENT_ANALYSIS)

        try:
            analyzed = self.analyzer.analyze(
                AnalyzerInput(
                    project=bundle.project,
                    files=bundle.files,
                    requirement=bundle.requirement,
                )
            )
            self.store.save_requirement(analyzed)
            self._apply_requirement_to_project(bundle.project, analyzed)

            self.pipeline.complete_stage(
                project_id,
                PipelineStage.REQUIREMENT_ANALYSIS,
                StageResult(
                    requirement_json=analyzed.to_dict(),
                    output={"analyzer": analyzed.analyzer_version},
                ),
            )
            self.project_engine.stage_finish(
                project_id,
                ProjectLifecycleStatus.REQUIREMENTS_READY,
                success=True,
                model_used=analyzed.analyzer_version,
            )
            self._sync_pipeline_state(project_id)
            return self.store.require_bundle(project_id)
        except Exception as exc:  # noqa: BLE001
            self.project_engine.stage_finish(
                project_id,
                ProjectLifecycleStatus.REQUIREMENTS_READY,
                success=False,
                error=str(exc),
            )
            raise

    def calculate_pricing(self, project_id: str, *, priority: str = "standard") -> ProjectBundle:
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        if not requirement.get("analyzed_at") and not requirement.get("assignment_type"):
            raise ValueError("Requirement analysis must complete before pricing")

        pricing = calculate_project_price(requirement, priority=priority)
        project = bundle.project
        project.price = float(pricing["amount_usd"])
        project.artifacts["pricing"] = pricing
        project.updated_at = utc_now()
        self.store.save_project(project)

        self.pipeline.start_stage(project_id, PipelineStage.PRICING)
        self.pipeline.complete_stage(
            project_id,
            PipelineStage.PRICING,
            StageResult(pricing=pricing, output={"amount_usd": pricing["amount_usd"], "priority": priority}),
        )
        self.pipeline.start_stage(project_id, PipelineStage.WAITING_FOR_PAYMENT)
        self._sync_pipeline_state(project_id)
        return self.store.require_bundle(project_id)

    def confirm_payment(self, project_id: str) -> ProjectBundle:
        bundle = self.store.require_bundle(project_id)
        if bundle.project.artifacts.get("payment_confirmed"):
            return bundle
        if bundle.project.price is None:
            raise ValueError("Price must be calculated before payment confirmation")
        pipeline_project = self.pipeline.get_project(project_id)
        pricing_state = pipeline_project.stage_state(PipelineStage.PRICING)
        if pricing_state.status != StageStatus.COMPLETED:
            raise ValueError("Pricing stage must complete before payment confirmation")

        bundle.project.artifacts["payment_confirmed"] = True
        bundle.project.artifacts["payment_confirmed_at"] = utc_now().isoformat()
        bundle.project.updated_at = utc_now()
        self.store.save_project(bundle.project)

        self.pipeline.complete_stage(
            project_id,
            PipelineStage.WAITING_FOR_PAYMENT,
            StageResult(output={"payment_confirmed": True}),
        )
        self._sync_pipeline_state(project_id)
        return self.store.require_bundle(project_id)

    def run_research(
        self,
        project_id: str,
        *,
        parsed_documents: list[dict] | None = None,
    ):
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        if not requirement.get("assignment_type") and not requirement.get("word_count"):
            raise ValueError("Requirement JSON must be analyzed before research planning")
        if not bundle.project.artifacts.get("payment_confirmed"):
            raise ValueError("Payment must be confirmed before research planning")

        documents = build_parsed_documents(bundle.files, parsed_documents)
        self.project_engine.stage_start(project_id, ProjectLifecycleStatus.RESEARCH_READY)
        self.pipeline.start_stage(project_id, PipelineStage.RESEARCH)

        try:
            plan = self.research.build_plan(
                requirement_json=requirement,
                parsed_documents=documents,
                project_id=project_id,
            )

            project = self.store.require_project(project_id)
            project.artifacts["research_plan_id"] = plan.id
            self.store.save_project(project)

            self.pipeline.complete_stage(
                project_id,
                PipelineStage.RESEARCH,
                StageResult(
                    output={"research_plan_id": plan.id, "engine": plan.engine_version},
                    artifacts={"research_plan": plan.to_dict()},
                ),
            )
            self.project_engine.stage_finish(
                project_id,
                ProjectLifecycleStatus.RESEARCH_READY,
                success=True,
                model_used=plan.engine_version,
            )
            self._sync_pipeline_state(project_id)
            return plan
        except Exception as exc:  # noqa: BLE001
            self.project_engine.stage_finish(
                project_id,
                ProjectLifecycleStatus.RESEARCH_READY,
                success=False,
                error=str(exc),
            )
            raise

    def get_research_plan(self, project_id: str):
        return self.research.get_plan_by_project(project_id)

    def update_research_plan(self, project_id: str, payload: dict):
        plan = self.research.get_plan_by_project(project_id)
        return self.research.update_plan_from_dict(plan.id, payload)

    def run_blueprint(self, project_id: str):
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        try:
            research_plan = self.research.get_plan_by_project(project_id).to_dict()
        except KeyError as exc:
            raise ValueError("Research Plan must exist before building a Blueprint") from exc

        self.project_engine.stage_start(project_id, ProjectLifecycleStatus.BLUEPRINT_READY)
        self.pipeline.start_stage(project_id, PipelineStage.BLUEPRINT)
        try:
            blueprint = self.blueprint.build_blueprint(
                requirement_json=requirement,
                research_plan=research_plan,
                project_id=project_id,
            )

            project = self.store.require_project(project_id)
            project.artifacts["blueprint_id"] = blueprint.id
            self.store.save_project(project)

            self.pipeline.complete_stage(
                project_id,
                PipelineStage.BLUEPRINT,
                StageResult(
                    output={"blueprint_id": blueprint.id, "engine": blueprint.engine_version},
                    artifacts={"blueprint": blueprint.to_dict()},
                ),
            )
            self.project_engine.stage_finish(
                project_id,
                ProjectLifecycleStatus.BLUEPRINT_READY,
                success=True,
                model_used=blueprint.engine_version,
            )
            self._sync_pipeline_state(project_id)
            return blueprint
        except Exception as exc:  # noqa: BLE001
            self.project_engine.stage_finish(
                project_id,
                ProjectLifecycleStatus.BLUEPRINT_READY,
                success=False,
                error=str(exc),
            )
            raise

    def get_blueprint(self, project_id: str):
        return self.blueprint.get_blueprint_by_project(project_id)

    def update_blueprint(self, project_id: str, payload: dict):
        blueprint = self.blueprint.get_blueprint_by_project(project_id)
        return self.blueprint.update_blueprint_from_dict(blueprint.id, payload)

    def start_writer(self, project_id: str):
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        research_plan = self.research.get_plan_by_project(project_id).to_dict()
        blueprint = self.blueprint.get_blueprint_by_project(project_id).to_dict()

        self.project_engine.stage_start(project_id, ProjectLifecycleStatus.WRITING)
        self.pipeline.start_stage(project_id, PipelineStage.WRITING)
        session = self.writer.create_session(
            requirement_json=requirement,
            research_plan=research_plan,
            blueprint=blueprint,
            project_id=project_id,
        )

        project = self.store.require_project(project_id)
        project.artifacts["writer_session_id"] = session.id
        self.store.save_project(project)
        self.project_engine.stage_finish(
            project_id,
            ProjectLifecycleStatus.WRITING,
            success=True,
            model_used=session.engine_version,
        )
        return session

    def advance_writer(self, project_id: str):
        session = self.writer.get_session_by_project(project_id)
        return self.writer.advance_section(session.id)

    def revise_writer_section(self, project_id: str, section_id: str | None = None):
        session = self.writer.get_session_by_project(project_id)
        return self.writer.revise_section(session.id, section_id)

    def merge_writer_draft(self, project_id: str):
        session = self.writer.get_session_by_project(project_id)
        bundle = self.store.require_bundle(project_id)
        title = bundle.project.title or bundle.requirement.title or "Assignment Draft"
        draft = self.writer.merge_draft(session.id, title=title)

        self.pipeline.complete_stage(
            project_id,
            PipelineStage.WRITING,
            StageResult(
                output={"writer_session_id": session.id, "draft_id": draft.id},
                artifacts={"draft": draft.to_dict()},
            ),
        )
        self.pipeline.complete_stage(
            project_id,
            PipelineStage.MERGE,
            StageResult(output={"draft_id": draft.id}, artifacts={"draft": draft.to_dict()}),
        )

        project = self.store.require_project(project_id)
        project.artifacts["draft_id"] = draft.id
        self.store.save_project(project)
        self.revision.register_initial_draft(draft)
        self.project_engine.stage_start(project_id, ProjectLifecycleStatus.WRITING_COMPLETED)
        self.project_engine.stage_finish(
            project_id,
            ProjectLifecycleStatus.WRITING_COMPLETED,
            success=True,
            model_used=draft.model,
        )
        self._sync_pipeline_state(project_id)
        return draft

    def get_writer_session(self, project_id: str):
        return self.writer.get_session_by_project(project_id)

    def get_draft(self, project_id: str):
        return self.writer.get_draft_by_project(project_id)

    def _draft_for_review(self, project_id: str) -> dict:
        try:
            return self.humanizer.get_humanized_draft_by_project(project_id).to_dict()
        except KeyError:
            return self.writer.get_draft_by_project(project_id).to_dict()

    def _rehumanize_revised_sections(self, project_id: str, section_names: list[str]) -> None:
        if not section_names:
            return
        session = self.humanizer.get_session_by_project(project_id)
        draft = self.writer.get_draft_by_project(project_id)
        blueprint = self.blueprint.get_blueprint_by_project(project_id).to_dict()
        self.humanizer.refresh_revised_sections(
            session.id,
            draft_content=draft.content,
            blueprint=blueprint,
            section_names=section_names,
        )

    def run_academic_review(self, project_id: str):
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        research_plan = self.research.get_plan_by_project(project_id).to_dict()
        blueprint = self.blueprint.get_blueprint_by_project(project_id).to_dict()
        draft = self._draft_for_review(project_id)

        self.pipeline.start_stage(project_id, PipelineStage.STYLE_REVIEW)
        report = self.reviewer.review_draft(
            requirement_json=requirement,
            research_plan=research_plan,
            blueprint=blueprint,
            draft=draft,
            project_id=project_id,
        )

        project = self.store.require_project(project_id)
        pass_number = int(project.artifacts.get("review_pass_number", 0)) + 1
        project.artifacts["review_report_id"] = report.id
        project.artifacts["review_pass_number"] = pass_number
        project.artifacts["last_review_issues_found"] = len(report.issues)
        self.store.save_project(project)

        draft = self.writer.get_draft_by_project(project_id)
        try:
            self.revision.update_review_score(
                project_id,
                version=draft.version,
                review_score=report.overall_score,
            )
        except KeyError:
            self.revision.register_initial_draft(draft)

        if not report.passed:
            history = self.revision.get_history_or_empty(project_id)
            if history.revision_attempts >= MAX_REVISION_ATTEMPTS:
                self.revision.mark_needs_manual_review(project_id)
                project = self.store.require_project(project_id)
                project.status = ProjectStatus.NEEDS_MANUAL_REVIEW
                self.store.save_project(project)

        self.pipeline.complete_stage(
            project_id,
            PipelineStage.STYLE_REVIEW,
            StageResult(
                output={"review_report_id": report.id, "passed": report.passed, "overall_score": report.overall_score},
                artifacts={"review_report": report.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return report

    def get_review_report(self, project_id: str):
        return self.reviewer.get_report_by_project(project_id)

    def run_revision(self, project_id: str):
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        research_plan = self.research.get_plan_by_project(project_id).to_dict()
        blueprint = self.blueprint.get_blueprint_by_project(project_id).to_dict()
        draft = self._draft_for_review(project_id)
        review_report = self.reviewer.get_report_by_project(project_id).to_dict()

        if review_report.get("passed"):
            raise ValueError("Review report passed — revision is not required")

        history = self.revision.get_history_or_empty(project_id)
        if history.revision_attempts >= MAX_REVISION_ATTEMPTS or history.needs_manual_review:
            raise ValueError("Maximum automatic revision attempts reached — project needs manual review")

        self._complete_placeholder_stages_before_revision(project_id)

        self.pipeline.start_stage(project_id, PipelineStage.REVISION)
        result = self.revision.revise_draft(
            requirement_json=requirement,
            research_plan=research_plan,
            blueprint=blueprint,
            draft=draft,
            review_report=review_report,
            project_id=project_id,
        )

        project = self.store.require_project(project_id)
        project.artifacts["draft_id"] = result.draft["id"]
        project.artifacts["revision_attempts"] = result.attempt_number
        project.artifacts["last_revision_id"] = result.id
        project.artifacts["last_issues_fixed"] = len(result.issues_addressed)
        section_names = [item.section for item in result.sections_revised if item.section]
        try:
            self._rehumanize_revised_sections(project_id, section_names)
        except KeyError:
            pass
        if project.status == ProjectStatus.NEEDS_MANUAL_REVIEW and result.attempt_number < MAX_REVISION_ATTEMPTS:
            project.status = ProjectStatus.ACTIVE
        self.store.save_project(project)

        self.pipeline.complete_stage(
            project_id,
            PipelineStage.REVISION,
            StageResult(
                output={
                    "revision_id": result.id,
                    "draft_version": result.new_version,
                    "attempt_number": result.attempt_number,
                },
                artifacts={"revision_result": result.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return result

    def get_revision_history(self, project_id: str):
        return self.revision.get_history_or_empty(project_id)

    def restore_draft_version(self, project_id: str, version: int):
        draft = self.revision.restore_version(project_id, version)
        project = self.store.require_project(project_id)
        project.artifacts["draft_id"] = draft.id
        self.store.save_project(project)
        return draft

    def start_humanizer(self, project_id: str):
        bundle = self.store.require_bundle(project_id)
        draft = self._draft_for_review(project_id)
        blueprint = self.blueprint.get_blueprint_by_project(project_id).to_dict()

        self._complete_placeholder_stages_before_humanization(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.HUMANIZATION)

        session = self.humanizer.create_session(
            draft=draft,
            requirement_json=bundle.requirement.to_dict(),
            blueprint=blueprint,
            project_id=project_id,
        )

        project = self.store.require_project(project_id)
        project.artifacts["humanizer_session_id"] = session.id
        self.store.save_project(project)
        return session

    def advance_humanizer(self, project_id: str):
        session = self.humanizer.get_session_by_project(project_id)
        return self.humanizer.advance_paragraph(session.id)

    def merge_humanized_draft(self, project_id: str):
        session = self.humanizer.get_session_by_project(project_id)
        bundle = self.store.require_bundle(project_id)
        title = bundle.project.title or bundle.requirement.title or "Humanized Assignment Draft"
        humanized = self.humanizer.merge_humanized_draft(session.id, title=title)

        project = self.store.require_project(project_id)
        project.artifacts["humanized_draft_id"] = humanized.id
        self.store.save_project(project)

        self.pipeline.complete_stage(
            project_id,
            PipelineStage.HUMANIZATION,
            StageResult(
                output={
                    "humanized_draft_id": humanized.id,
                    "version": humanized.version,
                    "paragraphs_processed": humanized.paragraphs_processed,
                    "average_ai_reduction": humanized.average_ai_reduction,
                },
                artifacts={"humanized_draft": humanized.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return humanized

    def get_humanizer_session(self, project_id: str):
        return self.humanizer.get_session_by_project(project_id)

    def get_humanized_draft(self, project_id: str):
        return self.humanizer.get_humanized_draft_by_project(project_id)

    def start_ai_detection(self, project_id: str):
        bundle = self.store.require_bundle(project_id)
        humanized = self.humanizer.get_humanized_draft_by_project(project_id).to_dict()
        humanizer_session = self.humanizer.get_session_by_project(project_id)
        humanizer_ids = [p.paragraph_id for p in humanizer_session.paragraphs]

        project = self.store.require_project(project_id)
        attempt_number = int(project.artifacts.get("detection_attempt_number", 0)) + 1
        project.artifacts["detection_attempt_number"] = attempt_number

        self.pipeline.start_stage(project_id, PipelineStage.AI_DETECTION)
        session = self.ai_detection.create_session(
            humanized_draft=humanized,
            requirement_json=bundle.requirement.to_dict(),
            project_id=project_id,
            humanizer_paragraph_ids=humanizer_ids,
        )

        project.artifacts["detection_session_id"] = session.id
        self.store.save_project(project)
        return session

    def advance_ai_detection(self, project_id: str):
        session = self.ai_detection.get_session_by_project(project_id)
        humanizer_session = self.humanizer.get_session_by_project(project_id)

        def rehumanize(paragraph_id: str, _current_text: str) -> str:
            return self.humanizer.rehumanize_paragraph_for_detection(humanizer_session.id, paragraph_id)

        return self.ai_detection.advance_paragraph(session.id, rehumanize=rehumanize)

    def finalize_ai_detection(self, project_id: str):
        session = self.ai_detection.get_session_by_project(project_id)
        if not session.report_id:
            session = self.ai_detection.finalize_session(session.id)
        report = self.ai_detection.get_report(session.report_id)

        project = self.store.require_project(project_id)
        project.artifacts["detection_report_id"] = report.id
        if report.final_status.value == "needs_manual_review":
            project.status = ProjectStatus.NEEDS_MANUAL_REVIEW
        self.store.save_project(project)

        self.pipeline.complete_stage(
            project_id,
            PipelineStage.AI_DETECTION,
            StageResult(
                output={
                    "detection_report_id": report.id,
                    "overall_ai_score": report.overall_ai_score,
                    "final_status": report.final_status.value,
                },
                artifacts={"detection_report": report.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return report

    def prepare_detection_retry(self, project_id: str) -> None:
        """Re-humanize paragraphs that exceeded the AI score threshold, then require a new review."""
        from services.ai_detection_engine.thresholds import DEFAULT_THRESHOLDS, score_passes

        report = self.get_detection_report(project_id)
        threshold = report.thresholds.acceptable_max if report.thresholds else DEFAULT_THRESHOLDS.acceptable_max
        high_sections = [
            str(item.get("section") or "")
            for item in (report.paragraph_scores or [])
            if not score_passes(float(item.get("ai_score") or 0), report.thresholds)
        ]
        if high_sections:
            self._rehumanize_revised_sections(project_id, high_sections)
        project = self.store.require_project(project_id)
        project.artifacts.pop("review_report_id", None)
        project.artifacts.pop("detection_report_id", None)
        project.artifacts.pop("detection_session_id", None)
        self.store.save_project(project)

    def get_detection_session(self, project_id: str):
        return self.ai_detection.get_session_by_project(project_id)

    def get_detection_report(self, project_id: str):
        return self.ai_detection.get_report_by_project(project_id)

    def run_delivery(self, project_id: str):
        bundle = self.store.require_bundle(project_id)
        try:
            final_draft = self.humanizer.get_humanized_draft_by_project(project_id).to_dict()
        except KeyError:
            final_draft = self.writer.get_draft_by_project(project_id).to_dict()

        research_plan = self.research.get_plan_by_project(project_id).to_dict()
        blueprint = self.blueprint.get_blueprint_by_project(project_id).to_dict()
        review_report = self.reviewer.get_report_by_project(project_id).to_dict()
        detection_report = self.ai_detection.get_report_by_project(project_id).to_dict()

        revision_history = self.revision.get_history_or_empty(project_id)
        humanizer_session = self.humanizer.get_session_by_project(project_id)
        completion_time = (
            str(research_plan.get("estimated_completion_time") or "")
            or str(blueprint.get("estimated_completion_time") or "")
            or "—"
        )

        self.pipeline.start_stage(project_id, PipelineStage.DELIVERY)
        package = self.delivery.prepare_package(
            final_draft=final_draft,
            requirement_json=bundle.requirement.to_dict(),
            research_plan=research_plan,
            blueprint=blueprint,
            review_report=review_report,
            detection_report=detection_report,
            project_id=project_id,
            revision_attempts=revision_history.revision_attempts,
            humanization_attempts=sum(p.attempts for p in humanizer_session.paragraphs),
            completion_time=completion_time,
        )

        project = self.store.require_project(project_id)
        project.artifacts["delivery_package_id"] = package.id
        project.status = ProjectStatus.COMPLETED
        self.store.save_project(project)

        self.pipeline.complete_stage(
            project_id,
            PipelineStage.DELIVERY,
            StageResult(
                output={
                    "delivery_package_id": package.id,
                    "status": package.status.value,
                    "package_download_url": package.package_download_url,
                },
                artifacts={"delivery_package": package.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return package

    def get_delivery_package(self, project_id: str):
        return self.delivery.get_package_by_project(project_id)

    def _complete_placeholder_stages_before_humanization(self, project_id: str) -> None:
        for stage in (
            PipelineStage.STYLE_REVIEW,
            PipelineStage.CITATION_GENERATION,
            PipelineStage.REQUIREMENT_VALIDATION,
            PipelineStage.REVISION,
        ):
            pipeline_project = self.pipeline.get_project(project_id)
            record = pipeline_project.stage_state(stage)
            if record.status != StageStatus.COMPLETED:
                self.pipeline.complete_stage(
                    project_id,
                    stage,
                    StageResult(output={"skipped": True, "reason": "awaiting_humanization"}),
                )

    def _complete_placeholder_stages_before_revision(self, project_id: str) -> None:
        for stage in (PipelineStage.CITATION_GENERATION, PipelineStage.REQUIREMENT_VALIDATION):
            pipeline_project = self.pipeline.get_project(project_id)
            record = pipeline_project.stage_state(stage)
            if record.status != StageStatus.COMPLETED:
                self.pipeline.complete_stage(
                    project_id,
                    stage,
                    StageResult(output={"skipped": True, "reason": "awaiting_revision"}),
                )

    def _add_file_record(self, project_id: str, entry: dict[str, Any]) -> ProjectFile:
        file_type_raw = entry.get("file_type") or entry.get("source") or ""
        file_type = normalize_file_type(str(file_type_raw))
        if file_type is None:
            raise ValueError(f"Unsupported file type: {file_type_raw}")

        original_filename = str(entry.get("original_filename") or entry.get("name") or "file")
        file_id = str(uuid.uuid4())
        storage_path = str(entry.get("storage_path") or _storage_path(project_id, file_id, original_filename))
        filename = Path(storage_path).name

        file_record = ProjectFile(
            id=file_id,
            project_id=project_id,
            file_type=file_type,
            filename=filename,
            original_filename=original_filename,
            storage_path=storage_path,
            parsed=bool(entry.get("parsed", False)),
        )
        return self.store.save_file(file_record)

    def _apply_requirement_to_project(self, project: Project, requirement: RequirementJSON) -> None:
        project.assignment_type = requirement.assignment_type
        project.title = requirement.title or project.title
        project.estimated_word_count = requirement.word_count
        project.citation_style = requirement.citation_style
        if requirement.deadline and project.deadline is None:
            project.deadline = _parse_deadline(requirement.deadline)
        project.status = ProjectStatus.ACTIVE
        project.updated_at = utc_now()
        self.store.save_project(project)

    def sync_pipeline_state(self, project_id: str) -> ProjectBundle:
        self._sync_pipeline_state(project_id)
        return self.store.require_bundle(project_id)

    def _sync_pipeline_state(self, project_id: str) -> None:
        project = self.store.require_project(project_id)
        try:
            pipeline_project = self.pipeline.get_project(project_id)
        except KeyError:
            return
        project.current_stage = pipeline_project.current_stage
        project.progress = pipeline_project.progress
        project.updated_at = utc_now()
        self.store.save_project(project)

    def _touch_project(self, project_id: str) -> None:
        project = self.store.require_project(project_id)
        project.updated_at = utc_now()
        self.store.save_project(project)

    def get_project_timeline(self, project_id: str) -> list[dict[str, Any]]:
        return self.project_engine.get_timeline(project_id)

    def get_project_lifecycle_status(self, project_id: str) -> dict[str, Any]:
        return self.project_engine.get_status(project_id)

    def get_resume_stage(self, project_id: str) -> str:
        return self.project_engine.resume_stage(project_id)


def _files_from_manifest(manifest_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for item in manifest_files:
        mapped.append(
            {
                "file_type": item.get("source") or item.get("file_type"),
                "original_filename": item.get("name") or item.get("original_filename"),
                "storage_path": item.get("storage_path"),
                "parsed": item.get("parsed", False),
            }
        )
    return mapped
