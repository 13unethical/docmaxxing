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
from services.assignment_project.paths import project_files_dir
from services.assignment_project.session_sync import pick_freshest, rank_of
from services.assignment_project.store import ProjectStore
from services.assignment_project.trace_log import trace
from services.research_engine.models import ResearchPlan
from services.research_engine.parsed_documents import build_parsed_documents
from services.research_engine.service import ResearchEngineService
from services.blueprint_engine.models import Blueprint
from services.blueprint_engine.service import BlueprintEngineService
from services.writer_engine.service import WriterEngineService
from services.writer_engine.models import Draft, WriterSectionStatus, WriterSession, WriterSessionStatus, count_words
from services.reviewer_engine.service import ReviewerEngineService
from services.reviewer_engine.models import ReviewReport
from services.revision_engine.service import RevisionEngineService
from services.revision_engine.models import MAX_REVISION_ATTEMPTS
from services.revision_engine.gemini_reviser import _strip_revision_meta
from services.humanizer_engine.service import HumanizerEngineService
from services.humanizer_engine.models import HumanizedDraft, HumanizerSession
from services.ai_detection_engine.service import AIDetectionEngineService
from services.ai_detection_engine.models import DetectionReport, DetectionSession
from services.delivery_engine.service import DeliveryEngineService
from services.project_engine import ProjectEngine, ProjectLifecycleStatus
from services.assignment_citations import AssignmentCitationEngine
from services.assignment_formatting import AssignmentFormatEngine
from services.requirement_validation import GeminiRequirementValidator
from services.assignment_pipeline.stages import PIPELINE_STAGES
from services.requirement_validation import GeminiRequirementValidator


def _parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _storage_path(project_id: str, file_id: str, original_filename: str) -> str:
    safe_name = Path(original_filename).name
    return str(project_files_dir(project_id) / f"{file_id}_{safe_name}")


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
        citation_engine: AssignmentCitationEngine | None = None,
        format_engine: AssignmentFormatEngine | None = None,
        requirement_validator: GeminiRequirementValidator | None = None,
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
        self.citation_engine = citation_engine or AssignmentCitationEngine()
        self.format_engine = format_engine or AssignmentFormatEngine()
        self.requirement_validator = requirement_validator or GeminiRequirementValidator()

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

        bundle_path = self.store._bundle_path(project_id)
        trace(
            "service.create_project.persisted",
            project_id=project_id,
            storage_root=str(self.store.storage_root),
            bundle_path=str(bundle_path.resolve()),
            bundle_exists=bundle_path.is_file(),
        )

        manifest_files = list((upload_manifest or {}).get("files") or [])
        payload_files = list(files or [])
        merged_files = payload_files or _files_from_manifest(manifest_files)

        for entry in merged_files:
            self._add_file_record(project_id, entry)

        self.pipeline.create_project(upload_manifest=upload_manifest, project_id=project_id)
        self._sync_pipeline_state(project_id)

        return self.store.require_bundle(project_id)

    def _ensure_pipeline_project(self, project_id: str) -> None:
        try:
            pipeline_project = self.pipeline.get_project(project_id)
            known = {item.stage for item in pipeline_project.stages}
            if known != set(PIPELINE_STAGES):
                # Stage enum changed — recreate and restore from artifacts.
                recreated = self.pipeline.create_project(project_id=project_id)
                self.pipeline.store.save(recreated)
        except KeyError:
            self.pipeline.create_project(project_id=project_id)
        self._restore_pipeline_from_bundle(project_id)

    def _ensure_project_engine(self, project_id: str) -> None:
        try:
            self.project_engine.get_status(project_id)
        except KeyError:
            self.project_engine.init_project(project_id)

    def _seed_research_plan(self, project_id: str, snapshot: dict[str, Any] | None) -> ResearchPlan | None:
        if not isinstance(snapshot, dict) or not snapshot.get("id"):
            return None
        plan = ResearchPlan.from_dict(snapshot)
        plan.project_id = project_id
        saved = self.research.store.save(plan)
        project = self.store.require_project(project_id)
        project.artifacts["research_plan_id"] = saved.id
        project.artifacts["research_plan"] = saved.to_dict()
        self.store.save_project(project)
        return saved

    def _load_research_plan(
        self,
        project_id: str,
        *,
        seed: dict[str, Any] | None = None,
    ) -> ResearchPlan:
        if seed:
            seeded = self._seed_research_plan(project_id, seed)
            if seeded is not None:
                return seeded
        plan = self.research.store.get_by_project(project_id)
        if plan is not None:
            return plan
        bundle = self.store.require_bundle(project_id)
        snapshot = bundle.project.artifacts.get("research_plan")
        if isinstance(snapshot, dict) and snapshot.get("id"):
            plan = ResearchPlan.from_dict(snapshot)
            plan.project_id = project_id
            return self.research.store.save(plan)
        raise KeyError(f"Research plan not found for project: {project_id}")

    def _load_blueprint(self, project_id: str) -> Blueprint:
        blueprint = self.blueprint.store.get_by_project(project_id)
        if blueprint is not None:
            return blueprint
        bundle = self.store.require_bundle(project_id)
        snapshot = bundle.project.artifacts.get("blueprint")
        if isinstance(snapshot, dict) and snapshot.get("id"):
            blueprint = Blueprint.from_dict(snapshot)
            self.blueprint.store.save(blueprint)
            return blueprint
        raise KeyError(f"Blueprint not found for project: {project_id}")

    def _persist_writer_session(self, project_id: str, session: WriterSession) -> WriterSession:
        session.project_id = project_id
        saved = self.writer.sessions.save(session)
        project = self.store.require_project(project_id)
        project.artifacts["writer_session_id"] = saved.id
        project.artifacts["writer_session"] = saved.to_dict()
        self.store.save_project(project)
        return saved

    def _seed_writer_session(self, project_id: str, snapshot: dict[str, Any] | None) -> WriterSession | None:
        if not isinstance(snapshot, dict) or not snapshot.get("id"):
            return None
        session = WriterSession.from_dict(snapshot)
        return self._persist_writer_session(project_id, session)

    def _load_writer_session(
        self,
        project_id: str,
        *,
        seed: dict[str, Any] | None = None,
    ) -> WriterSession:
        # Multi-worker safe: pick freshest among disk / memory / client seed.
        mem = self.writer.sessions.get_by_project(project_id)
        disk = None
        try:
            bundle = self.store.require_bundle(project_id)
            snapshot = bundle.project.artifacts.get("writer_session")
            if isinstance(snapshot, dict) and snapshot.get("id"):
                try:
                    disk = WriterSession.from_dict(snapshot)
                except Exception as exc:  # noqa: BLE001
                    trace(
                        "writer.session.disk_corrupt",
                        project_id=project_id,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                    disk = None
        except KeyError:
            disk = None
        seeded = None
        if isinstance(seed, dict) and seed.get("id"):
            try:
                seeded = WriterSession.from_dict(seed)
            except Exception:  # noqa: BLE001
                seeded = None
        best = pick_freshest([disk, mem, seeded])
        if best is None:
            raise KeyError(f"Writer session not found for project: {project_id}")
        self.writer.sessions.save(best)
        # Avoid rewriting huge artifacts on every GET; only persist when ahead of disk.
        if disk is None or rank_of(best) > rank_of(disk):
            return self._persist_writer_session(project_id, best)
        return best

    def _persist_draft(self, project_id: str, draft: Draft) -> Draft:
        draft.project_id = project_id
        saved = self.writer.drafts.save(draft)
        project = self.store.require_project(project_id)
        project.artifacts["draft_id"] = saved.id
        project.artifacts["draft"] = saved.to_dict()
        self.store.save_project(project)
        return saved

    def _load_draft(self, project_id: str) -> Draft:
        # Disk is source of truth across gunicorn workers.
        try:
            bundle = self.store.require_bundle(project_id)
            snapshot = bundle.project.artifacts.get("draft")
            if isinstance(snapshot, dict) and snapshot.get("id"):
                draft = Draft.from_dict(snapshot)
                draft.project_id = project_id
                return self.writer.drafts.save(draft)
        except KeyError:
            pass
        draft = self.writer.drafts.get_by_project(project_id)
        if draft is not None:
            return draft
        raise KeyError(f"Draft not found for project: {project_id}")

    def _persist_humanizer_session(self, project_id: str, session: HumanizerSession) -> HumanizerSession:
        session.project_id = project_id
        saved = self.humanizer.sessions.save(session)
        project = self.store.require_project(project_id)
        project.artifacts["humanizer_session_id"] = saved.id
        project.artifacts["humanizer_session"] = saved.to_dict()
        self.store.save_project(project)
        return saved

    def _seed_humanizer_session(
        self,
        project_id: str,
        snapshot: dict[str, Any] | None,
    ) -> HumanizerSession | None:
        if not isinstance(snapshot, dict) or not snapshot.get("id"):
            return None
        session = HumanizerSession.from_dict(snapshot)
        return self._persist_humanizer_session(project_id, session)

    def _load_humanizer_session(
        self,
        project_id: str,
        *,
        seed: dict[str, Any] | None = None,
    ) -> HumanizerSession:
        mem = self.humanizer.sessions.get_by_project(project_id)
        disk = None
        try:
            bundle = self.store.require_bundle(project_id)
            snapshot = bundle.project.artifacts.get("humanizer_session")
            if isinstance(snapshot, dict) and snapshot.get("id"):
                try:
                    disk = HumanizerSession.from_dict(snapshot)
                except Exception as exc:  # noqa: BLE001
                    trace(
                        "humanizer.session.disk_corrupt",
                        project_id=project_id,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                    disk = None
        except KeyError:
            disk = None
        seeded = None
        if isinstance(seed, dict) and seed.get("id"):
            try:
                seeded = HumanizerSession.from_dict(seed)
            except Exception:  # noqa: BLE001
                seeded = None
        best = pick_freshest([disk, mem, seeded])
        if best is None:
            raise KeyError(f"Humanizer session not found for project: {project_id}")
        self.humanizer.sessions.save(best)
        if disk is None or rank_of(best) > rank_of(disk):
            return self._persist_humanizer_session(project_id, best)
        return best

    def _persist_humanized_draft(self, project_id: str, draft: HumanizedDraft) -> HumanizedDraft:
        draft.project_id = project_id
        saved = self.humanizer.drafts.save(draft)
        project = self.store.require_project(project_id)
        project.artifacts["humanized_draft_id"] = saved.id
        project.artifacts["humanized_draft"] = saved.to_dict()
        self.store.save_project(project)
        return saved

    def _load_humanized_draft(self, project_id: str) -> HumanizedDraft:
        try:
            bundle = self.store.require_bundle(project_id)
            snapshot = bundle.project.artifacts.get("humanized_draft")
            if isinstance(snapshot, dict) and snapshot.get("id"):
                draft = HumanizedDraft.from_dict(snapshot)
                draft.project_id = project_id
                return self.humanizer.drafts.save(draft)
        except KeyError:
            pass
        draft = self.humanizer.drafts.get_by_project(project_id)
        if draft is not None:
            return draft
        raise KeyError(f"Humanized draft not found for project: {project_id}")

    def _persist_detection_session(self, project_id: str, session: DetectionSession) -> DetectionSession:
        session.project_id = project_id
        saved = self.ai_detection.sessions.save(session)
        project = self.store.require_project(project_id)
        project.artifacts["detection_session_id"] = saved.id
        project.artifacts["detection_session"] = saved.to_dict()
        self.store.save_project(project)
        return saved

    def _seed_detection_session(
        self,
        project_id: str,
        snapshot: dict[str, Any] | None,
    ) -> DetectionSession | None:
        if not isinstance(snapshot, dict) or not snapshot.get("id"):
            return None
        session = DetectionSession.from_dict(snapshot)
        return self._persist_detection_session(project_id, session)

    def _load_detection_session(
        self,
        project_id: str,
        *,
        seed: dict[str, Any] | None = None,
    ) -> DetectionSession:
        mem = self.ai_detection.sessions.get_by_project(project_id)
        disk = None
        try:
            bundle = self.store.require_bundle(project_id)
            snapshot = bundle.project.artifacts.get("detection_session")
            if isinstance(snapshot, dict) and snapshot.get("id"):
                try:
                    disk = DetectionSession.from_dict(snapshot)
                except Exception as exc:  # noqa: BLE001
                    trace(
                        "detection.session.disk_corrupt",
                        project_id=project_id,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                    disk = None
        except KeyError:
            disk = None
        seeded = None
        if isinstance(seed, dict) and seed.get("id"):
            try:
                seeded = DetectionSession.from_dict(seed)
            except Exception:  # noqa: BLE001
                seeded = None
        best = pick_freshest([disk, mem, seeded])
        if best is None:
            raise KeyError(f"Detection session not found for project: {project_id}")
        self.ai_detection.sessions.save(best)
        if disk is None or rank_of(best) > rank_of(disk):
            return self._persist_detection_session(project_id, best)
        return best

    def _persist_detection_report(self, project_id: str, report: DetectionReport) -> DetectionReport:
        report.project_id = project_id
        saved = self.ai_detection.reports.save(report)
        project = self.store.require_project(project_id)
        project.artifacts["detection_report_id"] = saved.id
        project.artifacts["detection_report"] = saved.to_dict()
        self.store.save_project(project)
        return saved

    def _load_detection_report(self, project_id: str) -> DetectionReport:
        try:
            bundle = self.store.require_bundle(project_id)
            snapshot = bundle.project.artifacts.get("detection_report")
            if isinstance(snapshot, dict) and snapshot.get("id"):
                report = DetectionReport.from_dict(snapshot)
                report.project_id = project_id
                return self.ai_detection.reports.save(report)
        except KeyError:
            pass
        report = self.ai_detection.reports.get_by_project(project_id)
        if report is not None:
            return report
        raise KeyError(f"Detection report not found for project: {project_id}")

    def _persist_review_report(self, project_id: str, report: ReviewReport) -> ReviewReport:
        report.project_id = project_id
        saved = self.reviewer.store.save(report)
        project = self.store.require_project(project_id)
        project.artifacts["review_report_id"] = saved.id
        project.artifacts["review_report"] = saved.to_dict()
        self.store.save_project(project)
        return saved

    def _seed_review_report(
        self,
        project_id: str,
        snapshot: dict[str, Any] | None,
    ) -> ReviewReport | None:
        if not isinstance(snapshot, dict) or not snapshot.get("id"):
            return None
        report = ReviewReport.from_dict(snapshot)
        return self._persist_review_report(project_id, report)

    def _load_review_report(
        self,
        project_id: str,
        *,
        seed: dict[str, Any] | None = None,
    ) -> ReviewReport:
        if seed:
            seeded = self._seed_review_report(project_id, seed)
            if seeded is not None:
                return seeded
        report = self.reviewer.store.get_by_project(project_id)
        if report is not None:
            return report
        bundle = self.store.require_bundle(project_id)
        snapshot = bundle.project.artifacts.get("review_report")
        if isinstance(snapshot, dict) and snapshot.get("id"):
            report = ReviewReport.from_dict(snapshot)
            return self.reviewer.store.save(report)
        raise KeyError(f"Review report not found for project: {project_id}")

    def _restore_pipeline_from_bundle(self, project_id: str) -> None:
        """Rebuild in-memory pipeline stages from persisted project artifacts."""
        bundle = self.store.require_bundle(project_id)
        project = bundle.project
        artifacts = project.artifacts
        requirement = bundle.requirement.to_dict()

        def complete(stage: PipelineStage, result: StageResult | None = None) -> None:
            pipeline_project = self.pipeline.get_project(project_id)
            record = pipeline_project.stage_state(stage)
            if record.status != StageStatus.COMPLETED:
                self.pipeline.complete_stage(project_id, stage, result)

        if requirement.get("analyzed_at") or requirement.get("assignment_type"):
            complete(
                PipelineStage.REQUIREMENT_ANALYSIS,
                StageResult(requirement_json=requirement),
            )

        pricing = artifacts.get("pricing")
        if project.price is not None and pricing:
            complete(
                PipelineStage.PRICING,
                StageResult(
                    pricing=pricing,
                    output={
                        "amount_usd": pricing.get("amount_usd", project.price),
                        "priority": pricing.get("priority", "standard"),
                    },
                ),
            )

        if artifacts.get("payment_confirmed"):
            complete(
                PipelineStage.WAITING_FOR_PAYMENT,
                StageResult(output={"payment_confirmed": True}),
            )
        elif project.price is not None:
            self.pipeline.start_stage(project_id, PipelineStage.WAITING_FOR_PAYMENT)

        if artifacts.get("research_plan_id"):
            complete(
                PipelineStage.RESEARCH,
                StageResult(output={"research_plan_id": artifacts["research_plan_id"]}),
            )

        if artifacts.get("blueprint_id"):
            complete(
                PipelineStage.BLUEPRINT,
                StageResult(output={"blueprint_id": artifacts["blueprint_id"]}),
            )

        if artifacts.get("writer_session_id"):
            complete(
                PipelineStage.WRITING,
                StageResult(output={"writer_session_id": artifacts["writer_session_id"]}),
            )

        if artifacts.get("draft_id"):
            complete(
                PipelineStage.MERGE,
                StageResult(output={"draft_id": artifacts["draft_id"]}),
            )

        if artifacts.get("review_report_id"):
            complete(
                PipelineStage.STYLE_REVIEW,
                StageResult(output={"review_report_id": artifacts["review_report_id"]}),
            )

        if artifacts.get("last_revision_id") or artifacts.get("revision_result"):
            rev_artifacts = {}
            if isinstance(artifacts.get("revision_result"), dict):
                rev_artifacts["revision_result"] = artifacts.get("revision_result")
            complete(
                PipelineStage.REVISION,
                StageResult(
                    output={"last_revision_id": artifacts.get("last_revision_id")},
                    artifacts=rev_artifacts,
                ),
            )

        if artifacts.get("citation_pack"):
            complete(
                PipelineStage.CITATION_GENERATION,
                StageResult(
                    output={"citation_pack_id": (artifacts.get("citation_pack") or {}).get("id")},
                    artifacts={"citation_pack": artifacts.get("citation_pack")},
                ),
            )

        if artifacts.get("humanized_draft_id"):
            complete(
                PipelineStage.HUMANIZATION,
                StageResult(output={"humanized_draft_id": artifacts["humanized_draft_id"]}),
            )

        if artifacts.get("formatted_document"):
            complete(
                PipelineStage.FORMATTING,
                StageResult(
                    output={"formatted_document_id": (artifacts.get("formatted_document") or {}).get("id")},
                    artifacts={"formatted_document": artifacts.get("formatted_document")},
                ),
            )

        if artifacts.get("validation_report"):
            complete(
                PipelineStage.REQUIREMENT_VALIDATION,
                StageResult(
                    output={
                        "passed": (artifacts.get("validation_report") or {}).get("passed"),
                        "validation_report_id": (artifacts.get("validation_report") or {}).get("id"),
                    },
                    artifacts={"validation_report": artifacts.get("validation_report")},
                ),
            )

        if artifacts.get("detection_report_id"):
            complete(
                PipelineStage.AI_DETECTION,
                StageResult(output={"detection_report_id": artifacts["detection_report_id"]}),
            )

        if artifacts.get("delivery_package_id"):
            complete(
                PipelineStage.DELIVERY,
                StageResult(output={"delivery_package_id": artifacts["delivery_package_id"]}),
            )

        self._sync_pipeline_state(project_id)

    def get_project(self, project_id: str) -> ProjectBundle:
        self._ensure_pipeline_project(project_id)
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
        self._ensure_pipeline_project(project_id)
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
        self._ensure_pipeline_project(project_id)
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        if not requirement.get("analyzed_at") and not requirement.get("assignment_type"):
            raise ValueError("Requirement analysis must complete before pricing")

        project = bundle.project
        pricing = calculate_project_price(requirement)
        from services.economy.pricing import USD_TO_COINS

        coins = max(1, int(round(float(pricing["amount_usd"]) * USD_TO_COINS)))
        pricing["amount_coins"] = coins
        project.price = float(pricing["amount_usd"])
        project.credits = coins
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

        saved = self.store.require_bundle(project_id)
        if saved.project.price is None:
            trace(
                "service.calculate_pricing.persist_failed",
                project_id=project_id,
                bundle_path=str(self.store._bundle_path(project_id).resolve()),
                pricing_artifact=saved.project.artifacts.get("pricing"),
            )
            raise ValueError("Price could not be persisted after pricing")
        trace(
            "service.calculate_pricing.persisted",
            project_id=project_id,
            price=saved.project.price,
            bundle_path=str(self.store._bundle_path(project_id).resolve()),
        )
        return saved

    def confirm_payment(self, project_id: str) -> ProjectBundle:
        bundle = self.store.require_bundle(project_id)
        trace(
            "service.confirm_payment.loaded",
            project_id=project_id,
            price=bundle.project.price,
            pricing_artifact=bundle.project.artifacts.get("pricing"),
            bundle_path=str(self.store._bundle_path(project_id).resolve()),
        )
        if bundle.project.artifacts.get("payment_confirmed"):
            return bundle
        if bundle.project.price is None:
            pricing = bundle.project.artifacts.get("pricing")
            if pricing and pricing.get("amount_usd") is not None:
                bundle.project.price = float(pricing["amount_usd"])
                self.store.save_project(bundle.project)
                bundle = self.store.require_bundle(project_id)
            else:
                trace(
                    "service.confirm_payment.missing_price",
                    **self.store.lookup_diagnostics(project_id),
                )
                raise ValueError("Price must be calculated before payment confirmation")
        self._ensure_pipeline_project(project_id)
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

        self._ensure_pipeline_project(project_id)
        documents = build_parsed_documents(bundle.files, parsed_documents)
        self._ensure_project_engine(project_id)
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
            project.artifacts["research_plan"] = plan.to_dict()
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
        return self._load_research_plan(project_id)

    def update_research_plan(self, project_id: str, payload: dict):
        plan = self._load_research_plan(project_id)
        return self.research.update_plan_from_dict(plan.id, payload)

    def run_blueprint(
        self,
        project_id: str,
        *,
        research_plan: dict[str, Any] | None = None,
    ):
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        try:
            research_plan_dict = self._load_research_plan(project_id, seed=research_plan).to_dict()
        except KeyError as exc:
            raise ValueError("Research Plan must exist before building a Blueprint") from exc

        self._ensure_pipeline_project(project_id)
        self._ensure_project_engine(project_id)
        self.project_engine.stage_start(project_id, ProjectLifecycleStatus.BLUEPRINT_READY)
        self.pipeline.start_stage(project_id, PipelineStage.BLUEPRINT)
        try:
            blueprint = self.blueprint.build_blueprint(
                requirement_json=requirement,
                research_plan=research_plan_dict,
                project_id=project_id,
            )

            project = self.store.require_project(project_id)
            project.artifacts["blueprint_id"] = blueprint.id
            project.artifacts["blueprint"] = blueprint.to_dict()
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
        return self._load_blueprint(project_id)

    def update_blueprint(self, project_id: str, payload: dict):
        blueprint = self._load_blueprint(project_id)
        return self.blueprint.update_blueprint_from_dict(blueprint.id, payload)

    def start_writer(self, project_id: str):
        try:
            return self._load_writer_session(project_id)
        except KeyError:
            pass

        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        research_plan = self._load_research_plan(project_id).to_dict()
        blueprint = self._load_blueprint(project_id).to_dict()

        self._ensure_pipeline_project(project_id)
        self.project_engine.stage_start(project_id, ProjectLifecycleStatus.WRITING)
        self.pipeline.start_stage(project_id, PipelineStage.WRITING)
        session = self.writer.create_session(
            requirement_json=requirement,
            research_plan=research_plan,
            blueprint=blueprint,
            project_id=project_id,
        )

        saved = self._persist_writer_session(project_id, session)
        self.project_engine.stage_finish(
            project_id,
            ProjectLifecycleStatus.WRITING,
            success=True,
            model_used=saved.engine_version,
        )
        return saved

    def advance_writer(self, project_id: str, *, writer_session: dict[str, Any] | None = None):
        session = self._load_writer_session(project_id, seed=writer_session)
        updated = self.writer.advance_section(session.id)
        return self._persist_writer_session(project_id, updated)

    def revise_writer_section(
        self,
        project_id: str,
        section_id: str | None = None,
        *,
        writer_session: dict[str, Any] | None = None,
    ):
        session = self._load_writer_session(project_id, seed=writer_session)
        updated = self.writer.revise_section(session.id, section_id)
        return self._persist_writer_session(project_id, updated)

    def merge_writer_draft(self, project_id: str, *, writer_session: dict[str, Any] | None = None):
        session = self._load_writer_session(project_id, seed=writer_session)

        # Repair inconsistent "completed" flags without starting new LLM calls here.
        # Long Claude writes must stay on /writer/advance — merge must be fast.
        changed = False
        for section in session.sections:
            if (
                section.status != WriterSectionStatus.COMPLETED
                and str(section.generated_text or "").strip()
            ):
                section.status = WriterSectionStatus.COMPLETED
                section.completed_at = section.completed_at or utc_now()
                if section.id not in session.completed_section_ids:
                    session.completed_section_ids.append(section.id)
                if section.id in session.remaining_section_ids:
                    session.remaining_section_ids.remove(section.id)
                changed = True

        incomplete = [s for s in session.sections if s.status != WriterSectionStatus.COMPLETED]
        if incomplete:
            if session.status != WriterSessionStatus.ACTIVE:
                session.status = WriterSessionStatus.ACTIVE
                changed = True
            if changed:
                self._persist_writer_session(project_id, session)
            titles = ", ".join(s.title for s in incomplete[:5])
            raise ValueError(
                "Writing is still in progress "
                f"({len(incomplete)} sections remaining: {titles}). "
                "Continue writing before merge."
            )

        session.status = WriterSessionStatus.COMPLETED
        session.progress = 100
        session.current_section_id = None
        session = self._persist_writer_session(project_id, session)

        bundle = self.store.require_bundle(project_id)
        title = bundle.project.title or bundle.requirement.title or "Assignment Draft"
        draft = self.writer.merge_draft(session.id, title=title)

        self._ensure_pipeline_project(project_id)
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

        self._persist_writer_session(project_id, session)
        saved_draft = self._persist_draft(project_id, draft)
        self.revision.register_initial_draft(saved_draft)
        self.project_engine.stage_start(project_id, ProjectLifecycleStatus.WRITING_COMPLETED)
        self.project_engine.stage_finish(
            project_id,
            ProjectLifecycleStatus.WRITING_COMPLETED,
            success=True,
            model_used=saved_draft.model,
        )
        self._sync_pipeline_state(project_id)
        return saved_draft

    def get_writer_session(self, project_id: str):
        return self._load_writer_session(project_id)

    def get_draft(self, project_id: str):
        return self._load_draft(project_id)

    def _draft_for_review(self, project_id: str) -> dict:
        try:
            return self._load_humanized_draft(project_id).to_dict()
        except KeyError:
            return self._load_draft(project_id).to_dict()

    def _rehumanize_revised_sections(self, project_id: str, section_names: list[str]) -> None:
        if not section_names:
            return
        session = self._load_humanizer_session(project_id)
        draft = self._load_draft(project_id)
        blueprint = self._load_blueprint(project_id).to_dict()
        self.humanizer.refresh_revised_sections(
            session.id,
            draft_content=draft.content,
            blueprint=blueprint,
            section_names=section_names,
        )

    def _draft_for_post_format_review(self, project_id: str) -> dict:
        """Prefer formatted/humanized text — review runs after Format."""
        bundle = self.store.require_bundle(project_id)
        formatted = bundle.project.artifacts.get("formatted_document")
        if isinstance(formatted, dict) and str(formatted.get("plain_text") or "").strip():
            try:
                base = self._load_humanized_draft(project_id).to_dict()
            except KeyError:
                base = self._load_draft(project_id).to_dict()
            return {
                **base,
                "content": str(formatted.get("plain_text") or base.get("content") or ""),
                "total_words": int(
                    formatted.get("word_count")
                    or base.get("total_words")
                    or len(str(formatted.get("plain_text") or "").split())
                ),
            }
        return self._draft_for_review(project_id)

    def run_academic_review(self, project_id: str):
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        research_plan = self._load_research_plan(project_id).to_dict()
        blueprint = self._load_blueprint(project_id).to_dict()
        # Review runs after Format — evaluate humanized/formatted content.
        draft = self._draft_for_post_format_review(project_id)

        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.STYLE_REVIEW, force=True)
        report = self.reviewer.review_draft(
            requirement_json=requirement,
            research_plan=research_plan,
            blueprint=blueprint,
            draft=draft,
            project_id=project_id,
        )

        project = self.store.require_project(project_id)
        pass_number = int(project.artifacts.get("review_pass_number", 0)) + 1
        project.artifacts["review_pass_number"] = pass_number
        project.artifacts["last_review_issues_found"] = len(report.issues)
        self.store.save_project(project)
        saved = self._persist_review_report(project_id, report)

        draft = self._load_draft(project_id)
        try:
            self.revision.update_review_score(
                project_id,
                version=draft.version,
                review_score=saved.overall_score,
            )
        except KeyError:
            self.revision.register_initial_draft(draft)

        if not saved.passed:
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
                output={
                    "review_report_id": saved.id,
                    "passed": saved.passed,
                    "overall_score": saved.overall_score,
                },
                artifacts={"review_report": saved.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return saved

    def get_review_report(self, project_id: str):
        return self._load_review_report(project_id)

    def run_revision(self, project_id: str, *, review_report: dict[str, Any] | None = None):
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        research_plan = self._load_research_plan(project_id).to_dict()
        blueprint = self._load_blueprint(project_id).to_dict()
        draft = self._draft_for_post_format_review(project_id)
        review = self._load_review_report(project_id, seed=review_report).to_dict()

        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.REVISION, force=True)

        if review.get("passed") or not list(review.get("issues") or []):
            result_payload = {
                "id": None,
                "skipped": False,
                "no_issues": True,
                "attempt_number": 0,
                "draft": draft,
            }
            self.pipeline.complete_stage(
                project_id,
                PipelineStage.REVISION,
                StageResult(
                    output={"no_issues": True, "draft_version": draft.get("version")},
                    artifacts={"revision_result": result_payload},
                ),
            )
            self._sync_pipeline_state(project_id)
            return result_payload

        history = self.revision.get_history_or_empty(project_id)
        if history.revision_attempts >= MAX_REVISION_ATTEMPTS or history.needs_manual_review:
            raise ValueError("Maximum automatic revision attempts reached — project needs manual review")

        result = self.revision.revise_draft(
            requirement_json=requirement,
            research_plan=research_plan,
            blueprint=blueprint,
            draft=draft,
            review_report=review,
            project_id=project_id,
        )

        # Strip any instructional revision markers before persisting.
        cleaned = _strip_revision_meta(str(result.draft.get("content") or ""))
        if cleaned != str(result.draft.get("content") or ""):
            result.draft["content"] = cleaned
            result.draft["total_words"] = count_words(cleaned)

        project = self.store.require_project(project_id)
        project.artifacts["draft_id"] = result.draft["id"]
        project.artifacts["revision_attempts"] = result.attempt_number
        project.artifacts["last_revision_id"] = result.id
        project.artifacts["last_issues_fixed"] = len(result.issues_addressed)
        project.artifacts["revision_result"] = result.to_dict()
        if project.status == ProjectStatus.NEEDS_MANUAL_REVIEW and result.attempt_number < MAX_REVISION_ATTEMPTS:
            project.status = ProjectStatus.ACTIVE
        self.store.save_project(project)
        self._persist_draft(project_id, Draft.from_dict(result.draft))
        try:
            humanized = self._load_humanized_draft(project_id)
            humanized.content = str(result.draft.get("content") or humanized.content)
            humanized.total_words = int(result.draft.get("total_words") or humanized.total_words)
            humanized.version = int(result.draft.get("version") or humanized.version)
            self._persist_humanized_draft(project_id, humanized)
        except KeyError:
            pass

        # Gemini revision rewrites prose and undoes StealthWriter — re-humanize immediately.
        try:
            self._rehumanize_current_prose(project_id, reason="post_revision")
        except Exception as exc:  # noqa: BLE001
            trace("rehumanize.post_revision_failed", project_id=project_id, error=str(exc))

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
        # Keep formatted.docx in sync with revised prose before validation/delivery.
        try:
            self.run_formatting(project_id)
        except Exception:  # noqa: BLE001
            pass
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
        try:
            return self._load_humanizer_session(project_id)
        except KeyError:
            pass

        bundle = self.store.require_bundle(project_id)
        draft = self._load_draft(project_id).to_dict()
        blueprint = self._load_blueprint(project_id).to_dict()

        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.HUMANIZATION, force=True)

        session = self.humanizer.create_session(
            draft=draft,
            requirement_json=bundle.requirement.to_dict(),
            blueprint=blueprint,
            project_id=project_id,
        )
        return self._persist_humanizer_session(project_id, session)

    def advance_humanizer(self, project_id: str, *, humanizer_session: dict[str, Any] | None = None):
        session = self._load_humanizer_session(project_id, seed=humanizer_session)
        updated = self.humanizer.advance_paragraph(session.id)
        return self._persist_humanizer_session(project_id, updated)

    def merge_humanized_draft(self, project_id: str, *, humanizer_session: dict[str, Any] | None = None):
        session = self._load_humanizer_session(project_id, seed=humanizer_session)
        bundle = self.store.require_bundle(project_id)
        title = bundle.project.title or bundle.requirement.title or "Humanized Assignment Draft"
        humanized = self.humanizer.merge_humanized_draft(session.id, title=title)

        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.HUMANIZATION, force=True)
        self._persist_humanizer_session(project_id, session)
        saved = self._persist_humanized_draft(project_id, humanized)

        self.pipeline.complete_stage(
            project_id,
            PipelineStage.HUMANIZATION,
            StageResult(
                output={
                    "humanized_draft_id": saved.id,
                    "version": saved.version,
                    "paragraphs_processed": saved.paragraphs_processed,
                    "average_ai_reduction": saved.average_ai_reduction,
                },
                artifacts={"humanized_draft": saved.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return saved

    def get_humanizer_session(self, project_id: str):
        return self._load_humanizer_session(project_id)

    def get_humanized_draft(self, project_id: str):
        return self._load_humanized_draft(project_id)

    def run_citation_generation(self, project_id: str):
        bundle = self.store.require_bundle(project_id)
        draft = self._load_draft(project_id).to_dict()
        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.CITATION_GENERATION, force=True)
        pack, updated_draft = self.citation_engine.generate(
            draft=draft,
            requirement_json=bundle.requirement.to_dict(),
            project_id=project_id,
        )
        saved_draft = self._persist_draft(project_id, Draft.from_dict(updated_draft))
        project = self.store.require_project(project_id)
        project.artifacts["citation_pack"] = pack.to_dict()
        project.artifacts["draft_id"] = saved_draft.id
        self.store.save_project(project)
        self.pipeline.complete_stage(
            project_id,
            PipelineStage.CITATION_GENERATION,
            StageResult(
                output={
                    "citation_pack_id": pack.id,
                    "reference_count": len(pack.references),
                    "unresolved_count": len(pack.unresolved),
                },
                artifacts={"citation_pack": pack.to_dict(), "draft": saved_draft.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return pack

    def run_formatting(self, project_id: str):
        bundle = self.store.require_bundle(project_id)
        try:
            draft = self._load_humanized_draft(project_id).to_dict()
        except KeyError:
            draft = self._load_draft(project_id).to_dict()
        citation_pack = bundle.project.artifacts.get("citation_pack")
        if not isinstance(citation_pack, dict):
            citation_pack = None
        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.FORMATTING, force=True)
        formatted = self.format_engine.format_draft(
            draft=draft,
            requirement_json=bundle.requirement.to_dict(),
            project_id=project_id,
            citation_pack=citation_pack,
        )
        project = self.store.require_project(project_id)
        project.artifacts["formatted_document"] = formatted
        self.store.save_project(project)
        self.pipeline.complete_stage(
            project_id,
            PipelineStage.FORMATTING,
            StageResult(
                output={
                    "formatted_document_id": formatted.get("id"),
                    "path": formatted.get("path"),
                    "style_id": formatted.get("style_id"),
                },
                artifacts={"formatted_document": formatted},
            ),
        )
        self._sync_pipeline_state(project_id)
        return formatted

    def run_requirement_validation(self, project_id: str):
        from services.assignment_spec import AssignmentSpec, build_assignment_spec, run_grade_gate
        from services.assignment_spec.llm_repair import llm_rubric_repair

        bundle = self.store.require_bundle(project_id)
        formatted = bundle.project.artifacts.get("formatted_document")
        if not isinstance(formatted, dict):
            formatted = None
        try:
            text = str((formatted or {}).get("plain_text") or self._load_humanized_draft(project_id).content)
        except KeyError:
            text = self._load_draft(project_id).content
        citation_pack = bundle.project.artifacts.get("citation_pack")
        if not isinstance(citation_pack, dict):
            citation_pack = None

        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.REQUIREMENT_VALIDATION, force=True)

        requirement = bundle.requirement.to_dict()
        spec_data = bundle.project.artifacts.get("assignment_spec")
        if isinstance(spec_data, dict) and spec_data:
            spec = AssignmentSpec.from_dict(spec_data)
        else:
            spec = build_assignment_spec(requirement, project_id=project_id)

        # Validate → Repair → Validate (max 5). Persist repaired prose when improved.
        gate = run_grade_gate(
            content=text,
            spec=spec,
            formatted_profile=(formatted or {}).get("profile_summary") if formatted else None,
            llm_repair=llm_rubric_repair,
        )
        if gate.content != text:
            text = gate.content
            self._persist_repaired_draft_content(project_id, text)
            # Template/LLM repairs after humanization raise AI score — re-humanize.
            try:
                self._rehumanize_current_prose(project_id, reason="post_grade_gate")
                try:
                    text = self._load_humanized_draft(project_id).content
                except KeyError:
                    pass
            except Exception as exc:  # noqa: BLE001
                trace("rehumanize.post_grade_gate_failed", project_id=project_id, error=str(exc))

        report = self.requirement_validator.validate(
            document_text=text,
            requirement_json=requirement,
            citation_pack=citation_pack,
            formatted_document=formatted,
            project_id=project_id,
        )
        # Grade gate is authoritative for export.
        report["passed"] = bool(gate.passed)
        report["export_blocked"] = bool(gate.export_blocked)
        report["blocking_issues"] = list(
            dict.fromkeys(list(gate.blocking_issues) + list(report.get("blocking_issues") or []))
        )
        report["spec_validation"] = gate.spec_validation.to_dict()
        report["rubric_coverage"] = gate.rubric_coverage.to_dict()
        report["grade_gate"] = {
            "iterations": gate.iterations,
            "repair_log": gate.repair_log,
            "overall_predicted_grade": gate.rubric_coverage.overall_predicted_grade,
            "per_criterion_coverage": {
                c.label: c.coverage_percent for c in gate.rubric_coverage.criteria
            },
        }
        report["overall_score"] = int(round(gate.rubric_coverage.overall_predicted_grade))

        project = self.store.require_project(project_id)
        project.artifacts["validation_report"] = report
        project.artifacts["assignment_spec"] = spec.to_dict()
        project.artifacts["rubric_coverage"] = gate.rubric_coverage.to_dict()
        project.artifacts["grade_gate"] = report["grade_gate"]
        self.store.save_project(project)

        self.pipeline.complete_stage(
            project_id,
            PipelineStage.REQUIREMENT_VALIDATION,
            StageResult(
                output={
                    "passed": bool(report.get("passed")),
                    "export_blocked": bool(report.get("export_blocked")),
                    "overall_score": report.get("overall_score"),
                    "predicted_grade": gate.rubric_coverage.overall_predicted_grade,
                    "validation_report_id": report.get("id"),
                    "blocking_issues": report.get("blocking_issues") or [],
                    "repair_iterations": gate.iterations,
                },
                artifacts={"validation_report": report, "rubric_coverage": gate.rubric_coverage.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return report

    def _persist_repaired_draft_content(self, project_id: str, content: str) -> None:
        """Write repaired grade-gate content back into draft artifacts."""
        words = count_words(content)
        try:
            draft = self._load_draft(project_id)
            draft.content = content
            draft.total_words = words
            self._persist_draft(project_id, draft)
        except KeyError:
            pass
        try:
            humanized = self._load_humanized_draft(project_id)
            humanized.content = content
            humanized.total_words = words
            self._persist_humanized_draft(project_id, humanized)
        except KeyError:
            pass
        project = self.store.require_project(project_id)
        formatted = project.artifacts.get("formatted_document")
        if isinstance(formatted, dict):
            formatted = {**formatted, "plain_text": content, "word_count": words}
            project.artifacts["formatted_document"] = formatted
            self.store.save_project(project)

    def _rehumanize_current_prose(self, project_id: str, *, reason: str) -> HumanizedDraft:
        """Re-run StealthWriter after Gemini/grade-gate rewrites that undo humanization."""
        bundle = self.store.require_bundle(project_id)
        try:
            current = self._load_humanized_draft(project_id)
            content = current.content
            source_id = current.source_draft_id
            source_ver = int(current.version or 1)
            title = current.title
        except KeyError:
            draft = self._load_draft(project_id)
            content = draft.content
            source_id = draft.id
            source_ver = int(draft.version or 1)
            title = draft.title

        try:
            blueprint = self._load_blueprint(project_id).to_dict()
        except KeyError:
            blueprint = bundle.project.artifacts.get("blueprint") or {}
        if not isinstance(blueprint, dict):
            blueprint = {}

        fresh = self.humanizer.rehumanize_full_draft(
            content=content,
            requirement_json=bundle.requirement.to_dict(),
            blueprint=blueprint,
            project_id=project_id,
            title=title,
            source_draft_id=source_id,
            source_draft_version=source_ver,
        )
        saved = self._persist_humanized_draft(project_id, fresh)
        project = self.store.require_project(project_id)
        formatted = project.artifacts.get("formatted_document")
        if isinstance(formatted, dict):
            project.artifacts["formatted_document"] = {
                **formatted,
                "plain_text": saved.content,
                "word_count": saved.total_words,
                "needs_reformat": True,
            }
        project.artifacts["rehumanized_after"] = reason
        self.store.save_project(project)
        # Rebuild DOCX from the newly humanized prose when a formatted artifact exists.
        if isinstance(formatted, dict):
            try:
                self.run_formatting(project_id)
            except Exception as exc:  # noqa: BLE001
                trace("rehumanize.reformat_failed", project_id=project_id, error=str(exc))
        trace(
            "rehumanize.applied",
            project_id=project_id,
            reason=reason,
            words=saved.total_words,
        )
        return saved

    def start_ai_detection(self, project_id: str):
        try:
            return self._load_detection_session(project_id)
        except KeyError:
            pass

        bundle = self.store.require_bundle(project_id)
        humanized = self._load_humanized_draft(project_id).to_dict()
        humanizer_session = self._load_humanizer_session(project_id)
        humanizer_ids = [p.paragraph_id for p in humanizer_session.paragraphs]

        project = self.store.require_project(project_id)
        attempt_number = int(project.artifacts.get("detection_attempt_number", 0)) + 1
        project.artifacts["detection_attempt_number"] = attempt_number
        self.store.save_project(project)

        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.AI_DETECTION, force=True)
        session = self.ai_detection.create_session(
            humanized_draft=humanized,
            requirement_json=bundle.requirement.to_dict(),
            project_id=project_id,
            humanizer_paragraph_ids=humanizer_ids,
        )
        return self._persist_detection_session(project_id, session)

    def advance_ai_detection(self, project_id: str, *, detection_session: dict[str, Any] | None = None):
        session = self._load_detection_session(project_id, seed=detection_session)
        humanizer_session = None
        try:
            humanizer_session = self._load_humanizer_session(project_id)
        except KeyError:
            trace("detection.advance.humanizer_missing", project_id=project_id)

        def rehumanize(paragraph_id: str, current_text: str) -> str:
            if humanizer_session is None:
                return current_text
            text = self.humanizer.rehumanize_paragraph_for_detection(humanizer_session.id, paragraph_id)
            self._persist_humanizer_session(project_id, humanizer_session)
            try:
                self._persist_humanized_draft(project_id, self._load_humanized_draft(project_id))
            except KeyError:
                pass
            return text

        updated = self.ai_detection.advance_paragraph(session.id, rehumanize=rehumanize)
        saved = self._persist_detection_session(project_id, updated)
        # advance_paragraph may auto-finalize into the worker's RAM — persist report to disk.
        if saved.report_id:
            try:
                report = self.ai_detection.reports.get(saved.report_id)
                if report is not None:
                    self._persist_detection_report(project_id, report)
            except Exception as exc:  # noqa: BLE001
                trace(
                    "detection.advance.report_persist_failed",
                    project_id=project_id,
                    error=str(exc),
                )
        return saved

    def finalize_ai_detection(self, project_id: str, *, detection_session: dict[str, Any] | None = None):
        session = self._load_detection_session(project_id, seed=detection_session)

        # Prefer report already on disk (other worker may have finalized during advance).
        try:
            existing = self._load_detection_report(project_id)
            if existing.session_id == session.id or not session.report_id:
                return self._finish_detection_pipeline(project_id, existing)
        except KeyError:
            pass

        report = None
        if session.report_id:
            report = self.ai_detection.reports.get(session.report_id)

        if report is None:
            # Rebuild on this worker if report was never persisted / wrong worker RAM.
            session.report_id = None
            session = self.ai_detection.finalize_session(session.id)
            self._persist_detection_session(project_id, session)
            report = self.ai_detection.reports.get(session.report_id)
            if report is None:
                raise KeyError(f"Detection report not found for session: {session.id}")

        saved = self._persist_detection_report(project_id, report)
        return self._finish_detection_pipeline(project_id, saved)

    def _finish_detection_pipeline(self, project_id: str, report: DetectionReport):
        self._ensure_pipeline_project(project_id)
        saved = self._persist_detection_report(project_id, report)
        project = self.store.require_project(project_id)
        if saved.final_status.value == "needs_manual_review":
            project.status = ProjectStatus.NEEDS_MANUAL_REVIEW
            self.store.save_project(project)

        self.pipeline.complete_stage(
            project_id,
            PipelineStage.AI_DETECTION,
            StageResult(
                output={
                    "detection_report_id": saved.id,
                    "overall_ai_score": saved.overall_ai_score,
                    "final_status": saved.final_status.value,
                },
                artifacts={"detection_report": saved.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return saved

    def prepare_detection_retry(self, project_id: str) -> None:
        """Re-humanize paragraphs that exceeded the AI score threshold, then require a new review."""
        from services.ai_detection_engine.thresholds import score_passes

        report = self.get_detection_report(project_id)
        high_sections = [
            str(item.get("section") or "")
            for item in (report.paragraph_scores or [])
            if not score_passes(float(item.get("ai_score") or 0), report.thresholds)
        ]
        if high_sections:
            self._rehumanize_revised_sections(project_id, high_sections)
        project = self.store.require_project(project_id)
        project.artifacts.pop("review_report_id", None)
        project.artifacts.pop("review_report", None)
        project.artifacts.pop("detection_report_id", None)
        project.artifacts.pop("detection_report", None)
        project.artifacts.pop("detection_session_id", None)
        project.artifacts.pop("detection_session", None)
        self.store.save_project(project)

    def get_detection_session(self, project_id: str):
        return self._load_detection_session(project_id)

    def get_detection_report(self, project_id: str):
        return self._load_detection_report(project_id)

    def run_delivery(self, project_id: str):
        bundle = self.store.require_bundle(project_id)
        try:
            final_draft = self._load_humanized_draft(project_id).to_dict()
        except KeyError:
            final_draft = self._load_draft(project_id).to_dict()

        formatted = bundle.project.artifacts.get("formatted_document")
        if isinstance(formatted, dict) and formatted.get("plain_text"):
            final_draft = {
                **final_draft,
                "content": formatted.get("plain_text"),
                "title": final_draft.get("title") or bundle.requirement.title,
            }

        # Hard grade gate: validate → repair (max 5) → export only if all checks pass.
        from services.assignment_spec import AssignmentSpec, build_assignment_spec, run_grade_gate
        from services.assignment_spec.llm_repair import llm_rubric_repair

        spec_data = bundle.project.artifacts.get("assignment_spec")
        if isinstance(spec_data, dict) and spec_data:
            spec = AssignmentSpec.from_dict(spec_data)
        else:
            spec = build_assignment_spec(bundle.requirement.to_dict(), project_id=project_id)

        gate = run_grade_gate(
            content=str(final_draft.get("content") or ""),
            spec=spec,
            formatted_profile=(formatted or {}).get("profile_summary") if isinstance(formatted, dict) else None,
            llm_repair=llm_rubric_repair,
        )
        if gate.content != str(final_draft.get("content") or ""):
            final_draft = {
                **final_draft,
                "content": gate.content,
                "total_words": count_words(gate.content),
            }
            self._persist_repaired_draft_content(project_id, gate.content)
            try:
                humanized = self._rehumanize_current_prose(project_id, reason="post_delivery_grade_gate")
                final_draft = {
                    **final_draft,
                    "content": humanized.content,
                    "total_words": humanized.total_words,
                }
            except Exception as exc:  # noqa: BLE001
                trace("rehumanize.post_delivery_grade_gate_failed", project_id=project_id, error=str(exc))
            # Re-format after successful content repair so delivery DOCX matches repaired prose.
            try:
                self.run_formatting(project_id)
                bundle = self.store.require_bundle(project_id)
                formatted = bundle.project.artifacts.get("formatted_document")
            except Exception:  # noqa: BLE001
                pass

        project = self.store.require_project(project_id)
        project.artifacts["assignment_spec"] = spec.to_dict()
        project.artifacts["rubric_coverage"] = gate.rubric_coverage.to_dict()
        project.artifacts["grade_gate"] = {
            "iterations": gate.iterations,
            "repair_log": gate.repair_log,
            "overall_predicted_grade": gate.rubric_coverage.overall_predicted_grade,
            "per_criterion_coverage": {
                c.label: c.coverage_percent for c in gate.rubric_coverage.criteria
            },
            "passed": gate.passed,
            "export_blocked": gate.export_blocked,
        }
        if not gate.passed:
            # Soft-export: keep packaging available so the student can download.
            # Blocking issues are stored for review; do not strand the UI on "ready" with no ZIP.
            project.artifacts["validation_report"] = {
                **(project.artifacts.get("validation_report") or {}),
                "passed": False,
                "export_blocked": False,
                "soft_export": True,
                "blocking_issues": gate.blocking_issues,
                "spec_validation": gate.spec_validation.to_dict(),
                "rubric_coverage": gate.rubric_coverage.to_dict(),
            }
            project.artifacts["grade_gate"]["export_blocked"] = False
            project.artifacts["grade_gate"]["soft_export"] = True
            self.store.save_project(project)
            trace(
                "delivery.soft_export",
                project_id=project_id,
                blocking_issues=gate.blocking_issues[:8],
            )
        else:
            self.store.save_project(project)

        research_plan = self._load_research_plan(project_id).to_dict()
        blueprint = self._load_blueprint(project_id).to_dict()
        try:
            review_report = self._load_review_report(project_id).to_dict()
        except KeyError as exc:
            raise KeyError(
                "Review report not found — finish academic review before delivery"
            ) from exc
        try:
            detection_report = self._load_detection_report(project_id).to_dict()
        except KeyError as exc:
            raise KeyError(
                "Detection report not found — finish AI detection before delivery"
            ) from exc

        revision_history = self.revision.get_history_or_empty(project_id)
        humanization_attempts = 0
        try:
            humanizer_session = self._load_humanizer_session(project_id)
            humanization_attempts = sum(p.attempts for p in humanizer_session.paragraphs)
        except KeyError:
            humanization_attempts = 0
        completion_time = (
            str(research_plan.get("estimated_completion_time") or "")
            or str(blueprint.get("estimated_completion_time") or "")
            or "—"
        )

        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.DELIVERY, force=True)
        formatted_path = None
        if isinstance(formatted, dict) and formatted.get("path"):
            candidate = Path(str(formatted["path"]))
            if candidate.is_file():
                formatted_path = str(candidate)

        package = self.delivery.prepare_package(
            final_draft=final_draft,
            requirement_json=bundle.requirement.to_dict(),
            research_plan=research_plan,
            blueprint=blueprint,
            review_report=review_report,
            detection_report=detection_report,
            project_id=project_id,
            revision_attempts=revision_history.revision_attempts,
            humanization_attempts=humanization_attempts,
            completion_time=completion_time,
            formatted_document_path=formatted_path,
        )

        project = self.store.require_project(project_id)
        project.artifacts["delivery_package_id"] = package.id
        project.artifacts["delivery_package"] = package.to_dict()
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
        try:
            return self.delivery.get_package_by_project(project_id)
        except KeyError:
            pass
        bundle = self.store.require_bundle(project_id)
        snapshot = bundle.project.artifacts.get("delivery_package")
        if isinstance(snapshot, dict) and snapshot.get("id"):
            from services.delivery_engine.models import DeliveryPackage

            package = DeliveryPackage.from_dict(snapshot)
            return self.delivery.store.save(package)
        raise KeyError(f"Delivery package not found for project: {project_id}")

    def find_delivery_package(self, package_id: str):
        """Restore a delivery package from disk when another worker created it."""
        try:
            return self.delivery.get_package(package_id)
        except KeyError:
            pass
        from services.delivery_engine.models import DeliveryPackage

        root = self.store.storage_root
        if not root.exists():
            raise KeyError(f"Delivery package not found: {package_id}")
        for child in root.iterdir():
            if not child.is_dir():
                continue
            try:
                bundle = self.store.require_bundle(child.name)
            except KeyError:
                continue
            snapshot = bundle.project.artifacts.get("delivery_package")
            if isinstance(snapshot, dict) and str(snapshot.get("id") or "") == package_id:
                package = DeliveryPackage.from_dict(snapshot)
                return self.delivery.store.save(package)
        raise KeyError(f"Delivery package not found: {package_id}")

    STAGE_ARTIFACT_KEYS: dict[PipelineStage, tuple[str, ...]] = {
        PipelineStage.STYLE_REVIEW: ("review_report", "review_report_id", "last_review_issues_found"),
        PipelineStage.REVISION: ("revision_result", "last_revision_id", "last_issues_fixed"),
        PipelineStage.CITATION_GENERATION: ("citation_pack",),
        PipelineStage.HUMANIZATION: (
            "humanizer_session",
            "humanizer_session_id",
            "humanized_draft",
            "humanized_draft_id",
        ),
        PipelineStage.FORMATTING: ("formatted_document",),
        PipelineStage.REQUIREMENT_VALIDATION: ("validation_report",),
        PipelineStage.AI_DETECTION: (
            "detection_session",
            "detection_session_id",
            "detection_report",
            "detection_report_id",
        ),
        PipelineStage.DELIVERY: ("delivery_package", "delivery_package_id"),
    }

    def retry_stage(self, project_id: str, stage: PipelineStage | str):
        """Clear one stage's artifacts and re-run only that stage."""
        if not isinstance(stage, PipelineStage):
            stage = PipelineStage(str(stage))
        self._ensure_pipeline_project(project_id)
        project = self.store.require_project(project_id)
        for key in self.STAGE_ARTIFACT_KEYS.get(stage, ()):
            project.artifacts.pop(key, None)
        self.store.save_project(project)
        self.pipeline.reset_stage(project_id, stage)

        runners = {
            PipelineStage.STYLE_REVIEW: self.run_academic_review,
            PipelineStage.REVISION: self.run_revision,
            PipelineStage.CITATION_GENERATION: self.run_citation_generation,
            PipelineStage.FORMATTING: self.run_formatting,
            PipelineStage.REQUIREMENT_VALIDATION: self.run_requirement_validation,
            PipelineStage.DELIVERY: self.run_delivery,
        }
        if stage == PipelineStage.HUMANIZATION:
            self.start_humanizer(project_id)
            return self.get_humanizer_session(project_id)
        if stage == PipelineStage.AI_DETECTION:
            return self.start_ai_detection(project_id)
        runner = runners.get(stage)
        if runner is None:
            raise ValueError(f"Stage retry is not supported for: {stage.value}")
        return runner(project_id)

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
        from services.assignment_spec import build_assignment_spec

        project.assignment_type = requirement.assignment_type
        project.title = requirement.title or project.title
        project.estimated_word_count = requirement.word_count
        project.citation_style = requirement.citation_style
        if requirement.deadline and project.deadline is None:
            project.deadline = _parse_deadline(requirement.deadline)
        # Canonical requirement contract for all downstream stages.
        spec = build_assignment_spec(requirement.to_dict(), project_id=project.id)
        project.artifacts["assignment_spec"] = spec.to_dict()
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
