"""Project lifecycle service — coordinates data models and pipeline state."""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from services import project_files
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
from services.assignment_project.project_lock import (
    BILLING_LOCK,
    DOCUMENT_LOCK,
    payment_gate,
    project_file_lock,
)
from services.assignment_project.store import ProjectStore, ProjectUpdateConflictError
from services.economy import assignment_entitlements as entitlements
from services.economy import assignment_payments as payment_ledger
from services.assignment_project.trace_log import trace
from services.research_engine.models import ResearchPlan
from services.research_engine.parsed_documents import build_parsed_documents, writer_source_material
from services.writer_engine.models import SOURCE_MATERIALS_KEY
from services.research_engine.service import ResearchEngineService
from services.blueprint_engine.models import Blueprint
from services.blueprint_engine.service import BlueprintEngineService
from services.writer_engine.service import WriterEngineService, refresh_session_metrics, writer_queue_ids
from services.writer_engine.models import Draft, WriterSectionStatus, WriterSession, WriterSessionStatus, count_words
from services.reviewer_engine.service import ReviewerEngineService
from services.reviewer_engine.models import ReviewReport
from services.revision_engine.service import RevisionEngineService
from services.revision_engine.models import MAX_REVISION_ATTEMPTS
from services.revision_engine.gemini_reviser import _strip_revision_meta
from services.humanizer_engine.service import HumanizerEngineService
from services.humanizer_engine.models import HumanizedDraft, HumanizerSession
from services.ai_detection_engine.service import AIDetectionEngineService
from services.ai_detection_engine.models import (
    DetectionReport,
    DetectionSession,
    DetectionSessionStatus,
    DetectionThresholds,
    FinalDetectionStatus,
)
from services.delivery_engine.service import DeliveryEngineService
from services.project_engine import ProjectEngine, ProjectLifecycleStatus
from services.assignment_citations import AssignmentCitationEngine, repair_citation_names
from services.assignment_facts import FACTS_ARTIFACT, facts_material, facts_wanted, gather_verified_facts
from services.humanizer_engine.fidelity import repair_humanizer_meaning
from services.assignment_formatting import AssignmentFormatEngine
from services.requirement_validation import GeminiRequirementValidator
from services.assignment_pipeline.stages import PIPELINE_STAGES
from services.requirement_validation import GeminiRequirementValidator

MAX_CLIENT_REVISION_ROUNDS = 5


class PaymentRequiredError(ValueError):
    """A paid stage was requested for a project whose payment is not confirmed on the server."""


class StagePreconditionError(ValueError):
    """The request does not fit the project's current state (missing input, wrong order, limits).

    These are the caller's errors, never processing failures, so they are not refund evidence.
    """


class RequirementsLockedError(StagePreconditionError):
    """The project is paid for: its billable inputs (requirements, files, quote) are frozen."""

    code = "REQUIREMENTS_LOCKED"


class PriceChangedError(StagePreconditionError):
    """The stored quote no longer prices the project's current inputs, or is not the one shown."""

    code = "PRICE_CHANGED"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__("The price of this assignment changed. Review the new price and confirm again.")


class QuoteRequiredError(StagePreconditionError):
    """A new payment names no quote: the student has to confirm a price they were shown."""

    code = "QUOTE_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Review the current price and confirm it to continue.")


class PaidScopeError(PaymentRequiredError):
    """The project's billable inputs differ from the scope its payment covers."""


class RevisionLimitError(StagePreconditionError):
    """Every revision chat round of the project is used or held by a running request."""

    code = "REVISION_LIMIT_REACHED"


class RevisionScopeExceededError(StagePreconditionError):
    """A revision chat edit would grow the document beyond the words the payment covers."""

    code = "PAID_SCOPE_LIMIT_EXCEEDED"


class ProjectChangedError(StagePreconditionError):
    """The document an AI step worked from changed meanwhile; its result is not stored."""

    code = "PROJECT_CHANGED"

    def __init__(self) -> None:
        super().__init__("The assignment changed while this step was running. Nothing was overwritten; try again.")


class PaidScopeLimitExceededError(StagePreconditionError):
    """The finished document is longer than the words the payment covers; it is not delivered."""

    code = "PAID_SCOPE_LIMIT_EXCEEDED"


class DeliveryPackageStaleError(StagePreconditionError):
    """The stored package is not the checked build of the current document and payment."""

    code = "DELIVERY_PACKAGE_STALE"

    def __init__(self) -> None:
        super().__init__("This download is out of date. Prepare the delivery again to get the current version.")


class ResearchPlanChangedError(StagePreconditionError):
    """The plan this worker would use is not the project's current recorded version."""

    code = "RESEARCH_PLAN_CHANGED"


class PaidScopeExceededError(RuntimeError):
    """A built blueprint asks for more words than the payment covers; it is never stored."""


class PaymentStateUnavailableError(RuntimeError):
    """The payment ledger could not be read, so billable inputs are left unchanged."""


PROCESSING_FAILURE_KEY = "processing_failure"
DELIVERY_SCOPE_KEY = "delivery_scope"
REFUND_HISTORY_KEY = "refund_history"
REFUND_REVIEW_KEY = "refund_review_required"
PAYMENT_CYCLE_KEY = "payment_cycle_id"
PAYMENT_CYCLES_KEY = "payment_cycles"
PAYMENT_QUOTE_KEY = "payment_quote_id"
PRICING_KEY = "pricing"
QUOTE_SCOPE_VERSION = 1
# A blueprint may exceed the paid length only by the engine's per-section minimums.
BLUEPRINT_WORD_RATIO = 1.2
BLUEPRINT_WORD_SLACK = 200
WRITER_EXPECTED_SECTIONS_KEY = "writer_expected_section_ids"
# Append-only JSONL next to bundle.json: writer sections moved out of the current session.
WRITER_ARCHIVE_FILE = "writer_archive.jsonl"
RESEARCH_PLAN_SOURCE_KEY = "research_plan_source"
# Sticky: set the first time generated text is persisted, never cleared by retries, seeds or
# a new payment (earlier text becomes visible again once a refunded project is re-paid).
OUTPUT_GENERATED_KEY = "output_generated_at"
FAILURE_CLASSIFICATION = "execution"

_REFUND_MESSAGES = {
    "ALREADY_REFUNDED": "This assignment was already refunded.",
    "NOT_PAID": "Nothing to refund — payment was not charged.",
    "DELIVERED": "Delivery already completed — not eligible for an automatic refund.",
    "OUTPUT_GENERATED": (
        "Your assignment text was already generated, so this run is not eligible for an "
        "automatic refund. Please contact support if something is wrong."
    ),
    "NO_RECORDED_FAILURE": (
        "No failed step was recorded for this assignment, so it is not eligible for an "
        "automatic refund. Press Retry to continue, or contact support."
    ),
    "NO_AMOUNT": "Cannot determine refund amount for this project.",
    "NO_OWNER": "This project cannot be refunded automatically. Please contact support.",
    "LEGACY_PAYMENT_REVIEW": (
        "This payment needs a manual check before it can be refunded. Please contact support."
    ),
    "PAYMENT_RECORD_MISSING": (
        "This payment needs a manual check before it can be refunded. Please contact support."
    ),
    "OPERATION_IN_PROGRESS": (
        "A step of this assignment is still running. Wait for it to finish, then try again."
    ),
    "OPERATION_INTERRUPTED": (
        "This payment needs a manual check before it can be refunded. Please contact support."
    ),
    "OUTPUT_STATE_UNKNOWN": (
        "This payment needs a manual check before it can be refunded. Please contact support."
    ),
    "CLIENT_INPUT": (
        "This run used a research plan you edited, so it is not eligible for an automatic "
        "refund. Please contact support if something is wrong."
    ),
}

# Codes the ledger raises that need a human decision rather than a plain "no".
_REVIEW_REFUND_CODES = frozenset({"OPERATION_INTERRUPTED", "OUTPUT_STATE_UNKNOWN"})

# Raised before or around an engine call but describing the request, not the execution.
_REQUEST_ERRORS = (
    PaymentRequiredError,
    StagePreconditionError,
    ProjectUpdateConflictError,
    KeyError,
    PermissionError,
)


class RefundNotEligibleError(ValueError):
    """Refund refused by server-side rules; ``code`` is stable, the message is safe to show."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_REFUND_MESSAGES.get(code, "This assignment is not eligible for a refund."))


def _writer_text_generated(session: Any) -> bool:
    sections = session.get("sections") if isinstance(session, dict) else None
    if not isinstance(sections, list):
        return False
    return any(isinstance(section, dict) and str(section.get("generated_text") or "").strip() for section in sections)


def has_generated_output(artifacts: dict[str, Any] | None) -> bool:
    """True once any generated document text (even one section) was stored for this project."""
    art = artifacts if isinstance(artifacts, dict) else {}
    for key in (
        OUTPUT_GENERATED_KEY,
        "delivery_package",
        "formatted_document",
        "humanized_draft",
        "draft",
        "citation_pack",
        "revision_result",
    ):
        if art.get(key):
            return True
    return _writer_text_generated(art.get("writer_session"))


class _PaidOperation:
    __slots__ = ("project_id", "name", "op_id", "cycle_id")

    def __init__(self, project_id: str, name: str) -> None:
        self.project_id = project_id
        self.name = name
        self.op_id: str | None = None
        self.cycle_id: str | None = None


_paid_ops = threading.local()


def _current_paid_operation(project_id: str) -> _PaidOperation | None:
    for op in reversed(getattr(_paid_ops, "stack", None) or []):
        if op.project_id == project_id:
            return op
    return None


def _paid_operation(name: str):
    """Run a paid ProjectService method inside the project's payment gate (see project_lock)."""

    def decorate(method):
        @functools.wraps(method)
        def run(self: "ProjectService", project_id: str, *args: Any, **kwargs: Any):
            with self._paid_operation_scope(project_id, name):
                return method(self, project_id, *args, **kwargs)

        return run

    return decorate


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
        # The engines' memory stores are shared with the standalone APIs; a memory copy only
        # stands in for a project's stored artifact when this service produced or loaded it
        # for that same project. Keys are (artifact type, project id, object id).
        self._vouched_keys: set[tuple[str, str, str]] = set()
        self._vouched_lock = threading.Lock()

    def _require_payment(self, project_id: str, action: str) -> int:
        """Every paid stage calls this first, so no caller (route, retry, debug) can skip payment.

        The wallet ledger outranks the project JSON: a payment cycle already refunded there
        (say the worker died before the project was marked) can never fund more generation,
        and a cycle only funds the billable scope it was bound to. Returns the paid word count.
        """
        project = self.store.require_project(project_id)
        artifacts = project.artifacts if isinstance(project.artifacts, dict) else {}
        if artifacts.get("payment_confirmed") is not True:
            raise PaymentRequiredError(f"Payment must be confirmed before {action}")
        try:
            evidence = self.ledger_refund_evidence(project_id, artifacts)
        except (sqlite3.Error, LookupError):
            raise PaymentRequiredError(f"Payment could not be verified before {action}") from None
        if evidence is not None:
            self.reconcile_payment_state(project_id)
            raise PaymentRequiredError(f"Payment was refunded — confirm a new payment before {action}")
        return self._verify_paid_scope(project_id, artifacts, action)

    # ------------------------------------------------------------------ quotes and paid scope

    @staticmethod
    def scope_hash(bundle: ProjectBundle) -> str:
        """Fingerprint of everything a quote prices: the requirement JSON and the project's files."""
        payload = {
            "v": QUOTE_SCOPE_VERSION,
            "project_id": bundle.project.id,
            "requirement": bundle.requirement.to_dict(),
            "files": sorted(str(item.id) for item in bundle.files),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _list_price(requirement: RequirementJSON) -> dict[str, Any]:
        from services.economy.pricing import USD_TO_COINS

        pricing = calculate_project_price(requirement.to_dict())
        pricing["amount_coins"] = max(1, int(round(float(pricing["amount_usd"]) * USD_TO_COINS)))
        return pricing

    def _quote_problem(self, bundle: ProjectBundle) -> str | None:
        """Why the stored quote can't be paid as is; None when it prices exactly these inputs."""
        project = bundle.project
        quote = project.artifacts.get(PRICING_KEY)
        if not isinstance(quote, dict) or not quote.get("quote_id") or not quote.get("scope_hash"):
            return "QUOTE_MISSING"
        if str(quote.get("project_id") or "") != str(project.id):
            return "QUOTE_OTHER_PROJECT"
        if quote.get("quote_version") != QUOTE_SCOPE_VERSION or "user_id" not in quote:
            return "QUOTE_MISSING"
        if str(quote.get("user_id") or "") != str(project.user_id or ""):
            return "QUOTE_OTHER_USER"
        if quote["scope_hash"] != self.scope_hash(bundle):
            return "SCOPE_CHANGED"
        fresh = self._list_price(bundle.requirement)
        if quote.get("currency") != fresh["currency"]:
            return "CURRENCY_CHANGED"
        try:
            same = (
                round(float(quote["amount_usd"]), 2) == round(float(fresh["amount_usd"]), 2)
                and int(quote["amount_coins"]) == fresh["amount_coins"]
                and int(quote["word_count"]) == int(fresh["word_count"])
                and project.price is not None
                and round(float(project.price), 2) == round(float(fresh["amount_usd"]), 2)
            )
        except (KeyError, TypeError, ValueError):
            same = False
        return None if same else "AMOUNT_CHANGED"

    def payable_quote(self, project_id: str, *, quote_id: str | None = None) -> dict[str, Any]:
        """The server quote a payment may be taken for, recomputed from the stored inputs.

        ``quote_id`` is the quote the student was shown and confirmed. It is required: the
        current quote is never charged in place of one the student did not name.
        """
        bundle = self.store.require_bundle(project_id)
        art = bundle.project.artifacts
        if bundle.project.price is None and not isinstance(art.get(PRICING_KEY), dict):
            raise StagePreconditionError("Price must be calculated before payment confirmation")
        problem = self._quote_problem(bundle)
        if problem is not None:
            trace("service.quote.refused", project_id=project_id, reason=problem)
            raise PriceChangedError(problem)
        if not isinstance(quote_id, str) or not quote_id.strip():
            raise QuoteRequiredError()
        quote = dict(art[PRICING_KEY])
        if quote_id != str(quote["quote_id"]):
            raise PriceChangedError("QUOTE_SUPERSEDED")
        return quote

    def _billing_lock(self, project_id: str):
        return project_file_lock(project_id, name=BILLING_LOCK, root=self.store.storage_root)

    def inputs_locked_by_payment(self, project_id: str) -> bool:
        """Paid per the project JSON or, when that was lost, per a live cycle in the ledger."""
        art = self.store.require_project(project_id).artifacts or {}
        if art.get("payment_confirmed") is True:
            return True
        try:
            return payment_ledger.live_cycle(project_id) is not None
        except sqlite3.Error:
            raise PaymentStateUnavailableError("Payment state is temporarily unavailable.") from None

    def _assert_inputs_editable(self, project_id: str, message: str) -> None:
        if self.inputs_locked_by_payment(project_id):
            trace("service.inputs_locked", project_id=project_id)
            raise RequirementsLockedError(message)

    def _requote_locked(self, project_id: str) -> None:
        """Billable inputs changed: a project that had a quote gets one for the new inputs."""
        project = self.store.require_project(project_id)
        if project.price is None and not project.artifacts.get(PRICING_KEY):
            return
        self._price_locked(project_id)

    def requote(self, project_id: str) -> ProjectBundle:
        """Replace an outdated quote of an unpaid project (caller may hold the billing lock)."""
        with self._billing_lock(project_id):
            self._assert_inputs_editable(project_id, "The price can't be changed after payment.")
            return self._price_locked(project_id)

    def _verify_paid_scope(self, project_id: str, artifacts: dict[str, Any], action: str) -> int:
        """The live payment must cover exactly the current billable inputs; returns its word count."""
        bundle = self.store.require_bundle(project_id)
        current = self.scope_hash(bundle)
        cycle_id = artifacts.get(PAYMENT_CYCLE_KEY)
        cycle: dict[str, Any] | None = None
        if cycle_id:
            try:
                cycle = payment_ledger.get_cycle(str(cycle_id))
            except sqlite3.Error:
                raise PaymentRequiredError(f"Payment could not be verified before {action}") from None
            if cycle is None or cycle.get("project_id") != project_id:
                raise PaymentRequiredError(f"Payment could not be verified before {action}")
            if cycle.get("scope_hash"):
                if cycle["scope_hash"] != current:
                    trace("service.paid_scope.mismatch", project_id=project_id, cycle_id=str(cycle_id))
                    raise PaidScopeError(f"The assignment no longer matches what was paid for ({action}).")
                return int(cycle.get("quoted_word_count") or self._list_price(bundle.requirement)["word_count"])
        words = self._legacy_paid_words(bundle, current)
        if words is None:
            trace("service.paid_scope.unverified", project_id=project_id, cycle_id=str(cycle_id or ""))
            raise PaidScopeError(f"This payment needs a manual check before {action}. Please contact support.")
        if cycle is not None:
            try:
                payment_ledger.bind_cycle_scope(project_id, str(cycle_id), scope_hash=current, word_count=words)
                bound = payment_ledger.get_cycle(str(cycle_id)) or {}
            except sqlite3.Error:
                raise PaymentRequiredError(f"Payment could not be verified before {action}") from None
            if bound.get("scope_hash") != current:
                raise PaidScopeError(f"The assignment no longer matches what was paid for ({action}).")
            trace("service.paid_scope.legacy_bound", project_id=project_id, cycle_id=str(cycle_id))
        return words

    def _legacy_paid_words(self, bundle: ProjectBundle, current: str) -> int | None:
        """Word count a payment without a bound scope covers, if its stored pricing proves it.

        The pricing artifact was computed from the requirement when the project was priced; the
        payment is trusted only while the current requirement still yields that same volume.
        """
        pricing = bundle.project.artifacts.get(PRICING_KEY)
        if not isinstance(pricing, dict):
            return None
        try:
            stored_words = int(pricing["word_count"])
        except (KeyError, TypeError, ValueError):
            return None
        if pricing.get("scope_hash"):
            return stored_words if pricing["scope_hash"] == current else None
        fresh = int(self._list_price(bundle.requirement)["word_count"])
        return fresh if fresh == stored_words else None

    def flag_payment_review(self, project_id: str, reason: str) -> None:
        self._flag_refund_review(project_id, reason)

    def ledger_refund_evidence(self, project_id: str, artifacts: dict[str, Any]) -> dict[str, Any] | None:
        """Refund already booked in the wallet ledger for the project's current payment, if any."""
        cycle_id = artifacts.get(PAYMENT_CYCLE_KEY)
        if cycle_id:
            return payment_ledger.cycle_refund_evidence(project_id, str(cycle_id))
        confirmed_at = artifacts.get("payment_confirmed_at")
        if not confirmed_at:
            return None
        reference = f"assignment-refund:{project_id}:{confirmed_at}"
        try:
            booked = payment_ledger.refund_recorded(reference)
        except sqlite3.Error:
            # Payments from before payment cycles: the ledger check is best effort only.
            return None
        return {"coins": booked, "reference": reference, "status": "legacy"} if booked is not None else None

    def reconcile_payment_state(self, project_id: str, *, locked: bool = False) -> bool:
        """Mark the project refunded when the ledger already refunded its current payment.

        Never moves money. Runs under the billing lock (``locked=True`` when the caller holds
        it) so it cannot interleave with a new confirmation or another refund.
        """
        if not locked:
            artifacts = self.store.require_project(project_id).artifacts or {}
            if artifacts.get("payment_confirmed") is not True:
                return False
            if self.ledger_refund_evidence(project_id, artifacts) is None:
                return False
            with project_file_lock(project_id, name=BILLING_LOCK, root=self.store.storage_root):
                return self.reconcile_payment_state(project_id, locked=True)
        artifacts = self.store.require_project(project_id).artifacts or {}
        if artifacts.get("payment_confirmed") is not True:
            return False
        evidence = self.ledger_refund_evidence(project_id, artifacts)
        if evidence is None:
            return False
        cycle_id = artifacts.get(PAYMENT_CYCLE_KEY)
        if cycle_id and evidence.get("status") == "refund_row_only":
            # Close the cycle against the booked row (no credit) so a later confirmation
            # cannot adopt it as a live payment.
            cycle = payment_ledger.get_cycle(str(cycle_id)) or {}
            closed = payment_ledger.close_cycle(
                project_id,
                str(cycle_id),
                user_id=int(cycle.get("user_id") or 0),
                kind="reconciled",
                reason="refund row found without closed cycle",
            )
            evidence = {**evidence, "coins": int(closed.get("coins_refunded") or 0)}
        self.mark_assignment_refunded(
            project_id,
            int(evidence.get("coins") or 0),
            reference=evidence.get("reference"),
            kind="reconciled",
            reason=f"ledger refund recovered ({evidence.get('status')})",
        )
        trace(
            "refund.assignment.reconciled",
            project_id=project_id,
            reference=evidence.get("reference"),
            ledger_status=evidence.get("status"),
        )
        return True

    @contextmanager
    def _execution_boundary(self, project_id: str, stage: str, *, client_seeded: bool = False) -> Iterator[None]:
        """Wrap the one engine call that does the generation work (AI provider, document build).

        Only an exception raised inside it becomes refund evidence for the current payment
        cycle; request errors (payment, prerequisites, order, limits) are raised before it
        or pass through. A successful run resolves earlier evidence.
        """
        try:
            yield
        except _REQUEST_ERRORS:
            raise
        except Exception as exc:
            seeded = client_seeded or self._client_input_used(project_id)
            self._record_processing_failure(project_id, stage, exc, client_seeded=seeded)
            raise
        else:
            self._clear_processing_failure(project_id)

    @contextmanager
    def _paid_operation_scope(self, project_id: str, name: str) -> Iterator[None]:
        """Payment gate held shared from the payment check until the output evidence exists.

        Refunds take the gate exclusively, so none can land between ``_require_payment`` and
        the persisted output of an operation running in any worker. Nested paid calls (retry,
        delivery repairs) run inside the outer operation.
        """
        if _current_paid_operation(project_id) is not None:
            yield
            return
        self.store.require_project(project_id)
        with payment_gate(project_id, root=self.store.storage_root):
            op = _PaidOperation(project_id, name)
            stack = getattr(_paid_ops, "stack", None)
            if stack is None:
                stack = _paid_ops.stack = []
            stack.append(op)
            status = "completed"
            try:
                self._journal_operation_start(op)
                yield
            except _REQUEST_ERRORS:
                status = "rejected"
                raise
            except Exception:
                status = "failed"
                raise
            except BaseException:
                status = "interrupted"
                raise
            finally:
                stack.remove(op)
                if op.op_id:
                    try:
                        payment_ledger.finish_operation(op.op_id, status)
                    except sqlite3.Error as exc:
                        trace(
                            "operation.finish_failed",
                            project_id=project_id,
                            operation=name,
                            error_type=type(exc).__name__,
                        )

    def _journal_operation_start(self, op: _PaidOperation) -> None:
        art = self.store.require_project(op.project_id).artifacts or {}
        if art.get("payment_confirmed") is not True:
            return
        cycle_id = art.get(PAYMENT_CYCLE_KEY)
        op.cycle_id = str(cycle_id) if cycle_id else None
        try:
            op.op_id = payment_ledger.begin_operation(op.project_id, op.cycle_id, op.name, pid=os.getpid())
        except sqlite3.Error:
            if op.cycle_id:
                raise PaymentRequiredError(f"Payment could not be verified before {op.name}") from None
            # Payments without a cycle are never refunded automatically; journaling is best effort.
            trace("operation.journal_unavailable", project_id=op.project_id, operation=op.name)

    def _save_output(self, project: Project, operation: str) -> None:
        """Persist ``project`` carrying generated text, then record that durably in the ledger.

        The journal is flagged 'persisting' before the JSON write and the append-only evidence
        row is added after it, so a crash in between blocks automatic refunds instead of
        allowing one, and evidence never precedes the stored text.
        """
        op = _current_paid_operation(project.id)
        if op is not None and op.op_id:
            payment_ledger.operation_persisting(op.op_id)
        self._mark_output_generated(project)
        with project_file_lock(project.id, name=DOCUMENT_LOCK, root=self.store.storage_root):
            self.store.save_project(project)
        self._record_output_evidence(
            project.id,
            project.artifacts.get(PAYMENT_CYCLE_KEY),
            op.name if op is not None else operation,
            source="persisted",
            op=op,
        )

    def _record_output_evidence(
        self,
        project_id: str,
        cycle_id: Any,
        operation: str,
        *,
        source: str,
        op: _PaidOperation | None = None,
    ) -> bool:
        try:
            payment_ledger.record_output(
                project_id,
                str(cycle_id) if cycle_id else None,
                operation,
                source=source,
                op_id=op.op_id if op is not None else None,
            )
            return True
        except sqlite3.Error as exc:
            # A journaled operation stays 'persisting', which keeps automatic refunds blocked.
            trace(
                "output.evidence_failed",
                project_id=project_id,
                operation=operation,
                error_type=type(exc).__name__,
            )
            return False

    def _record_processing_failure(
        self,
        project_id: str,
        stage: str,
        exc: BaseException,
        *,
        client_seeded: bool = False,
    ) -> None:
        def record(project: Project):
            if not project.artifacts.get("payment_confirmed"):
                return False
            project.artifacts[PROCESSING_FAILURE_KEY] = {
                "stage": stage,
                "classification": FAILURE_CLASSIFICATION,
                "error_type": type(exc).__name__,
                "recorded_at": utc_now().isoformat(),
                "payment_cycle_id": project.artifacts.get(PAYMENT_CYCLE_KEY),
                "payment_confirmed_at": project.artifacts.get("payment_confirmed_at"),
                "client_seeded": bool(client_seeded),
            }
            return True

        try:
            self.store.update_project(project_id, record)
        except Exception as record_exc:  # noqa: BLE001
            trace(
                "service.processing_failure.record_failed",
                project_id=project_id,
                stage=stage,
                error_type=type(record_exc).__name__,
            )

    def _clear_processing_failure(self, project_id: str) -> None:
        try:
            if PROCESSING_FAILURE_KEY not in self.store.require_project(project_id).artifacts:
                return
            self.store.update_project(
                project_id, lambda project: project.artifacts.pop(PROCESSING_FAILURE_KEY, None) is not None
            )
        except Exception as clear_exc:  # noqa: BLE001
            trace(
                "service.processing_failure.clear_failed",
                project_id=project_id,
                error_type=type(clear_exc).__name__,
            )

    def _flag_refund_review(self, project_id: str, reason: str) -> None:
        flag = {"reason": reason, "flagged_at": utc_now().isoformat()}
        try:
            self.store.update_project(project_id, lambda project: project.artifacts.__setitem__(REFUND_REVIEW_KEY, flag))
        except Exception as flag_exc:  # noqa: BLE001
            trace("refund.review_flag_failed", project_id=project_id, error_type=type(flag_exc).__name__)
        trace("refund.review_required", project_id=project_id, reason=reason)

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

        manifest_files = [
            {key: value for key, value in item.items() if key != "storage_path"}
            for item in list((upload_manifest or {}).get("files") or [])
            if isinstance(item, dict)
        ]
        if upload_manifest is not None:
            upload_manifest = {**upload_manifest, "files": manifest_files}
        payload_files = list(files or [])
        merged_files = payload_files or _files_from_manifest(manifest_files)

        for entry in merged_files:
            self._add_file_record(project_id, entry)

        self._sync_assignment_images(project_id)
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

    def _note_ignored_seed(self, project_id: str, kind: str, seed: Any, server_id: str | None) -> None:
        if isinstance(seed, dict) and seed:
            trace(
                "session.client_seed_ignored",
                project_id=project_id,
                kind=kind,
                same_id=bool(server_id) and str(seed.get("id") or "") == str(server_id),
            )

    @staticmethod
    def _vouch_key(obj: Any, project_id: str) -> tuple[str, str, str] | None:
        obj_id = str(getattr(obj, "id", "") or "")
        project_id = str(project_id or "")
        if not obj_id or not project_id:
            return None
        return (type(obj).__name__, project_id, obj_id)

    def _vouch(self, obj: Any) -> Any:
        """Register ``obj`` as this service's copy for the project named in ``obj.project_id``."""
        key = self._vouch_key(obj, getattr(obj, "project_id", None))
        if key is not None:
            with self._vouched_lock:
                self._vouched_keys.add(key)
        return obj

    def _vouched(self, obj: Any, project_id: str) -> bool:
        """``obj`` is this project's own copy: same project on the object and in the registry."""
        if obj is None or str(getattr(obj, "project_id", "") or "") != str(project_id or ""):
            return False
        key = self._vouch_key(obj, project_id)
        with self._vouched_lock:
            return key is not None and key in self._vouched_keys

    def _memory_matches_snapshot(self, mem: Any, snapshot: dict[str, Any], project_id: str) -> bool:
        """This worker's copy is the stored one: same id and same content (edits keep the id)."""
        if mem is None or mem.id != str(snapshot["id"]) or not self._vouched(mem, project_id):
            return False
        try:
            return type(mem).from_dict(snapshot).to_dict() == mem.to_dict()
        except Exception:  # noqa: BLE001
            return False

    def _stored_artifact(self, project_id: str, key: str) -> dict[str, Any] | None:
        try:
            snapshot = self.store.require_project(project_id).artifacts.get(key)
        except KeyError:
            return None
        return snapshot if isinstance(snapshot, dict) and snapshot.get("id") else None

    def _server_research_plan(self, project_id: str) -> ResearchPlan | None:
        mem = self.research.store.get_by_project(project_id)
        snapshot = self._stored_artifact(project_id, "research_plan")
        if snapshot is not None:
            if self._memory_matches_snapshot(mem, snapshot, project_id):
                return mem
            plan = ResearchPlan.from_dict(snapshot)
            plan.project_id = project_id
            return self._vouch(self.research.store.save(plan))
        if self._vouched(mem, project_id):
            return mem
        return None

    def _load_research_plan(
        self,
        project_id: str,
        *,
        seed: dict[str, Any] | None = None,
    ) -> ResearchPlan:
        """The server's plan; a browser copy is only adopted when the server has none.

        An adopted plan is tagged as client-sourced so failures built on it never count as
        refund evidence.
        """
        plan = self._server_research_plan(project_id)
        if plan is not None:
            self._note_ignored_seed(project_id, "research_plan", seed, plan.id)
            return plan
        if isinstance(seed, dict) and seed.get("id"):
            adopted = ResearchPlan.from_dict(seed)
            # A browser-chosen id could collide with another project's plan in the shared store.
            adopted.id = str(uuid.uuid4())
            adopted.project_id = project_id
            saved = self._vouch(self.research.store.save(adopted))
            with self._billing_lock(project_id):
                self._record_plan_version(project_id, saved.to_dict(), entitlements.SOURCE_CLIENT)
                project = self.store.require_project(project_id)
                project.artifacts["research_plan_id"] = saved.id
                project.artifacts["research_plan"] = saved.to_dict()
                project.artifacts[RESEARCH_PLAN_SOURCE_KEY] = "client"
                self.store.save_project(project)
            trace("research_plan.adopted_client_copy", project_id=project_id)
            return saved
        raise KeyError(f"Research plan not found for project: {project_id}")

    def _load_blueprint(self, project_id: str) -> Blueprint:
        mem = self.blueprint.store.get_by_project(project_id)
        snapshot = self._stored_artifact(project_id, "blueprint")
        if snapshot is not None:
            if self._memory_matches_snapshot(mem, snapshot, project_id):
                return mem
            blueprint = Blueprint.from_dict(snapshot)
            blueprint.project_id = project_id
            self.blueprint.store.save(blueprint)
            return self._vouch(blueprint)
        if self._vouched(mem, project_id):
            return mem
        raise KeyError(f"Blueprint not found for project: {project_id}")

    @staticmethod
    def _mark_output_generated(project: Project) -> None:
        if not project.artifacts.get(OUTPUT_GENERATED_KEY):
            project.artifacts[OUTPUT_GENERATED_KEY] = utc_now().isoformat()
            project.artifacts["output_generated_cycle_id"] = project.artifacts.get(PAYMENT_CYCLE_KEY)

    def _persist_writer_session(self, project_id: str, session: WriterSession) -> WriterSession:
        session.project_id = project_id
        saved = self._vouch(self.writer.sessions.save(session))
        project = self.store.require_project(project_id)
        project.artifacts["writer_session_id"] = saved.id
        project.artifacts["writer_session"] = saved.to_dict()
        if _writer_text_generated(project.artifacts["writer_session"]):
            self._save_output(project, "writing")
        else:
            self.store.save_project(project)
        return saved

    @staticmethod
    def _expected_writer_section_ids(artifacts: dict[str, Any]) -> list[str]:
        """Sections the server planned to write: recorded at session start from the stored blueprint."""
        recorded = artifacts.get(WRITER_EXPECTED_SECTIONS_KEY)
        if isinstance(recorded, list) and recorded:
            return [str(item) for item in recorded]
        blueprint = artifacts.get("blueprint")
        if isinstance(blueprint, dict) and blueprint.get("id"):
            return writer_queue_ids(blueprint)
        return []

    def _writer_archive_path(self, project_id: str) -> Path:
        return self.store.storage_root / project_id / WRITER_ARCHIVE_FILE

    def archived_writer_sections(self, project_id: str) -> list[dict[str, Any]]:
        """Quarantined writer sections (server-side audit/recovery only; never served as current)."""
        path = self._writer_archive_path(project_id)
        if not path.is_file():
            return []
        entries = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and entry.get("project_id") == project_id:
                entries.append(entry)
        return entries

    def _quarantine_writer_sections(
        self, project_id: str, session: WriterSession, sections: list[Any], artifacts: dict[str, Any], *, reason: str
    ) -> None:
        """Append sections leaving the current session to the project's archive, durably, first."""
        now = utc_now().isoformat()
        with project_file_lock(project_id, name="writer-archive", root=self.store.storage_root):
            known = {entry.get("key") for entry in self.archived_writer_sections(project_id)}
            lines = []
            for section in sections:
                data = section.to_dict()
                digest = hashlib.sha256(str(data.get("generated_text") or "").encode("utf-8")).hexdigest()
                key = f"{session.id}:{section.id}:{digest}"
                if key in known:
                    continue
                known.add(key)
                lines.append(
                    json.dumps(
                        {
                            "key": key,
                            "project_id": project_id,
                            "writer_session_id": session.id,
                            "section": data,
                            "archived_at": now,
                            "reason": reason,
                            "payment_cycle_id": artifacts.get(PAYMENT_CYCLE_KEY),
                            "blueprint_id": (artifacts.get("blueprint") or {}).get("id")
                            if isinstance(artifacts.get("blueprint"), dict)
                            else None,
                        },
                        ensure_ascii=False,
                    )
                )
            if lines:
                path = self._writer_archive_path(project_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n".join(lines) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
        if any(str(section.generated_text or "").strip() for section in sections):
            self._record_output_evidence(
                project_id, artifacts.get(PAYMENT_CYCLE_KEY), "writing", source="archived_section"
            )

    def _authoritative_writer_session(
        self, project_id: str, session: WriterSession, artifacts: dict[str, Any]
    ) -> tuple[WriterSession, bool]:
        """Move sections the blueprint never planned (legacy injected snapshots, sections of a
        replaced blueprint) out of the current session into the project's quarantine archive."""
        changed = session.project_id != project_id
        session.project_id = project_id
        expected = self._expected_writer_section_ids(artifacts)
        if not expected:
            return session, changed
        allowed = set(expected)
        seen: set[str] = set()
        kept = []
        for section in session.sections:
            if section.id in allowed and section.id not in seen:
                kept.append(section)
                seen.add(section.id)
        if len(kept) == len(session.sections):
            return session, changed
        kept_refs = {id(section) for section in kept}
        dropped = [section for section in session.sections if id(section) not in kept_refs]
        self._quarantine_writer_sections(
            project_id, session, dropped, artifacts, reason="not_in_expected_sections"
        )
        trace(
            "writer.session.unexpected_sections_quarantined",
            project_id=project_id,
            quarantined=[section.id for section in dropped][:20],
        )
        session.sections = kept
        if session.current_section_id not in seen:
            session.current_section_id = None
        refresh_session_metrics(session)
        if session.status == WriterSessionStatus.ACTIVE and session.current_section_id is None:
            pending = next((s for s in kept if s.status != WriterSectionStatus.COMPLETED), None)
            session.current_section_id = pending.id if pending else None
        return session, True

    def _load_writer_session(
        self,
        project_id: str,
        *,
        seed: dict[str, Any] | None = None,
    ) -> WriterSession:
        """The server-owned session: the stored copy, else this worker's memory.

        Browsers echo the session back on /writer/advance and /writer/merge. That copy never
        becomes state (it could add sections or fake progress); it is only noted.
        """
        try:
            artifacts = self.store.require_project(project_id).artifacts or {}
        except KeyError:
            artifacts = {}
        disk = None
        snapshot = artifacts.get("writer_session")
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
        mem = self.writer.sessions.get_by_project(project_id)
        if disk is not None:
            session = disk
        elif self._vouched(mem, project_id):
            session = mem
        else:
            raise KeyError(f"Writer session not found for project: {project_id}")
        self._note_ignored_seed(project_id, "writer_session", seed, session.id)
        session, changed = self._authoritative_writer_session(project_id, session, artifacts)
        self._vouch(self.writer.sessions.save(session))
        if disk is None or changed:
            return self._persist_writer_session(project_id, session)
        return session

    def _persist_draft(self, project_id: str, draft: Draft) -> Draft:
        draft.project_id = project_id
        saved = self._vouch(self.writer.drafts.save(draft))
        project = self.store.require_project(project_id)
        project.artifacts["draft_id"] = saved.id
        project.artifacts["draft"] = saved.to_dict()
        self._save_output(project, "draft")
        return saved

    def _load_draft(self, project_id: str) -> Draft:
        # Disk is source of truth across gunicorn workers.
        try:
            bundle = self.store.require_bundle(project_id)
            snapshot = bundle.project.artifacts.get("draft")
            if isinstance(snapshot, dict) and snapshot.get("id"):
                draft = Draft.from_dict(snapshot)
                draft.project_id = project_id
                return self._vouch(self.writer.drafts.save(draft))
        except KeyError:
            pass
        draft = self.writer.drafts.get_by_project(project_id)
        if self._vouched(draft, project_id):
            return draft
        raise KeyError(f"Draft not found for project: {project_id}")

    def _persist_humanizer_session(self, project_id: str, session: HumanizerSession) -> HumanizerSession:
        session.project_id = project_id
        saved = self._vouch(self.humanizer.sessions.save(session))
        project = self.store.require_project(project_id)
        project.artifacts["humanizer_session_id"] = saved.id
        project.artifacts["humanizer_session"] = saved.to_dict()
        self.store.save_project(project)
        return saved

    def _load_server_session(self, project_id: str, *, key: str, model: Any, memory: Any, persist: Any, seed: Any):
        """Stored copy, else this worker's memory; a browser-sent copy never becomes state.

        The memory fallback only accepts a session this service created or loaded for the
        project, never one created through the standalone engine APIs.
        """
        try:
            artifacts = self.store.require_project(project_id).artifacts or {}
        except KeyError:
            artifacts = {}
        disk = None
        snapshot = artifacts.get(key)
        if isinstance(snapshot, dict) and snapshot.get("id"):
            try:
                disk = model.from_dict(snapshot)
            except Exception as exc:  # noqa: BLE001
                trace(f"{key}.disk_corrupt", project_id=project_id, error=str(exc), error_type=type(exc).__name__)
        mem = memory.get_by_project(project_id)
        if disk is not None:
            session = disk
        elif self._vouched(mem, project_id):
            session = mem
        else:
            raise KeyError(f"{key} not found for project: {project_id}")
        self._note_ignored_seed(project_id, key, seed, session.id)
        session.project_id = project_id
        self._vouch(memory.save(session))
        if disk is None:
            return persist(project_id, session)
        return session

    def _load_humanizer_session(
        self,
        project_id: str,
        *,
        seed: dict[str, Any] | None = None,
    ) -> HumanizerSession:
        return self._load_server_session(
            project_id,
            key="humanizer_session",
            model=HumanizerSession,
            memory=self.humanizer.sessions,
            persist=self._persist_humanizer_session,
            seed=seed,
        )

    def _persist_humanized_draft(self, project_id: str, draft: HumanizedDraft) -> HumanizedDraft:
        draft.project_id = project_id
        draft.content = repair_citation_names(draft.content or "")
        saved = self._vouch(self.humanizer.drafts.save(draft))
        project = self.store.require_project(project_id)
        project.artifacts["humanized_draft_id"] = saved.id
        project.artifacts["humanized_draft"] = saved.to_dict()
        self._save_output(project, "humanized_draft")
        return saved

    def _load_humanized_draft(self, project_id: str) -> HumanizedDraft:
        try:
            bundle = self.store.require_bundle(project_id)
            snapshot = bundle.project.artifacts.get("humanized_draft")
            if isinstance(snapshot, dict) and snapshot.get("id"):
                draft = HumanizedDraft.from_dict(snapshot)
                draft.project_id = project_id
                return self._vouch(self.humanizer.drafts.save(draft))
        except KeyError:
            pass
        draft = self.humanizer.drafts.get_by_project(project_id)
        if self._vouched(draft, project_id):
            return draft
        raise KeyError(f"Humanized draft not found for project: {project_id}")

    def _persist_detection_session(self, project_id: str, session: DetectionSession) -> DetectionSession:
        session.project_id = project_id
        saved = self._vouch(self.ai_detection.sessions.save(session))
        project = self.store.require_project(project_id)
        project.artifacts["detection_session_id"] = saved.id
        project.artifacts["detection_session"] = saved.to_dict()
        self.store.save_project(project)
        return saved

    def _load_detection_session(
        self,
        project_id: str,
        *,
        seed: dict[str, Any] | None = None,
    ) -> DetectionSession:
        return self._load_server_session(
            project_id,
            key="detection_session",
            model=DetectionSession,
            memory=self.ai_detection.sessions,
            persist=self._persist_detection_session,
            seed=seed,
        )

    def _persist_detection_report(self, project_id: str, report: DetectionReport) -> DetectionReport:
        report.project_id = project_id
        saved = self._vouch(self.ai_detection.reports.save(report))
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
                return self._vouch(self.ai_detection.reports.save(report))
        except KeyError:
            pass
        report = self.ai_detection.reports.get_by_project(project_id)
        if self._vouched(report, project_id):
            return report
        raise KeyError(f"Detection report not found for project: {project_id}")

    def _persist_review_report(self, project_id: str, report: ReviewReport) -> ReviewReport:
        report.project_id = project_id
        saved = self._vouch(self.reviewer.store.save(report))
        project = self.store.require_project(project_id)
        project.artifacts["review_report_id"] = saved.id
        project.artifacts["review_report"] = saved.to_dict()
        self.store.save_project(project)
        return saved

    def _load_review_report(
        self,
        project_id: str,
        *,
        seed: dict[str, Any] | None = None,
    ) -> ReviewReport:
        """The server's review; a browser copy is only adopted when the server has none."""
        mem = self.reviewer.store.get_by_project(project_id)
        snapshot = self._stored_artifact(project_id, "review_report")
        report = None
        if snapshot is not None:
            if self._memory_matches_snapshot(mem, snapshot, project_id):
                report = mem
            else:
                restored = ReviewReport.from_dict(snapshot)
                restored.project_id = project_id
                report = self._vouch(self.reviewer.store.save(restored))
        elif self._vouched(mem, project_id):
            report = mem
        if report is not None:
            self._note_ignored_seed(project_id, "review_report", seed, report.id)
            return report
        if isinstance(seed, dict) and seed.get("id"):
            trace("review_report.adopted_client_copy", project_id=project_id)
            adopted = ReviewReport.from_dict(seed)
            # A browser-chosen id could collide with another project's report in the shared store.
            adopted.id = str(uuid.uuid4())
            return self._persist_review_report(project_id, adopted)
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

        pricing = artifacts.get(PRICING_KEY)
        paid = artifacts.get("payment_confirmed") is True
        # Unpaid: only a quote that prices the current inputs counts as a finished Pricing stage.
        priced = project.price is not None and bool(pricing) and (paid or self._quote_problem(bundle) is None)
        if priced:
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
        elif not paid:
            pipeline_project = self.pipeline.get_project(project_id)
            for stage in (PipelineStage.PRICING, PipelineStage.WAITING_FOR_PAYMENT):
                if pipeline_project.stage_state(stage).status != StageStatus.PENDING:
                    self.pipeline.reset_stage(project_id, stage)

        if paid:
            complete(
                PipelineStage.WAITING_FOR_PAYMENT,
                StageResult(output={"payment_confirmed": True}),
            )
        elif priced:
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
        with self._billing_lock(project_id):
            self._assert_inputs_editable(project_id, "Files can't be added after payment.")
            file_record = self._add_file_record(
                project_id,
                {
                    "file_type": file_type,
                    "original_filename": original_filename,
                    "parsed": parsed,
                },
                storage_path=storage_path,
            )
            self._requote_locked(project_id)
        self._sync_assignment_images(project_id)
        self._touch_project(project_id)
        return file_record

    def _project_images(self, project_id: str, images: Any) -> list[dict[str, str]]:
        """Stored image entries that still name a file inside this project's files directory."""
        from services.assignment_figures import merge_image_lists

        return merge_image_lists(images if isinstance(images, list) else [], project_id=project_id)

    def _sync_assignment_images(
        self,
        project_id: str,
        *,
        auto_fetch: bool = False,
    ) -> list[dict[str, str]]:
        """Persist image paths (uploads + optional Commons auto-fetch) for FIGURE embedding."""
        from services.assignment_figures import (
            brief_requires_photos,
            collect_assignment_images,
            extract_figure_queries,
            fetch_commons_figures,
            merge_image_lists,
        )
        from services.assignment_project.paths import project_files_dir
        from services.assignment_project.requirement_analyzer import _extract_file_text

        bundle = self.store.require_bundle(project_id)
        project = bundle.project
        uploaded = collect_assignment_images(bundle.files, project_id=project_id)
        existing = project.artifacts.get("assignment_images")
        existing_list = existing if isinstance(existing, list) else []

        images = merge_image_lists(uploaded, existing_list, project_id=project_id)

        if auto_fetch:
            source_bits = [
                project.note or "",
                project.title or "",
                str(bundle.requirement.title or ""),
            ]
            for file in bundle.files:
                try:
                    source_bits.append(_extract_file_text(file, project_id))
                except Exception:  # noqa: BLE001
                    continue
            source_blob = "\n\n".join(source_bits)
            if brief_requires_photos(source_blob) or not images:
                # Fetch when brief/sample asks for photos, or when we have none yet
                # but placeholders exist. Skip network if uploads already cover need.
                needs = brief_requires_photos(source_blob)
                if needs:
                    queries = extract_figure_queries(
                        source_blob,
                        sections=list(bundle.requirement.required_sections or []),
                        community=str(bundle.requirement.title or project.title or ""),
                    )
                    # Only fetch queries not already satisfied by existing captions/filenames.
                    have = {
                        str(i.get("query") or i.get("caption") or "").lower()
                        for i in images
                    }
                    pending = [
                        q
                        for q in queries
                        if q.get("query", "").lower() not in have
                        and q.get("caption", "").lower() not in have
                    ]
                    # If we already have enough images for scoped sections, skip.
                    scoped = [
                        s
                        for s in (bundle.requirement.required_sections or [])
                        if not re.search(
                            r"\b(references?|bibliography|works cited|cover)\b",
                            str(s),
                            re.I,
                        )
                    ]
                    target = max(2, min(4, len(scoped) * 2)) if scoped else 2
                    if pending and len(images) < target:
                        dest = project_files_dir(project_id) / "auto_figures"
                        need = max(0, target - len(images))
                        fetched = fetch_commons_figures(
                            project_id=project_id,
                            dest_dir=dest,
                            queries=pending[: max(need, len(pending))],
                        )
                        # Prefer exactly the remaining slots.
                        images = merge_image_lists(
                            images, fetched[:need] if need else fetched, project_id=project_id
                        )

        # The fetch above may be slow: write onto the current project, not the copy read before it.
        project = self.store.require_project(project_id)
        if images:
            project.artifacts["assignment_images"] = images
        else:
            project.artifacts.pop("assignment_images", None)
        project.updated_at = utc_now()
        self.store.save_project(project)
        return images

    def analyze_requirements(self, project_id: str) -> ProjectBundle:
        locked_message = "The requirements can't be changed after payment."
        self._ensure_pipeline_project(project_id)
        self._assert_inputs_editable(project_id, locked_message)
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
            # No lock across the AI call; the result is applied under the billing lock, so a
            # payment confirmed meanwhile wins and the late result is dropped untouched.
            with self._billing_lock(project_id):
                self._assert_inputs_editable(project_id, locked_message)
                current = self.store.require_requirement(project_id)
                analyzed.id = current.id
                analyzed.project_id = project_id
                self.store.save_requirement(analyzed, replace=True)
                self._apply_requirement_to_project(self.store.require_project(project_id), analyzed)
                self._requote_locked(project_id)
            self._sync_assignment_images(project_id, auto_fetch=True)

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
        with self._billing_lock(project_id):
            self._assert_inputs_editable(project_id, "The price can't be changed after payment.")
            return self._price_locked(project_id, priority=priority)

    def _price_locked(self, project_id: str, *, priority: str = "standard") -> ProjectBundle:
        """Store a new quote for the current inputs; the caller holds the billing lock."""
        self._ensure_pipeline_project(project_id)
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        if not requirement.get("analyzed_at") and not requirement.get("assignment_type"):
            raise ValueError("Requirement analysis must complete before pricing")

        project = bundle.project
        pricing = self._list_price(bundle.requirement)
        coins = int(pricing["amount_coins"])
        pricing.update(
            quote_id=uuid.uuid4().hex,
            quote_version=QUOTE_SCOPE_VERSION,
            project_id=project_id,
            user_id=str(project.user_id or ""),
            scope_hash=self.scope_hash(bundle),
            quoted_at=utc_now().isoformat(),
        )
        project.price = float(pricing["amount_usd"])
        project.credits = coins
        project.artifacts[PRICING_KEY] = pricing
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

    BRIEF_MIN_WORDS = 100
    BRIEF_MAX_WORDS = 20000

    def update_brief(
        self,
        project_id: str,
        *,
        assignment_type: str | None = None,
        word_count: int | None = None,
        citation_style: str | None = None,
        deadline: str | None = None,
        instructions: str | None = None,
    ) -> ProjectBundle:
        """Apply the student's corrections to the analyzed brief and re-price it."""
        with self._billing_lock(project_id):
            self._assert_inputs_editable(project_id, "The brief can't be changed after payment.")
            return self._update_brief_locked(
                project_id,
                assignment_type=assignment_type,
                word_count=word_count,
                citation_style=citation_style,
                deadline=deadline,
                instructions=instructions,
            )

    def _update_brief_locked(
        self,
        project_id: str,
        *,
        assignment_type: str | None,
        word_count: int | None,
        citation_style: str | None,
        deadline: str | None,
        instructions: str | None,
    ) -> ProjectBundle:
        bundle = self.store.require_bundle(project_id)
        project, requirement = bundle.project, bundle.requirement
        if not requirement.analyzed_at and not requirement.assignment_type:
            raise ValueError("Requirement analysis must complete before editing the brief.")

        if assignment_type is not None:
            requirement.assignment_type = assignment_type.strip()[:120] or None
        if word_count is not None:
            if not self.BRIEF_MIN_WORDS <= int(word_count) <= self.BRIEF_MAX_WORDS:
                raise ValueError(
                    f"Length must be between {self.BRIEF_MIN_WORDS} and {self.BRIEF_MAX_WORDS:,} words."
                )
            requirement.word_count = int(word_count)
        if citation_style is not None:
            requirement.citation_style = citation_style.strip()[:60] or None
        if deadline is not None:
            requirement.deadline = deadline.strip()[:120] or None
            project.deadline = _parse_deadline(requirement.deadline)
        if instructions is not None:
            instructions = instructions.strip()[:4000]
            base_note = project.artifacts.setdefault("original_note", project.note or "")
            project.artifacts["brief_instructions"] = instructions
            extra = f"Additional instructions from the student:\n{instructions}" if instructions else ""
            project.note = "\n\n".join(part for part in (base_note, extra) if part) or None

        self.store.save_requirement(requirement)
        self._apply_requirement_to_project(project, requirement)
        return self._price_locked(project_id)

    def check_payment_ready(self, project_id: str, *, quote_id: str | None = None) -> ProjectBundle:
        """Raise unless the stored quote prices the current inputs; nothing is charged here.

        Neither the pipeline's Pricing stage nor the JSON ``price`` can stand in for the quote:
        both are recomputed against the requirement and files before any payment.
        """
        bundle = self.store.require_bundle(project_id)
        trace(
            "service.confirm_payment.loaded",
            project_id=project_id,
            price=bundle.project.price,
            pricing_artifact=bundle.project.artifacts.get(PRICING_KEY),
            bundle_path=str(self.store._bundle_path(project_id).resolve()),
        )
        self.payable_quote(project_id, quote_id=quote_id)
        self._ensure_pipeline_project(project_id)
        pipeline_project = self.pipeline.get_project(project_id)
        pricing_state = pipeline_project.stage_state(PipelineStage.PRICING)
        if pricing_state.status != StageStatus.COMPLETED:
            raise StagePreconditionError("Pricing stage must complete before payment confirmation")
        return self.store.require_bundle(project_id)

    def confirm_payment(
        self,
        project_id: str,
        *,
        cycle: dict[str, Any] | None = None,
        quote_id: str | None = None,
    ) -> ProjectBundle:
        """Start a payment cycle on the project.

        ``cycle`` is the ``assignment_payments`` row the caller opened (debit or plan
        allowance); its id and amount become the only refund basis for this payment. Without
        it (internal callers, tests) nothing is refundable automatically. The quote is checked
        again under the billing lock, so inputs changed after the caller's check are refused.
        """
        bundle = self.store.require_bundle(project_id)
        if bundle.project.artifacts.get("payment_confirmed"):
            return bundle
        with self._billing_lock(project_id):
            return self._confirm_payment_locked(project_id, cycle=cycle, quote_id=quote_id)

    def _confirm_payment_locked(
        self,
        project_id: str,
        *,
        cycle: dict[str, Any] | None,
        quote_id: str | None,
    ) -> ProjectBundle:
        bundle = self.store.require_bundle(project_id)
        if bundle.project.artifacts.get("payment_confirmed"):
            return bundle
        bundle = self.check_payment_ready(project_id, quote_id=quote_id)
        quote = bundle.project.artifacts[PRICING_KEY]
        if cycle is not None and cycle.get("scope_hash") and cycle["scope_hash"] != quote["scope_hash"]:
            raise PaidScopeError("This payment covers a different version of the assignment.")
        artifacts = bundle.project.artifacts
        now = utc_now().isoformat()
        artifacts["payment_confirmed"] = True
        artifacts["payment_confirmed_at"] = now
        for key in (
            "payment_refunded",
            "payment_refunded_at",
            "payment_refund_coins",
            PROCESSING_FAILURE_KEY,
            REFUND_REVIEW_KEY,
            PAYMENT_CYCLE_KEY,
            "coins_charged",
            "plan_free_paper",
        ):
            artifacts.pop(key, None)
        artifacts[PAYMENT_QUOTE_KEY] = str(quote["quote_id"])
        if cycle is not None:
            method = cycle.get("method")
            artifacts[PAYMENT_CYCLE_KEY] = str(cycle["cycle_id"])
            artifacts["coins_charged"] = int(cycle.get("coins") or 0) if method == payment_ledger.METHOD_COINS else 0
            if method == payment_ledger.METHOD_ALLOWANCE:
                artifacts["plan_free_paper"] = True
            history = artifacts.get(PAYMENT_CYCLES_KEY)
            history = list(history) if isinstance(history, list) else []
            history.append(
                {
                    "cycle_id": str(cycle["cycle_id"]),
                    "method": method,
                    "coins": int(cycle.get("coins") or 0),
                    "confirmed_at": now,
                    "quote_id": str(quote["quote_id"]),
                }
            )
            artifacts[PAYMENT_CYCLES_KEY] = history
        bundle.project.updated_at = utc_now()
        self.store.save_project(bundle.project)

        self.pipeline.complete_stage(
            project_id,
            PipelineStage.WAITING_FOR_PAYMENT,
            StageResult(output={"payment_confirmed": True}),
        )
        self._sync_pipeline_state(project_id)
        return self.store.require_bundle(project_id)

    def _current_payment_cycle(self, project_id: str, art: dict[str, Any]) -> dict[str, Any]:
        """The ledger cycle behind the project's live payment; legacy payments go to admin review."""
        cycle_id = art.get(PAYMENT_CYCLE_KEY)
        if not cycle_id:
            self._flag_refund_review(project_id, "payment_without_cycle_record")
            raise RefundNotEligibleError("LEGACY_PAYMENT_REVIEW")
        try:
            cycle = payment_ledger.get_cycle(str(cycle_id))
        except sqlite3.Error:
            raise RefundNotEligibleError("PAYMENT_RECORD_MISSING") from None
        if cycle is None or cycle["project_id"] != project_id:
            self._flag_refund_review(project_id, "payment_cycle_record_missing")
            raise RefundNotEligibleError("PAYMENT_RECORD_MISSING")
        if cycle["status"] != payment_ledger.STATUS_ACTIVE:
            raise RefundNotEligibleError("ALREADY_REFUNDED")
        return cycle

    def refundable_amount(self, project_id: str) -> int:
        """Coins the current payment cycle actually debited (0 when paid from a plan allowance)."""
        art = self.store.require_project(project_id).artifacts or {}
        cycle = self._current_payment_cycle(project_id, art)
        return int(cycle["coins"] or 0) if cycle["method"] == payment_ledger.METHOD_COINS else 0

    def assert_admin_refund_allowed(self, project_id: str) -> int:
        """Admin exception path: only requires a live, not-yet-refunded payment cycle."""
        art = self.store.require_project(project_id).artifacts or {}
        if art.get("payment_refunded"):
            raise RefundNotEligibleError("ALREADY_REFUNDED")
        if art.get("payment_confirmed") is not True:
            raise RefundNotEligibleError("NOT_PAID")
        return self.refundable_amount(project_id)

    def assert_assignment_refund_eligible(self, project_id: str) -> int:
        """Automatic refund rules: paid, not refunded, no generated content yet, and an
        unresolved execution failure the server recorded for the current payment cycle."""
        art = self.store.require_project(project_id).artifacts or {}
        if art.get("payment_refunded"):
            raise RefundNotEligibleError("ALREADY_REFUNDED")
        if art.get("payment_confirmed") is not True:
            raise RefundNotEligibleError("NOT_PAID")
        delivery = art.get("delivery_package")
        if isinstance(delivery, dict) and delivery:
            self._record_output_evidence(project_id, art.get(PAYMENT_CYCLE_KEY), "delivery", source="json_backfill")
            raise RefundNotEligibleError("DELIVERED")
        if has_generated_output(art):
            # Projects written before the ledger kept output evidence: make it durable now.
            self._record_output_evidence(project_id, art.get(PAYMENT_CYCLE_KEY), "legacy", source="json_backfill")
            raise RefundNotEligibleError("OUTPUT_GENERATED")
        # The JSON bundle can be overwritten by a stale write; the ledger evidence cannot.
        # Payments without a cycle never reach an automatic refund (LEGACY_PAYMENT_REVIEW below).
        blocker = None
        if art.get(PAYMENT_CYCLE_KEY):
            try:
                blocker = payment_ledger.refund_blocker(project_id)
            except sqlite3.Error:
                raise RefundNotEligibleError("PAYMENT_RECORD_MISSING") from None
        if blocker == "OUTPUT_GENERATED":
            raise RefundNotEligibleError("OUTPUT_GENERATED")
        failure = art.get(PROCESSING_FAILURE_KEY)
        if (
            not isinstance(failure, dict)
            or failure.get("classification") != FAILURE_CLASSIFICATION
            or failure.get("payment_confirmed_at") != art.get("payment_confirmed_at")
            or failure.get("payment_cycle_id") != art.get(PAYMENT_CYCLE_KEY)
        ):
            raise RefundNotEligibleError("NO_RECORDED_FAILURE")
        if failure.get("client_seeded") is not False:
            raise RefundNotEligibleError("CLIENT_INPUT")
        # The JSON failure record can be a stale copy; the ledger's provenance rows cannot.
        if art.get(PAYMENT_CYCLE_KEY):
            try:
                client_input = entitlements.client_input_used(project_id, art.get(PAYMENT_CYCLE_KEY))
            except sqlite3.Error:
                raise RefundNotEligibleError("PAYMENT_RECORD_MISSING") from None
            if client_input:
                raise RefundNotEligibleError("CLIENT_INPUT")
        if blocker in _REVIEW_REFUND_CODES:
            self._flag_refund_review(project_id, blocker.lower())
            raise RefundNotEligibleError(blocker)
        return self.refundable_amount(project_id)

    def refund_reference(self, project_id: str) -> str:
        """Ledger idempotency key: one refund per payment cycle, derived only from server state."""
        art = self.store.require_project(project_id).artifacts or {}
        cycle_id = art.get(PAYMENT_CYCLE_KEY)
        if cycle_id:
            return payment_ledger.refund_ref(project_id, str(cycle_id))
        return f"assignment-refund:{project_id}:{art.get('payment_confirmed_at') or 'legacy'}"

    def mark_assignment_refunded(
        self,
        project_id: str,
        coins: int,
        *,
        reference: str | None = None,
        kind: str = "failure",
        reason: str | None = None,
        admin_id: int | None = None,
    ) -> ProjectBundle:
        """Mark payment reversed so the user can re-pay or abandon cleanly."""
        project = self.store.require_project(project_id)
        now = utc_now().isoformat()
        history = project.artifacts.get(REFUND_HISTORY_KEY)
        history = list(history) if isinstance(history, list) else []
        history.append(
            {
                "refunded_at": now,
                "coins": int(coins),
                "reference": reference,
                "kind": kind,
                "reason": (reason or "")[:200] or None,
                "admin_id": admin_id,
                "payment_confirmed_at": project.artifacts.get("payment_confirmed_at"),
                "payment_cycle_id": project.artifacts.get(PAYMENT_CYCLE_KEY),
                "failure": project.artifacts.get(PROCESSING_FAILURE_KEY),
            }
        )
        project.artifacts[REFUND_HISTORY_KEY] = history
        cycle_id = project.artifacts.get(PAYMENT_CYCLE_KEY)
        cycles = project.artifacts.get(PAYMENT_CYCLES_KEY)
        if cycle_id and isinstance(cycles, list):
            for entry in cycles:
                if isinstance(entry, dict) and entry.get("cycle_id") == cycle_id and not entry.get("refunded_at"):
                    entry["refunded_at"] = now
                    entry["refund_kind"] = kind
        project.artifacts["payment_refunded"] = True
        project.artifacts["payment_refunded_at"] = now
        project.artifacts["payment_refund_coins"] = int(coins)
        project.artifacts["payment_confirmed"] = False
        project.updated_at = utc_now()
        self.store.save_project(project)
        return self.store.require_bundle(project_id)

    @_paid_operation("research")
    def run_research(
        self,
        project_id: str,
        *,
        parsed_documents: list[dict] | None = None,
    ):
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        if not requirement.get("assignment_type") and not requirement.get("word_count"):
            raise StagePreconditionError("Requirement JSON must be analyzed before research planning")
        self._require_payment(project_id, "research planning")

        self._ensure_pipeline_project(project_id)
        documents = build_parsed_documents(bundle.files, parsed_documents, project_id=project_id)
        self._ensure_project_engine(project_id)
        self.project_engine.stage_start(project_id, ProjectLifecycleStatus.RESEARCH_READY)
        self.pipeline.start_stage(project_id, PipelineStage.RESEARCH)

        try:
            with self._execution_boundary(project_id, "research"):
                plan = self.research.build_plan(
                    requirement_json=requirement,
                    parsed_documents=documents,
                    project_id=project_id,
                )

            self._vouch(plan)
            with self._billing_lock(project_id):
                self._record_plan_version(project_id, plan.to_dict(), entitlements.SOURCE_SERVER)
                project = self.store.require_project(project_id)
                project.artifacts["research_plan_id"] = plan.id
                project.artifacts["research_plan"] = plan.to_dict()
                project.artifacts[RESEARCH_PLAN_SOURCE_KEY] = "server"
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
        """Apply a student's plan edit; the edited plan is client input from then on.

        It is stored like any plan, so every worker builds from the same copy, and tagged as
        client-sourced, so failures built on it are never automatic refund evidence.
        """
        plan = self._load_research_plan(project_id)
        updated = self._vouch(self.research.update_plan_from_dict(plan.id, payload))
        with self._billing_lock(project_id):
            self._record_plan_version(project_id, updated.to_dict(), entitlements.SOURCE_CLIENT)
            project = self.store.require_project(project_id)
            project.artifacts["research_plan_id"] = updated.id
            project.artifacts["research_plan"] = updated.to_dict()
            project.artifacts[RESEARCH_PLAN_SOURCE_KEY] = "client"
            project.updated_at = utc_now()
            self.store.save_project(project)
        trace("research_plan.client_edit", project_id=project_id)
        return updated

    def _research_plan_from_client(self, project_id: str, plan_dict: dict[str, Any]) -> bool:
        """The plan about to be used is (or may be) the student's, not the server's own output."""
        stored = self.store.require_project(project_id).artifacts
        if stored.get(RESEARCH_PLAN_SOURCE_KEY) != "server":
            return True
        snapshot = stored.get("research_plan")
        if not isinstance(snapshot, dict):
            return True
        return ResearchPlan.from_dict(snapshot).to_dict() != plan_dict

    @staticmethod
    def _plan_content_hash(plan_dict: dict[str, Any]) -> str:
        normalized = ResearchPlan.from_dict(plan_dict).to_dict()
        raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _provenance_cycle_id(self, project_id: str) -> str | None:
        cycle_id = (self.store.require_project(project_id).artifacts or {}).get(PAYMENT_CYCLE_KEY)
        return str(cycle_id) if cycle_id else None

    def _record_plan_version(self, project_id: str, plan_dict: dict[str, Any], source: str) -> None:
        """Make ``plan_dict`` the project's recorded current plan (caller holds the billing lock)."""
        try:
            entitlements.record_plan_version(project_id, self._plan_content_hash(plan_dict), source)
        except sqlite3.Error:
            if self._provenance_cycle_id(project_id):
                raise PaymentRequiredError("The research plan could not be saved. Please try again.") from None
            # Payments without a cycle are never refunded automatically; recording is best effort.
            trace("research_plan.version_unrecorded", project_id=project_id, source=source)

    def _consume_research_plan(self, project_id: str, plan_dict: dict[str, Any], stage: str) -> bool:
        """Admit ``plan_dict`` into a paid stage; True when it is (or may be) the student's plan.

        The plan must be the project's latest recorded version, so a worker holding an older copy
        is refused instead of running it. A plan the server never generated with exactly this
        content marks the payment cycle: no later failure of the cycle is refund evidence.
        """
        content_hash = self._plan_content_hash(plan_dict)
        cycle_id = self._provenance_cycle_id(project_id)
        labelled_client = self._research_plan_from_client(project_id, plan_dict)
        with self._billing_lock(project_id):
            try:
                latest = entitlements.latest_plan_version(project_id)
                if latest is None:
                    # A plan stored before versions were recorded keeps the bundle's own label.
                    source = entitlements.SOURCE_CLIENT if labelled_client else entitlements.SOURCE_SERVER
                    latest = entitlements.record_plan_version(project_id, content_hash, source)
                if latest["content_hash"] != content_hash:
                    trace("research_plan.stale_copy_refused", project_id=project_id, stage=stage)
                    raise ResearchPlanChangedError(
                        "The research plan was changed in another session. Reload the page and try again."
                    )
                from_client = labelled_client or not entitlements.server_generated_plan(project_id, content_hash)
                if from_client:
                    entitlements.record_client_input_use(project_id, cycle_id, stage, content_hash)
            except sqlite3.Error:
                if cycle_id:
                    raise PaymentRequiredError(f"Payment could not be verified before {stage}") from None
                trace("research_plan.provenance_unavailable", project_id=project_id, stage=stage)
                return labelled_client
        return from_client

    def _client_input_used(self, project_id: str) -> bool:
        """The current payment cycle already ran a paid stage on student-provided input."""
        cycle_id = self._provenance_cycle_id(project_id)
        try:
            return entitlements.client_input_used(project_id, cycle_id)
        except sqlite3.Error:
            return bool(cycle_id)

    @_paid_operation("blueprint")
    def run_blueprint(
        self,
        project_id: str,
        *,
        research_plan: dict[str, Any] | None = None,
    ):
        paid_words = self._require_payment(project_id, "building the blueprint")
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        if not requirement.get("word_count") and not requirement.get("estimatedWordCount"):
            # The quote priced the default length; the plan's section sizes must not raise it.
            requirement["word_count"] = paid_words
        try:
            research_plan_dict = self._load_research_plan(project_id, seed=research_plan).to_dict()
        except KeyError as exc:
            raise StagePreconditionError("Research Plan must exist before building a Blueprint") from exc
        plan_from_client = self._consume_research_plan(project_id, research_plan_dict, "blueprint")
        word_ceiling = int(paid_words * BLUEPRINT_WORD_RATIO) + BLUEPRINT_WORD_SLACK

        self._ensure_pipeline_project(project_id)
        self._ensure_project_engine(project_id)
        self.project_engine.stage_start(project_id, ProjectLifecycleStatus.BLUEPRINT_READY)
        self.pipeline.start_stage(project_id, PipelineStage.BLUEPRINT)
        try:
            with self._execution_boundary(project_id, "blueprint", client_seeded=plan_from_client):
                blueprint = self.blueprint.build_blueprint(
                    requirement_json=requirement,
                    research_plan=research_plan_dict,
                    project_id=project_id,
                )
                if int(blueprint.total_target_words or 0) > word_ceiling:
                    trace(
                        "service.blueprint.over_paid_scope",
                        project_id=project_id,
                        target_words=int(blueprint.total_target_words or 0),
                        paid_words=paid_words,
                    )
                    raise PaidScopeExceededError(
                        "The plan asks for more words than this payment covers. Shorten the plan and try again."
                    )

            self._vouch(blueprint)
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

    @_paid_operation("writing")
    def start_writer(self, project_id: str):
        self._require_payment(project_id, "writing")
        try:
            return self._load_writer_session(project_id)
        except KeyError:
            pass

        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        images = self._project_images(project_id, bundle.project.artifacts.get("assignment_images"))
        if not images:
            images = self._sync_assignment_images(project_id, auto_fetch=True)
        if images:
            # Attached or auto-fetched images are available for [[FIGURE:...]] markers.
            requirement["assignment_images"] = images
            requirement["include_assignment_images"] = True
        requirement[SOURCE_MATERIALS_KEY] = writer_source_material(
            bundle.files, project_id=project_id, note=bundle.project.note or ""
        )
        facts = self._verified_facts(project_id, requirement[SOURCE_MATERIALS_KEY])
        if facts:
            block = facts_material(facts, style=str(requirement.get("citation_style") or "Harvard"))
            requirement[SOURCE_MATERIALS_KEY] = f"{requirement[SOURCE_MATERIALS_KEY].rstrip()}\n\n{block}"
        research_plan = self._load_research_plan(project_id).to_dict()
        self._consume_research_plan(project_id, research_plan, "writing")
        stored_blueprint = bundle.project.artifacts.get("blueprint")
        if isinstance(stored_blueprint, dict) and stored_blueprint.get("id"):
            blueprint = stored_blueprint
        else:
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

        project = self.store.require_project(project_id)
        project.artifacts[WRITER_EXPECTED_SECTIONS_KEY] = [section.id for section in session.sections]
        self.store.save_project(project)
        saved = self._persist_writer_session(project_id, session)
        self.project_engine.stage_finish(
            project_id,
            ProjectLifecycleStatus.WRITING,
            success=True,
            model_used=saved.engine_version,
        )
        return saved

    def _verified_facts(self, project_id: str, materials: str) -> list[dict[str, str]]:
        """Best-effort web-verified statistics for the brief, gathered once per project."""
        project = self.store.require_project(project_id)
        cached = project.artifacts.get(FACTS_ARTIFACT)
        if isinstance(cached, list):
            return cached
        if not facts_wanted(materials):
            return []
        try:
            facts = gather_verified_facts(materials)
        except Exception as exc:  # noqa: BLE001
            trace("facts.failed", project_id=project_id, error=str(exc)[:300])
            return []
        trace("facts.gathered", project_id=project_id, count=len(facts), sources=[f.get("url") for f in facts])
        project = self.store.require_project(project_id)
        project.artifacts[FACTS_ARTIFACT] = facts
        self.store.save_project(project)
        return facts

    @_paid_operation("writing")
    def advance_writer(self, project_id: str, *, writer_session: dict[str, Any] | None = None):
        self._require_payment(project_id, "writing")
        # Cross-worker lock: overlapping /writer/advance (retries, dual tabs) used to
        # rewrite the same section on two gunicorn workers and freeze progress.
        with project_file_lock(project_id, name="writer", root=self.store.storage_root):
            session = self._load_writer_session(project_id, seed=writer_session)
            with self._execution_boundary(project_id, "writing"):
                updated = self.writer.advance_section(session.id)
            return self._persist_writer_session(project_id, updated)

    @_paid_operation("writing")
    def revise_writer_section(
        self,
        project_id: str,
        section_id: str | None = None,
        *,
        writer_session: dict[str, Any] | None = None,
    ):
        self._require_payment(project_id, "writing")
        with project_file_lock(project_id, name="writer", root=self.store.storage_root):
            session = self._load_writer_session(project_id, seed=writer_session)
            target_id = section_id or session.current_section_id
            target = next((s for s in session.sections if s.id == target_id), None)
            if target is None:
                raise StagePreconditionError("No section available for revision")
            if target.status != WriterSectionStatus.REVISION:
                raise StagePreconditionError("Section is not awaiting revision")
            with self._execution_boundary(project_id, "writing"):
                updated = self.writer.revise_section(session.id, section_id)
            return self._persist_writer_session(project_id, updated)

    @_paid_operation("merge")
    def merge_writer_draft(self, project_id: str, *, writer_session: dict[str, Any] | None = None):
        self._require_payment(project_id, "merging the draft")
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
            raise StagePreconditionError(
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
        draft.content = self._attach_appendices(project_id, draft.content)

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

    def _attach_appendices(self, project_id: str, content: str) -> str:
        """Build appendix tables when the brief allows appendices; best effort."""
        from services.assignment_appendices import (
            APPENDICES_ARTIFACT,
            appendices_markdown,
            appendices_wanted,
            generate_appendices,
            link_appendices,
        )

        bundle = self.store.require_bundle(project_id)
        materials = writer_source_material(bundle.files, project_id=project_id, note=bundle.project.note or "")
        if not appendices_wanted(bundle.requirement.to_dict(), materials):
            return content
        try:
            appendices = generate_appendices(materials=materials, draft_content=content)
        except Exception as exc:  # noqa: BLE001
            trace("appendices.failed", project_id=project_id, error=str(exc))
            return content
        if not appendices:
            return content
        project = self.store.require_project(project_id)
        project.artifacts[APPENDICES_ARTIFACT] = appendices_markdown(appendices)
        self.store.save_project(project)
        return link_appendices(content, appendices)

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

    @_paid_operation("review")
    def run_academic_review(self, project_id: str):
        self._require_payment(project_id, "the academic review")
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        research_plan = self._load_research_plan(project_id).to_dict()
        self._consume_research_plan(project_id, research_plan, "review")
        blueprint = self._load_blueprint(project_id).to_dict()
        # Review runs after Format — evaluate humanized/formatted content.
        draft = self._draft_for_post_format_review(project_id)

        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.STYLE_REVIEW, force=True)
        with self._execution_boundary(project_id, "review"):
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

    @_paid_operation("revision")
    def run_revision(self, project_id: str, *, review_report: dict[str, Any] | None = None):
        self._require_payment(project_id, "revision")
        bundle = self.store.require_bundle(project_id)
        requirement = bundle.requirement.to_dict()
        research_plan = self._load_research_plan(project_id).to_dict()
        self._consume_research_plan(project_id, research_plan, "revision")
        blueprint = self._load_blueprint(project_id).to_dict()
        fingerprint = self._document_fingerprint(project_id)
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
            raise StagePreconditionError("Maximum automatic revision attempts reached — project needs manual review")

        with self._execution_boundary(project_id, "revision"):
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

        with self._unchanged_document(project_id, fingerprint, step="revision"):
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
            self._rehumanize_current_prose(
                project_id, reason="post_revision", previous_content=str(draft.get("content") or "")
            )
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

    @_paid_operation("humanization")
    def start_humanizer(self, project_id: str):
        self._require_payment(project_id, "humanization")
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

    @_paid_operation("humanization")
    def advance_humanizer(self, project_id: str, *, humanizer_session: dict[str, Any] | None = None):
        self._require_payment(project_id, "humanization")
        with project_file_lock(project_id, name="humanizer", root=self.store.storage_root):
            session = self._load_humanizer_session(project_id, seed=humanizer_session)
            with self._execution_boundary(project_id, "humanization"):
                updated = self.humanizer.advance_paragraph(session.id)
            return self._persist_humanizer_session(project_id, updated)

    @_paid_operation("humanization")
    def merge_humanized_draft(self, project_id: str, *, humanizer_session: dict[str, Any] | None = None):
        self._require_payment(project_id, "humanization")
        session = self._load_humanizer_session(project_id, seed=humanizer_session)
        bundle = self.store.require_bundle(project_id)
        title = bundle.project.title or bundle.requirement.title or "Humanized Assignment Draft"
        humanized = self.humanizer.merge_humanized_draft(session.id, title=title)

        # If StealthWriter inflated length, trim body only (keep References intact).
        # Soft: never fail the pipeline — always continue with best-effort budget fit.
        humanized = self._fit_humanized_word_budget(project_id, humanized)
        try:
            source = self._load_draft(project_id).content
        except KeyError:
            source = ""
        humanized = self._repair_humanized_meaning(project_id, source, humanized, reason="humanization")

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
                    "total_words": saved.total_words,
                },
                artifacts={"humanized_draft": saved.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return saved

    def _repair_humanized_meaning(
        self, project_id: str, original: str, humanized: HumanizedDraft, *, reason: str
    ) -> HumanizedDraft:
        """Fix terms, facts and nonsense phrases the humanizer garbled (small edits only)."""
        if not original.strip() or original.strip() == (humanized.content or "").strip():
            return humanized
        fixed, edits = repair_humanizer_meaning(original, humanized.content or "")
        if edits:
            humanized.content = fixed
            trace("humanizer.meaning_repair", project_id=project_id, reason=reason, edits=edits[:40])
        return humanized

    def _fit_humanized_word_budget(self, project_id: str, humanized: HumanizedDraft) -> HumanizedDraft:
        """Post-humanize: delete complete coherent sentences only — never Gemini-rewrite SW prose."""
        try:
            from services.assignment_spec import build_assignment_spec
            from services.assignment_spec.validate import count_body_words
            from services.writer_engine.gemini_trim import fit_humanized_content_to_budget

            bundle = self.store.require_bundle(project_id)
            req = bundle.requirement.to_dict()
            spec = build_assignment_spec(req, project_id=project_id)
            before = count_body_words(humanized.content or "")
            fitted, meta = fit_humanized_content_to_budget(humanized.content or "", spec=spec)
            if not meta.get("trimmed"):
                humanized.total_words = before
                return humanized
            humanized.content = fitted
            humanized.total_words = int(meta.get("body_words") or count_body_words(fitted))
            trace(
                "humanizer.word_budget_trim",
                project_id=project_id,
                method=meta.get("method"),
                before_body_words=before,
                after_body_words=humanized.total_words,
                dropped_ids=meta.get("dropped_ids"),
                target=spec.total_word_target,
                max_words=spec.max_total_words,
            )
        except Exception as exc:  # noqa: BLE001
            try:
                trace(
                    "humanizer.word_budget_trim_skipped",
                    project_id=project_id,
                    error=str(exc),
                )
            except Exception:  # noqa: BLE001
                pass
        return humanized

    def get_humanizer_session(self, project_id: str):
        return self._load_humanizer_session(project_id)

    def get_humanized_draft(self, project_id: str):
        return self._load_humanized_draft(project_id)

    @_paid_operation("citations")
    def run_citation_generation(self, project_id: str):
        self._require_payment(project_id, "citation generation")
        bundle = self.store.require_bundle(project_id)
        draft = self._load_draft(project_id).to_dict()
        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.CITATION_GENERATION, force=True)
        requirement = bundle.requirement.to_dict()
        facts = bundle.project.artifacts.get(FACTS_ARTIFACT)
        if isinstance(facts, list) and facts:
            requirement[FACTS_ARTIFACT] = facts
        with self._execution_boundary(project_id, "citations"):
            pack, updated_draft = self.citation_engine.generate(
                draft=draft,
                requirement_json=requirement,
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

    @_paid_operation("formatting")
    def run_formatting(self, project_id: str):
        self._require_payment(project_id, "formatting")
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
        images = self._project_images(project_id, bundle.project.artifacts.get("assignment_images"))
        if not images:
            images = self._sync_assignment_images(project_id, auto_fetch=True)
        from services.assignment_figures import ensure_figure_markers

        content = ensure_figure_markers(str(draft.get("content") or ""), images, project_id=project_id)
        if content != str(draft.get("content") or ""):
            draft = dict(draft)
            draft["content"] = content
            # Keep humanized/plain draft in sync so delivery text matches DOCX.
            try:
                humanized = self._load_humanized_draft(project_id)
                humanized.content = content
                self._persist_humanized_draft(project_id, humanized)
            except Exception:  # noqa: BLE001
                try:
                    raw_draft = self._load_draft(project_id)
                    raw_draft.content = content
                    self._persist_draft(project_id, raw_draft)
                except Exception:  # noqa: BLE001
                    pass
        with self._execution_boundary(project_id, "formatting"):
            formatted = self.format_engine.format_draft(
                draft=draft,
                requirement_json=bundle.requirement.to_dict(),
                project_id=project_id,
                citation_pack=citation_pack,
                assignment_images=images or None,
                appendices=str(bundle.project.artifacts.get("assignment_appendices") or ""),
            )
        project = self.store.require_project(project_id)
        project.artifacts["formatted_document"] = formatted
        self._save_output(project, "formatting")
        self.pipeline.complete_stage(
            project_id,
            PipelineStage.FORMATTING,
            StageResult(
                output={
                    "formatted_document_id": formatted.get("id"),
                    "path": formatted.get("path"),
                    "style_id": formatted.get("style_id"),
                    "notices": formatted.get("notices") or [],
                },
                artifacts={"formatted_document": formatted},
            ),
        )
        self._sync_pipeline_state(project_id)
        return formatted

    @_paid_operation("validation")
    def run_requirement_validation(self, project_id: str):
        self._require_payment(project_id, "requirement validation")
        from services.assignment_spec import AssignmentSpec, build_assignment_spec, run_grade_gate
        from services.assignment_spec.llm_repair import llm_rubric_repair

        bundle = self.store.require_bundle(project_id)
        fingerprint = self._delivery_source_hash(bundle.project)
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
            before_gate = text
            text = gate.content
            with self._unchanged_document(project_id, fingerprint, step="validation_grade_gate"):
                self._persist_repaired_draft_content(project_id, text)
            # LLM repairs after humanization raise AI score — re-humanize the new sentences.
            try:
                self._rehumanize_current_prose(
                    project_id, reason="post_grade_gate", previous_content=before_gate
                )
                try:
                    text = self._load_humanized_draft(project_id).content
                except KeyError:
                    pass
            except Exception as exc:  # noqa: BLE001
                trace("rehumanize.post_grade_gate_failed", project_id=project_id, error=str(exc))

        with self._execution_boundary(project_id, "validation"):
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

    def _rehumanize_current_prose(
        self, project_id: str, *, reason: str, previous_content: str | None = None
    ) -> HumanizedDraft:
        """Re-run StealthWriter after Gemini/grade-gate rewrites that undo humanization.

        ``previous_content`` is the humanized text before the rewrite; only new sentences
        are sent to the provider then.
        """
        bundle = self.store.require_bundle(project_id)
        fingerprint = self._delivery_source_hash(bundle.project)
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
            previous_content=previous_content,
        )
        fresh = self._fit_humanized_word_budget(project_id, fresh)
        fresh = self._repair_humanized_meaning(project_id, content, fresh, reason=reason)
        with self._unchanged_document(project_id, fingerprint, step=f"rehumanize:{reason}"):
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

    def _skipped_detection_artifacts(self, project_id: str) -> tuple[DetectionSession, DetectionReport]:
        """Build a no-op passed detection session/report (AI detection stage disabled)."""
        now = utc_now()
        session_id = str(uuid.uuid4())
        report_id = str(uuid.uuid4())
        draft_id = ""
        try:
            draft_id = self._load_humanized_draft(project_id).id
        except KeyError:
            try:
                draft_id = self._load_draft(project_id).id
            except KeyError:
                draft_id = ""
        report = DetectionReport(
            id=report_id,
            project_id=project_id,
            session_id=session_id,
            overall_ai_score=0.0,
            paragraph_scores=[],
            average_score=0.0,
            highest_score=0.0,
            lowest_score=0.0,
            paragraphs_reprocessed=0,
            final_status=FinalDetectionStatus.PASSED,
            thresholds=DetectionThresholds(),
            engine_version="skipped-disabled",
            generated_at=now,
        )
        session = DetectionSession(
            id=session_id,
            project_id=project_id,
            humanized_draft_id=str(draft_id or ""),
            paragraphs=[],
            current_paragraph_id=None,
            completed_paragraph_ids=[],
            remaining_paragraph_ids=[],
            progress=100,
            paragraphs_completed=0,
            average_ai_score=0.0,
            thresholds=DetectionThresholds(),
            status=DetectionSessionStatus.COMPLETED,
            report_id=report_id,
            engine_version="skipped-disabled",
            requirement_json={},
            created_at=now,
            updated_at=now,
        )
        return session, report

    @_paid_operation("ai_detection")
    def start_ai_detection(self, project_id: str):
        """AI detection stage is disabled — immediately mark as passed and continue."""
        self._require_payment(project_id, "AI detection")
        try:
            existing = self._load_detection_session(project_id)
            if existing.status in (
                DetectionSessionStatus.COMPLETED,
                DetectionSessionStatus.NEEDS_MANUAL_REVIEW,
            ):
                return existing
        except KeyError:
            pass

        self._ensure_pipeline_project(project_id)
        self.pipeline.start_stage(project_id, PipelineStage.AI_DETECTION, force=True)
        session, report = self._skipped_detection_artifacts(project_id)
        self._persist_detection_session(project_id, session)
        self._finish_detection_pipeline(project_id, report)
        trace("detection.skipped_disabled", project_id=project_id)
        return self._persist_detection_session(project_id, session)

    @_paid_operation("ai_detection")
    def advance_ai_detection(self, project_id: str, *, detection_session: dict[str, Any] | None = None):
        """No-op: detection disabled."""
        self._require_payment(project_id, "AI detection")
        del detection_session
        return self.start_ai_detection(project_id)

    @_paid_operation("ai_detection")
    def finalize_ai_detection(self, project_id: str, *, detection_session: dict[str, Any] | None = None):
        """No-op: detection disabled — return/create stub passed report."""
        self._require_payment(project_id, "AI detection")
        del detection_session
        try:
            return self._load_detection_report(project_id)
        except KeyError:
            self.start_ai_detection(project_id)
            return self._load_detection_report(project_id)

    def _finish_detection_pipeline(self, project_id: str, report: DetectionReport):
        self._ensure_pipeline_project(project_id)
        saved = self._persist_detection_report(project_id, report)
        project = self.store.require_project(project_id)
        # Disabled stage never flips project into needs_manual_review from AI scores.
        if (
            saved.engine_version != "skipped-disabled"
            and saved.final_status.value == "needs_manual_review"
        ):
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
                    "skipped": saved.engine_version == "skipped-disabled",
                },
                artifacts={"detection_report": saved.to_dict()},
            ),
        )
        self._sync_pipeline_state(project_id)
        return saved

    def prepare_detection_retry(self, project_id: str) -> None:
        """Detection disabled — clear stale artifacts only."""
        project = self.store.require_project(project_id)
        project.artifacts.pop("detection_report_id", None)
        project.artifacts.pop("detection_report", None)
        project.artifacts.pop("detection_session_id", None)
        project.artifacts.pop("detection_session", None)
        self.store.save_project(project)

    def get_detection_session(self, project_id: str):
        return self._load_detection_session(project_id)

    def get_detection_report(self, project_id: str):
        return self._load_detection_report(project_id)

    @_paid_operation("delivery")
    def run_delivery(self, project_id: str):
        paid_words, word_cap = self._paid_word_cap(project_id, "delivery")
        bundle = self.store.require_bundle(project_id)
        fingerprint = self._delivery_source_hash(bundle.project)
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
        # Checked before the grade gate's repairs (no AI spend on a refusal) and again on the result.
        self._enforce_paid_word_cap(project_id, str(final_draft.get("content") or ""), paid_words, word_cap)

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
            before_gate = str(final_draft.get("content") or "")
            final_draft = {
                **final_draft,
                "content": gate.content,
                "total_words": count_words(gate.content),
            }
            with self._unchanged_document(project_id, fingerprint, step="delivery_grade_gate"):
                self._persist_repaired_draft_content(project_id, gate.content)
            try:
                humanized = self._rehumanize_current_prose(
                    project_id, reason="post_delivery_grade_gate", previous_content=before_gate
                )
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
            warnings: list[str] = []
            cite_pack = project.artifacts.get("citation_pack")
            if isinstance(cite_pack, dict):
                settings = cite_pack.get("settings") if isinstance(cite_pack.get("settings"), dict) else {}
                used = int(settings.get("used_sources") or len(cite_pack.get("references") or []))
                minimum = int(settings.get("minimum_sources") or bundle.requirement.minimum_sources or 0)
                if minimum and used < minimum:
                    warnings.append(
                        f"Used {used} verified cited sources (brief asked for {minimum}). "
                        "Sources were not padded with unused or invented references."
                    )
            project.artifacts["validation_report"] = {
                **(project.artifacts.get("validation_report") or {}),
                "passed": False,
                "export_blocked": False,
                "soft_export": True,
                "blocking_issues": gate.blocking_issues,
                "warnings": warnings,
                "spec_validation": gate.spec_validation.to_dict(),
                "rubric_coverage": gate.rubric_coverage.to_dict(),
            }
            project.artifacts["grade_gate"]["export_blocked"] = False
            project.artifacts["grade_gate"]["soft_export"] = True
            project.artifacts["grade_gate"]["warnings"] = warnings
            self.store.save_project(project)
            trace(
                "delivery.soft_export",
                project_id=project_id,
                blocking_issues=gate.blocking_issues[:8],
                warnings=warnings[:4],
            )
        else:
            self.store.save_project(project)

        delivered_text = str(final_draft.get("content") or "")
        delivered_words = self._enforce_paid_word_cap(project_id, delivered_text, paid_words, word_cap)

        research_plan = self._load_research_plan(project_id).to_dict()
        self._consume_research_plan(project_id, research_plan, "delivery")
        blueprint = self._load_blueprint(project_id).to_dict()
        try:
            review_report = self._load_review_report(project_id).to_dict()
        except KeyError as exc:
            raise KeyError(
                "Review report not found — finish academic review before delivery"
            ) from exc
        try:
            detection_report = self._load_detection_report(project_id).to_dict()
        except KeyError:
            # AI detection stage disabled — invent a passed stub so packaging still works.
            _session, stub = self._skipped_detection_artifacts(project_id)
            detection_report = self._persist_detection_report(project_id, stub).to_dict()
            try:
                self.pipeline.complete_stage(
                    project_id,
                    PipelineStage.AI_DETECTION,
                    StageResult(
                        output={
                            "detection_report_id": stub.id,
                            "overall_ai_score": 0.0,
                            "final_status": "passed",
                            "skipped": True,
                        },
                        artifacts={"detection_report": detection_report},
                    ),
                )
            except Exception:  # noqa: BLE001
                pass

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
        formatted_path = self._delivery_formatted_path(project_id, formatted)

        with self._execution_boundary(project_id, "delivery"):
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
                assignment_images=self._project_images(project_id, bundle.project.artifacts.get("assignment_images"))
                or None,
            )

        project = self.store.require_project(project_id)
        project.artifacts["delivery_package_id"] = package.id
        project.artifacts["delivery_package"] = package.to_dict()
        project.artifacts[DELIVERY_SCOPE_KEY] = {
            "package_id": package.id,
            "cycle_id": str(project.artifacts.get(PAYMENT_CYCLE_KEY) or ""),
            "words": delivered_words,
            "paid_words": paid_words,
            "word_cap": word_cap,
            "content_sha256": hashlib.sha256(delivered_text.encode("utf-8")).hexdigest(),
            "source_sha256": self._delivery_source_hash(project),
            "checked_at": utc_now().isoformat(),
        }
        project.status = ProjectStatus.COMPLETED
        self._save_output(project, "delivery")

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

    @staticmethod
    def _delivery_formatted_path(project_id: str, formatted: Any) -> str | None:
        """The stored Format Engine path of this project's own record; the packager confines the read."""
        if not isinstance(formatted, dict) or not isinstance(formatted.get("path"), str):
            return None
        if str(formatted.get("project_id") or project_id) != project_id:
            return None
        return formatted["path"]

    def _paid_word_cap(self, project_id: str, action: str) -> tuple[int, int]:
        """(paid words, most words a deliverable may have) for the live payment.

        With a payment cycle the words are the cycle's own; ``_require_payment`` has already
        bound it to the current scope. Payments made before the ledger existed have no cycle
        and use the volume ``_require_payment`` verified against the stored requirement.
        """
        paid_words = self._require_payment(project_id, action)
        cycle_id = (self.store.require_project(project_id).artifacts or {}).get(PAYMENT_CYCLE_KEY)
        if cycle_id:
            try:
                cycle = payment_ledger.get_cycle(str(cycle_id))
            except sqlite3.Error:
                raise PaymentRequiredError(f"Payment could not be verified before {action}") from None
            words = int((cycle or {}).get("quoted_word_count") or 0)
            if cycle is None or cycle.get("project_id") != project_id or words <= 0:
                trace("service.paid_scope.no_cycle_words", project_id=project_id, cycle_id=str(cycle_id))
                raise PaidScopeError(f"This payment needs a manual check before {action}. Please contact support.")
            paid_words = words
        return paid_words, int(paid_words * BLUEPRINT_WORD_RATIO) + BLUEPRINT_WORD_SLACK

    @staticmethod
    def _enforce_paid_word_cap(project_id: str, text: str, paid_words: int, word_cap: int) -> int:
        words = count_words(text)
        if words > word_cap:
            trace("delivery.over_paid_scope", project_id=project_id, words=words, cap=word_cap, paid_words=paid_words)
            raise PaidScopeLimitExceededError(
                f"The finished assignment is {words} words, but your payment covers up to {word_cap} words "
                f"for a {paid_words}-word assignment, so it can't be delivered as it is. Ask for a shorter "
                "version in the revision chat or contact support."
            )
        return words

    @staticmethod
    def _delivery_source_hash(project: Project) -> str:
        """Fingerprint of the stored document a delivery is built from."""
        art = project.artifacts if isinstance(project.artifacts, dict) else {}
        sources = {}
        for key in ("formatted_document", "humanized_draft", "draft"):
            snapshot = art.get(key)
            if isinstance(snapshot, dict):
                sources[key] = {
                    "id": str(snapshot.get("id") or ""),
                    "text": str(snapshot.get("plain_text" if key == "formatted_document" else "content") or ""),
                    "path": str(snapshot.get("path") or "") if key == "formatted_document" else "",
                }
        raw = json.dumps(sources, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _document_fingerprint(self, project_id: str) -> str:
        return self._delivery_source_hash(self.store.require_project(project_id))

    @contextmanager
    def _unchanged_document(self, project_id: str, fingerprint: str, *, step: str) -> Iterator[None]:
        """Write an AI result made from the document with ``fingerprint`` only if it is still current.

        Every generated-text save takes the same document lock (``_save_output``), so no other
        worker can replace the document between this check and the caller's writes.
        """
        with project_file_lock(project_id, name=DOCUMENT_LOCK, root=self.store.storage_root):
            if self._document_fingerprint(project_id) != fingerprint:
                trace("document.stale_result_dropped", project_id=project_id, step=step)
                raise ProjectChangedError()
            yield

    def verify_delivery_package(self, project_id: str, package) -> None:
        """Refuse a package that is not the checked build of the current document and payment.

        Raises ``DeliveryPackageStaleError`` when the document, payment or package changed since
        it was built (or it predates the check), ``PaidScopeLimitExceededError`` when it is
        longer than the payment covers now.
        """
        paid_words, word_cap = self._paid_word_cap(project_id, "download")
        project = self.store.require_project(project_id)
        art = project.artifacts if isinstance(project.artifacts, dict) else {}
        record = art.get(DELIVERY_SCOPE_KEY)
        words = record.get("words") if isinstance(record, dict) else None
        if (
            not isinstance(words, int)
            or isinstance(words, bool)
            or str(record.get("package_id") or "") != str(getattr(package, "id", "") or "")
            or str(record.get("cycle_id") or "") != str(art.get(PAYMENT_CYCLE_KEY) or "")
            or record.get("source_sha256") != self._delivery_source_hash(project)
        ):
            trace("delivery.package_stale", project_id=project_id, package_id=str(getattr(package, "id", "")))
            raise DeliveryPackageStaleError()
        if words > word_cap:
            trace("delivery.over_paid_scope", project_id=project_id, words=words, cap=word_cap, paid_words=paid_words)
            raise PaidScopeLimitExceededError(
                f"The finished assignment is {words} words, but your payment covers up to {word_cap} words "
                f"for a {paid_words}-word assignment, so it can't be delivered as it is."
            )

    def get_delivery_package(self, project_id: str):
        """The package persisted on the project; a memory copy only when it is that same package."""
        from services.delivery_engine.models import DeliveryPackage

        snapshot = self.store.require_bundle(project_id).project.artifacts.get("delivery_package")
        if not (isinstance(snapshot, dict) and snapshot.get("id")):
            raise KeyError(f"Delivery package not found for project: {project_id}")
        mem = self.delivery.store.get_by_project(project_id)
        if mem is not None and mem.id == str(snapshot["id"]) and mem.project_id == project_id:
            return mem
        package = DeliveryPackage.from_dict(snapshot)
        package.project_id = project_id
        return self.delivery.store.save(package)

    def trusted_delivery_package(self, package):
        """The persisted record for ``package``, or None when it isn't its project's current package."""
        from services.delivery_engine.models import DeliveryPackage

        project_id = str(getattr(package, "project_id", None) or "").strip()
        if not project_id:
            return None
        snapshot = self._stored_artifact(project_id, "delivery_package")
        if snapshot is None or str(snapshot["id"]) != str(getattr(package, "id", "") or ""):
            return None
        trusted = DeliveryPackage.from_dict(snapshot)
        trusted.project_id = project_id
        return trusted

    def find_delivery_package(self, package_id: str):
        """The persisted package with this id (memory is only a hint; other workers' packages come from disk)."""
        try:
            trusted = self.trusted_delivery_package(self.delivery.get_package(package_id))
        except KeyError:
            trusted = None
        if trusted is not None:
            return trusted
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
                package.project_id = child.name
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
        PipelineStage.DELIVERY: ("delivery_package", "delivery_package_id", DELIVERY_SCOPE_KEY),
    }

    @_paid_operation("retry")
    def retry_stage(self, project_id: str, stage: PipelineStage | str):
        """Clear one stage's artifacts and re-run only that stage."""
        self._require_payment(project_id, "retrying a stage")
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

    def _add_file_record(
        self, project_id: str, entry: dict[str, Any], *, storage_path: str | None = None
    ) -> ProjectFile:
        """``entry`` is request metadata and never names a location on disk.

        ``storage_path`` is accepted only from the server's own upload writers and must lie in
        this project's files directory.
        """
        file_type_raw = entry.get("file_type") or entry.get("source") or ""
        file_type = normalize_file_type(str(file_type_raw))
        if file_type is None:
            raise ValueError(f"Unsupported file type: {file_type_raw}")

        original_filename = str(entry.get("original_filename") or entry.get("name") or "file")
        file_id = str(uuid.uuid4())
        if storage_path:
            try:
                storage_path = project_files.validate_storage_path(project_id, str(storage_path))
            except project_files.ProjectFileDenied:
                raise ValueError("Invalid file location.") from None
        else:
            storage_path = _storage_path(project_id, file_id, original_filename)
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
        self.store.require_project(project_id)
        try:
            pipeline_project = self.pipeline.get_project(project_id)
        except KeyError:
            return

        def mirror(project: Project) -> None:
            project.current_stage = pipeline_project.current_stage
            project.progress = pipeline_project.progress
            project.updated_at = utc_now()

        self.store.update_project(project_id, mirror)

    def _touch_project(self, project_id: str) -> None:
        self.store.update_project(project_id, lambda project: setattr(project, "updated_at", utc_now()))

    def get_project_timeline(self, project_id: str) -> list[dict[str, Any]]:
        return self.project_engine.get_timeline(project_id)

    def get_project_lifecycle_status(self, project_id: str) -> dict[str, Any]:
        return self.project_engine.get_status(project_id)

    def get_resume_stage(self, project_id: str) -> str:
        return self.project_engine.resume_stage(project_id)

    def list_projects_for_user(self, user_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for project in self.store.list_projects_for_user(str(user_id)):
            item = project.to_dict()
            has_delivery = bool(
                isinstance(project.artifacts.get("delivery_package"), dict)
                and project.artifacts.get("delivery_package")
            )
            item["has_delivery"] = has_delivery
            item["can_download"] = has_delivery or project.status.value == "completed"
            chat = project.artifacts.get("revision_chat") if isinstance(project.artifacts.get("revision_chat"), dict) else {}
            item["revision_rounds_used"] = int(chat.get("rounds_used") or 0)
            out.append(item)
        return out

    def get_revision_chat(self, project_id: str) -> dict[str, Any]:
        project = self.store.require_project(project_id)
        chat = project.artifacts.get("revision_chat")
        if not isinstance(chat, dict):
            chat = {}
        rounds_used = int(chat.get("rounds_used") or 0)
        return {
            "messages": list(chat.get("messages") or []),
            "rounds_used": max(rounds_used, self._revision_rounds_used(project_id, fallback=rounds_used)),
            "max_rounds": MAX_CLIENT_REVISION_ROUNDS,
        }

    def _reserve_revision_round(self, project_id: str, *, legacy_used: int) -> str:
        try:
            return entitlements.reserve_revision_round(
                project_id, limit=MAX_CLIENT_REVISION_ROUNDS, legacy_used=legacy_used
            )
        except entitlements.RevisionRoundsExhausted:
            raise RevisionLimitError(
                f"Revision limit reached ({MAX_CLIENT_REVISION_ROUNDS} free rounds for this assignment)."
            ) from None
        except sqlite3.Error:
            raise PaymentRequiredError("Revision rounds could not be verified. Please try again.") from None

    def _finish_revision_round(self, project_id: str, reservation_id: str, *, consumed: bool) -> None:
        try:
            entitlements.finish_revision_round(reservation_id, consumed=consumed)
        except sqlite3.Error as exc:
            # An unfinished reservation keeps counting as used, which is the safe side.
            trace("revision_chat.round_unfinished", project_id=project_id, error=str(exc))

    def _revision_rounds_used(self, project_id: str, *, fallback: int) -> int:
        try:
            return entitlements.revision_rounds_used(project_id)
        except sqlite3.Error:
            return fallback

    def get_chat_transcript(self, project_id: str) -> list[dict[str, Any]]:
        project = self.store.require_project(project_id)
        raw = project.artifacts.get("chat_transcript")
        if not isinstance(raw, list):
            return []
        out: list[dict[str, Any]] = []
        for item in raw[:120]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "assistant")
            if role not in ("user", "assistant"):
                role = "assistant"
            kind = str(item.get("kind") or "")[:64]
            html = str(item.get("html") or "")
            if len(html) > 80000:
                html = html[:80000]
            if not html.strip():
                continue
            out.append({"role": role, "kind": kind, "html": html})
        return out

    def save_chat_transcript(self, project_id: str, messages: list[Any]) -> list[dict[str, Any]]:
        self.store.require_project(project_id)
        cleaned: list[dict[str, Any]] = []
        if not isinstance(messages, list):
            messages = []
        for item in messages[:120]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "assistant")
            if role not in ("user", "assistant"):
                role = "assistant"
            kind = str(item.get("kind") or "")[:64]
            # Skip ephemeral analyzing status lines
            if kind == "status":
                continue
            html = str(item.get("html") or "")
            if len(html) > 80000:
                html = html[:80000]
            if not html.strip():
                continue
            cleaned.append({"role": role, "kind": kind, "html": html})
        self.store.update_project(
            project_id, lambda project: project.artifacts.__setitem__("chat_transcript", cleaned)
        )
        return cleaned

    @_paid_operation("client_revision")
    def apply_client_revision(self, project_id: str, message: str) -> dict[str, Any]:
        """Apply a free-form client revision request (max 5 rounds), then reformat + repackage.

        A round is reserved in the ledger database before the model is called, so workers share
        one count. A provider error gives the round back; any answer from the provider uses it,
        including one that is then rejected, so rejected answers cannot be farmed for free.
        """
        paid_words = self._require_payment(project_id, "a revision request")
        from services.assignment_llm import (
            STAGE_REVISION,
            assignment_generate_json,
            assignment_llm_configured,
        )
        from services.assignment_project.paths import assignment_storage_root

        text = (message or "").strip()
        if not text:
            raise ValueError("Revision message is required")
        if len(text) > 4000:
            raise ValueError("Revision message is too long")

        project = self.store.require_project(project_id)
        fingerprint = self._delivery_source_hash(project)
        chat = project.artifacts.get("revision_chat") if isinstance(project.artifacts.get("revision_chat"), dict) else {}
        rounds_used = int(chat.get("rounds_used") or 0)
        if rounds_used >= MAX_CLIENT_REVISION_ROUNDS:
            raise RevisionLimitError(
                f"Revision limit reached ({MAX_CLIENT_REVISION_ROUNDS} free rounds for this assignment)."
            )

        try:
            humanized = self._load_humanized_draft(project_id)
            content = humanized.content or ""
            title = humanized.title or project.title
        except KeyError:
            draft = self._load_draft(project_id)
            content = draft.content or ""
            title = draft.title or project.title

        if not assignment_llm_configured(STAGE_REVISION):
            raise ValueError("Revision AI is not configured")

        word_cap = int(paid_words * BLUEPRINT_WORD_RATIO) + BLUEPRINT_WORD_SLACK
        reservation_id = self._reserve_revision_round(project_id, legacy_used=rounds_used)

        system = (
            "You edit an academic assignment draft based on the student's revision request. "
            "Return ONLY JSON: {"
            "\"scope\": \"small|medium|large\", "
            "\"content\": \"full markdown WITH ## headings\", "
            "\"assistant_reply\": \"short confirmation of what you changed and the scope applied\", "
            "\"notes\": []"
            "}. "
            "Scale the edit to the request: "
            "small = wording/typos/local fixes only; "
            "medium = expand/shorten a section or adjust structure within reason; "
            "large = multi-section rewrite when the user clearly asks for it. "
            "Do not over-edit for small requests. Do not invent bibliographic sources. "
            "Keep required section headings. Preserve complete sentences. "
            "If a References section exists, keep it unless the user asks to fix it; "
            "you may fix formatting of existing refs only."
        )
        try:
            data, _ = assignment_generate_json(
                system_prompt=system,
                user_prompt=json.dumps(
                    {
                        "revision_request": text,
                        "title": title,
                        "draft": content[:28000],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                temperature=0.2,
                max_retries=1,
                stage=STAGE_REVISION,
            )
        except BaseException:
            self._finish_revision_round(project_id, reservation_id, consumed=False)
            raise
        if self._document_fingerprint(project_id) != fingerprint:
            # The answer edits a document that no longer exists; it is dropped, not charged.
            self._finish_revision_round(project_id, reservation_id, consumed=False)
            trace("document.stale_result_dropped", project_id=project_id, step="revision_chat")
            raise ProjectChangedError()
        self._finish_revision_round(project_id, reservation_id, consumed=True)
        if not isinstance(data, dict):
            raise ValueError("Revision model returned an invalid response")
        updated = str(data.get("content") or "").strip()
        if not updated or len(updated) < max(80, int(len(content) * 0.45)):
            raise ValueError("Revision did not produce usable content")
        if content.count("## ") >= 2 and updated.count("## ") < 2:
            raise ValueError("Revision dropped required section headings")
        updated_words = count_words(updated)
        # A draft already longer than the cap may still be edited, as long as it does not grow.
        if updated_words > word_cap and updated_words > count_words(content):
            trace(
                "revision_chat.over_paid_scope",
                project_id=project_id,
                words=updated_words,
                cap=word_cap,
                paid_words=paid_words,
            )
            raise RevisionScopeExceededError(
                f"This change would make the assignment about {updated_words} words. Your payment covers "
                f"up to {word_cap} words for a {paid_words}-word assignment. Nothing was changed; "
                "ask for a smaller change."
            )

        reply = str(data.get("assistant_reply") or data.get("notes") or "Updated your assignment.").strip()
        if isinstance(data.get("notes"), list) and not str(data.get("assistant_reply") or "").strip():
            reply = "; ".join(str(n) for n in data["notes"][:4]) or reply
        scope = str(data.get("scope") or "").strip().lower()
        if scope in {"small", "medium", "large"} and scope not in reply.lower():
            reply = f"[{scope} edit] {reply}"

        with self._unchanged_document(project_id, fingerprint, step="revision_chat"):
            self._persist_repaired_draft_content(project_id, updated)
        try:
            self._rehumanize_current_prose(
                project_id, reason="client_revision_chat", previous_content=content
            )
        except Exception as exc:  # noqa: BLE001
            trace("revision_chat.rehumanize_skipped", project_id=project_id, error=str(exc))

        try:
            self.run_formatting(project_id)
        except Exception as exc:  # noqa: BLE001
            trace("revision_chat.format_failed", project_id=project_id, error=str(exc))

        package = None
        try:
            package = self.run_delivery(project_id)
        except Exception as exc:  # noqa: BLE001
            trace("revision_chat.delivery_failed", project_id=project_id, error=str(exc))

        now = utc_now().isoformat()
        exchange = [
            {"role": "user", "content": text, "at": now},
            {"role": "assistant", "content": reply, "at": now},
        ]
        rounds_used = self._revision_rounds_used(project_id, fallback=rounds_used + 1)
        record: dict[str, Any] = {}

        def append_exchange(project: Project) -> None:
            # Appended to the latest stored chat, so a concurrent round's messages stay.
            current = project.artifacts.get("revision_chat")
            history = list(current.get("messages") or []) if isinstance(current, dict) else []
            record.update(
                {
                    "messages": (history + exchange)[-40:],
                    "rounds_used": rounds_used,
                    "max_rounds": MAX_CLIENT_REVISION_ROUNDS,
                    "updated_at": now,
                }
            )
            project.artifacts["revision_chat"] = dict(record)
            project.updated_at = utc_now()

        self.store.update_project(project_id, append_exchange)
        messages = record["messages"]

        # Persist a copy on disk for support.
        chat_path = assignment_storage_root() / project_id / "revision_chat.json"
        chat_path.parent.mkdir(parents=True, exist_ok=True)
        chat_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "assistant_reply": reply,
            "rounds_used": rounds_used,
            "max_rounds": MAX_CLIENT_REVISION_ROUNDS,
            "messages": messages[-40:],
            "delivery_package": package.to_dict() if package is not None else None,
        }


def _files_from_manifest(manifest_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for item in manifest_files:
        mapped.append(
            {
                "file_type": item.get("source") or item.get("file_type"),
                "original_filename": item.get("name") or item.get("original_filename"),
                "parsed": item.get("parsed", False),
            }
        )
    return mapped
