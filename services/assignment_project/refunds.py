"""Single refund path for paid assignments (user request, automatic, admin exception).

Project state lives in a JSON bundle and coins in SQLite, so the two cannot share one
transaction. Money moves only in SQLite: closing the project's payment cycle credits
exactly the coins its debit took (or releases the plan allowance it used) in the same
transaction as the active -> refunded transition, so it happens at most once. The JSON
marking follows under the per-project billing lock; if the process dies in between, the
closed cycle is found on the next access and only the marking is finished.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from services.assignment_project.project_lock import (
    BILLING_LOCK,
    LockBusyError,
    payment_gate,
    project_file_lock,
)
from services.assignment_project.service import (
    _REVIEW_REFUND_CODES,
    PAYMENT_CYCLE_KEY,
    ProjectService,
    RefundNotEligibleError,
)
from services.assignment_project.trace_log import trace
from services.economy import assignment_payments as payment_ledger

# How long a refund waits for running paid operations of the project before giving up.
REFUND_GATE_WAIT_SECONDS = 5.0


def _owner_id(service: ProjectService, project_id: str) -> int:
    raw = str(service.store.require_project(project_id).user_id or "").strip()
    try:
        return int(raw)
    except ValueError:
        raise RefundNotEligibleError("NO_OWNER") from None


def _finish(
    service: ProjectService,
    wallet: Any,
    project_id: str,
    user_id: int,
    coins: int,
    *,
    reference: str,
    kind: str,
    reason: str,
    admin_id: int | None,
    event: str,
) -> dict[str, Any]:
    service.mark_assignment_refunded(
        project_id, coins, reference=reference, kind=kind, reason=reason, admin_id=admin_id
    )
    trace(event, project_id=project_id, reference=reference, coins=coins, kind=kind)
    return {"refunded": True, "coins_refunded": coins, "balance": wallet.get_balance(user_id)}


def _refund_legacy_payment(
    service: ProjectService,
    wallet: Any,
    project_id: str,
    user_id: int,
    *,
    reason: str,
    admin_id: int | None,
) -> dict[str, Any]:
    """Payments confirmed before payment cycles existed have no exact debit on record."""
    kind = "admin" if admin_id is not None else "failure"
    reference = service.refund_reference(project_id)
    booked = wallet.assignment_refund_recorded(reference)
    if booked is not None:
        return _finish(
            service, wallet, project_id, user_id, booked,
            reference=reference, kind=kind, reason=reason, admin_id=admin_id,
            event="refund.assignment.resumed",
        )
    if admin_id is not None:
        service.assert_admin_refund_allowed(project_id)
    else:
        service.assert_assignment_refund_eligible(project_id)
    raise RefundNotEligibleError("LEGACY_PAYMENT_REVIEW")


def refund_assignment(
    service: ProjectService,
    wallet: Any,
    project_id: str,
    *,
    reason: str,
    admin_id: int | None = None,
) -> dict[str, Any]:
    """Refund the project owner at most once per payment cycle.

    Raises RefundNotEligibleError (safe message) or KeyError for an unknown project.
    Without ``admin_id`` the automatic rules apply (recorded execution failure, no
    generated content). The payment gate is taken exclusively first, so no paid operation
    of this project is running in any worker while eligibility is judged and money moves.
    """
    service.store.require_project(project_id)
    try:
        with payment_gate(
            project_id, root=service.store.storage_root, exclusive=True, wait_seconds=REFUND_GATE_WAIT_SECONDS
        ):
            return _refund_under_gate(service, wallet, project_id, reason=reason, admin_id=admin_id)
    except LockBusyError:
        raise RefundNotEligibleError("OPERATION_IN_PROGRESS") from None


def _refund_under_gate(
    service: ProjectService,
    wallet: Any,
    project_id: str,
    *,
    reason: str,
    admin_id: int | None,
) -> dict[str, Any]:
    with project_file_lock(project_id, name=BILLING_LOCK, root=service.store.storage_root):
        user_id = _owner_id(service, project_id)
        art = service.store.require_project(project_id).artifacts or {}
        if art.get("payment_refunded"):
            raise RefundNotEligibleError("ALREADY_REFUNDED")
        if art.get("payment_confirmed") is not True:
            raise RefundNotEligibleError("NOT_PAID")
        cycle_id = art.get(PAYMENT_CYCLE_KEY)
        if not cycle_id:
            return _refund_legacy_payment(
                service, wallet, project_id, user_id, reason=reason, admin_id=admin_id
            )
        cycle_id = str(cycle_id)
        kind = "admin" if admin_id is not None else "failure"
        reference = payment_ledger.refund_ref(project_id, cycle_id)

        try:
            evidence = service.ledger_refund_evidence(project_id, art)
        except payment_ledger.PaymentRecordError:
            service._flag_refund_review(project_id, "payment_cycle_record_missing")
            raise RefundNotEligibleError("PAYMENT_RECORD_MISSING") from None
        except sqlite3.Error:
            raise RefundNotEligibleError("PAYMENT_RECORD_MISSING") from None
        if evidence is None:
            if admin_id is not None:
                service.assert_admin_refund_allowed(project_id)
            else:
                service.assert_assignment_refund_eligible(project_id)
            event = "refund.assignment.completed"
        else:
            event = "refund.assignment.resumed"

        try:
            closed = payment_ledger.close_cycle(
                project_id, cycle_id, user_id=user_id, kind=kind, reason=reason, admin_id=admin_id
            )
        except payment_ledger.PaymentRecordError:
            service._flag_refund_review(project_id, "payment_debit_record_missing")
            raise RefundNotEligibleError("PAYMENT_RECORD_MISSING") from None
        except payment_ledger.RefundBlockedError as exc:
            if exc.code in _REVIEW_REFUND_CODES:
                service._flag_refund_review(project_id, exc.code.lower())
            raise RefundNotEligibleError(exc.code) from None
        if closed.get("already_closed") and evidence is None:
            event = "refund.assignment.resumed"
        return _finish(
            service, wallet, project_id, user_id, int(closed.get("coins_refunded") or 0),
            reference=reference, kind=kind, reason=reason, admin_id=admin_id, event=event,
        )
