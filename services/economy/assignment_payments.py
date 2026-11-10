"""Payment cycles for assignment projects.

Every confirmed payment of a project opens one cycle row, written in the same SQLite
transaction as the coin debit or plan-allowance consumption it records. A partial unique
index allows a single active cycle per project, so parallel confirmations cannot charge
twice. Refunding (or voiding) a cycle is one active -> refunded transition in the same
transaction as the refund ledger row or allowance release, so it happens at most once and
always returns exactly what that cycle took.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from .db import connect
from .ledger import classify_transaction
from .wallet import InsufficientCoins, _log_wallet_activity

FEATURE = "assignment"

STATUS_ACTIVE = "active"
STATUS_REFUNDED = "refunded"
STATUS_VOIDED = "voided"

METHOD_COINS = "coins"
METHOD_ALLOWANCE = "plan_allowance"


class PaymentRecordError(LookupError):
    """The cycle is unknown, belongs to another project/user, or its debit row is missing."""


def payment_ref(project_id: str, cycle_id: str) -> str:
    return f"assignment-payment:{project_id}:{cycle_id}"


def refund_ref(project_id: str, cycle_id: str) -> str:
    return f"assignment-refund:{project_id}:{cycle_id}"


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def get_cycle(cycle_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _row(
            conn.execute("SELECT * FROM assignment_payments WHERE cycle_id = ?", (str(cycle_id),)).fetchone()
        )


def active_cycle(project_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _row(
            conn.execute(
                "SELECT * FROM assignment_payments WHERE project_id = ? AND status = ?",
                (str(project_id), STATUS_ACTIVE),
            ).fetchone()
        )


def live_cycle(project_id: str) -> dict[str, Any] | None:
    """The project's active payment cycle, for decisions that must not trust the project JSON.

    A ledger whose ``assignment_payments`` table was never created holds no cycles (``open_cycle``
    cannot succeed against it). Every other database error propagates so callers fail closed.
    """
    try:
        return active_cycle(project_id)
    except sqlite3.OperationalError as exc:
        if str(exc).lower().startswith("no such table"):
            return None
        raise


def bind_cycle_scope(project_id: str, cycle_id: str, *, scope_hash: str, word_count: int | None) -> bool:
    """Record the verified billable scope of a legacy active cycle; never replaces a bound one."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE assignment_payments SET scope_hash = ?, quoted_word_count = ? "
            "WHERE cycle_id = ? AND project_id = ? AND status = ? AND scope_hash IS NULL",
            (str(scope_hash), word_count, str(cycle_id), str(project_id), STATUS_ACTIVE),
        )
        return cur.rowcount == 1


def refund_recorded(ref_id: str) -> int | None:
    """Coins of an assignment refund already booked under ``ref_id``, if any."""
    with connect() as conn:
        row = conn.execute(
            "SELECT amount FROM transactions "
            "WHERE kind = 'refund' AND feature = ? AND ref_id = ? ORDER BY id LIMIT 1",
            (FEATURE, ref_id),
        ).fetchone()
    return int(row["amount"]) if row else None


def cycle_refund_evidence(project_id: str, cycle_id: str) -> dict[str, Any] | None:
    """Ledger proof that this cycle was already given back (closed cycle or a booked refund row)."""
    cycle = get_cycle(cycle_id)
    if cycle is None or cycle["project_id"] != project_id:
        raise PaymentRecordError("payment cycle not found")
    reference = refund_ref(project_id, cycle_id)
    if cycle["status"] != STATUS_ACTIVE:
        return {"coins": int(cycle["refunded_coins"] or 0), "reference": reference, "status": cycle["status"]}
    booked = refund_recorded(reference)
    if booked is not None:
        return {"coins": booked, "reference": reference, "status": "refund_row_only"}
    return None


class RefundBlockedError(RuntimeError):
    """The ledger itself forbids an automatic refund; ``code`` matches RefundNotEligibleError codes."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def record_output(
    project_id: str,
    cycle_id: str | None,
    operation: str,
    *,
    source: str,
    op_id: str | None = None,
) -> None:
    """Record (once) that generated text of ``project_id`` is durably stored; never undone."""
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO assignment_output_evidence "
            "(project_id, cycle_id, operation, source, op_id) VALUES (?, ?, ?, ?, ?)",
            (str(project_id), str(cycle_id or ""), str(operation), str(source), op_id),
        )
        if op_id:
            conn.execute(
                "UPDATE assignment_operations SET output_phase = 'recorded' WHERE op_id = ?",
                (op_id,),
            )


def output_evidence(project_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM assignment_output_evidence WHERE project_id = ? ORDER BY id",
            (str(project_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def begin_operation(project_id: str, cycle_id: str | None, operation: str, *, pid: int | None = None) -> str:
    op_id = uuid.uuid4().hex
    with connect() as conn:
        conn.execute(
            "INSERT INTO assignment_operations (op_id, project_id, cycle_id, operation, status, pid) "
            "VALUES (?, ?, ?, ?, 'started', ?)",
            (op_id, str(project_id), str(cycle_id or ""), str(operation), pid),
        )
    return op_id


def operation_persisting(op_id: str) -> None:
    """Called right before generated text is written; cleared only by ``record_output``."""
    with connect() as conn:
        conn.execute(
            "UPDATE assignment_operations SET output_phase = 'persisting' "
            "WHERE op_id = ? AND output_phase IS NULL",
            (op_id,),
        )


def finish_operation(op_id: str, status: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE assignment_operations SET status = ?, finished_at = datetime('now') WHERE op_id = ?",
            (str(status), op_id),
        )


def _refund_blocker(conn: sqlite3.Connection, project_id: str) -> str | None:
    pid = str(project_id)
    if conn.execute(
        "SELECT 1 FROM assignment_output_evidence WHERE project_id = ? LIMIT 1", (pid,)
    ).fetchone():
        return "OUTPUT_GENERATED"
    if conn.execute(
        "SELECT 1 FROM assignment_operations WHERE project_id = ? AND output_phase = 'persisting' LIMIT 1",
        (pid,),
    ).fetchone():
        return "OPERATION_INTERRUPTED"
    # Payments taken before operations were journaled: whether text was delivered is unknown.
    if conn.execute(
        "SELECT 1 FROM assignment_payments WHERE project_id = ? AND output_tracking = 0 LIMIT 1", (pid,)
    ).fetchone():
        return "OUTPUT_STATE_UNKNOWN"
    if conn.execute(
        "SELECT 1 FROM transactions WHERE kind = 'debit' AND feature = ? AND ref_id = ? LIMIT 1",
        (FEATURE, pid),
    ).fetchone():
        return "OUTPUT_STATE_UNKNOWN"
    return None


def refund_blocker(project_id: str) -> str | None:
    """Why the ledger forbids an automatic refund of ``project_id`` (None when it doesn't)."""
    with connect() as conn:
        return _refund_blocker(conn, project_id)


def open_cycle(
    user_id: int,
    project_id: str,
    *,
    coins: int,
    allowance: dict[str, Any] | None,
    quote: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Charge for a new payment cycle, or return the live one without charging again.

    ``allowance`` comes from ``plans.allowance_rule``; when it still has room the cycle is
    paid from the plan, otherwise ``coins`` (already discounted by the caller) are debited.
    ``quote`` is the server quote being paid; its id and scope are stored on the cycle in the
    same transaction as the charge. Raises InsufficientCoins without writing anything.
    """
    cycle_id = uuid.uuid4().hex
    reference = payment_ref(project_id, cycle_id)
    debit: dict[str, Any] | None = None
    quote = quote or {}
    quote_cols = (
        str(quote["quote_id"]) if quote.get("quote_id") else None,
        str(quote["scope_hash"]) if quote.get("scope_hash") else None,
        int(quote["word_count"]) if quote.get("word_count") is not None else None,
        int(quote["amount_coins"]) if quote.get("amount_coins") is not None else None,
    )
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM assignment_payments WHERE project_id = ? AND status = ?",
            (str(project_id), STATUS_ACTIVE),
        ).fetchone()
        if existing is not None:
            return {**dict(existing), "existing": True}

        use_allowance = False
        if allowance is not None:
            if allowance.get("mode") == "unlimited":
                use_allowance = True
            elif allowance.get("mode") == "quota" and allowance.get("period_key"):
                row = conn.execute(
                    "SELECT used FROM plan_usage WHERE user_id = ? AND feature = ? AND period_key = ?",
                    (int(user_id), FEATURE, allowance["period_key"]),
                ).fetchone()
                if (int(row["used"]) if row else 0) < int(allowance.get("limit") or 0):
                    conn.execute(
                        "INSERT INTO plan_usage (user_id, feature, period_key, used) VALUES (?, ?, ?, 1) "
                        "ON CONFLICT(user_id, feature, period_key) DO UPDATE SET used = used + 1",
                        (int(user_id), FEATURE, allowance["period_key"]),
                    )
                    use_allowance = True

        if use_allowance:
            conn.execute(
                "INSERT INTO assignment_payments "
                "(cycle_id, project_id, user_id, method, coins, allowance_mode, allowance_period, status, "
                " output_tracking, quote_id, scope_hash, quoted_word_count, quoted_coins) "
                "VALUES (?, ?, ?, ?, 0, ?, ?, ?, 1, ?, ?, ?, ?)",
                (
                    cycle_id,
                    str(project_id),
                    int(user_id),
                    METHOD_ALLOWANCE,
                    allowance.get("mode"),
                    allowance.get("period_key"),
                    STATUS_ACTIVE,
                    *quote_cols,
                ),
            )
        else:
            amount = int(coins)
            if amount <= 0:
                raise ValueError("Price must be calculated before payment confirmation")
            conn.execute("INSERT OR IGNORE INTO wallets (user_id, balance) VALUES (?, 0)", (int(user_id),))
            row = conn.execute("SELECT balance FROM wallets WHERE user_id = ?", (int(user_id),)).fetchone()
            balance_before = int(row["balance"]) if row else 0
            cur = conn.execute(
                "UPDATE wallets SET balance = balance - ?, updated_at = datetime('now') "
                "WHERE user_id = ? AND balance >= ?",
                (amount, int(user_id), amount),
            )
            if cur.rowcount != 1:
                raise InsufficientCoins(required=amount, balance=balance_before)
            tx_type, reference_type = classify_transaction(kind="debit", feature=FEATURE)
            meta = {"project_id": project_id, "cycle_id": cycle_id}
            cur = conn.execute(
                "INSERT INTO transactions "
                "(user_id, kind, feature, amount, balance_before, balance_after, "
                " type, reference_type, status, ref_id, meta_json) "
                "VALUES (?, 'debit', ?, ?, ?, ?, ?, ?, 'completed', ?, ?)",
                (
                    int(user_id),
                    FEATURE,
                    amount,
                    balance_before,
                    balance_before - amount,
                    tx_type,
                    reference_type,
                    reference,
                    json.dumps(meta),
                ),
            )
            debit = {
                "id": cur.lastrowid,
                "amount": amount,
                "before": balance_before,
                "type": tx_type,
                "reference_type": reference_type,
                "meta": meta,
            }
            conn.execute(
                "INSERT INTO assignment_payments "
                "(cycle_id, project_id, user_id, method, coins, debit_tx_id, status, output_tracking, "
                " quote_id, scope_hash, quoted_word_count, quoted_coins) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                (cycle_id, str(project_id), int(user_id), METHOD_COINS, amount, debit["id"], STATUS_ACTIVE,
                 *quote_cols),
            )
        created = conn.execute("SELECT * FROM assignment_payments WHERE cycle_id = ?", (cycle_id,)).fetchone()

    if debit is not None:
        _log_wallet_activity(
            debit["id"],
            int(user_id),
            tx_type=debit["type"] or "debit",
            feature=FEATURE,
            credits=-debit["amount"],
            balance_before=debit["before"],
            balance_after=debit["before"] - debit["amount"],
            reference_type=debit["reference_type"],
            ref_id=reference,
            meta=debit["meta"],
        )
    return {**dict(created), "existing": False}


def close_cycle(
    project_id: str,
    cycle_id: str,
    *,
    user_id: int,
    kind: str,
    reason: str,
    admin_id: int | None = None,
) -> dict[str, Any]:
    """Give back exactly what the cycle took, at most once.

    Returns the closed cycle plus ``already_closed`` (nothing moved now) and
    ``coins_refunded``. A refund row already booked under the cycle's reference (an
    interrupted earlier attempt) closes the cycle without crediting again. An automatic
    (``kind="failure"``) refund raises RefundBlockedError, in the same transaction, when
    output evidence or an unresolved/unknown operation exists for the project.
    """
    reference = refund_ref(project_id, cycle_id)
    status = STATUS_VOIDED if kind == "void" else STATUS_REFUNDED
    credit: dict[str, Any] | None = None
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cycle = conn.execute("SELECT * FROM assignment_payments WHERE cycle_id = ?", (str(cycle_id),)).fetchone()
        if cycle is None or cycle["project_id"] != str(project_id) or int(cycle["user_id"]) != int(user_id):
            raise PaymentRecordError("payment cycle not found")
        if cycle["status"] != STATUS_ACTIVE:
            return {**dict(cycle), "already_closed": True, "coins_refunded": int(cycle["refunded_coins"] or 0)}

        booked = conn.execute(
            "SELECT id, amount FROM transactions WHERE kind = 'refund' AND feature = ? AND ref_id = ? "
            "ORDER BY id LIMIT 1",
            (FEATURE, reference),
        ).fetchone()
        refund_tx_id: int | None = None
        coins = 0
        if booked is None and kind == "failure":
            blocker = _refund_blocker(conn, str(project_id))
            if blocker is not None:
                raise RefundBlockedError(blocker)
        if booked is not None:
            refund_tx_id, coins = int(booked["id"]), int(booked["amount"])
        elif cycle["method"] == METHOD_COINS:
            debit_row = conn.execute(
                "SELECT amount, user_id FROM transactions "
                "WHERE id = ? AND kind = 'debit' AND feature = ? AND ref_id = ?",
                (cycle["debit_tx_id"], FEATURE, payment_ref(project_id, cycle_id)),
            ).fetchone()
            if debit_row is None or int(debit_row["user_id"]) != int(user_id):
                raise PaymentRecordError("payment debit not found")
            coins = int(debit_row["amount"])
            conn.execute("INSERT OR IGNORE INTO wallets (user_id, balance) VALUES (?, 0)", (int(user_id),))
            row = conn.execute("SELECT balance FROM wallets WHERE user_id = ?", (int(user_id),)).fetchone()
            balance_before = int(row["balance"]) if row else 0
            conn.execute(
                "UPDATE wallets SET balance = ?, updated_at = datetime('now') WHERE user_id = ?",
                (balance_before + coins, int(user_id)),
            )
            tx_type, reference_type = classify_transaction(kind="refund", feature=FEATURE)
            meta: dict[str, Any] = {"reason": reason[:200], "project_id": project_id, "cycle_id": cycle_id}
            if admin_id is not None:
                meta["admin_id"] = int(admin_id)
            cur = conn.execute(
                "INSERT INTO transactions "
                "(user_id, kind, feature, amount, balance_before, balance_after, "
                " type, reference_type, status, ref_id, meta_json) "
                "VALUES (?, 'refund', ?, ?, ?, ?, ?, ?, 'completed', ?, ?)",
                (
                    int(user_id),
                    FEATURE,
                    coins,
                    balance_before,
                    balance_before + coins,
                    tx_type,
                    reference_type,
                    reference,
                    json.dumps(meta),
                ),
            )
            refund_tx_id = cur.lastrowid
            credit = {
                "id": refund_tx_id,
                "before": balance_before,
                "type": tx_type,
                "reference_type": reference_type,
                "meta": meta,
            }
        elif cycle["allowance_mode"] == "quota" and cycle["allowance_period"]:
            conn.execute(
                "UPDATE plan_usage SET used = MAX(0, used - 1) "
                "WHERE user_id = ? AND feature = ? AND period_key = ?",
                (int(user_id), FEATURE, cycle["allowance_period"]),
            )

        conn.execute(
            "UPDATE assignment_payments SET status = ?, refund_tx_id = ?, refunded_coins = ?, "
            "refund_kind = ?, refund_reason = ?, refund_admin_id = ?, closed_at = datetime('now') "
            "WHERE cycle_id = ? AND status = ?",
            (
                status,
                refund_tx_id,
                coins,
                kind,
                reason[:200],
                int(admin_id) if admin_id is not None else None,
                str(cycle_id),
                STATUS_ACTIVE,
            ),
        )
        closed = conn.execute("SELECT * FROM assignment_payments WHERE cycle_id = ?", (str(cycle_id),)).fetchone()

    if credit is not None:
        _log_wallet_activity(
            credit["id"],
            int(user_id),
            tx_type=credit["type"] or "refund",
            feature=FEATURE,
            credits=coins,
            balance_before=credit["before"],
            balance_after=credit["before"] + coins,
            reference_type=credit["reference_type"],
            ref_id=reference,
            meta=credit["meta"],
        )
    return {**dict(closed), "already_closed": False, "coins_refunded": coins}
