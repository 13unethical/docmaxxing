"""Writer sessions stay server-owned, only real execution failures are refundable, and every
payment cycle refunds exactly what it charged, once."""

from __future__ import annotations

import json
import multiprocessing
import os
from types import SimpleNamespace

import pytest

from services.assignment_project.refunds import refund_assignment
from services.assignment_project.service import (
    OUTPUT_GENERATED_KEY,
    PAYMENT_CYCLE_KEY,
    PROCESSING_FAILURE_KEY,
    PaymentRequiredError,
    RefundNotEligibleError,
    StagePreconditionError,
)
from services.economy import assignment_payments as payment_ledger
from services.economy import db as economy_db
from services.economy.plans import activate_plan
from services.reviewer_engine.models import ReviewReport
from tests.assignment_helpers import current_quote_id
from tests.test_security_paid_pipelines import (  # noqa: F401  (economy is a fixture)
    _client,
    _priced_project,
    _signed_in,
    _user,
    economy,
)
from tests.test_security_refund_integrity import (  # noqa: F401  (refund_app is a fixture)
    _admin_refund,
    _fail_writer_via_route,
    _plan_and_blueprint,
    _refund,
    _refund_rows,
    _url,
    _write_everything,
    refund_app,
)

FORK = multiprocessing.get_context("fork")


def _artifacts(env, project_id: str) -> dict:
    return env.service.store.require_project(project_id).artifacts


def _confirm(env, owner, *, topup: int = 1_000_000, project_id: str | None = None):
    """Priced project paid through the real confirm route; returns (project_id, response body)."""
    if project_id is None:
        project_id = _priced_project(env.service, user_id=str(owner["id"]))
    if topup:
        env.wallet.credit(owner["id"], topup, "test_topup")
    res = _signed_in(_client(), owner).post(
        _url(project_id, "confirm-payment"), json={"quote_id": current_quote_id(env.service, project_id)}
    )
    assert res.status_code == 200, res.get_data(as_text=True)
    return project_id, res.get_json()


def _debit_rows(project_id: str) -> list[dict]:
    with economy_db.connect() as conn:
        rows = conn.execute(
            "SELECT amount, ref_id FROM transactions WHERE kind = 'debit' AND feature = 'assignment' AND ref_id LIKE ?",
            (f"assignment-payment:{project_id}:%",),
        ).fetchall()
    return [dict(row) for row in rows]


def _plan_used(user_id: int) -> int:
    with economy_db.connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(used), 0) AS used FROM plan_usage WHERE user_id = ? AND feature = 'assignment'",
            (int(user_id),),
        ).fetchone()
    return int(row["used"])


def _forged_session(server_session: dict) -> dict:
    forged = json.loads(json.dumps(server_session))
    fake = dict(forged["sections"][0])
    fake.update(id="injected-fake", title="Injected Fake", status="pending", generated_text="", word_count=0)
    forged["sections"].append(fake)
    forged["updated_at"] = "2999-01-01T00:00:00+00:00"
    forged["status"] = "active"
    forged["progress"] = 10
    return forged


# ------------------------------------------------------------ C1: server-owned writer session


def test_c1_poc_forged_session_cannot_hide_output_or_buy_a_refund(refund_app):
    owner = _user("owner@example.com")
    project_id, paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    client = _signed_in(_client(), owner)
    refund_app.service.start_writer(project_id)
    for _ in range(30):
        session = refund_app.service.get_writer_session(project_id)
        if all(s.status.value == "completed" for s in session.sections):
            break
        refund_app.service.advance_writer(project_id)

    legit = client.get(_url(project_id, "writer")).get_json()
    real_ids = [s["id"] for s in legit["sections"]]
    assert all(s["generated_text"].strip() for s in legit["sections"])
    forged = _forged_session(legit)

    assert client.post(_url(project_id, "writer/advance"), json={"writer_session": forged}).status_code == 200
    stored = _artifacts(refund_app, project_id)["writer_session"]
    assert [s["id"] for s in stored["sections"]] == real_ids
    assert stored["updated_at"] != forged["updated_at"]

    merge = client.post(_url(project_id, "writer/merge"), json={"writer_session": forged})
    assert merge.status_code == 201, merge.get_data(as_text=True)
    artifacts = _artifacts(refund_app, project_id)
    assert PROCESSING_FAILURE_KEY not in artifacts
    assert artifacts[OUTPUT_GENERATED_KEY]

    balance = refund_app.wallet.get_balance(owner["id"])
    res = _refund(client, project_id)
    assert res.status_code == 400 and res.get_json()["reason"] == "OUTPUT_GENERATED"
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    assert _refund_rows(project_id) == []
    assert paid["coins_charged"] == 3000


def test_injected_section_already_on_disk_is_dropped_and_output_detected(refund_app):
    owner = _user("owner@example.com")
    project_id, _paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    refund_app.service.start_writer(project_id)
    refund_app.service.advance_writer(project_id)
    # Snapshot persisted by an older build: a fake pending section and no output marker.
    project = refund_app.service.store.require_project(project_id)
    project.artifacts["writer_session"] = _forged_session(project.artifacts["writer_session"])
    project.artifacts.pop(OUTPUT_GENERATED_KEY, None)
    refund_app.service.store.save_project(project)

    session = refund_app.service.get_writer_session(project_id)

    assert "injected-fake" not in [s.id for s in session.sections]
    artifacts = _artifacts(refund_app, project_id)
    assert "injected-fake" not in [s["id"] for s in artifacts["writer_session"]["sections"]]
    assert artifacts[OUTPUT_GENERATED_KEY]


def test_client_cannot_complete_sections_or_rewrite_text(refund_app):
    owner = _user("owner@example.com")
    project_id, _paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    client = _signed_in(_client(), owner)
    server = refund_app.service.start_writer(project_id).to_dict()
    forged = json.loads(json.dumps(server))
    for section in forged["sections"]:
        section.update(status="completed", generated_text="client text")
    forged.update(status="completed", progress=100, project_id="someone-else")

    res = client.post(_url(project_id, "writer/merge"), json={"writer_session": forged})

    assert res.status_code == 400
    stored = _artifacts(refund_app, project_id)["writer_session"]
    assert all(s["status"] != "completed" and "client text" not in (s["generated_text"] or "") for s in stored["sections"])
    assert PROCESSING_FAILURE_KEY not in _artifacts(refund_app, project_id)


def test_ui_echo_sync_still_writes_and_merges(refund_app):
    owner = _user("owner@example.com")
    project_id, _paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    client = _signed_in(_client(), owner)
    ws = client.post(_url(project_id, "writer/start")).get_json()
    for _ in range(30):
        if all(s["status"] == "completed" for s in ws["sections"]):
            break
        res = client.post(_url(project_id, "writer/advance"), json={"writer_session": ws})
        assert res.status_code == 200, res.get_data(as_text=True)
        ws = res.get_json()

    merge = client.post(_url(project_id, "writer/merge"), json={"writer_session": ws})

    assert merge.status_code == 201
    texts = [s["generated_text"].strip() for s in ws["sections"]]
    draft = merge.get_json()["content"]
    assert all(text.splitlines()[0] in draft for text in texts if text)


def test_partial_output_blocks_automatic_refund_even_after_a_real_failure(refund_app):
    owner = _user("owner@example.com")
    project_id, _paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    refund_app.service.start_writer(project_id)
    refund_app.service.advance_writer(project_id)
    artifacts = _artifacts(refund_app, project_id)
    assert artifacts[OUTPUT_GENERATED_KEY]
    assert artifacts["output_generated_cycle_id"] == artifacts[PAYMENT_CYCLE_KEY]

    def provider_down(**_kwargs):
        raise ValueError("Claude API error: overloaded")

    refund_app.service.blueprint.build_blueprint = provider_down
    with pytest.raises(ValueError):
        refund_app.service.run_blueprint(project_id)
    failure = _artifacts(refund_app, project_id)[PROCESSING_FAILURE_KEY]
    assert failure["stage"] == "blueprint" and failure["client_seeded"] is False

    refused = _refund(_signed_in(_client(), owner), project_id)
    assert refused.status_code == 400 and refused.get_json()["reason"] == "OUTPUT_GENERATED"


# ------------------------------------------------------------ C2: failure classification


def _paid_with_plan(env, owner) -> str:
    project_id, _paid = _confirm(env, owner)
    _plan_and_blueprint(env, project_id)
    return project_id


def _no_failure(env, project_id: str) -> bool:
    return PROCESSING_FAILURE_KEY not in _artifacts(env, project_id)


def test_missing_research_plan_is_a_precondition_not_a_failure(refund_app):
    owner = _user("owner@example.com")
    project_id, _paid = _confirm(refund_app, owner)
    with pytest.raises(StagePreconditionError):
        refund_app.service.run_blueprint(project_id)
    assert _no_failure(refund_app, project_id)


def test_premature_merge_is_a_precondition_not_a_failure(refund_app):
    owner = _user("owner@example.com")
    project_id = _paid_with_plan(refund_app, owner)
    refund_app.service.start_writer(project_id)
    res = _signed_in(_client(), owner).post(_url(project_id, "writer/merge"), json={})
    assert res.status_code == 400
    assert _no_failure(refund_app, project_id)
    assert _refund(_signed_in(_client(), owner), project_id).get_json()["reason"] == "NO_RECORDED_FAILURE"


def test_maximum_revisions_is_a_precondition_not_a_failure(refund_app, monkeypatch):
    owner = _user("owner@example.com")
    project_id = _paid_with_plan(refund_app, owner)
    _write_everything(refund_app, project_id)
    refund_app.service._persist_review_report(
        project_id,
        ReviewReport.from_dict({"id": "rr-1", "passed": False, "issues": [{"issue_id": "i1", "description": "x"}]}),
    )
    monkeypatch.setattr(
        refund_app.service.revision,
        "get_history_or_empty",
        lambda _pid: SimpleNamespace(revision_attempts=3, needs_manual_review=False),
    )
    with pytest.raises(StagePreconditionError):
        refund_app.service.run_revision(project_id)
    assert _no_failure(refund_app, project_id)


def test_invalid_transitions_and_missing_artifacts_are_not_failures(refund_app):
    owner = _user("owner@example.com")
    project_id, _paid = _confirm(refund_app, owner)
    client = _signed_in(_client(), owner)
    with pytest.raises(KeyError):
        refund_app.service.start_writer(project_id)  # no research plan / blueprint yet
    with pytest.raises(KeyError):
        refund_app.service.run_citation_generation(project_id)  # no draft yet
    client.post(_url(project_id, "stages/writing/fail"), json={"error": "provider exploded"})
    client.post(_url(project_id, "stages/humanization/fail"), json={"error": "timeout"})
    assert _no_failure(refund_app, project_id)
    assert _refund(client, project_id).get_json()["reason"] == "NO_RECORDED_FAILURE"


def test_authorization_and_payment_errors_are_not_failures(refund_app):
    owner = _user("owner@example.com")
    project_id = _paid_with_plan(refund_app, owner)
    refund_app.service.start_writer(project_id)
    intruder = _signed_in(_client(), _user("intruder@example.com"))
    refund_app.writer.fail = True
    assert intruder.post(_url(project_id, "writer/advance"), json={}).status_code == 403
    refund_app.writer.fail = False
    unpaid = _priced_project(refund_app.service, user_id=str(owner["id"]))
    with pytest.raises(PaymentRequiredError):
        refund_app.service.advance_writer(unpaid)
    assert _no_failure(refund_app, project_id) and _no_failure(refund_app, unpaid)


def test_revise_request_for_a_section_not_awaiting_revision_is_not_a_failure(refund_app):
    owner = _user("owner@example.com")
    project_id = _paid_with_plan(refund_app, owner)
    session = refund_app.service.start_writer(project_id)
    client = _signed_in(_client(), owner)
    for body in ({}, {"section_id": session.sections[0].id}, {"section_id": "no-such-section"}):
        res = client.post(_url(project_id, "writer/revise"), json=body)
        assert res.status_code == 400, (body, res.get_data(as_text=True))
    assert _no_failure(refund_app, project_id)
    assert _refund(client, project_id).get_json()["reason"] == "NO_RECORDED_FAILURE"


def test_generic_exception_outside_the_engine_call_is_not_evidence(refund_app, monkeypatch):
    owner = _user("owner@example.com")
    project_id = _paid_with_plan(refund_app, owner)

    def broken_load(_project_id, **_kwargs):
        raise RuntimeError("bug in our own code")

    monkeypatch.setattr(refund_app.service, "_load_research_plan", broken_load)
    with pytest.raises(RuntimeError):
        refund_app.service.run_blueprint(project_id)
    assert _no_failure(refund_app, project_id)


def test_only_a_provider_failure_inside_the_execution_boundary_qualifies(refund_app):
    owner = _user("owner@example.com")
    project_id, paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    artifacts = _artifacts(refund_app, project_id)
    failure = artifacts[PROCESSING_FAILURE_KEY]
    assert failure["classification"] == "execution" and failure["client_seeded"] is False
    assert failure["payment_cycle_id"] == artifacts[PAYMENT_CYCLE_KEY]

    res = _refund(_signed_in(_client(), owner), project_id)
    assert res.status_code == 200 and res.get_json()["coins_refunded"] == paid["coins_charged"]


@pytest.mark.parametrize(
    "tamper, reason",
    [
        (lambda f, a: f.pop("classification"), "NO_RECORDED_FAILURE"),
        (lambda f, a: f.update(payment_cycle_id="0" * 32), "NO_RECORDED_FAILURE"),
        (lambda f, a: f.update(client_seeded=True), "CLIENT_INPUT"),
    ],
    ids=["unclassified-legacy-record", "other-cycle", "client-seeded"],
)
def test_failure_records_from_other_cycles_or_unclassified_do_not_qualify(refund_app, tamper, reason):
    owner = _user("owner@example.com")
    project_id, _paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    project = refund_app.service.store.require_project(project_id)
    tamper(project.artifacts[PROCESSING_FAILURE_KEY], project.artifacts)
    refund_app.service.store.save_project(project)
    res = _refund(_signed_in(_client(), owner), project_id)
    assert res.status_code == 400 and res.get_json()["reason"] == reason


def test_client_research_plan_failure_is_not_trusted(refund_app):
    owner = _user("owner@example.com")
    project_id, _paid = _confirm(refund_app, owner)
    plan = {"id": "plan-client", "assignment_topic": "Mine", "section_list": []}

    def failing_blueprint(**_kwargs):
        raise ValueError("Claude API error: overloaded")

    refund_app.service.blueprint.build_blueprint = failing_blueprint
    with pytest.raises(ValueError):
        refund_app.service.run_blueprint(project_id, research_plan=plan)
    failure = _artifacts(refund_app, project_id)[PROCESSING_FAILURE_KEY]
    assert failure["client_seeded"] is True
    res = _refund(_signed_in(_client(), owner), project_id)
    assert res.status_code == 400 and res.get_json()["reason"] == "CLIENT_INPUT"


# ------------------------------------------------------------ payment cycles and amounts


def test_cycle_debits_and_refunds_the_exact_amount(refund_app):
    owner = _user("owner@example.com")
    before = refund_app.wallet.get_balance(owner["id"]) + 1_000_000
    project_id, paid = _confirm(refund_app, owner, topup=1_000_000)
    artifacts = _artifacts(refund_app, project_id)
    cycle = payment_ledger.get_cycle(artifacts[PAYMENT_CYCLE_KEY])
    assert paid["coins_charged"] == 3000 and cycle["coins"] == 3000 and cycle["method"] == "coins"
    assert refund_app.wallet.get_balance(owner["id"]) == before - 3000
    assert _debit_rows(project_id) == [{"amount": 3000, "ref_id": payment_ledger.payment_ref(project_id, cycle["cycle_id"])}]

    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    res = _refund(_signed_in(_client(), owner), project_id)

    assert res.status_code == 200 and res.get_json()["coins_refunded"] == 3000
    assert refund_app.wallet.get_balance(owner["id"]) == before
    closed = payment_ledger.get_cycle(cycle["cycle_id"])
    assert closed["status"] == "refunded" and closed["refunded_coins"] == 3000 and closed["refund_tx_id"]


def test_pro_discount_is_charged_and_refunded_from_the_ledger(refund_app):
    owner = _user("pro@example.com")
    with economy_db.connect() as conn:
        conn.execute("UPDATE users SET is_pro = 1 WHERE id = ?", (owner["id"],))
    before = refund_app.wallet.get_balance(owner["id"]) + 1_000_000
    project_id, paid = _confirm(refund_app, owner, topup=1_000_000)
    assert paid["coins_charged"] == 2700
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)

    res = _refund(_signed_in(_client(), owner), project_id)

    assert res.get_json()["coins_refunded"] == 2700
    assert refund_app.wallet.get_balance(owner["id"]) == before


def test_free_allowance_cycle_then_coin_cycle_refund_what_each_used(refund_app):
    owner = _user("planner@example.com")
    activate_plan(owner["id"], "basic")  # one free assignment per pass
    refund_app.wallet.credit(owner["id"], 1_000_000, "test_topup")
    start = refund_app.wallet.get_balance(owner["id"])

    project_id, first = _confirm(refund_app, owner, topup=0)
    assert first["coins_charged"] == 0 and _artifacts(refund_app, project_id)["plan_free_paper"] is True
    assert _plan_used(owner["id"]) == 1
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    refunded = _refund(_signed_in(_client(), owner), project_id)
    assert refunded.status_code == 200 and refunded.get_json()["coins_refunded"] == 0
    assert _plan_used(owner["id"]) == 0

    other_id, other = _confirm(refund_app, owner, topup=0)  # takes the allowance back
    assert other["coins_charged"] == 0 and _plan_used(owner["id"]) == 1

    _pid, second = _confirm(refund_app, owner, topup=0, project_id=project_id)
    artifacts = _artifacts(refund_app, project_id)
    assert second["coins_charged"] == 3000 and "plan_free_paper" not in artifacts
    assert refund_app.wallet.get_balance(owner["id"]) == start - 3000
    _fail_writer_via_route(refund_app, owner, project_id)
    again = _refund(_signed_in(_client(), owner), project_id)

    assert again.status_code == 200 and again.get_json()["coins_refunded"] == 3000
    assert refund_app.wallet.get_balance(owner["id"]) == start
    assert _plan_used(owner["id"]) == 1  # the other project's allowance is untouched
    assert _artifacts(refund_app, other_id)["payment_confirmed"] is True


def test_legacy_payment_without_cycle_goes_to_admin_review(refund_app):
    owner = _user("owner@example.com")
    project_id = _priced_project(refund_app.service, user_id=str(owner["id"]))
    refund_app.service.confirm_payment(project_id, quote_id=current_quote_id(refund_app.service, project_id))
    project = refund_app.service.store.require_project(project_id)
    project.artifacts["coins_charged"] = 50_000  # untrusted historical value
    refund_app.service.store.save_project(project)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    res = _refund(_signed_in(_client(), owner), project_id)
    admin = _admin_refund(refund_app, project_id)

    assert res.status_code == 400 and res.get_json()["reason"] == "LEGACY_PAYMENT_REVIEW"
    assert admin.status_code == 400 and admin.get_json()["reason"] == "LEGACY_PAYMENT_REVIEW"
    assert _artifacts(refund_app, project_id)["refund_review_required"]
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    assert _refund_rows(project_id) == []


def test_repayment_opens_a_new_cycle_and_keeps_history(refund_app):
    owner = _user("owner@example.com")
    project_id, _first = _confirm(refund_app, owner)
    first_cycle = _artifacts(refund_app, project_id)[PAYMENT_CYCLE_KEY]
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    assert _refund(_signed_in(_client(), owner), project_id).status_code == 200

    _pid, second = _confirm(refund_app, owner, topup=0, project_id=project_id)

    artifacts = _artifacts(refund_app, project_id)
    assert artifacts[PAYMENT_CYCLE_KEY] != first_cycle and second["coins_charged"] == 3000
    assert [c["cycle_id"] for c in artifacts["payment_cycles"]] == [first_cycle, artifacts[PAYMENT_CYCLE_KEY]]
    assert artifacts["payment_cycles"][0]["refunded_at"] and "refunded_at" not in artifacts["payment_cycles"][1]
    assert len(artifacts["refund_history"]) == 1 and "payment_refunded" not in artifacts
    assert PROCESSING_FAILURE_KEY not in artifacts
    assert payment_ledger.get_cycle(first_cycle)["status"] == "refunded"


def test_duplicate_refund_never_credits_twice(refund_app):
    owner = _user("owner@example.com")
    project_id, paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    cycle_id = _artifacts(refund_app, project_id)[PAYMENT_CYCLE_KEY]
    client = _signed_in(_client(), owner)
    assert _refund(client, project_id).status_code == 200
    balance = refund_app.wallet.get_balance(owner["id"])

    assert _refund(client, project_id).status_code == 409
    replay = payment_ledger.close_cycle(project_id, cycle_id, user_id=owner["id"], kind="failure", reason="replay")
    assert replay["already_closed"] is True
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    assert [row["amount"] for row in _refund_rows(project_id)] == [paid["coins_charged"]]


def test_wrong_or_foreign_cycle_id_is_refused(refund_app):
    owner = _user("owner@example.com")
    project_id, _paid = _confirm(refund_app, owner)
    other_id, _other = _confirm(refund_app, owner, topup=0)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    project = refund_app.service.store.require_project(project_id)
    project.artifacts[PAYMENT_CYCLE_KEY] = _artifacts(refund_app, other_id)[PAYMENT_CYCLE_KEY]
    project.artifacts[PROCESSING_FAILURE_KEY]["payment_cycle_id"] = project.artifacts[PAYMENT_CYCLE_KEY]
    refund_app.service.store.save_project(project)
    balance = refund_app.wallet.get_balance(owner["id"])

    res = _refund(_signed_in(_client(), owner), project_id)

    # The project guard already fails closed when the tampered cycle can't be reconciled.
    body = res.get_json()
    assert (res.status_code == 400 and body["reason"] in {"PAYMENT_RECORD_MISSING", "NO_RECORDED_FAILURE"}) or (
        res.status_code == 503 and body["error"] == "PROJECT_UNAVAILABLE"
    )
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    with pytest.raises(PaymentRequiredError):
        refund_app.service.advance_writer(project_id)
    assert payment_ledger.get_cycle(_artifacts(refund_app, other_id)[PAYMENT_CYCLE_KEY])["status"] == "active"


def test_confirming_a_paid_project_again_charges_nothing(refund_app):
    owner = _user("owner@example.com")
    project_id, paid = _confirm(refund_app, owner)
    balance = refund_app.wallet.get_balance(owner["id"])
    client = _signed_in(_client(), owner)
    paid_quote = _artifacts(refund_app, project_id)["payment_quote_id"]
    again = client.post(_url(project_id, "confirm-payment"), json={"quote_id": paid_quote})
    assert again.status_code == 200
    # A replay reports what the payment cost, and that nothing was charged now.
    assert again.get_json()["coins_charged"] == paid["coins_charged"] > 0
    assert again.get_json()["charged_now"] == 0 and again.get_json()["idempotent_replay"] is True
    unnamed = client.post(_url(project_id, "confirm-payment"), json={})
    assert unnamed.status_code == 409 and unnamed.get_json()["error"] == "QUOTE_REQUIRED"
    assert unnamed.get_json()["payment_confirmed"] is True
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    assert len(_debit_rows(project_id)) == 1


def test_failed_confirmation_voids_its_cycle(refund_app, monkeypatch):
    owner = _user("owner@example.com")
    project_id = _priced_project(refund_app.service, user_id=str(owner["id"]))
    refund_app.wallet.credit(owner["id"], 1_000_000, "test_topup")
    balance = refund_app.wallet.get_balance(owner["id"])

    def broken_confirm(_project_id, *, cycle=None, quote_id=None):
        raise ValueError("pipeline unavailable")

    quote_id = current_quote_id(refund_app.service, project_id)
    monkeypatch.setattr(refund_app.service, "confirm_payment", broken_confirm)
    res = _signed_in(_client(), owner).post(_url(project_id, "confirm-payment"), json={"quote_id": quote_id})

    assert res.status_code == 400
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    assert payment_ledger.active_cycle(project_id) is None
    assert _artifacts(refund_app, project_id).get("payment_confirmed") is not True


# ------------------------------------------------------------ concurrency and recovery


def _run_children(target, count: int, *args) -> list:
    queue = FORK.Queue()
    barrier = FORK.Barrier(count)
    procs = [FORK.Process(target=target, args=(queue, barrier, *args)) for _ in range(count)]
    for proc in procs:
        proc.start()
    results = [queue.get(timeout=60) for _ in procs]
    for proc in procs:
        proc.join(timeout=60)
    return results


def _child_confirm(queue, barrier, owner, project_id, quote_id):
    status = "error"
    try:
        client = _signed_in(_client(), owner)
        barrier.wait()
        status = client.post(_url(project_id, "confirm-payment"), json={"quote_id": quote_id}).status_code
    except BaseException as exc:  # noqa: BLE001
        status = f"error: {type(exc).__name__}: {exc}"
    finally:
        queue.put(status)
        queue.close()
        queue.join_thread()
        os._exit(0)


def test_parallel_confirmations_in_separate_processes_charge_once(refund_app):
    owner = _user("owner@example.com")
    project_id = _priced_project(refund_app.service, user_id=str(owner["id"]))
    refund_app.wallet.credit(owner["id"], 1_000_000, "test_topup")
    balance = refund_app.wallet.get_balance(owner["id"])

    statuses = _run_children(_child_confirm, 6, owner, project_id, current_quote_id(refund_app.service, project_id))

    assert statuses == [200] * 6
    debits = _debit_rows(project_id)
    assert len(debits) == 1
    assert refund_app.wallet.get_balance(owner["id"]) == balance - debits[0]["amount"]
    with economy_db.connect() as conn:
        cycles = conn.execute("SELECT status FROM assignment_payments WHERE project_id = ?", (project_id,)).fetchall()
    assert [row["status"] for row in cycles] == ["active"]
    assert _artifacts(refund_app, project_id)[PAYMENT_CYCLE_KEY]


def _child_refund(queue, barrier, service, wallet, project_id):
    outcome = "error"
    try:
        barrier.wait()
        refund_assignment(service, wallet, project_id, reason="race")
        outcome = "ok"
    except RefundNotEligibleError as exc:
        outcome = exc.code
    finally:
        queue.put(outcome)
        queue.close()
        queue.join_thread()
        os._exit(0)


def test_parallel_refunds_in_separate_processes_refund_once(refund_app):
    owner = _user("owner@example.com")
    project_id, paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    outcomes = _run_children(_child_refund, 6, refund_app.service, refund_app.wallet, project_id)

    assert outcomes.count("ok") == 1 and set(outcomes) - {"ok"} <= {"ALREADY_REFUNDED"}
    assert refund_app.wallet.get_balance(owner["id"]) == balance + paid["coins_charged"]
    assert len(_refund_rows(project_id)) == 1
    assert len(_artifacts(refund_app, project_id)["refund_history"]) == 1


def _child_crash_after_ledger(service, wallet, project_id):
    service.mark_assignment_refunded = lambda *_a, **_k: os._exit(3)
    refund_assignment(service, wallet, project_id, reason="crash")
    os._exit(0)


def test_crash_between_ledger_refund_and_project_update_is_recovered(refund_app):
    owner = _user("owner@example.com")
    project_id, paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    proc = FORK.Process(target=_child_crash_after_ledger, args=(refund_app.service, refund_app.wallet, project_id))
    proc.start()
    proc.join(timeout=60)
    assert proc.exitcode == 3
    assert refund_app.wallet.get_balance(owner["id"]) == balance + paid["coins_charged"]
    assert _artifacts(refund_app, project_id)["payment_confirmed"] is True  # JSON never marked

    refund_app.writer.fail = True  # any AI call would raise RuntimeError, not PaymentRequiredError
    with pytest.raises(PaymentRequiredError):
        refund_app.service.advance_writer(project_id)
    refund_app.writer.fail = False

    artifacts = _artifacts(refund_app, project_id)
    assert artifacts["payment_refunded"] is True and artifacts["payment_confirmed"] is False
    assert artifacts["refund_history"][-1]["kind"] == "reconciled"
    assert _refund(_signed_in(_client(), owner), project_id).status_code == 409
    assert refund_app.wallet.get_balance(owner["id"]) == balance + paid["coins_charged"]
    assert len(_refund_rows(project_id)) == 1


def test_no_generation_once_the_ledger_shows_a_refund(refund_app):
    owner = _user("owner@example.com")
    project_id, _paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    refund_app.service.start_writer(project_id)
    cycle_id = _artifacts(refund_app, project_id)[PAYMENT_CYCLE_KEY]
    payment_ledger.close_cycle(project_id, cycle_id, user_id=owner["id"], kind="admin", reason="out of band")

    refund_app.writer.fail = True
    for call in (
        lambda: refund_app.service.advance_writer(project_id),
        lambda: refund_app.service.run_blueprint(project_id),
        lambda: refund_app.service.merge_writer_draft(project_id),
    ):
        with pytest.raises(PaymentRequiredError):
            call()
    refund_app.writer.fail = False
    assert _artifacts(refund_app, project_id)["payment_refunded"] is True


def test_refund_row_without_closed_cycle_is_reconciled_before_repayment(refund_app):
    owner = _user("owner@example.com")
    project_id, paid = _confirm(refund_app, owner)
    cycle_id = _artifacts(refund_app, project_id)[PAYMENT_CYCLE_KEY]
    refund_app.wallet.refund_once(
        owner["id"], paid["coins_charged"], "assignment", ref_id=payment_ledger.refund_ref(project_id, cycle_id)
    )
    balance = refund_app.wallet.get_balance(owner["id"])

    _pid, second = _confirm(refund_app, owner, topup=0, project_id=project_id)

    assert payment_ledger.get_cycle(cycle_id)["status"] == "refunded"
    assert second["coins_charged"] == 3000
    assert _artifacts(refund_app, project_id)[PAYMENT_CYCLE_KEY] != cycle_id
    assert refund_app.wallet.get_balance(owner["id"]) == balance - 3000
    assert len(_refund_rows(project_id)) == 1


def test_ledger_outage_fails_paid_stages_closed(refund_app, monkeypatch):
    import sqlite3

    owner = _user("owner@example.com")
    project_id = _paid_with_plan(refund_app, owner)
    refund_app.service.start_writer(project_id)

    def down(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(payment_ledger, "get_cycle", down)
    with pytest.raises(PaymentRequiredError):
        refund_app.service.advance_writer(project_id)


# ------------------------------------------------------------ existing behaviour


def test_legitimate_paid_assignment_runs_end_to_end(refund_app):
    owner = _user("owner@example.com")
    project_id, _paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _write_everything(refund_app, project_id)
    draft = refund_app.service.get_draft(project_id)
    artifacts = _artifacts(refund_app, project_id)
    assert draft.content.strip() and artifacts[OUTPUT_GENERATED_KEY]
    assert PROCESSING_FAILURE_KEY not in artifacts and artifacts["payment_confirmed"] is True


def test_admin_refund_after_output_returns_the_exact_debit(refund_app):
    owner = _user("owner@example.com")
    project_id, paid = _confirm(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _write_everything(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    res = _admin_refund(refund_app, project_id)

    assert res.status_code == 200 and res.get_json()["coins_refunded"] == paid["coins_charged"]
    assert refund_app.wallet.get_balance(owner["id"]) == balance + paid["coins_charged"]
    cycle = payment_ledger.get_cycle(_artifacts(refund_app, project_id)[PAYMENT_CYCLE_KEY])
    assert cycle["status"] == "refunded" and cycle["refund_kind"] == "admin" and cycle["refund_admin_id"]
