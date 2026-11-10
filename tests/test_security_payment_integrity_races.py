"""Patch 3E: durable output evidence, refund-versus-generation races, quarantined sections.

Every AI call goes to the offline MockSectionWriter or a trap; races are ordered with events,
barriers and forked processes (separate flock owners, like gunicorn workers), not sleeps.
"""

from __future__ import annotations

import copy
import json
import multiprocessing
import os
import sqlite3
import threading

import pytest

from services.assignment_project import refunds as refunds_mod
from services.assignment_project.project_lock import LockBusyError, payment_gate
from services.assignment_project.refunds import refund_assignment
from services.assignment_project.service import (
    OUTPUT_GENERATED_KEY,
    PAYMENT_CYCLE_KEY,
    PROCESSING_FAILURE_KEY,
    WRITER_EXPECTED_SECTIONS_KEY,
    PaymentRequiredError,
    ProjectService,
    RefundNotEligibleError,
    StagePreconditionError,
    has_generated_output,
)
from services.assignment_project.store import ProjectStore
from services.economy import assignment_payments as payment_ledger
from services.economy import db as economy_db
from services.writer_engine import WriterEngineService
from services.writer_engine.mock_reviewer import MockSectionReviewer
from tests.test_security_paid_pipelines import (  # noqa: F401  (economy is a fixture)
    _client,
    _signed_in,
    _user,
    economy,
)
from tests.test_security_refund_integrity import (  # noqa: F401  (refund_app is a fixture)
    _admin_refund,
    _fail_writer_via_route,
    _paid_project,
    _plan_and_blueprint,
    _refund,
    _refund_rows,
    _url,
    refund_app,
)

FORK = multiprocessing.get_context("fork")
WAIT = 30


# ------------------------------------------------------------------ helpers


def _artifacts(env, project_id: str) -> dict:
    return env.service.store.require_project(project_id).artifacts


def _evidence(project_id: str) -> list[dict]:
    return payment_ledger.output_evidence(project_id)


def _ops(project_id: str) -> list[dict]:
    with economy_db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM assignment_operations WHERE project_id = ? ORDER BY rowid", (project_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def _fresh_worker(env) -> ProjectService:
    """Another gunicorn worker: same disk and ledger, empty memory."""
    return ProjectService(
        store=ProjectStore(root=env.service.store.storage_root),
        pipeline=env.service.pipeline,
        analyzer=env.service.analyzer,
        research=env.service.research,
        blueprint=env.service.blueprint,
        writer=WriterEngineService(writer=env.writer, reviewer=MockSectionReviewer()),
        delivery=env.service.delivery,
    )


def _provider_down(**_kwargs):
    raise RuntimeError("provider unavailable")


def _record_genuine_failure(env, project_id: str) -> None:
    """A real execution failure of a later paid stage (blueprint rebuild hits a provider outage)."""
    original = env.service.blueprint.build_blueprint
    env.service.blueprint.build_blueprint = _provider_down
    try:
        with pytest.raises(RuntimeError):
            env.service.run_blueprint(project_id)
    finally:
        env.service.blueprint.build_blueprint = original
    failure = _artifacts(env, project_id)[PROCESSING_FAILURE_KEY]
    assert failure["client_seeded"] is False


def _erase_output_from_json(env, project_id: str, writer_session: dict | None) -> None:
    """What a stale bundle write does: older writer session, no output marker.

    The store keeps the output marker on every save, so the erased copy is put on disk
    directly, as an older build or a restored backup would.
    """
    from tests.assignment_helpers import plant_stale_project_json

    project = env.service.store.require_project(project_id)
    if writer_session is None:
        project.artifacts.pop("writer_session", None)
    else:
        project.artifacts["writer_session"] = writer_session
    for key in (OUTPUT_GENERATED_KEY, "output_generated_cycle_id", "draft", "humanized_draft"):
        project.artifacts.pop(key, None)
    plant_stale_project_json(env.service.store.storage_root, project_id, project.to_dict())
    assert not has_generated_output(_artifacts(env, project_id))


def _assert_refund_refused(env, owner, project_id: str, reason: str, balance: int) -> None:
    res = _refund(_signed_in(_client(), owner), project_id)
    assert res.status_code == 400, res.get_data(as_text=True)
    assert res.get_json()["reason"] == reason
    assert env.wallet.get_balance(owner["id"]) == balance
    assert _refund_rows(project_id) == []
    cycle = payment_ledger.get_cycle(_artifacts(env, project_id)[PAYMENT_CYCLE_KEY])
    assert cycle["status"] == "active"


def _started_writer(env, owner) -> tuple[str, int]:
    project_id, coins = _paid_project(env, owner)
    _plan_and_blueprint(env, project_id)
    env.service.start_writer(project_id)
    return project_id, coins


class _GatedProvider:
    """Section writer that parks inside the AI call until released."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        self.entered.set()
        assert self.release.wait(WAIT)
        return self.inner(**kwargs)


def _child_refund(queue, service, wallet, project_id, wait_seconds):
    outcome = "error"
    try:
        refunds_mod.REFUND_GATE_WAIT_SECONDS = wait_seconds
        refund_assignment(service, wallet, project_id, reason="race")
        outcome = "ok"
    except RefundNotEligibleError as exc:
        outcome = exc.code
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {type(exc).__name__}: {exc}"
    finally:
        queue.put(outcome)
        queue.close()
        queue.join_thread()
        os._exit(0)


def _refund_in_child(env, project_id: str, wait_seconds: float) -> str:
    queue = FORK.Queue()
    proc = FORK.Process(target=_child_refund, args=(queue, env.service, env.wallet, project_id, wait_seconds))
    proc.start()
    outcome = queue.get(timeout=WAIT)
    proc.join(timeout=WAIT)
    return outcome


# ------------------------------------------------------------------ 2. durable, monotonic output evidence


def test_output_evidence_is_recorded_after_the_text_is_stored(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    assert _evidence(project_id) == []

    refund_app.service.advance_writer(project_id)

    rows = _evidence(project_id)
    cycle_id = _artifacts(refund_app, project_id)[PAYMENT_CYCLE_KEY]
    assert [(r["cycle_id"], r["operation"], r["source"]) for r in rows] == [(cycle_id, "writing", "persisted")]
    writing = [op for op in _ops(project_id) if op["operation"] == "writing"]
    assert writing[-1]["status"] == "completed" and writing[-1]["output_phase"] == "recorded"
    assert rows[0]["op_id"] == writing[-1]["op_id"]


def test_evidence_is_never_written_when_the_text_was_not_stored(refund_app, monkeypatch):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    store = refund_app.service.store
    real_save = store.save_project

    def disk_full(project):
        if OUTPUT_GENERATED_KEY in project.artifacts:
            raise OSError("No space left on device")
        return real_save(project)

    monkeypatch.setattr(store, "save_project", disk_full)
    with pytest.raises(OSError):
        refund_app.service.advance_writer(project_id)
    monkeypatch.setattr(store, "save_project", real_save)

    assert _evidence(project_id) == []
    assert _ops(project_id)[-1]["output_phase"] == "persisting"  # outcome unknown -> conservative
    _record_genuine_failure(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])
    _assert_refund_refused(refund_app, owner, project_id, "OPERATION_INTERRUPTED", balance)


def test_scenario1_stale_project_json_cannot_erase_output_evidence(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    stale = refund_app.service.store.require_project(project_id)  # loaded before any text exists
    stale_data = copy.deepcopy(stale.to_dict())

    refund_app.service.advance_writer(project_id)
    assert has_generated_output(_artifacts(refund_app, project_id))

    refund_app.service.store.save_project(stale)  # the store keeps the newer output evidence
    assert has_generated_output(_artifacts(refund_app, project_id))
    from tests.assignment_helpers import plant_stale_project_json

    plant_stale_project_json(refund_app.service.store.storage_root, project_id, stale_data)
    assert not has_generated_output(_artifacts(refund_app, project_id))  # stale snapshot on disk anyway
    _record_genuine_failure(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    _assert_refund_refused(refund_app, owner, project_id, "OUTPUT_GENERATED", balance)
    cycle_id = _artifacts(refund_app, project_id)[PAYMENT_CYCLE_KEY]
    with pytest.raises(payment_ledger.RefundBlockedError) as blocked:
        payment_ledger.close_cycle(project_id, cycle_id, user_id=owner["id"], kind="failure", reason="direct")
    assert blocked.value.code == "OUTPUT_GENERATED"
    assert refund_app.wallet.get_balance(owner["id"]) == balance


def test_scenario2_stale_writer_session_cannot_erase_output_evidence(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    empty_session = json.loads(json.dumps(_artifacts(refund_app, project_id)["writer_session"]))

    refund_app.service.advance_writer(project_id)
    client = _signed_in(_client(), owner)
    # The browser echoes its old (empty) session back; it never becomes state.
    assert client.post(_url(project_id, "writer/advance"), json={"writer_session": empty_session}).status_code == 200
    _erase_output_from_json(refund_app, project_id, empty_session)
    _record_genuine_failure(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    _assert_refund_refused(refund_app, owner, project_id, "OUTPUT_GENERATED", balance)


def test_scenario12_reload_and_worker_restart_keep_output_evidence(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    refund_app.service.advance_writer(project_id)
    _erase_output_from_json(refund_app, project_id, None)
    _record_genuine_failure(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    restarted = _fresh_worker(refund_app)
    restarted.store.require_bundle(project_id)  # reload from disk
    with pytest.raises(RefundNotEligibleError) as refused:
        refund_assignment(restarted, refund_app.wallet, project_id, reason="after restart")
    assert refused.value.code == "OUTPUT_GENERATED"
    assert _refund_in_child(refund_app, project_id, 1.0) == "OUTPUT_GENERATED"
    assert refund_app.wallet.get_balance(owner["id"]) == balance and _refund_rows(project_id) == []


def test_evidence_rows_are_append_only(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    refund_app.service.advance_writer(project_id)
    with economy_db.connect() as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM assignment_output_evidence WHERE project_id = ?", (project_id,))
    with economy_db.connect() as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE assignment_output_evidence SET project_id = 'x' WHERE project_id = ?", (project_id,))
    assert len(_evidence(project_id)) == 1


def test_repeated_refund_requests_stay_idempotent(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])
    client = _signed_in(_client(), owner)

    assert _refund(client, project_id).status_code == 200
    for _ in range(3):
        again = _refund(client, project_id)
        assert again.status_code == 409 and again.get_json()["reason"] == "ALREADY_REFUNDED"
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins
    assert [row["amount"] for row in _refund_rows(project_id)] == [coins]


# ------------------------------------------------------------------ 3. refund versus generation


def test_case_a_scenario5_refund_cannot_land_while_generation_runs(refund_app, monkeypatch):
    """Generation holds the gate: a refund from another process fails safely, then is refused."""
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)  # recorded failure: refundable right now
    balance = refund_app.wallet.get_balance(owner["id"])
    gated = _GatedProvider(refund_app.writer.write_section)
    monkeypatch.setattr(refund_app.writer, "write_section", gated)
    errors: list[BaseException] = []

    def generate():
        try:
            refund_app.service.advance_writer(project_id)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    worker = threading.Thread(target=generate)
    worker.start()
    assert gated.entered.wait(WAIT)

    assert _refund_in_child(refund_app, project_id, 0.2) == "OPERATION_IN_PROGRESS"
    assert refund_app.wallet.get_balance(owner["id"]) == balance

    gated.release.set()
    worker.join(WAIT)
    assert not errors and gated.calls == 1
    assert _evidence(project_id)

    assert _refund_in_child(refund_app, project_id, 1.0) == "OUTPUT_GENERATED"
    assert refund_app.wallet.get_balance(owner["id"]) == balance and _refund_rows(project_id) == []


def test_case_a_scenario7_waiting_refund_is_rejected_once_generation_persists(refund_app, monkeypatch):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])
    gated = _GatedProvider(refund_app.writer.write_section)
    monkeypatch.setattr(refund_app.writer, "write_section", gated)
    monkeypatch.setattr(refunds_mod, "REFUND_GATE_WAIT_SECONDS", WAIT)
    judging = threading.Event()
    real_eligible = refund_app.service.assert_assignment_refund_eligible

    def eligible(pid):
        judging.set()
        return real_eligible(pid)

    monkeypatch.setattr(refund_app.service, "assert_assignment_refund_eligible", eligible)
    outcome: list[str] = []

    worker = threading.Thread(target=lambda: refund_app.service.advance_writer(project_id))
    worker.start()
    assert gated.entered.wait(WAIT)

    def refund():
        try:
            refund_assignment(refund_app.service, refund_app.wallet, project_id, reason="race")
            outcome.append("ok")
        except RefundNotEligibleError as exc:
            outcome.append(exc.code)

    refunder = threading.Thread(target=refund)
    refunder.start()
    # Exclusion: while generation is inside the AI call the refund cannot even judge eligibility.
    assert not judging.wait(1.0)
    gated.release.set()
    worker.join(WAIT)
    refunder.join(WAIT)

    assert outcome == ["OUTPUT_GENERATED"]
    assert refund_app.wallet.get_balance(owner["id"]) == balance and _refund_rows(project_id) == []
    assert _artifacts(refund_app, project_id)["payment_confirmed"] is True


def _child_generate(queue, service, project_id, started, reached_check):
    outcome = "error"
    calls: list[int] = []
    try:

        def trap(**_kwargs):
            calls.append(1)
            raise AssertionError("AI provider called after refund")

        real_check = service._require_payment

        def check(pid, action):
            reached_check.set()
            return real_check(pid, action)

        service.writer.writer.write_section = trap
        service._require_payment = check
        started.set()
        service.advance_writer(project_id)
        outcome = "generated"
    except PaymentRequiredError:
        outcome = "payment_required"
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {type(exc).__name__}: {exc}"
    finally:
        queue.put((outcome, len(calls)))
        queue.close()
        queue.join_thread()
        os._exit(0)


def test_case_b_scenario6_generation_after_refund_never_reaches_the_provider(refund_app, monkeypatch):
    """Refund holds the gate: a generation request from another worker waits, then fails its payment check."""
    owner = _user("owner@example.com")
    project_id, coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])
    holding, go = threading.Event(), threading.Event()
    real_close = payment_ledger.close_cycle

    def slow_close(*args, **kwargs):
        holding.set()
        assert go.wait(WAIT)
        return real_close(*args, **kwargs)

    monkeypatch.setattr(payment_ledger, "close_cycle", slow_close)
    result: list[str] = []
    refunder = threading.Thread(
        target=lambda: result.append(str(refund_assignment(refund_app.service, refund_app.wallet, project_id, reason="r")["refunded"]))
    )
    refunder.start()
    assert holding.wait(WAIT)

    queue, started, reached_check = FORK.Queue(), FORK.Event(), FORK.Event()
    child = FORK.Process(
        target=_child_generate, args=(queue, refund_app.service, project_id, started, reached_check)
    )
    child.start()
    assert started.wait(WAIT)
    # Exclusion: the other worker cannot reach its payment check while the refund holds the gate.
    assert not reached_check.wait(1.0)
    go.set()
    refunder.join(WAIT)
    outcome, provider_calls = queue.get(timeout=WAIT)
    child.join(WAIT)

    assert result == ["True"]
    assert (outcome, provider_calls) == ("payment_required", 0)
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins
    assert _evidence(project_id) == []

    calls: list[int] = []
    monkeypatch.setattr(refund_app.writer, "write_section", lambda **_k: calls.append(1))
    for stage in (
        refund_app.service.advance_writer,
        refund_app.service.run_blueprint,
        refund_app.service.merge_writer_draft,
        refund_app.service.run_formatting,
    ):
        with pytest.raises(PaymentRequiredError):
            stage(project_id)
    assert calls == []


def _child_advance(queue, barrier, service, project_id):
    outcome = "error"
    try:
        barrier.wait()
        service.advance_writer(project_id)
        outcome = "ok"
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {type(exc).__name__}: {exc}"
    finally:
        queue.put(outcome)
        queue.close()
        queue.join_thread()
        os._exit(0)


def test_scenario4_two_concurrent_generations_on_one_cycle(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    queue, barrier = FORK.Queue(), FORK.Barrier(2)
    procs = [FORK.Process(target=_child_advance, args=(queue, barrier, refund_app.service, project_id)) for _ in range(2)]
    for proc in procs:
        proc.start()
    outcomes = [queue.get(timeout=WAIT) for _ in procs]
    for proc in procs:
        proc.join(WAIT)

    assert outcomes == ["ok", "ok"]
    twin_id, _ = _started_writer(refund_app, owner)
    refund_app.service.advance_writer(twin_id)
    refund_app.service.advance_writer(twin_id)

    def shape(pid):
        session = _artifacts(refund_app, pid)["writer_session"]
        return [(s["id"], s["status"], bool(s["generated_text"].strip())) for s in session["sections"]]

    assert shape(project_id) == shape(twin_id)  # serialized exactly like two sequential requests
    cycle_id = _artifacts(refund_app, project_id)[PAYMENT_CYCLE_KEY]
    assert [(r["cycle_id"], r["operation"]) for r in _evidence(project_id)] == [(cycle_id, "writing")]
    writing = [op for op in _ops(project_id) if op["operation"] == "writing" and op["output_phase"]]
    assert [(op["status"], op["output_phase"]) for op in writing] == [("completed", "recorded")] * 2


def test_case_c_request_errors_stay_non_refundable_and_genuine_failures_still_refund(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _started_writer(refund_app, owner)
    with pytest.raises(StagePreconditionError):
        refund_app.service.revise_writer_section(project_id)
    assert _ops(project_id)[-1]["status"] == "rejected"
    assert PROCESSING_FAILURE_KEY not in _artifacts(refund_app, project_id)

    _fail_writer_via_route(refund_app, owner, project_id)
    assert _ops(project_id)[-1]["status"] == "failed"
    balance = refund_app.wallet.get_balance(owner["id"])
    res = _refund(_signed_in(_client(), owner), project_id)
    assert res.status_code == 200, res.get_data(as_text=True)
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins


def test_refund_from_inside_a_running_operation_is_refused(refund_app, monkeypatch):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    seen: list[str] = []
    inner = refund_app.writer.write_section

    def provider(**kwargs):
        try:
            refund_assignment(refund_app.service, refund_app.wallet, project_id, reason="nested")
            seen.append("ok")
        except RefundNotEligibleError as exc:
            seen.append(exc.code)
        return inner(**kwargs)

    monkeypatch.setattr(refund_app.writer, "write_section", provider)
    refund_app.service.advance_writer(project_id)
    assert seen == ["OPERATION_IN_PROGRESS"]
    with pytest.raises(LockBusyError):
        with payment_gate(project_id, root=refund_app.service.store.storage_root):
            with payment_gate(project_id, root=refund_app.service.store.storage_root, exclusive=True):
                pass


def _child_crash_while_persisting(service, project_id):
    payment_ledger.record_output = lambda *_a, **_k: os._exit(7)
    service.advance_writer(project_id)
    os._exit(0)


def _child_crash_in_provider(service, project_id):
    service.writer.writer.write_section = lambda **_k: os._exit(5)
    service.advance_writer(project_id)
    os._exit(0)


def test_case_d_scenario8_worker_dies_between_storing_text_and_evidence(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    empty_session = json.loads(json.dumps(_artifacts(refund_app, project_id)["writer_session"]))

    proc = FORK.Process(target=_child_crash_while_persisting, args=(refund_app.service, project_id))
    proc.start()
    proc.join(WAIT)

    assert proc.exitcode == 7
    assert has_generated_output(_artifacts(refund_app, project_id))  # text reached disk
    assert _evidence(project_id) == []
    crashed = [op for op in _ops(project_id) if op["output_phase"] == "persisting"]
    assert len(crashed) == 1 and crashed[0]["status"] == "started"
    # Worst case afterwards: a stale write hides the text and a real failure is recorded.
    _erase_output_from_json(refund_app, project_id, empty_session)
    _record_genuine_failure(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    _assert_refund_refused(refund_app, owner, project_id, "OPERATION_INTERRUPTED", balance)
    assert _artifacts(refund_app, project_id)["refund_review_required"]["reason"] == "operation_interrupted"
    admin = _admin_refund(refund_app, project_id, reason="support reviewed the interrupted run")
    assert admin.status_code == 200  # a human can still decide


def test_case_d_worker_dying_inside_the_ai_call_does_not_block_a_later_genuine_refund(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _started_writer(refund_app, owner)

    proc = FORK.Process(target=_child_crash_in_provider, args=(refund_app.service, project_id))
    proc.start()
    proc.join(WAIT)

    assert proc.exitcode == 5
    assert [op["status"] for op in _ops(project_id) if op["operation"] == "writing"][-1] == "started"
    assert not has_generated_output(_artifacts(refund_app, project_id)) and _evidence(project_id) == []
    _fail_writer_via_route(refund_app, owner, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])
    res = _refund(_signed_in(_client(), owner), project_id)
    assert res.status_code == 200, res.get_data(as_text=True)
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins


def _child_refund_barrier(queue, barrier, service, wallet, project_id):
    outcome = "error"
    try:
        barrier.wait()
        refund_assignment(service, wallet, project_id, reason="dup")
        outcome = "ok"
    except RefundNotEligibleError as exc:
        outcome = exc.code
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {type(exc).__name__}: {exc}"
    finally:
        queue.put(outcome)
        queue.close()
        queue.join_thread()
        os._exit(0)


def test_scenario9_duplicate_refunds_from_separate_processes(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])
    queue, barrier = FORK.Queue(), FORK.Barrier(6)
    procs = [
        FORK.Process(target=_child_refund_barrier, args=(queue, barrier, refund_app.service, refund_app.wallet, project_id))
        for _ in range(6)
    ]
    for proc in procs:
        proc.start()
    outcomes = [queue.get(timeout=WAIT) for _ in procs]
    for proc in procs:
        proc.join(WAIT)

    assert outcomes.count("ok") == 1 and set(outcomes) - {"ok"} == {"ALREADY_REFUNDED"}
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins
    assert [row["amount"] for row in _refund_rows(project_id)] == [coins]
    assert len(_artifacts(refund_app, project_id)["refund_history"]) == 1


# ------------------------------------------------------------------ legacy data


def test_scenario10_legacy_output_without_new_metadata_backfills_evidence(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    project = refund_app.service.store.require_project(project_id)
    session = json.loads(json.dumps(project.artifacts["writer_session"]))
    session["sections"][0].update(generated_text="Legacy paragraph written by an older build.", status="completed")
    project.artifacts["writer_session"] = session  # written directly, like an old deploy did
    project.artifacts.pop(WRITER_EXPECTED_SECTIONS_KEY, None)
    refund_app.service.store.save_project(project)
    assert _evidence(project_id) == []
    _record_genuine_failure(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    _assert_refund_refused(refund_app, owner, project_id, "OUTPUT_GENERATED", balance)
    assert [r["source"] for r in _evidence(project_id)] == ["json_backfill"]

    _erase_output_from_json(refund_app, project_id, None)  # later stale write
    _assert_refund_refused(refund_app, owner, project_id, "OUTPUT_GENERATED", balance)


def _make_cycle_untracked(project_id: str) -> None:
    with economy_db.connect() as conn:
        conn.execute("UPDATE assignment_payments SET output_tracking = 0 WHERE project_id = ?", (project_id,))


def test_scenario11_untracked_legacy_cycle_fails_closed(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _paid_project(refund_app, owner)
    _make_cycle_untracked(project_id)  # cycle opened before operations were journaled
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    _assert_refund_refused(refund_app, owner, project_id, "OUTPUT_STATE_UNKNOWN", balance)
    assert _artifacts(refund_app, project_id)["refund_review_required"]["reason"] == "output_state_unknown"
    admin = _admin_refund(refund_app, project_id, reason="support checked the history")
    assert admin.status_code == 200 and admin.get_json()["coins_refunded"] == coins


def test_scenario11_legacy_debit_before_cycles_fails_closed(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    refund_app.wallet.debit(owner["id"], 500, "assignment", ref_id=project_id)  # pre-cycle payment format
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    _assert_refund_refused(refund_app, owner, project_id, "OUTPUT_STATE_UNKNOWN", balance)


def test_migration_is_idempotent_and_marks_existing_cycles_untracked(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE assignment_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id TEXT NOT NULL UNIQUE,
            project_id TEXT NOT NULL, user_id INTEGER NOT NULL, method TEXT NOT NULL,
            coins INTEGER NOT NULL DEFAULT 0, debit_tx_id INTEGER, allowance_mode TEXT,
            allowance_period TEXT, status TEXT NOT NULL, refund_tx_id INTEGER,
            refunded_coins INTEGER, refund_kind TEXT, refund_reason TEXT, refund_admin_id INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), closed_at TEXT
        );
        INSERT INTO assignment_payments (cycle_id, project_id, user_id, method, coins, status)
        VALUES ('old-cycle', 'old-project', 1, 'coins', 100, 'active');
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(economy_db, "DB_PATH", db_path)

    economy_db.init_db()
    economy_db.init_db()

    assert payment_ledger.get_cycle("old-cycle")["output_tracking"] == 0
    assert payment_ledger.refund_blocker("old-project") == "OUTPUT_STATE_UNKNOWN"
    payment_ledger.record_output("old-project", "old-cycle", "writing", source="persisted")
    payment_ledger.record_output("old-project", "old-cycle", "writing", source="persisted")
    assert len(payment_ledger.output_evidence("old-project")) == 1
    assert payment_ledger.refund_blocker("old-project") == "OUTPUT_GENERATED"


# ------------------------------------------------------------------ 4. generated sections survive


def test_scenario3_blueprint_replacement_keeps_written_sections_and_evidence(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    refund_app.service.advance_writer(project_id)
    before = {s["id"]: s["generated_text"] for s in _artifacts(refund_app, project_id)["writer_session"]["sections"]}
    written = {k: v for k, v in before.items() if v.strip()}
    assert written

    refund_app.service.run_blueprint(project_id)  # new blueprint replaces the stored one
    session = _fresh_worker(refund_app).get_writer_session(project_id)

    after = {s.id: s.generated_text for s in session.sections}
    assert all(after.get(k) == v for k, v in written.items())
    assert refund_app.service.archived_writer_sections(project_id) == []
    _record_genuine_failure(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])
    _assert_refund_refused(refund_app, owner, project_id, "OUTPUT_GENERATED", balance)


def _replace_blueprint_ids(blueprint: dict, renamed: dict[str, str]) -> dict:
    out = json.loads(json.dumps(blueprint))
    out["id"] = f"{out['id']}-v2"
    for section in out.get("sections") or []:
        section["id"] = renamed.get(str(section.get("id")), section.get("id"))
    if out.get("writing_order"):
        out["writing_order"] = [renamed.get(str(item), item) for item in out["writing_order"]]
    return out


def test_unmapped_legacy_sections_are_quarantined_not_deleted(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    refund_app.service.advance_writer(project_id)
    stored = _artifacts(refund_app, project_id)["writer_session"]
    written = next(s for s in stored["sections"] if s["generated_text"].strip())
    # Legacy session (no recorded plan) whose blueprint was replaced and no longer has this section.
    project = refund_app.service.store.require_project(project_id)
    project.artifacts.pop(WRITER_EXPECTED_SECTIONS_KEY, None)
    project.artifacts["blueprint"] = _replace_blueprint_ids(project.artifacts["blueprint"], {written["id"]: "replacement"})
    for key in (OUTPUT_GENERATED_KEY, "output_generated_cycle_id"):
        project.artifacts.pop(key, None)
    refund_app.service.store.save_project(project)

    session = _fresh_worker(refund_app).get_writer_session(project_id)

    assert written["id"] not in [s.id for s in session.sections]
    archive = refund_app.service.archived_writer_sections(project_id)
    assert len(archive) == 1
    entry = archive[0]
    assert entry["section"]["id"] == written["id"]
    assert entry["section"]["generated_text"] == written["generated_text"]
    assert entry["section"]["completed_at"] == written["completed_at"]
    assert entry["writer_session_id"] == stored["id"] and entry["reason"] == "not_in_expected_sections"
    assert entry["payment_cycle_id"] == _artifacts(refund_app, project_id)[PAYMENT_CYCLE_KEY]
    assert {r["source"] for r in _evidence(project_id)} >= {"persisted"}

    # Quarantined text is not current: not served, and not merged into a draft.
    client = _signed_in(_client(), owner)
    payload = client.get(_url(project_id, "writer")).get_data(as_text=True)
    project_payload = client.get(_url(project_id)).get_data(as_text=True)
    assert written["generated_text"] not in payload and written["generated_text"] not in project_payload
    _erase_output_from_json(refund_app, project_id, _artifacts(refund_app, project_id)["writer_session"])
    _record_genuine_failure(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])
    _assert_refund_refused(refund_app, owner, project_id, "OUTPUT_GENERATED", balance)


def test_quarantine_of_legacy_text_records_evidence_when_none_existed(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    project = refund_app.service.store.require_project(project_id)
    session = json.loads(json.dumps(project.artifacts["writer_session"]))
    session["sections"][0].update(generated_text="Old text from an older build.", status="completed")
    project.artifacts["writer_session"] = session
    project.artifacts.pop(WRITER_EXPECTED_SECTIONS_KEY, None)
    project.artifacts["blueprint"] = _replace_blueprint_ids(
        project.artifacts["blueprint"], {session["sections"][0]["id"]: "replacement"}
    )
    refund_app.service.store.save_project(project)
    assert _evidence(project_id) == []

    _fresh_worker(refund_app).get_writer_session(project_id)

    assert [r["source"] for r in _evidence(project_id)] == ["archived_section"]
    assert refund_app.service.archived_writer_sections(project_id)[0]["section"]["generated_text"] == (
        "Old text from an older build."
    )


def test_client_snapshots_cannot_delete_historical_sections(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    refund_app.service.advance_writer(project_id)
    stored = _artifacts(refund_app, project_id)["writer_session"]
    texts = {s["id"]: s["generated_text"] for s in stored["sections"]}
    forged = json.loads(json.dumps(stored))
    forged["sections"] = []
    forged["completed_section_ids"] = []
    client = _signed_in(_client(), owner)

    client.post(_url(project_id, "writer/advance"), json={"writer_session": forged})
    client.post(_url(project_id, "writer/merge"), json={"writer_session": forged})

    after = {s["id"]: s["generated_text"] for s in _artifacts(refund_app, project_id)["writer_session"]["sections"]}
    assert set(texts) <= set(after)
    assert all(after[k] == v for k, v in texts.items() if v.strip())
    assert refund_app.service.archived_writer_sections(project_id) == []
    assert _evidence(project_id)


def test_normal_paid_writer_workflow_still_completes(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _started_writer(refund_app, owner)
    client = _signed_in(_client(), owner)
    ws = client.get(_url(project_id, "writer")).get_json()
    for _ in range(30):
        if all(s["status"] == "completed" for s in ws["sections"]):
            break
        res = client.post(_url(project_id, "writer/advance"), json={"writer_session": ws})
        assert res.status_code == 200, res.get_data(as_text=True)
        ws = res.get_json()
    merge = client.post(_url(project_id, "writer/merge"), json={"writer_session": ws})
    assert merge.status_code == 201, merge.get_data(as_text=True)
    assert {r["operation"] for r in _evidence(project_id)} >= {"writing", "merge"}
    assert all(op["status"] != "started" for op in _ops(project_id))
