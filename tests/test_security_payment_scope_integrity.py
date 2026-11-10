"""A payment covers exactly the project inputs that were quoted, across workers and processes.

F-02: re-analysis or file changes could keep an old, cheaper quote, or change a paid project.
F-10: a student-edited research plan reached the blueprint labelled as the server's plan.
F-16: bundle saves wrote a worker's cached copy, putting back state other workers had changed.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import sqlite3
import threading
from types import SimpleNamespace

import pytest

from services.assignment_pipeline.models import PipelineStage, StageStatus, utc_now
from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project.models import RequirementFormatting
from services.assignment_project.service import (
    PAYMENT_CYCLE_KEY,
    PROCESSING_FAILURE_KEY,
    RESEARCH_PLAN_SOURCE_KEY,
    PaidScopeError,
    PaymentRequiredError,
    ProjectService,
    RequirementsLockedError,
    ResearchPlanChangedError,
)
from services.assignment_project.store import ProjectStore
from services.economy import assignment_payments as payment_ledger
from services.economy import db as economy_db
from services.economy.plans import allowance_rule
from services.research_engine.service import ResearchEngineService
from tests.test_assignment_project import _StubResearchService
from tests.test_security_paid_pipelines import _client, _signed_in, _user, economy  # noqa: F401

FORK = multiprocessing.get_context("fork")
WAIT = 30


# ------------------------------------------------------------------ fakes (no providers)


class _WordsAnalyzer:
    """Requirement analyzer whose billable volume the test controls; counts every call."""

    VERSION = "words-stub"

    def __init__(self, words: int) -> None:
        self.words = words
        self.calls = 0
        self.entered = None
        self.release = None

    def analyze(self, payload):
        self.calls += 1
        if self.entered is not None:
            self.entered.set()
            assert self.release.wait(WAIT)
        req = payload.requirement
        req.assignment_type = "Essay"
        req.word_count = self.words
        req.citation_style = "APA 7"
        req.required_sections = ["Introduction", "Conclusion"]
        req.rubric = []
        req.learning_outcomes = []
        req.minimum_sources = 5
        req.formatting = RequirementFormatting(font_family="Times New Roman")
        req.analyzer_version = self.VERSION
        req.analyzed_at = utc_now()
        return req


class _EditableResearch(_StubResearchService):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def build_plan(self, **kwargs):
        self.calls += 1
        return super().build_plan(**kwargs)

    def update_plan_from_dict(self, plan_id, payload):
        return ResearchEngineService.update_plan_from_dict(self, plan_id, payload)  # type: ignore[arg-type]


class _BudgetBlueprint:
    """Sizes sections like the real engine: the length budget split over the plan, 40 words minimum."""

    def __init__(self) -> None:
        from services.blueprint_engine.service import BlueprintEngineService

        self.store = BlueprintEngineService().store
        self.calls = 0
        self.crash = False
        self.seen: list[dict] = []

    def build_blueprint(self, *, requirement_json, research_plan, project_id=None):
        from services.blueprint_engine.models import Blueprint

        self.calls += 1
        self.seen.append({"requirement": dict(requirement_json), "plan": dict(research_plan)})
        if self.crash:
            raise RuntimeError("blueprint engine crashed")
        specs = list(research_plan.get("section_list") or [{"title": "Introduction"}])
        budget = int(requirement_json.get("word_count") or requirement_json.get("estimatedWordCount")
                     or sum(int(s.get("estimated_words") or 0) for s in specs) or 800)
        per = max(40, budget // len(specs))
        sections = [{"id": f"s{i}", "title": str(s.get("title") or f"S{i}"), "objective": "x",
                     "estimated_words": per, "key_points": []} for i, s in enumerate(specs)]
        blueprint = Blueprint.from_dict({
            "id": f"bp-{project_id}", "project_id": project_id, "total_target_words": per * len(sections),
            "total_target_sections": len(sections), "writing_order": [s["id"] for s in sections],
            "citation_strategy": "APA 7", "academic_tone": "Formal", "sections": sections,
            "word_distribution": [{"title": s["title"], "estimated_words": per} for s in sections],
            "writing_queue": [s["id"] for s in sections], "engine_version": "budget-stub",
        })
        return self.store.save(blueprint)


# ------------------------------------------------------------------ fixture and helpers


def _service(root, pipeline, analyzer, research, blueprint) -> ProjectService:
    service = ProjectService(store=ProjectStore(root=root), pipeline=pipeline, analyzer=analyzer,
                             research=research, blueprint=blueprint)  # type: ignore[arg-type]
    service._sync_assignment_images = lambda *a, **k: []  # no image fetches
    return service


@pytest.fixture()
def env(economy, tmp_path, monkeypatch):  # noqa: F811
    import app as app_mod

    analyzer, research, blueprint = _WordsAnalyzer(500), _EditableResearch(), _BudgetBlueprint()
    service = _service(tmp_path / "projects", app_mod.assignment_pipeline, analyzer, research, blueprint)
    monkeypatch.setattr(app_mod, "project_service", service)
    monkeypatch.setattr(app_mod, "PROJECT_STORAGE_ROOT", tmp_path / "projects")
    return SimpleNamespace(app=app_mod, service=service, analyzer=analyzer, research=research,
                           blueprint=blueprint, wallet=app_mod.wallet, root=tmp_path / "projects")


def _fresh_worker(env, pipeline=None) -> ProjectService:
    """Another gunicorn worker: same disk and ledger, empty memory."""
    return _service(env.root, pipeline or AssignmentPipelineService(), env.analyzer, env.research, env.blueprint)


def _url(pid, suffix=""):
    return f"/api/assignment/projects/{pid}" + (f"/{suffix}" if suffix else "")


def _owner(env, email="owner@example.com", coins=1_000_000):
    owner = _user(email)
    env.wallet.credit(owner["id"], coins, "test_topup")
    return owner


def _project(env, owner) -> str:
    return env.service.create_project(
        user_id=str(owner["id"]), files=[{"file_type": "assignment_brief", "original_filename": "b.txt"}]
    ).project.id


def _priced(env, owner) -> tuple[str, object]:
    pid = _project(env, owner)
    client = _signed_in(_client(), owner)
    assert client.post(_url(pid, "analyze-requirements")).status_code == 200
    assert client.post(_url(pid, "pricing"), json={}).status_code == 200
    return pid, client


def _paid(env, owner) -> tuple[str, object, dict]:
    pid, client = _priced(env, owner)
    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]})
    assert res.status_code == 200, res.get_data(as_text=True)
    return pid, client, res.get_json()


def _quote(env, pid) -> dict:
    return dict(env.service.store.require_project(pid).artifacts["pricing"])


def _fair_coins(env, pid) -> int:
    return env.service._list_price(env.service.store.require_requirement(pid))["amount_coins"]


def _scope(env, pid) -> str:
    return env.service.scope_hash(env.service.store.require_bundle(pid))


def _debits(pid) -> list[int]:
    with economy_db.connect() as conn:
        rows = conn.execute(
            "SELECT amount FROM transactions WHERE kind = 'debit' AND feature = 'assignment' AND ref_id LIKE ?",
            (f"assignment-payment:{pid}:%",),
        ).fetchall()
    return [int(r["amount"]) for r in rows]


def _cycles(pid) -> list[dict]:
    with economy_db.connect() as conn:
        rows = conn.execute("SELECT * FROM assignment_payments WHERE project_id = ?", (pid,)).fetchall()
    return [dict(r) for r in rows]


def _disk(env, pid) -> dict:
    return json.loads((env.root / pid / "bundle.json").read_text(encoding="utf-8"))


def _assert_paid_scope_consistent(env, pid) -> None:
    """The live cycle is bound to exactly the inputs on disk, at the price the server computes."""
    cycle = payment_ledger.active_cycle(pid)
    assert cycle is not None
    assert cycle["scope_hash"] == _scope(env, pid)
    assert cycle["quoted_word_count"] == env.service.store.require_requirement(pid).word_count
    if cycle["method"] == payment_ledger.METHOD_COINS:
        assert cycle["coins"] == cycle["quoted_coins"] == _fair_coins(env, pid)


def _child_exit(queue, outcome):
    queue.put(outcome)
    queue.close()
    queue.join_thread()
    os._exit(0)


# ------------------------------------------------------------------ 1-8 pricing and re-analysis


def test_reanalysis_replaces_the_quote_and_the_new_price_is_charged(env):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    old = _quote(env, pid)
    assert old["word_count"] == 500 and old["scope_hash"] == _scope(env, pid)

    env.analyzer.words = 20000
    assert client.post(_url(pid, "analyze-requirements")).status_code == 200

    new = _quote(env, pid)
    assert new["quote_id"] != old["quote_id"]
    assert new["word_count"] == 20000 and new["scope_hash"] == _scope(env, pid)
    assert new["amount_coins"] == _fair_coins(env, pid) > 10 * old["amount_coins"]
    assert env.service.store.require_project(pid).price == new["amount_usd"]

    stale = client.post(_url(pid, "confirm-payment"), json={"quote_id": old["quote_id"]})
    assert stale.status_code == 409 and stale.get_json()["error"] == "PRICE_CHANGED"
    assert _debits(pid) == [] and _cycles(pid) == []

    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": new["quote_id"]})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["coins_charged"] == new["amount_coins"]
    _assert_paid_scope_consistent(env, pid)


def test_f02_documented_poc_charges_nothing_until_the_new_price_is_confirmed(env):
    """PoC: analyze, price, add a file, re-analyze to 20 000 words, confirm with an empty body."""
    owner = _owner(env)
    pid, client = _priced(env, owner)
    cheap = _quote(env, pid)["amount_coins"]
    balance = env.wallet.get_balance(owner["id"])
    env.analyzer.words = 20000
    assert client.post(_url(pid, "files"), json={"file_type": "assignment_brief",
                                                 "original_filename": "big.txt"}).status_code == 201
    assert client.post(_url(pid, "analyze-requirements")).status_code == 200
    res = client.post(_url(pid, "confirm-payment"))
    assert res.status_code == 409, res.get_data(as_text=True)
    assert res.get_json()["error"] == "QUOTE_REQUIRED" and res.get_json()["payment_confirmed"] is False
    shown = res.get_json()["project"]["project"]["artifacts"]["pricing"]
    assert shown["word_count"] == 20000 and shown["amount_coins"] == _fair_coins(env, pid)
    assert env.wallet.get_balance(owner["id"]) == balance and _debits(pid) == [] and _cycles(pid) == []

    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": shown["quote_id"]})
    assert res.status_code == 200, res.get_data(as_text=True)
    charged = res.get_json()["coins_charged"]
    assert charged == _fair_coins(env, pid) and charged > 10 * cheap
    _assert_paid_scope_consistent(env, pid)


def test_stale_pricing_snapshot_cannot_make_an_old_quote_payable(env):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    stale_project = env.service.store.require_project(pid).to_dict()
    env.analyzer.words = 20000
    assert client.post(_url(pid, "analyze-requirements")).status_code == 200

    # Another worker writes back its older project copy: old price and old quote. The store
    # refuses it; it is then put on disk directly, so the checks below still have to hold.
    from services.assignment_project.models import Project
    from services.assignment_project.store import ProjectUpdateConflictError
    from tests.assignment_helpers import plant_stale_project_json

    worker = _fresh_worker(env)
    with pytest.raises(ProjectUpdateConflictError):
        worker.store.save_project(Project.from_dict(stale_project))
    plant_stale_project_json(env.root, pid, stale_project)
    # And the in-memory pipeline is told Pricing finished with a forged amount.
    client.post(_url(pid, "stages/pricing/complete"), json={"pricing": {"amount_usd": 0.01}})

    restarted = _fresh_worker(env)
    restarted._ensure_pipeline_project(pid)
    assert restarted.pipeline.get_project(pid).stage_state(PipelineStage.PRICING).status != StageStatus.COMPLETED
    assert env.service._quote_problem(env.service.store.require_bundle(pid)) == "SCOPE_CHANGED"

    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": stale_project["artifacts"]["pricing"]["quote_id"]})
    assert res.status_code == 409, res.get_data(as_text=True)
    body = res.get_json()
    assert body["error"] == "PRICE_CHANGED" and body["reason"] == "SCOPE_CHANGED"
    assert body["project"]["project"]["artifacts"]["pricing"]["word_count"] == 20000
    assert _debits(pid) == []

    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]})
    assert res.status_code == 200 and res.get_json()["coins_charged"] == _fair_coins(env, pid)
    _assert_paid_scope_consistent(env, pid)


def test_sync_pipeline_state_does_not_restore_obsolete_pricing(env):
    owner = _owner(env)
    pid, _client_ = _priced(env, owner)
    project = env.service.store.require_project(pid)
    requirement = env.service.store.require_requirement(pid)
    requirement.word_count = 9000  # inputs changed without a new quote (stale write)
    env.service.store.save_requirement(requirement)
    env.service.store.save_project(project)

    worker = _fresh_worker(env)
    worker._ensure_pipeline_project(pid)
    worker.sync_pipeline_state(pid)
    pipeline = worker.pipeline.get_project(pid)
    assert pipeline.stage_state(PipelineStage.PRICING).status == StageStatus.PENDING
    assert pipeline.stage_state(PipelineStage.WAITING_FOR_PAYMENT).status == StageStatus.PENDING
    with pytest.raises(Exception) as exc:
        worker.check_payment_ready(pid)
    assert getattr(exc.value, "code", "") == "PRICE_CHANGED"

    # The worker that priced it had Pricing completed in memory; that is withdrawn as well.
    env.service._ensure_pipeline_project(pid)
    own = env.service.pipeline.get_project(pid)
    assert own.stage_state(PipelineStage.PRICING).status == StageStatus.PENDING


def test_forged_client_price_fields_are_ignored(env):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    env.analyzer.words = 20000
    client.post(_url(pid, "analyze-requirements"))
    forged = {"amount_usd": 0.01, "amount_coins": 1, "price": 0.01, "coins": 1, "credits": 1, "word_count": 1,
              "currency": "XTS", "plan": "pro", "status": "paid", "payment_confirmed": True,
              "pricing": {"amount_usd": 0.01, "amount_coins": 1, "word_count": 1}}
    assert client.post(_url(pid, "pricing"), json=forged).status_code == 200
    res = client.post(_url(pid, "confirm-payment"), json=forged)
    assert res.status_code == 409 and res.get_json()["error"] == "QUOTE_REQUIRED"
    assert _debits(pid) == []
    res = client.post(_url(pid, "confirm-payment"), json={**forged, "quote_id": _quote(env, pid)["quote_id"]})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["coins_charged"] == _fair_coins(env, pid)
    assert _debits(pid) == [_fair_coins(env, pid)]
    _assert_paid_scope_consistent(env, pid)


# ------------------------------------------------------------------ 9-15 analysis/payment races


def _child_analyze(queue, owner, pid):
    outcome = "error"
    try:
        res = _signed_in(_client(), owner).post(_url(pid, "analyze-requirements"))
        outcome = (res.status_code, (res.get_json() or {}).get("error"))
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {type(exc).__name__}: {exc}"
    finally:
        _child_exit(queue, outcome)


def test_analysis_finishing_after_payment_in_another_process_is_dropped(env):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    env.analyzer.words = 20000
    env.analyzer.entered, env.analyzer.release = FORK.Event(), FORK.Event()
    queue = FORK.Queue()
    proc = FORK.Process(target=_child_analyze, args=(queue, owner, pid))
    proc.start()
    assert env.analyzer.entered.wait(WAIT)  # the other worker is inside the AI call

    paid = client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]})
    assert paid.status_code == 200, paid.get_data(as_text=True)
    env.analyzer.release.set()
    outcome = queue.get(timeout=WAIT)
    proc.join(WAIT)
    env.analyzer.entered = env.analyzer.release = None

    assert outcome == (409, "REQUIREMENTS_LOCKED")
    assert env.service.store.require_requirement(pid).word_count == 500
    assert _disk(env, pid)["requirement"]["word_count"] == 500
    _assert_paid_scope_consistent(env, pid)
    assert env.service._require_payment(pid, "test") == 500
    env.service.run_research(pid)
    env.service.run_blueprint(pid)
    assert env.blueprint.seen[-1]["requirement"]["word_count"] == 500


def _child_add_file(queue, owner, pid):
    outcome = "error"
    try:
        res = _signed_in(_client(), owner).post(_url(pid, "files"), json={"file_type": "rubric",
                                                                          "original_filename": "r.txt"})
        outcome = (res.status_code, (res.get_json() or {}).get("error"))
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {type(exc).__name__}: {exc}"
    finally:
        _child_exit(queue, outcome)


def test_file_added_in_another_process_serializes_before_confirmation(env, monkeypatch):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    seen_quote = _quote(env, pid)["quote_id"]
    entered, release = FORK.Event(), FORK.Event()
    real_add = ProjectService._add_file_record

    def parked_add(self, *args, **kwargs):
        record = real_add(self, *args, **kwargs)
        entered.set()
        assert release.wait(WAIT)
        return record

    monkeypatch.setattr(ProjectService, "_add_file_record", parked_add)
    queue = FORK.Queue()
    proc = FORK.Process(target=_child_add_file, args=(queue, owner, pid))
    proc.start()
    assert entered.wait(WAIT)  # the other worker holds the billing lock mid-mutation

    result = {}
    confirm = threading.Thread(target=lambda: result.update(res=_signed_in(_client(), owner).post(
        _url(pid, "confirm-payment"), json={"quote_id": seen_quote})))
    confirm.start()
    confirm.join(1.0)
    assert confirm.is_alive(), "confirmation must wait for the file mutation"
    release.set()
    assert queue.get(timeout=WAIT) == (201, None)
    proc.join(WAIT)
    confirm.join(WAIT)

    res = result["res"]
    assert res.status_code == 409 and res.get_json()["error"] == "PRICE_CHANGED"
    assert _debits(pid) == [] and payment_ledger.active_cycle(pid) is None
    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]})
    assert res.status_code == 200
    assert len(env.service.store.list_files(pid)) == 2
    _assert_paid_scope_consistent(env, pid)


def _child_confirm(queue, owner, pid, quote_id):
    outcome = "error"
    try:
        res = _signed_in(_client(), owner).post(_url(pid, "confirm-payment"), json={"quote_id": quote_id})
        body = res.get_json() or {}
        outcome = (res.status_code, body.get("coins_charged"), body.get("error"))
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {type(exc).__name__}: {exc}"
    finally:
        _child_exit(queue, outcome)


def test_confirmation_in_another_process_serializes_before_a_file_mutation(env, monkeypatch):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    entered, release = FORK.Event(), FORK.Event()
    real_open = payment_ledger.open_cycle

    def parked_open(*args, **kwargs):
        entered.set()
        assert release.wait(WAIT)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(payment_ledger, "open_cycle", parked_open)
    queue = FORK.Queue()
    proc = FORK.Process(target=_child_confirm, args=(queue, owner, pid, _quote(env, pid)["quote_id"]))
    proc.start()
    assert entered.wait(WAIT)

    result = {}
    adder = threading.Thread(target=lambda: result.update(res=_signed_in(_client(), owner).post(
        _url(pid, "files"), json={"file_type": "rubric", "original_filename": "late.txt"})))
    adder.start()
    adder.join(1.0)
    assert adder.is_alive(), "the file mutation must wait for the confirmation"
    release.set()
    status, charged, _err = queue.get(timeout=WAIT)
    proc.join(WAIT)
    adder.join(WAIT)

    assert status == 200 and charged == _fair_coins(env, pid)
    assert result["res"].status_code == 409 and result["res"].get_json()["error"] == "REQUIREMENTS_LOCKED"
    assert len(env.service.store.list_files(pid)) == 1
    _assert_paid_scope_consistent(env, pid)


def _child_brief(queue, barrier, owner, pid, words):
    outcome = "error"
    try:
        client = _signed_in(_client(), owner)
        barrier.wait()
        res = client.post(_url(pid, "brief"), json={"word_count": words})
        outcome = res.status_code
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {type(exc).__name__}: {exc}"
    finally:
        _child_exit(queue, outcome)


def _child_file_barrier(queue, barrier, owner, pid, name):
    outcome = "error"
    try:
        client = _signed_in(_client(), owner)
        barrier.wait()
        res = client.post(_url(pid, "files"), json={"file_type": "rubric", "original_filename": name})
        outcome = res.status_code
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {type(exc).__name__}: {exc}"
    finally:
        _child_exit(queue, outcome)


def test_concurrent_price_mutations_leave_no_stale_quote(env):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    queue, barrier = FORK.Queue(), FORK.Barrier(4)
    procs = [
        FORK.Process(target=_child_brief, args=(queue, barrier, owner, pid, 1500)),
        FORK.Process(target=_child_brief, args=(queue, barrier, owner, pid, 7000)),
        FORK.Process(target=_child_file_barrier, args=(queue, barrier, owner, pid, "a.txt")),
        FORK.Process(target=_child_file_barrier, args=(queue, barrier, owner, pid, "b.txt")),
    ]
    for proc in procs:
        proc.start()
    outcomes = sorted(queue.get(timeout=WAIT) for _ in procs)
    for proc in procs:
        proc.join(WAIT)

    assert outcomes == [200, 200, 201, 201]
    bundle = env.service.store.require_bundle(pid)
    assert len(bundle.files) == 3
    assert env.service._quote_problem(bundle) is None
    assert _quote(env, pid)["word_count"] == bundle.requirement.word_count in (1500, 7000)
    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]})
    assert res.status_code == 200
    _assert_paid_scope_consistent(env, pid)


def test_worker_restart_after_payment_keeps_the_paid_scope(env):
    owner = _owner(env)
    pid, _client_, _body = _paid(env, owner)
    worker = _fresh_worker(env)
    worker._ensure_pipeline_project(pid)
    pipeline = worker.pipeline.get_project(pid)
    assert pipeline.stage_state(PipelineStage.PRICING).status == StageStatus.COMPLETED
    assert pipeline.stage_state(PipelineStage.WAITING_FOR_PAYMENT).status == StageStatus.COMPLETED
    env.analyzer.words = 20000
    calls = env.analyzer.calls
    with pytest.raises(RequirementsLockedError):
        worker.analyze_requirements(pid)
    assert env.analyzer.calls == calls
    assert worker._require_payment(pid, "test") == 500
    worker.run_research(pid)
    _assert_paid_scope_consistent(env, pid)


def test_worker_restart_between_pricing_and_payment_keeps_the_quote(env):
    owner = _owner(env)
    pid, _client_ = _priced(env, owner)
    quote = _quote(env, pid)
    worker = _fresh_worker(env)
    worker._ensure_pipeline_project(pid)
    assert worker.pipeline.get_project(pid).stage_state(PipelineStage.PRICING).status == StageStatus.COMPLETED
    assert worker.payable_quote(pid, quote_id=quote["quote_id"])["quote_id"] == quote["quote_id"]


# ------------------------------------------------------------------ 16-24 payment confirmation


def test_exact_quote_is_charged_and_bound_to_the_cycle(env):
    owner = _owner(env)
    pid, _client_, body = _paid(env, owner)
    quote = _quote(env, pid)
    cycle = payment_ledger.active_cycle(pid)
    assert body["coins_charged"] == quote["amount_coins"] == cycle["quoted_coins"]
    assert cycle["quote_id"] == quote["quote_id"]
    assert env.service.store.require_project(pid).artifacts["payment_quote_id"] == quote["quote_id"]
    _assert_paid_scope_consistent(env, pid)


@pytest.mark.parametrize(
    "tamper, reason",
    [
        (lambda p, q: (setattr(p, "price", q["amount_usd"] / 10), q.update(amount_usd=q["amount_usd"] / 10,
                                                                        amount_coins=q["amount_coins"] // 10)),
         "AMOUNT_CHANGED"),
        (lambda p, q: (setattr(p, "price", q["amount_usd"] * 10), q.update(amount_usd=q["amount_usd"] * 10,
                                                                        amount_coins=q["amount_coins"] * 10)),
         "AMOUNT_CHANGED"),
        (lambda p, q: q.update(currency="EUR"), "CURRENCY_CHANGED"),
        (lambda p, q: q.update(word_count=100), "AMOUNT_CHANGED"),
        (lambda p, q: q.update(scope_hash="0" * 64), "SCOPE_CHANGED"),
        (lambda p, q: q.pop("quote_id"), "QUOTE_MISSING"),
    ],
    ids=["stale_lower_amount", "forged_higher_amount", "changed_currency", "changed_volume", "changed_scope",
         "legacy_without_quote"],
)
def test_tampered_stored_quote_is_refused_and_replaced(env, tamper, reason):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    project = env.service.store.require_project(pid)
    quote = dict(project.artifacts["pricing"])
    seen_quote = quote["quote_id"]
    tamper(project, quote)
    project.artifacts["pricing"] = quote
    env.service.store.save_project(project)
    balance = env.wallet.get_balance(owner["id"])

    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": seen_quote})
    assert res.status_code == 409, res.get_data(as_text=True)
    assert res.get_json()["error"] == "PRICE_CHANGED" and res.get_json()["reason"] == reason
    assert env.wallet.get_balance(owner["id"]) == balance and _debits(pid) == [] and _cycles(pid) == []
    assert env.service.store.require_project(pid).artifacts.get("payment_confirmed") is not True
    assert env.service._quote_problem(env.service.store.require_bundle(pid)) is None  # re-quoted

    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]})
    assert res.status_code == 200 and res.get_json()["coins_charged"] == _fair_coins(env, pid)
    _assert_paid_scope_consistent(env, pid)


def test_quote_from_another_project_is_refused(env):
    owner = _owner(env)
    pid_a, client = _priced(env, owner)
    pid_b, _ = _priced(env, owner)
    quote_b = _quote(env, pid_b)

    res = client.post(_url(pid_a, "confirm-payment"), json={"quote_id": quote_b["quote_id"]})
    assert res.status_code == 409 and res.get_json()["reason"] == "QUOTE_SUPERSEDED"

    project_a = env.service.store.require_project(pid_a)
    project_a.artifacts["pricing"] = dict(quote_b)  # copied wholesale, same price and volume
    env.service.store.save_project(project_a)
    res = client.post(_url(pid_a, "confirm-payment"), json={"quote_id": quote_b["quote_id"]})
    assert res.status_code == 409 and res.get_json()["reason"] == "QUOTE_OTHER_PROJECT"
    assert _debits(pid_a) == [] and _debits(pid_b) == []


def test_invalidated_quote_version_and_malformed_references_are_refused(env):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    first = _quote(env, pid)["quote_id"]
    assert client.post(_url(pid, "brief"), json={"word_count": 800}).status_code == 200
    assert _quote(env, pid)["quote_id"] != first

    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": first})
    assert res.status_code == 409 and res.get_json()["reason"] == "QUOTE_SUPERSEDED"
    for bad in (123, "", "x" * 65, ["q"], {"id": first}):
        res = client.post(_url(pid, "confirm-payment"), json={"quote_id": bad})
        assert res.status_code == 400, bad
    assert _debits(pid) == [] and _cycles(pid) == []


def test_duplicate_confirmations_debit_once(env):
    owner = _owner(env)
    pid, client, body = _paid(env, owner)
    again = client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]})
    stale = client.post(_url(pid, "confirm-payment"), json={})
    assert again.status_code == 200 and again.get_json()["coins_charged"] == body["coins_charged"] > 0
    assert again.get_json()["charged_now"] == 0 and again.get_json()["idempotent_replay"] is True
    assert stale.status_code == 409 and stale.get_json()["error"] == "QUOTE_REQUIRED"
    assert _debits(pid) == [body["coins_charged"]] and len(_cycles(pid)) == 1


def _child_confirm_barrier(queue, barrier, owner, pid, quote_id):
    outcome = "error"
    try:
        client = _signed_in(_client(), owner)
        barrier.wait()
        res = client.post(_url(pid, "confirm-payment"), json={"quote_id": quote_id})
        outcome = (res.status_code, (res.get_json() or {}).get("coins_charged"))
    except BaseException as exc:  # noqa: BLE001
        outcome = f"error: {type(exc).__name__}: {exc}"
    finally:
        _child_exit(queue, outcome)


def test_simultaneous_confirmations_from_separate_processes_debit_once(env):
    owner = _owner(env)
    pid, _client_ = _priced(env, owner)
    quote = _quote(env, pid)
    queue, barrier = FORK.Queue(), FORK.Barrier(6)
    procs = [FORK.Process(target=_child_confirm_barrier, args=(queue, barrier, owner, pid, quote["quote_id"]))
             for _ in range(6)]
    for proc in procs:
        proc.start()
    outcomes = [queue.get(timeout=WAIT) for _ in procs]
    for proc in procs:
        proc.join(WAIT)

    # One debit; every other confirmation of the same quote is a replay reporting that debit.
    assert outcomes == [(200, quote["amount_coins"])] * 6, outcomes
    assert _debits(pid) == [quote["amount_coins"]] and len(_cycles(pid)) == 1
    _assert_paid_scope_consistent(env, pid)


@pytest.mark.parametrize("cycle_scope", ["0" * 64, None], ids=["other_scope", "legacy_unbound"])
def test_live_payment_for_a_different_scope_is_reconciled_not_granted(env, cycle_scope):
    """A payment the ledger already took (crash before the JSON was marked) for other inputs."""
    owner = _owner(env)
    pid, client = _priced(env, owner)
    quote = _quote(env, pid)
    foreign = {**quote, "scope_hash": cycle_scope} if cycle_scope else None
    cycle = payment_ledger.open_cycle(int(owner["id"]), pid, coins=77, allowance=allowance_rule(int(owner["id"]),
                                      "assignment"), quote=foreign)
    balance = env.wallet.get_balance(owner["id"])

    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": quote["quote_id"]})
    assert res.status_code == 409, res.get_data(as_text=True)
    assert res.get_json()["error"] == "PAYMENT_SCOPE_MISMATCH"
    assert env.wallet.get_balance(owner["id"]) == balance  # no second debit and no automatic refund
    assert _debits(pid) == [77]
    assert payment_ledger.get_cycle(cycle["cycle_id"])["status"] == payment_ledger.STATUS_ACTIVE
    art = env.service.store.require_project(pid).artifacts
    assert art.get("payment_confirmed") is not True
    assert art["refund_review_required"]["reason"] == "payment_cycle_scope_mismatch"
    with pytest.raises(PaymentRequiredError):
        env.service.run_research(pid)
    assert env.research.calls == 0


# ------------------------------------------------------------------ 25-30 post-payment mutations


def test_adding_a_file_after_payment_is_refused(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    res = client.post(_url(pid, "files"), json={"file_type": "assignment_brief", "original_filename": "x.txt"})
    assert res.status_code == 409 and res.get_json()["error"] == "REQUIREMENTS_LOCKED"
    with pytest.raises(RequirementsLockedError):
        env.service.add_file(pid, file_type="rubric", original_filename="direct.txt")
    assert len(env.service.store.list_files(pid)) == 1
    _assert_paid_scope_consistent(env, pid)


def test_no_route_replaces_or_removes_files_of_a_paid_project(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    file_id = env.service.store.list_files(pid)[0].id
    for method in ("put", "patch", "delete"):
        res = getattr(client, method)(_url(pid, f"files/{file_id}"), json={"original_filename": "swap.txt"})
        assert res.status_code in (404, 405), (method, res.status_code)
        res = getattr(client, method)(_url(pid, "files"), json={"original_filename": "swap.txt"})
        assert res.status_code in (404, 405), (method, res.status_code)
    assert [f.id for f in env.service.store.list_files(pid)] == [file_id]
    _assert_paid_scope_consistent(env, pid)


@pytest.mark.parametrize("change", ["replace", "remove", "alter"])
def test_files_changed_behind_the_service_stop_paid_stages(env, change):
    owner = _owner(env)
    pid, _client_, _ = _paid(env, owner)
    data = _disk(env, pid)
    if change == "replace":
        data["files"][0]["id"] = "swapped-file"
    elif change == "remove":
        data["files"] = []
    else:
        data["requirement"]["word_count"] = 20000
    (env.root / pid / "bundle.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PaidScopeError):
        env.service.run_research(pid)
    assert env.research.calls == 0
    client = _signed_in(_client(), owner)
    res = client.post(_url(pid, "research"), json={})
    assert res.status_code in (400, 502) and env.research.calls == 0


def test_reanalysis_after_payment_is_refused_without_an_ai_call(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.analyzer.words = 20000
    calls = env.analyzer.calls
    res = client.post(_url(pid, "analyze-requirements"))
    assert res.status_code == 409 and res.get_json()["error"] == "REQUIREMENTS_LOCKED"
    assert env.analyzer.calls == calls
    assert env.service.store.require_requirement(pid).word_count == 500
    _assert_paid_scope_consistent(env, pid)


def test_f02b_documented_poc_cannot_inflate_the_paid_scope(env):
    """PoC: pay for 500 words, re-analyze to 20 000, run the paid stages."""
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.analyzer.words = 20000
    assert client.post(_url(pid, "analyze-requirements")).status_code == 409
    env.service.run_research(pid)
    env.service.run_blueprint(pid)
    assert env.service.store.require_requirement(pid).word_count == 500
    assert env.blueprint.seen[-1]["requirement"]["word_count"] == 500
    _assert_paid_scope_consistent(env, pid)


def test_billable_metadata_cannot_change_after_payment(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    before = _quote(env, pid)
    for suffix, body in (("brief", {"word_count": 20000}), ("brief", {"assignment_type": "Dissertation"}),
                         ("pricing", {"priority": "urgent"})):
        res = client.post(_url(pid, suffix), json=body)
        assert res.status_code == 409 and res.get_json()["error"] == "REQUIREMENTS_LOCKED", (suffix, body)
    assert _quote(env, pid) == before
    _assert_paid_scope_consistent(env, pid)


def test_ledger_outage_leaves_billable_inputs_unchanged(env, monkeypatch):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    before = _disk(env, pid)

    def down(_pid):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(payment_ledger, "live_cycle", down)
    for suffix, body in (("files", {"file_type": "rubric", "original_filename": "x"}),
                         ("brief", {"word_count": 900}), ("pricing", {}), ("analyze-requirements", None)):
        res = client.post(_url(pid, suffix), json=body)
        assert res.status_code == 503 and res.get_json()["error"] == "PAYMENT_UNAVAILABLE", suffix
    after = _disk(env, pid)
    assert after["files"] == before["files"] and after["requirement"] == before["requirement"]
    assert after["project"]["artifacts"]["pricing"] == before["project"]["artifacts"]["pricing"]


def test_lost_payment_json_still_locks_inputs_through_the_ledger(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    project = env.service.store.require_project(pid)
    project.artifacts.pop("payment_confirmed")  # a stale write dropped the JSON flag
    env.service.store.save_project(project)
    res = client.post(_url(pid, "analyze-requirements"))
    assert res.status_code == 409 and res.get_json()["error"] == "REQUIREMENTS_LOCKED"
    res = client.post(_url(pid, "files"), json={"file_type": "rubric", "original_filename": "x"})
    assert res.status_code == 409
    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]})
    assert res.status_code == 200 and res.get_json()["charged_now"] == 0
    assert res.get_json()["coins_charged"] == _debits(pid)[0]  # the live payment's own debit
    assert len(_debits(pid)) == 1


def test_failed_recovery_of_a_live_payment_neither_refunds_nor_charges(env, monkeypatch):
    owner = _owner(env)
    pid, client, body = _paid(env, owner)
    project = env.service.store.require_project(pid)
    project.artifacts.pop("payment_confirmed")  # worker died after the debit, before the JSON
    env.service.store.save_project(project)
    balance = env.wallet.get_balance(owner["id"])

    def broken(_pid, *, cycle=None, quote_id=None):
        raise ValueError("pipeline unavailable")

    monkeypatch.setattr(env.service, "confirm_payment", broken)
    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]})
    assert res.status_code == 400
    assert env.wallet.get_balance(owner["id"]) == balance
    cycle = payment_ledger.active_cycle(pid)
    assert cycle is not None and cycle["coins"] == body["coins_charged"]
    monkeypatch.delattr(env.service, "confirm_payment")
    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]})
    assert res.status_code == 200 and res.get_json()["charged_now"] == 0
    assert res.get_json()["coins_charged"] == body["coins_charged"]
    assert env.wallet.get_balance(owner["id"]) == balance
    assert _debits(pid) == [body["coins_charged"]]


def test_refunded_payment_cannot_be_revived_by_stale_json(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    stale = env.service.store.require_project(pid).to_dict()
    admin = _user("admin@example.com", admin=True)
    res = _signed_in(_client(), admin).post(f"/api/admin/assignment/projects/{pid}/refund", json={"reason": "t"})
    assert res.status_code == 200, res.get_data(as_text=True)

    from services.assignment_project.models import Project
    from services.assignment_project.store import ProjectUpdateConflictError
    from tests.assignment_helpers import plant_stale_project_json

    with pytest.raises(ProjectUpdateConflictError):
        ProjectStore(root=env.root).save_project(Project.from_dict(stale))
    plant_stale_project_json(env.root, pid, stale)  # paid JSON written back
    assert env.service.store.require_project(pid).artifacts["payment_confirmed"] is True
    with pytest.raises(PaymentRequiredError):
        env.service.run_research(pid)
    assert env.research.calls == 0
    balance = env.wallet.get_balance(owner["id"])
    res = client.post(_url(pid, "research"), json={})
    assert res.status_code in (400, 404) and env.research.calls == 0
    assert env.wallet.get_balance(owner["id"]) == balance


# ------------------------------------------------------------------ legacy payments and migration


def _legacy_paid(env, owner, *, keep_pricing=True) -> str:
    """A project paid before quotes existed: unbound cycle, pricing without quote fields."""
    pid, _client_ = _priced(env, owner)
    cycle = payment_ledger.open_cycle(int(owner["id"]), pid, coins=_fair_coins(env, pid), allowance=None)
    project = env.service.store.require_project(pid)
    pricing = project.artifacts.pop("pricing")
    if keep_pricing:
        project.artifacts["pricing"] = {k: v for k, v in pricing.items()
                                        if k not in ("quote_id", "scope_hash", "project_id", "quoted_at")}
    project.artifacts.update(payment_confirmed=True, payment_cycle_id=cycle["cycle_id"])
    env.service.store.save_project(project)
    return pid


def test_legacy_payment_matching_its_priced_volume_is_bound_once(env):
    owner = _owner(env)
    pid = _legacy_paid(env, owner)
    assert payment_ledger.active_cycle(pid)["scope_hash"] is None
    env.service.run_research(pid)
    cycle = payment_ledger.active_cycle(pid)
    assert cycle["scope_hash"] == _scope(env, pid) and cycle["quoted_word_count"] == 500

    requirement = env.service.store.require_requirement(pid)
    requirement.word_count = 20000  # later stale write
    env.service.store.save_requirement(requirement)
    with pytest.raises(PaidScopeError):
        env.service.run_blueprint(pid)
    assert payment_ledger.active_cycle(pid)["scope_hash"] == cycle["scope_hash"]


def test_legacy_payment_already_inflated_fails_closed(env):
    owner = _owner(env)
    pid = _legacy_paid(env, owner)
    requirement = env.service.store.require_requirement(pid)
    requirement.word_count = 20000  # re-analysed after payment by an older build
    env.service.store.save_requirement(requirement)
    with pytest.raises(PaidScopeError):
        env.service.run_research(pid)
    assert env.research.calls == 0
    assert payment_ledger.active_cycle(pid)["scope_hash"] is None


def test_legacy_payment_without_pricing_fails_closed(env):
    owner = _owner(env)
    pid = _legacy_paid(env, owner, keep_pricing=False)
    with pytest.raises(PaidScopeError):
        env.service.run_research(pid)
    assert env.research.calls == 0


def test_quote_columns_migration_is_idempotent_and_keeps_rows(tmp_path, monkeypatch):
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
            created_at TEXT NOT NULL DEFAULT (datetime('now')), closed_at TEXT,
            output_tracking INTEGER NOT NULL DEFAULT 1
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

    row = payment_ledger.get_cycle("old-cycle")
    assert row["coins"] == 100 and row["status"] == "active" and row["output_tracking"] == 1
    assert row["quote_id"] is None and row["scope_hash"] is None and row["quoted_word_count"] is None
    assert payment_ledger.bind_cycle_scope("old-project", "old-cycle", scope_hash="h1", word_count=500)
    assert not payment_ledger.bind_cycle_scope("old-project", "old-cycle", scope_hash="h2", word_count=900)
    assert payment_ledger.get_cycle("old-cycle")["scope_hash"] == "h1"


# ------------------------------------------------------------------ 31-36 F-10


SECTIONS_100 = [{"title": f"Section {i}", "description": "", "purpose": "", "estimated_words": 40}
                for i in range(100)]


def test_f10_patched_plan_failure_is_not_refundable(env):
    """PoC: PATCH the research plan, crash the blueprint on it, claim the automatic refund."""
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.service.run_research(pid)
    res = client.patch(_url(pid, "research-plan"), json={"assignment_topic": "INJECTED-BY-CLIENT"})
    assert res.status_code == 200
    art = env.service.store.require_project(pid).artifacts
    assert art[RESEARCH_PLAN_SOURCE_KEY] == "client"
    assert art["research_plan"]["assignment_topic"] == "INJECTED-BY-CLIENT"

    env.blueprint.crash = True
    assert client.post(_url(pid, "blueprint"), json={}).status_code == 502
    env.blueprint.crash = False
    assert "INJECTED-BY-CLIENT" in json.dumps(env.blueprint.seen[-1]["plan"])
    failure = env.service.store.require_project(pid).artifacts[PROCESSING_FAILURE_KEY]
    assert failure["client_seeded"] is True
    balance = env.wallet.get_balance(owner["id"])
    refund = client.post(_url(pid, "refund-failed"), json={})
    assert refund.status_code == 400, refund.get_data(as_text=True)
    assert env.wallet.get_balance(owner["id"]) == balance


def test_f10_server_plan_failure_still_refunds(env):
    owner = _owner(env)
    pid, client, body = _paid(env, owner)
    env.service.run_research(pid)
    env.blueprint.crash = True
    assert client.post(_url(pid, "blueprint"), json={}).status_code == 502
    env.blueprint.crash = False
    assert env.service.store.require_project(pid).artifacts[PROCESSING_FAILURE_KEY]["client_seeded"] is False
    balance = env.wallet.get_balance(owner["id"])
    refund = client.post(_url(pid, "refund-failed"), json={})
    assert refund.status_code == 200, refund.get_data(as_text=True)
    assert env.wallet.get_balance(owner["id"]) == balance + body["coins_charged"]


def test_f10_edit_in_one_worker_is_client_input_in_another(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.service.run_research(pid)
    client.patch(_url(pid, "research-plan"), json={"assignment_topic": "EDITED"})
    worker = _fresh_worker(env, pipeline=env.service.pipeline)
    worker.research = _EditableResearch()  # empty memory: only the stored plan is available
    env.blueprint.crash = True
    with pytest.raises(RuntimeError):
        worker.run_blueprint(pid)
    env.blueprint.crash = False
    assert "EDITED" in json.dumps(env.blueprint.seen[-1]["plan"])
    assert worker.store.require_project(pid).artifacts[PROCESSING_FAILURE_KEY]["client_seeded"] is True


def test_f10_stale_snapshot_cannot_relabel_an_edited_plan_as_server(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    env.service.run_research(pid)
    server_snapshot = dict(env.service.store.require_project(pid).artifacts["research_plan"])
    client.patch(_url(pid, "research-plan"), json={"assignment_topic": "EDITED"})
    # A stale worker writes back its older artifacts: server label and the unedited plan.
    project = env.service.store.require_project(pid)
    project.artifacts["research_plan"] = server_snapshot
    project.artifacts[RESEARCH_PLAN_SOURCE_KEY] = "server"
    env.service.store.save_project(project)

    # The recorded current plan is the edited one, so the reverted copy is never executed.
    seen = len(env.blueprint.seen)
    env.blueprint.crash = True
    with pytest.raises(ResearchPlanChangedError):
        env.service.run_blueprint(pid)
    env.blueprint.crash = False
    assert len(env.blueprint.seen) == seen
    assert PROCESSING_FAILURE_KEY not in env.service.store.require_project(pid).artifacts


def test_client_plan_cannot_raise_the_paid_length(env):
    """Alternate volume route: a plan with many sections, each with the engine's word minimum."""
    owner = _owner(env)
    pid, client, body = _paid(env, owner)
    env.service.run_research(pid)
    assert client.patch(_url(pid, "research-plan"), json={"section_list": SECTIONS_100}).status_code == 200
    res = client.post(_url(pid, "blueprint"), json={})
    assert res.status_code == 502
    art = env.service.store.require_project(pid).artifacts
    assert "blueprint" not in art
    assert art[PROCESSING_FAILURE_KEY]["client_seeded"] is True
    with pytest.raises(KeyError):
        env.service.get_blueprint(pid)
    refund = client.post(_url(pid, "refund-failed"), json={})
    assert refund.status_code == 400


def test_seeded_plan_without_stated_length_is_budgeted_to_the_paid_default(env):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    requirement = env.service.store.require_requirement(pid)
    requirement.word_count = None  # brief without a stated length: priced at the default
    env.service.store.save_requirement(requirement)
    client.post(_url(pid, "pricing"), json={})
    paid_words = _quote(env, pid)["word_count"]
    assert client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]}).status_code == 200
    seed = {"id": "seed", "assignment_topic": "Seeded", "section_list": SECTIONS_100[:10]}
    res = client.post(_url(pid, "blueprint"), json={"research_plan": seed})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert env.blueprint.seen[-1]["requirement"]["word_count"] == paid_words
    assert res.get_json()["blueprint"]["total_target_words"] <= paid_words


# ------------------------------------------------------------------ 33-36 F-16


def test_f16_cached_bundle_save_cannot_resurrect_cleared_state(env):
    """PoC: worker A cached a failure; worker B's retry cleared it; A then saves the requirement."""
    owner = _owner(env)
    pid, _client_, _ = _paid(env, owner)
    store_a, store_b = ProjectStore(root=env.root), ProjectStore(root=env.root)
    project_a = store_a.require_project(pid)
    project_a.artifacts[PROCESSING_FAILURE_KEY] = {"stage": "writing", "client_seeded": False}
    store_a.save_project(project_a)

    project_b = store_b.require_project(pid)
    project_b.artifacts.pop(PROCESSING_FAILURE_KEY)
    project_b.artifacts["writer_session_id"] = "retry-succeeded"
    store_b.save_project(project_b)

    store_a.save_requirement(store_a._requirements[pid])
    from services.assignment_project.models import ProjectFile

    store_a.save_file(ProjectFile.from_dict({**store_a._files[pid][0].to_dict(), "id": "f2"}))
    art = _disk(env, pid)["project"]["artifacts"]
    assert PROCESSING_FAILURE_KEY not in art
    assert art["writer_session_id"] == "retry-succeeded"


def test_f16_analysis_snapshot_does_not_overwrite_concurrent_changes(env):
    """Alternate route: the project read before the AI call is not written back after it."""
    owner = _owner(env)
    pid = _project(env, owner)
    entered, release = threading.Event(), threading.Event()
    env.analyzer.entered, env.analyzer.release = entered, release
    result = {}
    th = threading.Thread(target=lambda: result.update(bundle=env.service.analyze_requirements(pid)))
    th.start()
    assert entered.wait(WAIT)
    other = ProjectStore(root=env.root)
    project = other.require_project(pid)
    project.artifacts["chat_transcript"] = ["written meanwhile"]
    other.save_project(project)
    release.set()
    th.join(WAIT)
    env.analyzer.entered = env.analyzer.release = None
    assert _disk(env, pid)["project"]["artifacts"]["chat_transcript"] == ["written meanwhile"]


def test_f16_image_sync_writes_onto_the_current_project(env, monkeypatch):
    owner = _owner(env)
    pid = _project(env, owner)
    service = ProjectService(store=ProjectStore(root=env.root), pipeline=AssignmentPipelineService(),
                             analyzer=env.analyzer)

    def slow_images(files, *, project_id=None, **_kw):
        other = ProjectStore(root=env.root)
        project = other.require_project(project_id)
        project.artifacts["payment_review_note"] = "written meanwhile"
        other.save_project(project)
        return []

    import services.assignment_figures as figures

    monkeypatch.setattr(figures, "collect_assignment_images", slow_images)
    service._sync_assignment_images(pid)
    assert _disk(env, pid)["project"]["artifacts"]["payment_review_note"] == "written meanwhile"
