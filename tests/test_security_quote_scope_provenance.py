"""Mandatory quote confirmation, post-submission scope protection and Research Plan provenance.

Every confirmation names the quote the student accepted; the revision chat stays inside the paid
scope and its round limit across workers; a plan the student touched never becomes refund
evidence, whichever worker runs it. Providers and payments are fakes; nothing leaves the machine.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from pathlib import Path

import pytest

from services.assignment_project.models import Project
from services.assignment_project.service import (
    BLUEPRINT_WORD_RATIO,
    BLUEPRINT_WORD_SLACK,
    MAX_CLIENT_REVISION_ROUNDS,
    PAYMENT_QUOTE_KEY,
    PROCESSING_FAILURE_KEY,
    RESEARCH_PLAN_SOURCE_KEY,
    ResearchPlanChangedError,
)
from services.economy import assignment_entitlements as entitlements
from services.economy import assignment_payments as payment_ledger
from services.economy import db as economy_db
from services.economy.referral import apply_pro_discount
from services.writer_engine.models import Draft, count_words
from tests.test_security_paid_pipelines import _client, _signed_in, _user, economy  # noqa: F401
from tests.test_security_payment_scope_integrity import (  # noqa: F401
    FORK,
    WAIT,
    _child_exit,
    _cycles,
    _debits,
    _disk,
    _EditableResearch,
    _fair_coins,
    _fresh_worker,
    _owner,
    _paid,
    _priced,
    _quote,
    _url,
    env,
)
from tests.test_security_refund_integrity import _auto_refund_as

REPO = Path(__file__).resolve().parents[1]
PAID_WORDS = 500  # the env analyzer's default volume
CAP = int(PAID_WORDS * BLUEPRINT_WORD_RATIO) + BLUEPRINT_WORD_SLACK


# ------------------------------------------------------------------ helpers and traps


@pytest.fixture()
def charges(monkeypatch):
    """Payment trap: every attempt to open a payment cycle (the only debit path) is recorded."""
    calls: list[str] = []
    real = payment_ledger.open_cycle

    def trapped(user_id, project_id, **kwargs):
        calls.append(project_id)
        return real(user_id, project_id, **kwargs)

    monkeypatch.setattr(payment_ledger, "open_cycle", trapped)
    return calls


def _confirm(client, pid, body=..., **kwargs):
    if body is ...:
        return client.post(_url(pid, "confirm-payment"), **kwargs)
    return client.post(_url(pid, "confirm-payment"), json=body, **kwargs)


def _assert_nothing_charged(env, owner, pid, balance):
    assert env.wallet.get_balance(owner["id"]) == balance
    assert _debits(pid) == [] and _cycles(pid) == []
    assert env.service.store.require_project(pid).artifacts.get("payment_confirmed") is not True


def _set_pro(user, on=True):
    with economy_db.connect() as conn:
        conn.execute("UPDATE users SET is_pro = ? WHERE id = ?", (1 if on else 0, user["id"]))


def _admin():
    return _signed_in(_client(), _user(f"admin-{uuid.uuid4().hex[:8]}@example.com", admin=True))


def _refund_rows(pid) -> list[int]:
    with economy_db.connect() as conn:
        rows = conn.execute(
            "SELECT amount FROM transactions WHERE kind = 'refund' AND feature = 'assignment' AND ref_id LIKE ?",
            (f"assignment-refund:{pid}:%",),
        ).fetchall()
    return [int(r["amount"]) for r in rows]


def _doc(words: int) -> str:
    """Markdown draft with two headings and exactly ``words`` words (headings included)."""
    body = words - 2
    return "## Introduction\n" + "alpha " * (body // 2) + "\n## Conclusion\n" + "omega " * (body - body // 2)


def _seed_draft(env, pid, words) -> str:
    content = _doc(words)
    assert count_words(content) == words
    env.service._persist_draft(pid, Draft(id=str(uuid.uuid4()), project_id=pid, session_id="s",
                                          title="T", content=content, total_words=words))
    return content


def _chat_provider(env, monkeypatch, *, words=None, fail=False, log=None, delay=0.0):
    """Revision model fake: answers with a ``words``-word draft, or raises; logs calls to a file."""
    import services.assignment_llm as llm

    monkeypatch.setattr(llm, "assignment_llm_configured", lambda *a, **k: True)

    def fake_generate(**kwargs):
        if log is not None:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write("call\n")
        if delay:
            time.sleep(delay)
        if fail:
            raise RuntimeError("revision provider unavailable")
        draft = json.loads(kwargs["user_prompt"])["draft"]
        return {"scope": "large", "content": _doc(words or count_words(draft)), "assistant_reply": "done"}, None

    monkeypatch.setattr(llm, "assignment_generate_json", fake_generate)
    delivered: list[int] = []
    env.service._rehumanize_current_prose = lambda *a, **k: None
    env.service.run_formatting = lambda pid: None
    env.service.run_delivery = lambda pid: delivered.append(env.service._load_draft(pid).total_words)
    return delivered


def _calls(log) -> int:
    path = Path(log)
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


def _rounds_rows(pid) -> list[str]:
    with economy_db.connect() as conn:
        rows = conn.execute(
            "SELECT status FROM assignment_revision_rounds WHERE project_id = ? ORDER BY reserved_at", (pid,)
        ).fetchall()
    return [r["status"] for r in rows]


def _revise(client, pid, message="Please adjust the wording."):
    return client.post(_url(pid, "revision-chat"), json={"message": message})


def _crash_writer(env, monkeypatch, service=None):
    service = service or env.service

    def crash(_session_id):
        raise RuntimeError("writer provider unavailable")

    monkeypatch.setattr(service.writer, "advance_section", crash)


def _plan_blueprint(env, pid, service=None):
    service = service or env.service
    service._verified_facts = lambda *a, **k: []
    service.run_research(pid)
    service.run_blueprint(pid)


# ================================================================== 1-15 quote confirmation


def test_01_missing_quote_id_is_refused_without_a_charge(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    balance = env.wallet.get_balance(owner["id"])
    for res in (_confirm(client, pid), _confirm(client, pid, {})):
        assert res.status_code == 409, res.get_data(as_text=True)
        body = res.get_json()
        assert body["error"] == "QUOTE_REQUIRED" and body["payment_confirmed"] is False
        # The reply carries the price to show and ask about; it is the server's current quote.
        assert body["project"]["project"]["artifacts"]["pricing"]["quote_id"] == _quote(env, pid)["quote_id"]
    assert charges == []
    _assert_nothing_charged(env, owner, pid, balance)


def test_02_null_quote_id_is_a_missing_quote(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    balance = env.wallet.get_balance(owner["id"])
    res = _confirm(client, pid, {"quote_id": None})
    assert res.status_code == 409 and res.get_json()["error"] == "QUOTE_REQUIRED"
    assert charges == []
    _assert_nothing_charged(env, owner, pid, balance)


def test_03_empty_quote_id_is_refused(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    balance = env.wallet.get_balance(owner["id"])
    for bad in ("", "   ", "\t"):
        res = _confirm(client, pid, {"quote_id": bad})
        assert res.status_code == 400 and res.get_json()["error"] == "INVALID_QUOTE", repr(bad)
    assert charges == []
    _assert_nothing_charged(env, owner, pid, balance)


def test_04_malformed_or_wrong_type_quote_id_is_refused(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    good = _quote(env, pid)["quote_id"]
    balance = env.wallet.get_balance(owner["id"])
    malformed = [123, 1.5, True, ["q"], {"id": good}, "x" * 65, "Z" * 32, good.upper(), str(uuid.UUID(good)),
                 good + " ", " " + good, good[:-1], good + "0", "../" + good[:29], good[:31] + "\n"]
    for bad in malformed:
        res = _confirm(client, pid, {"quote_id": bad})
        assert res.status_code == 400 and res.get_json()["error"] == "INVALID_QUOTE", repr(bad)
    assert charges == []
    _assert_nothing_charged(env, owner, pid, balance)


def test_05_stale_quote_is_refused_with_the_new_price(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    shown = _quote(env, pid)
    assert _signed_in(_client(), owner).post(_url(pid, "brief"), json={"word_count": 20000}).status_code == 200
    balance = env.wallet.get_balance(owner["id"])
    res = _confirm(client, pid, {"quote_id": shown["quote_id"]})
    assert res.status_code == 409 and res.get_json()["error"] == "PRICE_CHANGED"
    new = res.get_json()["project"]["project"]["artifacts"]["pricing"]
    assert new["quote_id"] != shown["quote_id"] and new["amount_coins"] > 10 * shown["amount_coins"]
    assert charges == []
    _assert_nothing_charged(env, owner, pid, balance)


def test_06_superseded_quote_for_unchanged_inputs_is_refused(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    first = _quote(env, pid)
    assert client.post(_url(pid, "pricing"), json={}).status_code == 200  # re-quoted, same inputs
    second = _quote(env, pid)
    assert second["quote_id"] != first["quote_id"]
    res = _confirm(client, pid, {"quote_id": first["quote_id"]})
    assert res.status_code == 409 and res.get_json()["reason"] == "QUOTE_SUPERSEDED"
    assert charges == [] and _debits(pid) == []
    res = _confirm(client, pid, {"quote_id": second["quote_id"]})
    assert res.status_code == 200 and _debits(pid) == [second["amount_coins"]]


def test_07_quote_from_another_project_is_refused(env, charges):
    owner = _owner(env)
    pid_a, client = _priced(env, owner)
    pid_b, _ = _priced(env, owner)
    quote_b = _quote(env, pid_b)
    res = _confirm(client, pid_a, {"quote_id": quote_b["quote_id"]})
    assert res.status_code == 409 and res.get_json()["reason"] == "QUOTE_SUPERSEDED"
    project_a = env.service.store.require_project(pid_a)
    project_a.artifacts["pricing"] = dict(quote_b)
    env.service.store.save_project(project_a)
    res = _confirm(client, pid_a, {"quote_id": quote_b["quote_id"]})
    assert res.status_code == 409 and res.get_json()["reason"] == "QUOTE_OTHER_PROJECT"
    assert charges == [] and _debits(pid_a) == [] and _debits(pid_b) == []


def test_08_quote_bound_to_another_user_is_refused(env, charges):
    owner = _owner(env)
    intruder = _owner(env, email="intruder@example.com")
    pid, client = _priced(env, owner)
    quote = _quote(env, pid)
    # The intruder cannot use the owner's quote on the owner's project.
    res = _confirm(_signed_in(_client(), intruder), pid, {"quote_id": quote["quote_id"]})
    assert res.status_code in (403, 404)
    # A stored quote issued for someone else (copied, stale or tampered) is never payable.
    project = env.service.store.require_project(pid)
    project.artifacts["pricing"] = {**quote, "user_id": str(intruder["id"])}
    env.service.store.save_project(project)
    res = _confirm(client, pid, {"quote_id": quote["quote_id"]})
    assert res.status_code == 409 and res.get_json()["reason"] == "QUOTE_OTHER_USER"
    assert charges == [] and _debits(pid) == []
    fresh = _quote(env, pid)
    assert fresh["user_id"] == str(owner["id"]) and fresh["quote_id"] != quote["quote_id"]


def test_09_quote_with_altered_scope_hash_is_refused(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    quote = _quote(env, pid)
    project = env.service.store.require_project(pid)
    project.artifacts["pricing"] = {**quote, "scope_hash": "0" * 64}
    env.service.store.save_project(project)
    res = _confirm(client, pid, {"quote_id": quote["quote_id"]})
    assert res.status_code == 409 and res.get_json()["reason"] == "SCOPE_CHANGED"
    assert charges == [] and _debits(pid) == []


def test_10_same_quote_twice_is_an_idempotent_replay_of_the_real_debit(env, charges):
    owner = _owner(env)
    pid, client, first = _paid(env, owner)
    balance = env.wallet.get_balance(owner["id"])
    quote_id = env.service.store.require_project(pid).artifacts[PAYMENT_QUOTE_KEY]
    assert first["charged_now"] == first["coins_charged"] == _debits(pid)[0] > 0
    assert first["idempotent_replay"] is False
    for _ in range(3):
        res = _confirm(client, pid, {"quote_id": quote_id})
        assert res.status_code == 200
        body = res.get_json()
        assert body["coins_charged"] == first["coins_charged"]  # the original debit, not 0
        assert body["charged_now"] == 0 and body["idempotent_replay"] is True
    assert charges == [pid]
    assert env.wallet.get_balance(owner["id"]) == balance and len(_debits(pid)) == 1


def test_11_a_different_quote_after_payment_is_a_mismatch(env, charges):
    owner = _owner(env)
    pid, client, _first = _paid(env, owner)
    balance = env.wallet.get_balance(owner["id"])
    for other in (uuid.uuid4().hex, _quote(env, _priced(env, owner)[0])["quote_id"]):
        res = _confirm(client, pid, {"quote_id": other})
        assert res.status_code == 409, res.get_data(as_text=True)
        assert res.get_json()["error"] == "QUOTE_MISMATCH" and res.get_json()["payment_confirmed"] is True
    assert charges == [pid] and len(_debits(pid)) == 1
    assert env.wallet.get_balance(owner["id"]) == balance


def test_12_missing_quote_after_payment_is_explicit_and_not_a_replay(env, charges):
    owner = _owner(env)
    pid, client, _first = _paid(env, owner)
    balance = env.wallet.get_balance(owner["id"])
    for res in (_confirm(client, pid), _confirm(client, pid, {}), _confirm(client, pid, {"quote_id": None})):
        assert res.status_code == 409
        body = res.get_json()
        assert body["error"] == "QUOTE_REQUIRED" and body["payment_confirmed"] is True
        assert "idempotent_replay" not in body and "coins_charged" not in body
    assert charges == [pid] and len(_debits(pid)) == 1
    assert env.wallet.get_balance(owner["id"]) == balance


def _child_confirm(queue, barrier, owner, pid, body):
    outcome = "error"
    try:
        client = _signed_in(_client(), owner)
        barrier.wait(WAIT)
        res = client.post(_url(pid, "confirm-payment"), json=body)
        data = res.get_json() or {}
        outcome = (res.status_code, data.get("error"), data.get("coins_charged"), data.get("charged_now"))
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {exc!r}"
    finally:
        _child_exit(queue, outcome)


def _confirm_race(env, owner, pid, bodies):
    queue, barrier = FORK.Queue(), FORK.Barrier(len(bodies))
    procs = [FORK.Process(target=_child_confirm, args=(queue, barrier, owner, pid, body)) for body in bodies]
    for proc in procs:
        proc.start()
    outcomes = [queue.get(timeout=WAIT) for _ in procs]
    for proc in procs:
        proc.join(WAIT)
    return outcomes


def test_13_simultaneous_confirmations_from_separate_processes(env):
    owner = _owner(env)
    pid, _client_ = _priced(env, owner)
    quote = _quote(env, pid)
    amount = quote["amount_coins"]
    outcomes = _confirm_race(env, owner, pid, [{"quote_id": quote["quote_id"]}] * 2)
    assert sorted(o[:3] for o in outcomes) == [(200, None, amount)] * 2, outcomes
    assert sorted(o[3] for o in outcomes) == [0, amount]  # exactly one request charged
    assert _debits(pid) == [amount] and len(_cycles(pid)) == 1

    # A racing request without a quote never pays, whichever order the processes run in.
    pid2, _c2 = _priced(env, owner)
    quote2 = _quote(env, pid2)
    outcomes = _confirm_race(env, owner, pid2, [{"quote_id": quote2["quote_id"]}, {}, {"quote_id": None}])
    assert sorted(o[:2] for o in outcomes) == [(200, None), (409, "QUOTE_REQUIRED"), (409, "QUOTE_REQUIRED")]
    assert _debits(pid2) == [quote2["amount_coins"]] and len(_cycles(pid2)) == 1


def test_14_old_cached_frontend_without_quote_id_never_charges(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    balance = env.wallet.get_balance(owner["id"])
    # An old api.js sent {} ; an older page sent no body at all, or a form post.
    for res in (_confirm(client, pid, {}), _confirm(client, pid),
                client.post(_url(pid, "confirm-payment"), data={"quote_id": _quote(env, pid)["quote_id"]})):
        assert res.status_code == 409 and res.get_json()["error"] == "QUOTE_REQUIRED"
    assert charges == []
    _assert_nothing_charged(env, owner, pid, balance)


def test_14b_pages_load_the_new_scripts():
    app_v2 = (REPO / "templates" / "app_v2.html").read_text(encoding="utf-8")
    assignment = (REPO / "templates" / "assignment.html").read_text(encoding="utf-8")
    assert "app2/api.js') }}?v=20261110-p4b1" in app_v2
    assert "app2/app.js') }}?v=20261110-p4b1" in app_v2
    assert "assignment-page.js') }}?v=20261110-p4b1" in assignment
    for stale in ("api.js') }}?v=20261109-p3h", "app.js') }}?v=20261107-1", "?v=20260925-paste-images"):
        assert stale not in app_v2 and stale not in assignment


def test_14c_no_client_posts_a_confirmation_without_a_quote():
    api = (REPO / "static" / "app2" / "api.js").read_text(encoding="utf-8")
    page = (REPO / "static" / "assignment-page.js").read_text(encoding="utf-8")
    assert "quote_id: quoteId } : {}" not in api
    assert "quoteId ? { quote_id: quoteId } : {}" not in page
    # assignment-page.js confirms the quote the student clicked, never "whatever is current".
    start = page.index("async function ensurePaymentConfirmed")
    body = page[start:page.index("async function confirmPayment")]
    assert "state.consentQuoteId" in body and "state.pricing" not in body


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_14d_api_client_refuses_locally_without_a_quote(tmp_path):
    script = tmp_path / "probe.js"
    script.write_text(
        """
        const calls = [];
        global.window = global;
        global.fetch = async (url, init) => { calls.push([url, init && init.body]);
          return { ok: true, status: 200, json: async () => ({ ok: 1 }) }; };
        require(process.argv[2]);
        const api = window.DMX.api;
        (async () => {
          const out = {};
          for (const q of [undefined, null, '']) {
            try { await api.assignment.confirm('p1', q); out[String(q)] = 'sent'; }
            catch (e) { out[String(q)] = e.code; }
          }
          await api.assignment.confirm('p1', 'a'.repeat(32));
          console.log(JSON.stringify({ out, calls }));
        })();
        """,
        encoding="utf-8",
    )
    run = subprocess.run(["node", str(script), str(REPO / "static" / "app2" / "api.js")],
                         capture_output=True, text=True, timeout=60, check=True)
    result = json.loads(run.stdout.strip().splitlines()[-1])
    assert result["out"] == {"undefined": "QUOTE_REQUIRED", "null": "QUOTE_REQUIRED", "": "QUOTE_REQUIRED"}
    assert [(url, json.loads(body)) for url, body in result["calls"]] == [
        ("/api/assignment/projects/p1/confirm-payment", {"quote_id": "a" * 32})]


def test_15_price_changed_needs_a_new_explicit_confirmation(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    shown = _quote(env, pid)
    _signed_in(_client(), owner).post(_url(pid, "brief"), json={"word_count": 20000})
    balance = env.wallet.get_balance(owner["id"])
    # Retrying the consent the student gave never pays the new price.
    for _ in range(3):
        res = _confirm(client, pid, {"quote_id": shown["quote_id"]})
        assert res.status_code == 409 and res.get_json()["error"] == "PRICE_CHANGED"
    assert charges == []
    _assert_nothing_charged(env, owner, pid, balance)
    new = res.get_json()["project"]["project"]["artifacts"]["pricing"]
    res = _confirm(client, pid, {"quote_id": new["quote_id"]})
    assert res.status_code == 200 and res.get_json()["coins_charged"] == new["amount_coins"]

    app_js = (REPO / "static" / "app2" / "app.js").read_text(encoding="utf-8")
    page = (REPO / "static" / "assignment-page.js").read_text(encoding="utf-8")
    # A separate button for the new price; the generic confirm is inert while it is pending.
    assert 'data-act="assign-confirm-new-price"' in app_js
    assert "if (a.priceChange && !newPrice) return;" in app_js
    assert "data-asg-confirm-new-price" in page
    assert "if (state.priceChange || state.autoRunning) return;" in page
    # No automatic retry: a refusal only shows the new price and stops.
    confirm_fn = app_js[app_js.index("async function assignConfirm"):app_js.index("function sendAssignMessage")]
    refused = confirm_fn[confirm_fn.index("catch (err)"):]
    assert "assignConfirm(" not in refused and "API.assignment.confirm(" not in refused
    offer = page[page.index("function offerNewPrice"):page.index("function onPayClick")]
    assert "state.consentQuoteId = null;" in offer
    assert "runAutoProduction" not in offer and "api(" not in offer and "onConfirmNewPrice" not in offer
    assert page.count("offerNewPrice(err);\n        return;\n") == 2


# ================================================================== 16-25 revision chat


def test_16_revision_inside_the_paid_scope_is_saved(env, monkeypatch, tmp_path):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    _seed_draft(env, pid, PAID_WORDS)
    log = tmp_path / "calls"
    delivered = _chat_provider(env, monkeypatch, words=CAP, log=log)
    res = _revise(client, pid)
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["rounds_used"] == 1 and _calls(log) == 1
    assert env.service._load_draft(pid).total_words == CAP and delivered == [CAP]


@pytest.mark.parametrize("words", [CAP + 1, 1200, 2773, 20000])
def test_17_revision_beyond_the_paid_scope_is_refused_and_nothing_is_saved(env, monkeypatch, tmp_path, words):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    original = _seed_draft(env, pid, PAID_WORDS)
    before = _disk(env, pid)["project"]["artifacts"]
    log = tmp_path / "calls"
    delivered = _chat_provider(env, monkeypatch, words=words, log=log)
    res = _revise(client, pid, "Expand everything a lot.")
    assert res.status_code == 409, res.get_data(as_text=True)
    assert res.get_json()["error"] == "PAID_SCOPE_LIMIT_EXCEEDED"
    after = _disk(env, pid)["project"]["artifacts"]
    assert env.service._load_draft(pid).content == original
    assert after.get("draft") == before.get("draft") and after.get("revision_chat") == before.get("revision_chat")
    assert delivered == []
    assert _rounds_rows(pid) == ["consumed"]  # the provider answered, so the round is used


def test_18_paid_500_words_cannot_become_2773(env, monkeypatch, tmp_path):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    paid = payment_ledger.get_cycle(_cycles(pid)[0]["cycle_id"])["quoted_word_count"]
    assert paid == 500
    _seed_draft(env, pid, 500)
    delivered = _chat_provider(env, monkeypatch, words=2773, log=tmp_path / "calls")
    for _ in range(3):  # retries are refused the same way
        res = _revise(client, pid, "Please expand everything to 3000 words.")
        assert res.status_code == 409 and res.get_json()["error"] == "PAID_SCOPE_LIMIT_EXCEEDED"
    assert env.service._load_draft(pid).total_words == 500 and delivered == []


def test_18b_a_draft_already_over_the_cap_may_be_edited_but_not_grown(env, monkeypatch, tmp_path):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    _seed_draft(env, pid, CAP + 100)  # the writer overshot
    _chat_provider(env, monkeypatch, words=CAP + 100, log=tmp_path / "calls")
    assert _revise(client, pid).status_code == 200
    _chat_provider(env, monkeypatch, words=CAP + 101, log=tmp_path / "calls")
    assert _revise(client, pid).status_code == 409


def test_19_and_20_five_rounds_then_the_sixth_is_refused_before_the_provider(env, monkeypatch, tmp_path):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    _seed_draft(env, pid, PAID_WORDS)
    log = tmp_path / "calls"
    _chat_provider(env, monkeypatch, log=log)
    for n in range(1, MAX_CLIENT_REVISION_ROUNDS + 1):
        res = _revise(client, pid)
        assert res.status_code == 200 and res.get_json()["rounds_used"] == n
    res = _revise(client, pid)
    assert res.status_code == 409 and res.get_json()["error"] == "REVISION_LIMIT_REACHED"
    assert _calls(log) == MAX_CLIENT_REVISION_ROUNDS
    assert client.get(_url(pid, "revision-chat")).get_json()["rounds_used"] == MAX_CLIENT_REVISION_ROUNDS


def _child_revise(queue, barrier, owner, pid):
    outcome = "error"
    try:
        client = _signed_in(_client(), owner)
        barrier.wait(WAIT)
        res = _revise(client, pid)
        outcome = (res.status_code, (res.get_json() or {}).get("error"))
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {exc!r}"
    finally:
        _child_exit(queue, outcome)


def _revise_race(owner, pid, n):
    queue, barrier = FORK.Queue(), FORK.Barrier(n)
    procs = [FORK.Process(target=_child_revise, args=(queue, barrier, owner, pid)) for _ in range(n)]
    for proc in procs:
        proc.start()
    outcomes = [queue.get(timeout=WAIT) for _ in procs]
    for proc in procs:
        proc.join(WAIT)
    return outcomes


def test_21_one_round_left_and_three_simultaneous_requests(env, monkeypatch, tmp_path):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    _seed_draft(env, pid, PAID_WORDS)
    log = tmp_path / "calls"
    _chat_provider(env, monkeypatch, log=log, delay=0.3)
    for _ in range(MAX_CLIENT_REVISION_ROUNDS - 1):
        assert _revise(client, pid).status_code == 200
    outcomes = _revise_race(owner, pid, 3)
    assert sorted(outcomes, key=str) == sorted([(200, None), (409, "REVISION_LIMIT_REACHED"),
                                                (409, "REVISION_LIMIT_REACHED")], key=str), outcomes
    assert _calls(log) == MAX_CLIENT_REVISION_ROUNDS
    assert _rounds_rows(pid).count("consumed") == MAX_CLIENT_REVISION_ROUNDS


def test_22_provider_failure_gives_the_round_back(env, monkeypatch, tmp_path):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    original = _seed_draft(env, pid, PAID_WORDS)
    log = tmp_path / "calls"
    _chat_provider(env, monkeypatch, fail=True, log=log)
    res = _revise(client, pid)
    assert res.status_code == 500
    assert _rounds_rows(pid) == ["released"] and entitlements.revision_rounds_used(pid) == 0
    assert env.service._load_draft(pid).content == original
    _chat_provider(env, monkeypatch, log=log)
    res = _revise(client, pid)
    assert res.status_code == 200 and res.get_json()["rounds_used"] == 1
    assert sorted(_rounds_rows(pid)) == ["consumed", "released"]


def test_23_a_reservation_finishes_once(env):
    pid = "p-" + uuid.uuid4().hex
    rid = entitlements.reserve_revision_round(pid, limit=MAX_CLIENT_REVISION_ROUNDS)
    assert entitlements.revision_rounds_used(pid) == 1
    assert entitlements.finish_revision_round(rid, consumed=False) is True
    assert entitlements.finish_revision_round(rid, consumed=False) is False  # double release
    assert entitlements.finish_revision_round(rid, consumed=True) is False  # no reuse after release
    assert entitlements.revision_round_status(rid) == "released"
    assert entitlements.revision_rounds_used(pid) == 0
    rid2 = entitlements.reserve_revision_round(pid, limit=MAX_CLIENT_REVISION_ROUNDS)
    assert entitlements.finish_revision_round(rid2, consumed=True) is True
    assert entitlements.finish_revision_round(rid2, consumed=False) is False  # no release after use
    assert entitlements.revision_rounds_used(pid) == 1
    with pytest.raises(sqlite3.DatabaseError):
        with economy_db.connect() as conn:
            conn.execute("UPDATE assignment_revision_rounds SET status = 'reserved' WHERE reservation_id = ?",
                         (rid,))
    with pytest.raises(sqlite3.DatabaseError):
        with economy_db.connect() as conn:
            conn.execute("DELETE FROM assignment_revision_rounds WHERE reservation_id = ?", (rid2,))
    assert entitlements.revision_rounds_used(pid) == 1


def _child_rounds(queue, owner, pid, n):
    outcome = "error"
    try:
        client = _signed_in(_client(), owner)
        outcome = [_revise(client, pid).status_code for _ in range(n)]
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {exc!r}"
    finally:
        _child_exit(queue, outcome)


def test_24_workers_share_one_round_counter(env, monkeypatch, tmp_path):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    _seed_draft(env, pid, PAID_WORDS)
    log = tmp_path / "calls"
    _chat_provider(env, monkeypatch, log=log)
    for n in (3, 2):  # two forked workers, each with its own memory
        queue = FORK.Queue()
        proc = FORK.Process(target=_child_rounds, args=(queue, owner, pid, n))
        proc.start()
        assert queue.get(timeout=WAIT) == [200] * n
        proc.join(WAIT)
    # A stale worker writes back an older chat record with fewer rounds.
    project = env.service.store.require_project(pid)
    project.artifacts["revision_chat"] = {"messages": [], "rounds_used": 0}
    env.service.store.save_project(project)
    worker = _fresh_worker(env, pipeline=env.service.pipeline)
    monkeypatch.setattr(env.app, "project_service", worker)
    worker._rehumanize_current_prose = env.service._rehumanize_current_prose
    res = _revise(client, pid)
    assert res.status_code == 409 and res.get_json()["error"] == "REVISION_LIMIT_REACHED"
    assert _calls(log) == MAX_CLIENT_REVISION_ROUNDS
    assert worker.get_revision_chat(pid)["rounds_used"] == MAX_CLIENT_REVISION_ROUNDS


def test_25_no_provider_call_after_any_rejection(env, monkeypatch, tmp_path):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    _seed_draft(env, pid, PAID_WORDS)
    log = tmp_path / "calls"
    _chat_provider(env, monkeypatch, log=log)
    # Legacy count from before rounds were recorded in the ledger.
    project = env.service.store.require_project(pid)
    project.artifacts["revision_chat"] = {"messages": [], "rounds_used": MAX_CLIENT_REVISION_ROUNDS}
    env.service.store.save_project(project)
    assert _revise(client, pid).status_code == 409
    # Ledger unavailable: refused before the provider.
    pid2, client2, _ = _paid(env, owner)
    _seed_draft(env, pid2, PAID_WORDS)

    def down(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")

    real = entitlements.reserve_revision_round
    monkeypatch.setattr(entitlements, "reserve_revision_round", down)
    assert _revise(client2, pid2).status_code == 400
    monkeypatch.setattr(entitlements, "reserve_revision_round", real)
    # After a refund.
    _admin().post(f"/api/admin/assignment/projects/{pid2}/refund", json={"reason": "audit"})
    assert _revise(client2, pid2).status_code in (400, 404)
    assert _calls(log) == 0


# ================================================================== 26-35 Research Plan provenance


def _refund(client, pid):
    return client.post(_url(pid, "refund-failed"), json={})


def test_26_client_plan_edit_before_blueprint(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.service.run_research(pid)
    assert client.patch(_url(pid, "research-plan"), json={"assignment_topic": "EDITED"}).status_code == 200
    env.blueprint.crash = True
    assert client.post(_url(pid, "blueprint"), json={}).status_code == 502
    env.blueprint.crash = False
    assert "EDITED" in json.dumps(env.blueprint.seen[-1]["plan"])
    art = env.service.store.require_project(pid).artifacts
    assert art[PROCESSING_FAILURE_KEY]["client_seeded"] is True
    assert entitlements.client_input_used(pid, art["payment_cycle_id"]) is True
    res = _refund(client, pid)
    assert res.status_code == 400 and res.get_json()["reason"] == "CLIENT_INPUT"


def test_27_client_plan_edit_after_blueprint_taints_the_writer(env, monkeypatch):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    _plan_blueprint(env, pid)
    assert client.patch(_url(pid, "research-plan"), json={"assignment_topic": "CLIENT-POISON"}).status_code == 200
    env.service.start_writer(pid)
    assert "CLIENT-POISON" in json.dumps(env.service._load_writer_session(pid).research_plan)
    _crash_writer(env, monkeypatch)
    with pytest.raises(RuntimeError):
        env.service.advance_writer(pid)
    art = env.service.store.require_project(pid).artifacts
    assert art[PROCESSING_FAILURE_KEY]["client_seeded"] is True
    res = _refund(client, pid)
    assert res.status_code == 400 and res.get_json()["reason"] == "CLIENT_INPUT"


def test_28_writer_failure_after_client_plan_survives_a_stale_failure_record(env, monkeypatch):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    _plan_blueprint(env, pid)
    client.patch(_url(pid, "research-plan"), json={"assignment_topic": "CLIENT-POISON"})
    env.service.start_writer(pid)
    _crash_writer(env, monkeypatch)
    with pytest.raises(RuntimeError):
        env.service.advance_writer(pid)
    # A stale write puts back a "server" label and a clean failure record.
    project = env.service.store.require_project(pid)
    project.artifacts[PROCESSING_FAILURE_KEY]["client_seeded"] = False
    project.artifacts[RESEARCH_PLAN_SOURCE_KEY] = "server"
    env.service.store.save_project(project)
    balance = env.wallet.get_balance(owner["id"])
    res = _refund(client, pid)
    assert res.status_code == 400 and res.get_json()["reason"] == "CLIENT_INPUT"
    assert env.wallet.get_balance(owner["id"]) == balance and _refund_rows(pid) == []


def test_29_automatic_refund_skips_client_seeded_failures(env, monkeypatch):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    _plan_blueprint(env, pid)
    client.patch(_url(pid, "research-plan"), json={"assignment_topic": "EDITED"})
    env.service.start_writer(pid)
    _crash_writer(env, monkeypatch)
    with pytest.raises(RuntimeError):
        env.service.advance_writer(pid)
    balance = env.wallet.get_balance(owner["id"])
    assert _auto_refund_as(env.app, owner, pid) is None
    assert env.wallet.get_balance(owner["id"]) == balance and _refund_rows(pid) == []


def test_30_genuine_server_failure_is_still_refunded(env, monkeypatch):
    owner = _owner(env)
    start = env.wallet.get_balance(owner["id"])
    pid, client, body = _paid(env, owner)
    _plan_blueprint(env, pid)
    env.service.start_writer(pid)
    _crash_writer(env, monkeypatch)
    with pytest.raises(RuntimeError):
        env.service.advance_writer(pid)
    art = env.service.store.require_project(pid).artifacts
    assert art[PROCESSING_FAILURE_KEY]["client_seeded"] is False
    assert entitlements.client_input_used(pid, art["payment_cycle_id"]) is False
    res = _refund(client, pid)
    assert res.status_code == 200 and res.get_json()["coins_refunded"] == body["coins_charged"]
    assert env.wallet.get_balance(owner["id"]) == start


def _child_patch_plan(queue, barrier, owner, pid):
    outcome = "error"
    try:
        client = _signed_in(_client(), owner)
        barrier.wait(WAIT)
        outcome = client.patch(_url(pid, "research-plan"), json={"assignment_topic": "EDITED"}).status_code
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {exc!r}"
    finally:
        _child_exit(queue, outcome)


def test_31_plan_edit_in_another_worker_process_is_seen_and_tainted(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    worker_b = _fresh_worker(env, pipeline=env.service.pipeline)
    worker_b.research = _EditableResearch()
    worker_b.run_research(pid)  # B holds its own server plan in memory
    queue, barrier = FORK.Queue(), FORK.Barrier(2)
    proc = FORK.Process(target=_child_patch_plan, args=(queue, barrier, owner, pid))
    proc.start()
    barrier.wait(WAIT)
    assert queue.get(timeout=WAIT) == 200
    proc.join(WAIT)
    env.blueprint.crash = True
    with pytest.raises(RuntimeError):
        worker_b.run_blueprint(pid)
    env.blueprint.crash = False
    assert "EDITED" in json.dumps(env.blueprint.seen[-1]["plan"])  # same id, new content: not B's copy
    assert worker_b.store.require_project(pid).artifacts[PROCESSING_FAILURE_KEY]["client_seeded"] is True
    assert _refund(client, pid).get_json()["reason"] == "CLIENT_INPUT"


def test_32_a_stale_plan_version_is_refused(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.service.run_research(pid)
    stale = dict(env.service.store.require_project(pid).artifacts["research_plan"])
    client.patch(_url(pid, "research-plan"), json={"assignment_topic": "EDITED"})
    project = env.service.store.require_project(pid)
    project.artifacts["research_plan"] = stale
    project.artifacts[RESEARCH_PLAN_SOURCE_KEY] = "server"
    env.service.store.save_project(project)
    calls = env.blueprint.calls
    for worker in (env.service, _fresh_worker(env, pipeline=env.service.pipeline)):
        with pytest.raises(ResearchPlanChangedError):
            worker.run_blueprint(pid)
    res = client.post(_url(pid, "blueprint"), json={})
    assert res.status_code == 409 and res.get_json()["error"] == "RESEARCH_PLAN_CHANGED"
    assert env.blueprint.calls == calls
    assert PROCESSING_FAILURE_KEY not in env.service.store.require_project(pid).artifacts
    latest = entitlements.latest_plan_version(pid)
    assert latest["source"] == "client"  # the stale snapshot did not clear the provenance


def test_33_forged_provenance_fields_are_ignored(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.service.run_research(pid)
    forged = {"assignment_topic": "EDITED", RESEARCH_PLAN_SOURCE_KEY: "server", "source": "server",
              "client_seeded": False, "content_hash": "0" * 64, "version": 99, "provenance": "server",
              "id": "forged", "project_id": "other"}
    assert client.patch(_url(pid, "research-plan"), json=forged).status_code == 200
    art = env.service.store.require_project(pid).artifacts
    assert art[RESEARCH_PLAN_SOURCE_KEY] == "client"
    assert entitlements.latest_plan_version(pid)["source"] == "client"
    env.blueprint.crash = True
    res = client.post(_url(pid, "blueprint"), json={"client_seeded": False, "research_plan_source": "server"})
    env.blueprint.crash = False
    assert res.status_code == 502
    assert _refund(client, pid).get_json()["reason"] == "CLIENT_INPUT"


def test_34_retries_keep_the_provenance(env, monkeypatch):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.service._verified_facts = lambda *a, **k: []
    env.service.run_research(pid)
    client.patch(_url(pid, "research-plan"), json={"assignment_topic": "EDITED"})
    env.blueprint.crash = True
    for _ in range(2):
        assert client.post(_url(pid, "blueprint"), json={}).status_code == 502
        assert env.service.store.require_project(pid).artifacts[PROCESSING_FAILURE_KEY]["client_seeded"] is True
    env.blueprint.crash = False
    assert client.post(_url(pid, "blueprint"), json={}).status_code == 200
    env.service.start_writer(pid)
    _crash_writer(env, monkeypatch)
    with pytest.raises(RuntimeError):
        env.service.advance_writer(pid)
    assert env.service.store.require_project(pid).artifacts[PROCESSING_FAILURE_KEY]["client_seeded"] is True
    assert _refund(client, pid).get_json()["reason"] == "CLIENT_INPUT"


def _child_restarted_writer(queue, env, pid):
    outcome = "error"
    try:
        worker = _fresh_worker(env)
        worker.research = _EditableResearch()
        worker._verified_facts = lambda *a, **k: []
        worker.start_writer(pid)

        def crash(_session_id):
            raise RuntimeError("writer provider unavailable")

        worker.writer.advance_section = crash
        try:
            worker.advance_writer(pid)
        except RuntimeError:
            pass
        outcome = worker.store.require_project(pid).artifacts[PROCESSING_FAILURE_KEY]["client_seeded"]
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {exc!r}"
    finally:
        _child_exit(queue, outcome)


def test_35_worker_restart_keeps_the_provenance(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.service._verified_facts = lambda *a, **k: []
    env.service.run_research(pid)
    client.patch(_url(pid, "research-plan"), json={"assignment_topic": "EDITED"})
    env.service.run_blueprint(pid)
    # A new worker process with empty memory; the JSON label was also lost to a stale write.
    project = env.service.store.require_project(pid)
    project.artifacts[RESEARCH_PLAN_SOURCE_KEY] = "server"
    env.service.store.save_project(project)
    queue = FORK.Queue()
    proc = FORK.Process(target=_child_restarted_writer, args=(queue, env, pid))
    proc.start()
    assert queue.get(timeout=WAIT) is True
    proc.join(WAIT)
    assert _refund(client, pid).get_json()["reason"] == "CLIENT_INPUT"


def test_35b_plan_versions_and_client_use_rows_are_append_only(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.service.run_research(pid)
    client.patch(_url(pid, "research-plan"), json={"assignment_topic": "EDITED"})
    with pytest.raises(sqlite3.DatabaseError):
        with economy_db.connect() as conn:
            conn.execute("UPDATE assignment_plan_versions SET source = 'server' WHERE project_id = ?", (pid,))
    with pytest.raises(sqlite3.DatabaseError):
        with economy_db.connect() as conn:
            conn.execute("DELETE FROM assignment_plan_versions WHERE project_id = ?", (pid,))
    env.blueprint.crash = True
    client.post(_url(pid, "blueprint"), json={})
    env.blueprint.crash = False
    with pytest.raises(sqlite3.DatabaseError):
        with economy_db.connect() as conn:
            conn.execute("DELETE FROM assignment_client_input_use WHERE project_id = ?", (pid,))
    assert entitlements.latest_plan_version(pid)["source"] == "client"


# ================================================================== 36-40 regressions


def test_36_pro_discount_is_charged_replayed_and_refunded_exactly(env):
    owner = _owner(env)
    _set_pro(owner)
    start = env.wallet.get_balance(owner["id"])
    pid, client, body = _paid(env, owner)
    quote = _quote(env, pid)
    expected = apply_pro_discount({"is_pro": 1}, quote["amount_coins"])
    assert expected < quote["amount_coins"]
    cycle = _cycles(pid)[0]
    assert body["coins_charged"] == body["charged_now"] == expected == _debits(pid)[0] == cycle["coins"]
    assert cycle["quoted_coins"] == quote["amount_coins"]
    replay = _confirm(client, pid, {"quote_id": quote["quote_id"]})
    assert replay.get_json()["coins_charged"] == expected and replay.get_json()["charged_now"] == 0
    _set_pro(owner, False)  # a plan change after payment does not change the refund
    res = _admin().post(f"/api/admin/assignment/projects/{pid}/refund", json={"reason": "audit"})
    assert res.status_code == 200 and res.get_json()["coins_refunded"] == expected
    assert env.wallet.get_balance(owner["id"]) == start


def test_37_and_38_full_refund_returns_the_debit_once(env, monkeypatch):
    owner = _owner(env)
    start = env.wallet.get_balance(owner["id"])
    pid, client, body = _paid(env, owner)
    _plan_blueprint(env, pid)
    env.service.start_writer(pid)
    _crash_writer(env, monkeypatch)
    with pytest.raises(RuntimeError):
        env.service.advance_writer(pid)
    res = _refund(client, pid)
    assert res.status_code == 200 and res.get_json()["coins_refunded"] == body["coins_charged"]
    assert _refund(client, pid).status_code != 200
    assert _admin().post(f"/api/admin/assignment/projects/{pid}/refund", json={"reason": "x"}).status_code == 409
    assert _auto_refund_as(env.app, owner, pid) is None
    assert _refund_rows(pid) == [body["coins_charged"]] and env.wallet.get_balance(owner["id"]) == start


def test_39_a_valid_quote_still_pays(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    quote = _quote(env, pid)
    balance = env.wallet.get_balance(owner["id"])
    res = _confirm(client, pid, {"quote_id": quote["quote_id"]})
    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert body["coins_charged"] == body["charged_now"] == quote["amount_coins"] == _fair_coins(env, pid)
    assert body["idempotent_replay"] is False and body["balance"] == balance - quote["amount_coins"]
    assert charges == [pid] and _debits(pid) == [quote["amount_coins"]]
    assert env.service.store.require_project(pid).artifacts[PAYMENT_QUOTE_KEY] == quote["quote_id"]


def test_40_paid_assignment_workflow_still_runs(env, monkeypatch, tmp_path):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.service._verified_facts = lambda *a, **k: []
    assert client.post(_url(pid, "research"), json={}).status_code == 200
    assert client.post(_url(pid, "blueprint"), json={}).status_code == 200
    session = env.service.start_writer(pid)
    assert session.project_id == pid
    latest = entitlements.latest_plan_version(pid)
    assert latest["source"] == "server"
    art = env.service.store.require_project(pid).artifacts
    assert entitlements.client_input_used(pid, art["payment_cycle_id"]) is False
    _seed_draft(env, pid, PAID_WORDS)
    _chat_provider(env, monkeypatch, words=PAID_WORDS + 50, log=tmp_path / "calls")
    res = _revise(client, pid, "Tighten the conclusion.")
    assert res.status_code == 200 and res.get_json()["rounds_used"] == 1
    assert client.get(_url(pid, "revision-chat")).get_json()["rounds_used"] == 1


def test_40b_legacy_quote_without_binding_is_requoted_not_paid(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    project = env.service.store.require_project(pid)
    quote = dict(project.artifacts["pricing"])
    for key in ("quote_version", "user_id"):
        quote.pop(key)
    project.artifacts["pricing"] = quote
    env.service.store.save_project(project)
    res = _confirm(client, pid, {"quote_id": quote["quote_id"]})
    assert res.status_code == 409 and res.get_json()["reason"] == "QUOTE_MISSING"
    fresh = res.get_json()["project"]["project"]["artifacts"]["pricing"]
    assert fresh["user_id"] == str(owner["id"]) and fresh["quote_id"] != quote["quote_id"]
    assert charges == [] and _debits(pid) == []


def test_40c_stale_project_json_cannot_revive_a_payable_old_quote(env, charges):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    stale = env.service.store.require_project(pid).to_dict()
    old = _quote(env, pid)
    _signed_in(_client(), owner).post(_url(pid, "brief"), json={"word_count": 20000})
    from services.assignment_project.store import ProjectUpdateConflictError
    from tests.assignment_helpers import plant_stale_project_json

    with pytest.raises(ProjectUpdateConflictError):  # the store refuses a copy it did not load
        env.service.store.save_project(Project.from_dict(stale))
    plant_stale_project_json(env.service.store.storage_root, pid, stale)  # a stale worker's old quote
    res = _confirm(client, pid, {"quote_id": old["quote_id"]})
    assert res.status_code == 409 and res.get_json()["error"] == "PRICE_CHANGED"
    assert charges == [] and _debits(pid) == []
