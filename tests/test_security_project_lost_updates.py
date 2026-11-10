"""F-16: concurrent project updates are never lost and never bring back stale security state.

Every concurrent writer is a forked process with its own ProjectStore (a separate gunicorn
worker with its own flock handles and memory). Orderings come from barriers and events, and
crash points from patched os calls followed by os._exit. AI steps are fakes; nothing leaves
the machine.
"""

from __future__ import annotations

import copy
import fcntl
import json
import multiprocessing
import os
import signal
import threading
import traceback
import uuid

import pytest

from services.assignment_pipeline.models import PipelineStage, utc_now
from services.assignment_project import project_lock
from services.assignment_project.models import Project, ProjectFile, ProjectStatus, RequirementJSON
from services.assignment_project.project_lock import (
    BILLING_LOCK,
    BUNDLE_LOCK,
    DOCUMENT_LOCK,
    LockOrderError,
    payment_gate,
    project_file_lock,
)
from services.assignment_project.service import (
    DELIVERY_SCOPE_KEY,
    OUTPUT_GENERATED_KEY,
    PAYMENT_CYCLE_KEY,
    PROCESSING_FAILURE_KEY,
    RESEARCH_PLAN_SOURCE_KEY,
    PaymentRequiredError,
    ProjectChangedError,
    ProjectService,
)
from services.assignment_project.store import (
    ProjectBundleCorruptError,
    ProjectStore,
    ProjectUpdateConflictError,
)
from services.economy import assignment_payments as payment_ledger
from tests.assignment_helpers import plant_stale_project_json
from tests.test_security_delivery_scope_guard import dv  # noqa: F401
from tests.test_security_paid_pipelines import _client, _signed_in, _user, economy  # noqa: F401
from tests.test_security_payment_scope_integrity import _owner, _paid, _priced, _quote, _url, env  # noqa: F401
from tests.test_security_quote_scope_provenance import PAID_WORDS, _admin, _doc, _seed_draft

FORK = multiprocessing.get_context("fork")
WAIT = 30


# ------------------------------------------------------------------ helpers


def _seed(root, **artifacts) -> str:
    store = ProjectStore(root=root)
    pid = str(uuid.uuid4())
    now = utc_now()
    store.save_project(
        Project(
            id=pid, user_id="1", title="T", assignment_type=None, university=None,
            status=ProjectStatus.DRAFT, current_stage=PipelineStage.UPLOAD, progress=0, price=None,
            credits=None, estimated_word_count=None, citation_style=None, deadline=None,
            created_at=now, updated_at=now, artifacts=copy.deepcopy(artifacts),
        )
    )
    store.save_requirement(RequirementJSON(id=str(uuid.uuid4()), project_id=pid))
    return pid


def _disk(root, pid) -> dict:
    return json.loads((root / pid / "bundle.json").read_text(encoding="utf-8"))


def _art(root, pid) -> dict:
    return _disk(root, pid)["project"]["artifacts"]


def _child(fn, args):
    code = 0
    try:
        fn(*args)
    except BaseException:  # noqa: BLE001
        traceback.print_exc()
        code = 1
    finally:
        os._exit(code)


def _start(fn, *args):
    proc = FORK.Process(target=_child, args=(fn, args))
    proc.start()
    return proc


def _finish(procs, *, ok=True):
    for proc in procs:
        proc.join(WAIT * 2)
        if proc.is_alive():
            proc.kill()
            proc.join(WAIT)
            pytest.fail("worker hung")
        if ok:
            assert proc.exitcode == 0, f"worker failed with exit code {proc.exitcode}"


def _drain(queue) -> list:
    items = []
    while not queue.empty():
        items.append(queue.get())
    return items


def _stale_save(root, pid, barrier, results, change):
    """Read, wait until every worker has read, then apply ``change`` and save."""
    store = ProjectStore(root=root)
    project = store.require_project(pid)
    barrier.wait(WAIT)
    change(project)
    try:
        store.save_project(project)
        results.put("ok")
    except ProjectUpdateConflictError:
        results.put("conflict")


def _lock_free(root, pid, name) -> bool:
    path = project_lock._lock_path(pid, name, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return True


def _tmp_files(root, pid) -> list:
    return sorted((root / pid).glob(".bundle.json.*.tmp"))


# ================================================================== 1-10 concurrent updates


def _set_nested(i):
    return lambda project: project.artifacts.setdefault("nested", {}).__setitem__(f"k{i}", i)


def test_01_eighty_nested_updates_from_stale_copies_are_all_kept(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root, nested={})
    barrier, results = FORK.Barrier(80), FORK.SimpleQueue()
    _finish([_start(_stale_save, root, pid, barrier, results, _set_nested(i)) for i in range(80)])
    assert _drain(results) == ["ok"] * 80
    assert _art(root, pid)["nested"] == {f"k{i}": i for i in range(80)}


def _distinct_update(root, pid, i, barrier):
    store = ProjectStore(root=root)
    barrier.wait(WAIT)
    if i % 2:
        store.update_project(pid, lambda project: project.artifacts.__setitem__(f"f{i}", i))
    else:
        project = store.require_project(pid)
        project.artifacts[f"f{i}"] = i
        store.save_project(project)


def test_02_hundred_concurrent_distinct_field_updates_are_all_kept(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root)
    barrier = FORK.Barrier(100)
    _finish([_start(_distinct_update, root, pid, i, barrier) for i in range(100)])
    art = _art(root, pid)
    assert all(art[f"f{i}"] == i for i in range(100))
    assert _disk(root, pid)["revision"] == 101  # seed + one write per update, none skipped


def test_03_same_field_from_stale_copies_conflicts_instead_of_overwriting(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root, deadline_note="original")
    barrier, results = FORK.Barrier(2), FORK.SimpleQueue()
    procs = [
        _start(_stale_save, root, pid, barrier, results,
               lambda p, v=value: p.artifacts.__setitem__("deadline_note", v))
        for value in ("first", "second")
    ]
    _finish(procs)
    assert sorted(_drain(results)) == ["conflict", "ok"]
    assert _art(root, pid)["deadline_note"] in ("first", "second")  # the one acknowledged write

    barrier, results = FORK.Barrier(2), FORK.SimpleQueue()
    _finish([_start(_stale_save, root, pid, barrier, results,
                    lambda p: p.artifacts.__setitem__("deadline_note", "same")) for _ in range(2)])
    assert _drain(results) == ["ok", "ok"] and _art(root, pid)["deadline_note"] == "same"


def test_04_changes_to_separate_nested_objects_are_merged(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root, a={"x": 0}, b={"y": 0})
    changes = [
        lambda p: p.artifacts["a"].__setitem__("x", 1),
        lambda p: p.artifacts["b"].__setitem__("y", 1),
        lambda p: p.artifacts["a"].__setitem__("z", 1),
        lambda p: p.artifacts.__setitem__("c", {"new": True}),
    ]
    barrier, results = FORK.Barrier(len(changes)), FORK.SimpleQueue()
    _finish([_start(_stale_save, root, pid, barrier, results, change) for change in changes])
    assert _drain(results) == ["ok"] * len(changes)
    art = _art(root, pid)
    assert art["a"] == {"x": 1, "z": 1} and art["b"] == {"y": 1} and art["c"] == {"new": True}


def _append(root, pid, i, barrier):
    store = ProjectStore(root=root)
    barrier.wait(WAIT)
    store.update_project(
        pid, lambda p: p.artifacts.setdefault("messages", []).append({"id": f"m{i}", "text": str(i)})
    )


def test_05_appends_with_stable_ids_are_all_kept_and_stale_list_writes_conflict(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root, messages=[])
    barrier = FORK.Barrier(40)
    _finish([_start(_append, root, pid, i, barrier) for i in range(40)])
    ids = [m["id"] for m in _art(root, pid)["messages"]]
    assert sorted(ids) == sorted(f"m{i}" for i in range(40)) and len(set(ids)) == 40

    barrier, results = FORK.Barrier(2), FORK.SimpleQueue()
    _finish([_start(_stale_save, root, pid, barrier, results,
                    lambda p, n=n: p.artifacts["messages"].append({"id": n})) for n in ("x1", "x2")])
    outcome = _drain(results)
    assert sorted(outcome) == ["conflict", "ok"]
    ids = [m["id"] for m in _art(root, pid)["messages"]]
    assert len(ids) == 41 and len([i for i in ids if i in ("x1", "x2")]) == 1  # nothing silently dropped


def test_06_a_removal_survives_an_unrelated_stale_update_in_either_order(tmp_path):
    root = tmp_path / "p"
    for remove_first in (True, False):
        pid = _seed(root, obsolete={"v": 1})
        stale_store, fresh_store = ProjectStore(root=root), ProjectStore(root=root)
        stale = stale_store.require_project(pid)
        remover = fresh_store.require_project(pid)
        remover.artifacts.pop("obsolete")
        stale.artifacts["unrelated"] = 1
        order = [(fresh_store, remover), (stale_store, stale)]
        for store, project in order if remove_first else order[::-1]:
            store.save_project(project)
        art = _art(root, pid)
        assert "obsolete" not in art and art["unrelated"] == 1


def _counter_loop(root, pid, key, rounds, barrier):
    store = ProjectStore(root=root)
    barrier.wait(WAIT)
    for _ in range(rounds):
        project = store.require_project(pid)
        project.artifacts[key] = int(project.artifacts.get(key) or 0) + 1
        store.save_project(project)


def test_07_two_processes_interleaving_read_save_cycles_lose_nothing(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root)
    barrier = FORK.Barrier(2)
    _finish([_start(_counter_loop, root, pid, key, 50, barrier) for key in ("a", "b")])
    art = _art(root, pid)
    assert art["a"] == 50 and art["b"] == 50


def _shared_increment(root, pid, rounds, barrier):
    store = ProjectStore(root=root)
    barrier.wait(WAIT)
    for _ in range(rounds):
        store.update_project(pid, lambda p: p.artifacts.__setitem__("n", int(p.artifacts.get("n") or 0) + 1))


def test_08_several_workers_incrementing_one_field_through_update_project(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root, n=0)
    barrier = FORK.Barrier(8)
    _finish([_start(_shared_increment, root, pid, 25, barrier) for _ in range(8)])
    assert _art(root, pid)["n"] == 200


def test_09_stale_worker_after_a_newer_worker_writes_nothing(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root, quote={"id": "q1"})
    store_a, store_b = ProjectStore(root=root), ProjectStore(root=root)
    project_a = store_a.require_project(pid)
    project_b = store_b.require_project(pid)
    project_b.artifacts["quote"] = {"id": "q2"}
    store_b.save_project(project_b)

    project_a.artifacts["quote"] = {"id": "q-stale"}
    project_a.artifacts["side_note"] = "from A"
    with pytest.raises(ProjectUpdateConflictError):
        store_a.save_project(project_a)
    art = _art(root, pid)
    assert art["quote"] == {"id": "q2"} and "side_note" not in art  # all or nothing


def test_10_after_a_conflict_a_reload_sees_the_other_workers_write_and_saves(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root, quote={"id": "q1"})
    store_a = ProjectStore(root=root)
    stale = store_a.require_project(pid)

    def other_worker():
        store = ProjectStore(root=root)
        store.update_project(pid, lambda p: p.artifacts.__setitem__("quote", {"id": "q2"}))

    _finish([_start(other_worker)])
    stale.artifacts["quote"] = {"id": "q-stale"}
    with pytest.raises(ProjectUpdateConflictError):
        store_a.save_project(stale)
    fresh = store_a.require_project(pid)  # same long-lived store: no stale cache
    assert fresh.artifacts["quote"] == {"id": "q2"}
    fresh.artifacts["side_note"] = "after reload"
    store_a.save_project(fresh)
    art = _art(root, pid)
    assert art["quote"] == {"id": "q2"} and art["side_note"] == "after reload"


# ================================================================== 11-13 locks


def _hold_lock_forever(root, pid, ready):
    with project_file_lock(pid, name=BUNDLE_LOCK, root=root):
        ready.set()
        threading.Event().wait()


def _mutate_then_hang(root, pid, ready):
    def mutate(project):
        project.artifacts["half_done"] = True
        ready.set()
        threading.Event().wait()

    ProjectStore(root=root).update_project(pid, mutate)


@pytest.mark.parametrize("holder", [_hold_lock_forever, _mutate_then_hang], ids=["lock", "inside-update"])
def test_11_a_killed_lock_holder_releases_the_lock_and_writes_nothing(tmp_path, holder):
    root = tmp_path / "p"
    pid = _seed(root)
    before = _disk(root, pid)
    ready = FORK.Event()
    proc = _start(holder, root, pid, ready)
    try:
        assert ready.wait(WAIT)
        assert not _lock_free(root, pid, BUNDLE_LOCK)
    finally:
        os.kill(proc.pid, signal.SIGKILL)
        _finish([proc], ok=False)
    assert proc.exitcode == -signal.SIGKILL
    assert _disk(root, pid) == before and "half_done" not in _art(root, pid)
    ProjectStore(root=root).update_project(pid, lambda p: p.artifacts.__setitem__("after", 1))
    assert _art(root, pid)["after"] == 1


def _report_lock(root, pid, results):
    results.put(_lock_free(root, pid, BUNDLE_LOCK))
    results.put(sorted(getattr(project_lock._file_locks_held, "paths", set())))


def test_12_reentrant_locks_are_held_until_the_outermost_exit(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root)
    results = FORK.SimpleQueue()
    with project_file_lock(pid, name=BUNDLE_LOCK, root=root):
        with project_file_lock(pid, name=BUNDLE_LOCK, root=root):
            pass
        _finish([_start(_report_lock, root, pid, results)])
        free, child_held = _drain(results)
        assert free is False  # the inner exit did not release it
        assert child_held == []  # a forked worker does not inherit "already held"
    _finish([_start(_report_lock, root, pid, results)])
    assert _drain(results)[0] is True

    store = ProjectStore(root=root)

    def outer(project):
        store.update_project(pid, lambda p: p.artifacts.__setitem__("inner", 1))
        project.artifacts["outer"] = 1

    store.update_project(pid, outer)
    art = _art(root, pid)
    assert art["inner"] == 1 and art["outer"] == 1


def test_13_locks_out_of_order_are_refused_and_the_documented_order_works(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root)
    with project_file_lock(pid, name=BUNDLE_LOCK, root=root):
        with pytest.raises(LockOrderError):
            with project_file_lock(pid, name=BILLING_LOCK, root=root):
                pass
    with project_file_lock(pid, name=BILLING_LOCK, root=root):
        with pytest.raises(LockOrderError):
            with payment_gate(pid, root=root):
                pass
    with project_file_lock(pid, name=DOCUMENT_LOCK, root=root):
        with pytest.raises(LockOrderError):
            with project_file_lock(pid, name=BILLING_LOCK, root=root):
                pass
    with project_file_lock(pid, name="humanizer", root=root):
        with pytest.raises(LockOrderError):
            with project_file_lock(pid, name="writer", root=root):
                pass

    with payment_gate(pid, root=root):
        with project_file_lock(pid, name="writer", root=root):
            with project_file_lock(pid, name=BILLING_LOCK, root=root):
                with project_file_lock(pid, name=DOCUMENT_LOCK, root=root):
                    with project_file_lock(pid, name=BUNDLE_LOCK, root=root):
                        pass
    assert getattr(project_lock._order_held, "stack", []) == []

    def takes_billing(project):
        project.artifacts["inside"] = 1
        with project_file_lock(pid, name=BILLING_LOCK, root=root):
            pass

    with pytest.raises(LockOrderError):
        ProjectStore(root=root).update_project(pid, takes_billing)
    assert "inside" not in _art(root, pid)
    assert all(_lock_free(root, pid, name) for name in (BUNDLE_LOCK, BILLING_LOCK, DOCUMENT_LOCK))


# ================================================================== 14-21 security-sensitive state


def test_14_update_racing_a_payment_keeps_the_payment(env):
    owner = _owner(env)
    pid, client = _priced(env, owner)
    stale_store = ProjectStore(root=env.root)
    stale = stale_store.require_project(pid)  # read before the payment
    res = client.post(_url(pid, "confirm-payment"), json={"quote_id": _quote(env, pid)["quote_id"]})
    assert res.status_code == 200, res.get_data(as_text=True)

    stale.artifacts["chat_transcript"] = [{"role": "user", "kind": "", "html": "hi"}]
    stale_store.save_project(stale)
    art = _art(env.root, pid)
    cycle = payment_ledger.active_cycle(pid)
    assert art["payment_confirmed"] is True and art[PAYMENT_CYCLE_KEY] == cycle["cycle_id"]
    assert art["chat_transcript"][0]["html"] == "hi"
    assert env.service._require_payment(pid, "test") == cycle["quoted_word_count"]


def _refund(pid):
    res = _admin().post(f"/api/admin/assignment/projects/{pid}/refund", json={"reason": "t"})
    assert res.status_code == 200, res.get_data(as_text=True)


def test_15_update_racing_a_refund_keeps_the_refund(env):
    owner = _owner(env)
    pid, _client_, _ = _paid(env, owner)
    stale_store = ProjectStore(root=env.root)
    stale = stale_store.require_project(pid)  # read while paid
    _refund(pid)
    stale.artifacts["chat_transcript"] = [{"role": "user", "kind": "", "html": "later"}]
    stale_store.save_project(stale)
    art = _art(env.root, pid)
    assert art["payment_confirmed"] is False and art["payment_refunded"] is True
    assert art["chat_transcript"][0]["html"] == "later"
    with pytest.raises(PaymentRequiredError):
        env.service.run_research(pid)


def test_16_stale_paid_json_after_a_refund_cannot_restore_access(env):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    stale_data = copy.deepcopy(env.service.store.require_project(pid).to_dict())
    _refund(pid)
    with pytest.raises(ProjectUpdateConflictError):
        ProjectStore(root=env.root).save_project(Project.from_dict(stale_data))
    assert _art(env.root, pid)["payment_confirmed"] is False

    plant_stale_project_json(env.root, pid, stale_data)  # reached the disk anyway
    assert _art(env.root, pid)["payment_confirmed"] is True
    with pytest.raises(PaymentRequiredError):
        env.service.run_research(pid)  # SQLite stays the authority
    assert env.research.calls == 0


def test_17_stale_writer_cannot_clear_output_evidence_or_replace_newer_text(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root, draft={"id": "d1", "content": "old"})
    stale_store, writer_store = ProjectStore(root=root), ProjectStore(root=root)
    stale = stale_store.require_project(pid)
    stale_again = ProjectStore(root=root).require_project(pid)
    newer = writer_store.require_project(pid)
    newer.artifacts["draft"] = {"id": "d2", "content": "generated text"}
    newer.artifacts[OUTPUT_GENERATED_KEY] = "2026-01-01T00:00:00+00:00"
    writer_store.save_project(newer)

    stale.artifacts.pop(OUTPUT_GENERATED_KEY, None)
    stale.artifacts["chat_transcript"] = []
    stale_store.save_project(stale)
    art = _art(root, pid)
    assert art[OUTPUT_GENERATED_KEY] == "2026-01-01T00:00:00+00:00"
    assert art["draft"]["content"] == "generated text"

    stale_again.artifacts["draft"] = {"id": "d1", "content": "stale rewrite"}
    with pytest.raises(ProjectUpdateConflictError):
        ProjectStore(root=root).save_project(stale_again)
    assert _art(root, pid)["draft"]["content"] == "generated text"

    # Copies read after the evidence existed can't drop it either: stale, current or in a mutation.
    holder_store = ProjectStore(root=root)
    with_evidence = holder_store.require_project(pid)
    ProjectStore(root=root).update_project(pid, lambda p: p.artifacts.__setitem__("other", 1))
    with_evidence.artifacts.pop(OUTPUT_GENERATED_KEY)
    holder_store.save_project(with_evidence)
    current = holder_store.require_project(pid)
    current.artifacts.pop(OUTPUT_GENERATED_KEY)
    holder_store.save_project(current)
    holder_store.update_project(pid, lambda p: p.artifacts.pop(OUTPUT_GENERATED_KEY))
    art = _art(root, pid)
    assert art[OUTPUT_GENERATED_KEY] == "2026-01-01T00:00:00+00:00" and art["other"] == 1


def test_18_stale_server_plan_cannot_replace_the_clients_plan_or_provenance(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root, research_plan={"id": "server-1"}, **{RESEARCH_PLAN_SOURCE_KEY: "server"})
    stale = ProjectStore(root=root).require_project(pid)
    stale_plan = ProjectStore(root=root).require_project(pid)
    ProjectStore(root=root).update_project(
        pid,
        lambda p: p.artifacts.update(research_plan={"id": "client-edit"}, **{RESEARCH_PLAN_SOURCE_KEY: "client"}),
    )
    stale.artifacts["chat_transcript"] = []
    ProjectStore(root=root).save_project(stale)
    art = _art(root, pid)
    assert art["research_plan"] == {"id": "client-edit"} and art[RESEARCH_PLAN_SOURCE_KEY] == "client"

    stale_plan.artifacts["research_plan"] = {"id": "server-2"}
    with pytest.raises(ProjectUpdateConflictError):
        ProjectStore(root=root).save_project(stale_plan)
    art = _art(root, pid)
    assert art["research_plan"] == {"id": "client-edit"} and art[RESEARCH_PLAN_SOURCE_KEY] == "client"


def test_19_quote_update_and_file_add_from_different_workers_are_both_kept(env):
    owner = _owner(env)
    pid, _client_ = _priced(env, owner)
    file_store = ProjectStore(root=env.root)
    stale = file_store.require_project(pid)
    first = file_store.list_files(pid)[0]
    env.service.calculate_pricing(pid)  # a new quote from another worker
    quote = _quote(env, pid)

    file_store.save_file(ProjectFile.from_dict({**first.to_dict(), "id": "added-file"}))
    stale.note = "edited meanwhile"
    file_store.save_project(stale)
    bundle = env.service.store.require_bundle(pid)
    assert bundle.project.artifacts["pricing"]["quote_id"] == quote["quote_id"]
    assert "added-file" in {f.id for f in bundle.files} and bundle.project.note == "edited meanwhile"
    assert env.service._quote_problem(bundle) == "SCOPE_CHANGED"  # the new file needs a new quote


def test_20_delivery_records_survive_an_unrelated_stale_update(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root, delivery_package={"id": "pkg-old"})
    stale = ProjectStore(root=root).require_project(pid)
    stale_drop = ProjectStore(root=root).require_project(pid)
    ProjectStore(root=root).update_project(
        pid,
        lambda p: p.artifacts.update(
            delivery_package={"id": "pkg-new"}, **{DELIVERY_SCOPE_KEY: {"package_id": "pkg-new", "words": 10}}
        ),
    )
    stale.artifacts["chat_transcript"] = []
    ProjectStore(root=root).save_project(stale)
    art = _art(root, pid)
    assert art["delivery_package"] == {"id": "pkg-new"} and art[DELIVERY_SCOPE_KEY]["package_id"] == "pkg-new"

    stale_drop.artifacts.pop("delivery_package")
    with pytest.raises(ProjectUpdateConflictError):
        ProjectStore(root=root).save_project(stale_drop)
    assert _art(root, pid)["delivery_package"] == {"id": "pkg-new"}


def test_21_cleared_and_quarantined_state_is_not_resurrected(tmp_path):
    root = tmp_path / "p"
    pid = _seed(
        root,
        **{PROCESSING_FAILURE_KEY: {"stage": "writing"}},
        writer_session={"id": "w1", "sections": [{"id": "s1", "generated_text": "quarantined"}]},
    )
    stale = ProjectStore(root=root).require_project(pid)
    stale_edit = ProjectStore(root=root).require_project(pid)

    def clear(project):
        project.artifacts.pop(PROCESSING_FAILURE_KEY)
        project.artifacts["writer_session"] = {"id": "w2", "sections": []}

    ProjectStore(root=root).update_project(pid, clear)
    stale.artifacts["chat_transcript"] = []
    ProjectStore(root=root).save_project(stale)
    art = _art(root, pid)
    assert PROCESSING_FAILURE_KEY not in art and art["writer_session"] == {"id": "w2", "sections": []}

    stale_edit.artifacts[PROCESSING_FAILURE_KEY]["client_seeded"] = False
    with pytest.raises(ProjectUpdateConflictError):
        ProjectStore(root=root).save_project(stale_edit)
    assert PROCESSING_FAILURE_KEY not in _art(root, pid)


# ================================================================== 22-28 persistence


def _crash_at(root, pid, point):
    import services.assignment_project.store as store_mod

    real_replace = os.replace
    if point == "before_flush":
        store_mod.os.fsync = lambda fd: os._exit(9)
    elif point == "before_replace":
        store_mod.os.replace = lambda a, b: os._exit(9)
    else:
        def replace_then_die(a, b):
            real_replace(a, b)
            os._exit(9)

        store_mod.os.replace = replace_then_die
    ProjectStore(root=root).update_project(pid, lambda p: p.artifacts.__setitem__("crash_write", point))


@pytest.mark.parametrize("point", ["before_flush", "before_replace", "after_replace"])
def test_22_24_a_crash_mid_write_leaves_a_whole_bundle(tmp_path, point):
    root = tmp_path / "p"
    pid = _seed(root, keep="yes")
    proc = _start(_crash_at, root, pid, point)
    _finish([proc], ok=False)
    assert proc.exitcode == 9
    data = _disk(root, pid)  # parses: never a partial file
    if point == "after_replace":
        assert data["project"]["artifacts"]["crash_write"] == "after_replace"
        assert _tmp_files(root, pid) == []
    else:
        assert "crash_write" not in data["project"]["artifacts"] and data["project"]["artifacts"]["keep"] == "yes"
        leftovers = _tmp_files(root, pid)
        assert len(leftovers) == 1
        if point == "before_replace":
            assert json.loads(leftovers[0].read_text())["project"]["artifacts"]["crash_write"] == point
    ProjectStore(root=root).update_project(pid, lambda p: p.artifacts.__setitem__("next", 1))
    assert _tmp_files(root, pid) == [] and _art(root, pid)["next"] == 1


@pytest.mark.parametrize(
    "content",
    ["{not json", '{"project": {"id": "x"', "", '{"revision": 3}'],
    ids=["garbage", "truncated", "empty", "no-project"],
)
def test_25_a_malformed_bundle_is_refused_and_never_overwritten(tmp_path, content):
    root = tmp_path / "p"
    pid = _seed(root)
    store = ProjectStore(root=root)
    loaded = store.require_project(pid)
    path = root / pid / "bundle.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ProjectBundleCorruptError):
        ProjectStore(root=root).get_project(pid)
    with pytest.raises(KeyError):
        ProjectStore(root=root).require_project(pid)
    with pytest.raises(ProjectBundleCorruptError):
        ProjectStore(root=root).update_project(pid, lambda p: None)
    loaded.artifacts["x"] = 1
    with pytest.raises(ProjectBundleCorruptError):
        store.save_project(loaded)
    assert path.read_text(encoding="utf-8") == content


def test_25b_a_bundle_naming_another_project_is_refused(tmp_path):
    root = tmp_path / "p"
    pid, other = _seed(root), _seed(root)
    (root / pid / "bundle.json").write_text((root / other / "bundle.json").read_text())
    with pytest.raises(ProjectBundleCorruptError):
        ProjectStore(root=root).get_project(pid)


def test_26_a_missing_bundle_is_not_recreated_from_a_stale_copy(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root, secret="kept")
    store = ProjectStore(root=root)
    stale = store.require_project(pid)
    (root / pid / "bundle.json").unlink()
    stale.artifacts["x"] = 1
    with pytest.raises(ProjectUpdateConflictError):
        store.save_project(stale)
    with pytest.raises(KeyError):
        ProjectStore(root=root).update_project(pid, lambda p: None)
    assert not (root / pid / "bundle.json").exists()


def test_27_abandoned_temp_files_are_removed_and_permissions_kept(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root)
    path = root / pid / "bundle.json"
    os.chmod(path, 0o600)
    for name in (".bundle.json.dead1.tmp", ".bundle.json.dead2.tmp"):
        (root / pid / name).write_text('{"partial": ')
    ProjectStore(root=root).update_project(pid, lambda p: p.artifacts.__setitem__("x", 1))
    assert _tmp_files(root, pid) == []
    assert (path.stat().st_mode & 0o777) == 0o600
    assert _art(root, pid)["x"] == 1


def _big_writer(root, pid, rounds, started):
    store = ProjectStore(root=root)
    started.wait(WAIT)
    for i in range(rounds):
        store.update_project(pid, lambda p, i=i: p.artifacts.__setitem__("blob", f"{i}-" + "x" * (50_000 + i * 997)))


def _reader(root, pid, started, done, results):
    path = root / pid / "bundle.json"
    started.wait(WAIT)
    reads = bad = 0
    while not done.is_set() or reads < 50:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            bad += 1
        reads += 1
    results.put((reads, bad))


def test_28_readers_never_see_partial_json_while_workers_write(tmp_path):
    root = tmp_path / "p"
    pid = _seed(root)
    started, done, results = FORK.Event(), FORK.Event(), FORK.SimpleQueue()
    readers = [_start(_reader, root, pid, started, done, results) for _ in range(2)]
    writers = [_start(_big_writer, root, pid, 60, started) for _ in range(2)]
    try:
        started.set()
        _finish(writers)
    finally:
        done.set()
        _finish(readers)
    outcomes = _drain(results)
    assert len(outcomes) == 2 and all(bad == 0 and reads >= 50 for reads, bad in outcomes)
    assert _art(root, pid)["blob"].startswith("59-")


# ================================================================== 29-32 AI results and the API


def _edit_document(root, pid, content):
    def edit(project):
        for key in ("draft", "humanized_draft"):
            if isinstance(project.artifacts.get(key), dict):
                project.artifacts[key] = {**project.artifacts[key], "content": content}

    ProjectStore(root=root).update_project(pid, edit)


def _user_edits_during(root, pid, content):
    _finish([_start(_edit_document, root, pid, content)])


def test_29_revision_chat_result_from_an_older_document_is_dropped_and_not_charged(dv, monkeypatch):
    import services.assignment_llm as llm

    root = dv.svc.store.storage_root
    _seed_draft(dv.env, dv.pid, PAID_WORDS)
    newer = _doc(PAID_WORDS - 10)
    monkeypatch.setattr(llm, "assignment_llm_configured", lambda *a, **k: True)

    def model(**_kw):
        _user_edits_during(root, dv.pid, newer)  # another worker saves the user's edit meanwhile
        return {"scope": "small", "content": _doc(PAID_WORDS + 5), "assistant_reply": "done"}, None

    monkeypatch.setattr(llm, "assignment_generate_json", model)
    res = dv.client.post(_url(dv.pid, "revision-chat"), json={"message": "Tighten the intro."})
    assert res.status_code == 409, res.get_data(as_text=True)
    assert res.get_json()["error"] == "PROJECT_CHANGED"
    art = _art(root, dv.pid)
    assert art["draft"]["content"] == newer
    assert dv.svc._revision_rounds_used(dv.pid, fallback=-1) == 0  # the round was given back
    assert PROCESSING_FAILURE_KEY not in art and dv.packager.built == []


def test_30_rehumanized_and_grade_gate_results_from_an_older_document_are_dropped(dv, monkeypatch):
    import services.assignment_spec as spec_mod
    from services.humanizer_engine.models import HumanizedDraft

    root = dv.svc.store.storage_root
    svc = dv.svc
    _seed_draft(dv.env, dv.pid, PAID_WORDS)
    svc._fit_humanized_word_budget = lambda pid, fresh: fresh
    svc._repair_humanized_meaning = lambda pid, content, fresh, reason: fresh

    def rehumanize(*, content, project_id, title, source_draft_id, source_draft_version, **_kw):
        _user_edits_during(root, project_id, _doc(PAID_WORDS - 20))
        return HumanizedDraft(
            id="h-stale", project_id=project_id, session_id="s", source_draft_id=source_draft_id,
            source_version=source_draft_version, title=title, content=content + " stale", total_words=1,
            version=1, paragraphs_processed=1, average_ai_reduction=0.0,
        )

    svc.humanizer.rehumanize_full_draft = rehumanize
    with pytest.raises(ProjectChangedError):
        ProjectService._rehumanize_current_prose(svc, dv.pid, reason="test")
    art = _art(root, dv.pid)
    assert art["draft"]["content"] == _doc(PAID_WORDS - 20) and "humanized_draft" not in art

    def gate(*, content, **_kw):
        _user_edits_during(root, dv.pid, _doc(PAID_WORDS - 30))
        from types import SimpleNamespace

        coverage = SimpleNamespace(to_dict=lambda: {}, overall_predicted_grade="A", criteria=[])
        return SimpleNamespace(content=_doc(PAID_WORDS + 1), passed=True, export_blocked=False, iterations=1,
                               repair_log=[], rubric_coverage=coverage, blocking_issues=[])

    monkeypatch.setattr(spec_mod, "run_grade_gate", gate)
    res = dv.client.post(_url(dv.pid, "delivery"), json={})
    assert res.status_code == 409 and res.get_json()["error"] == "PROJECT_CHANGED", res.get_data(as_text=True)
    art = _art(root, dv.pid)
    assert art["draft"]["content"] == _doc(PAID_WORDS - 30) and dv.packager.built == []
    assert PROCESSING_FAILURE_KEY not in art


def _probe_locks(root, pid, results):
    results.put({name: _lock_free(root, pid, name) for name in (BUNDLE_LOCK, BILLING_LOCK, DOCUMENT_LOCK)})


def test_31_no_project_lock_is_held_while_the_ai_model_runs(dv, monkeypatch):
    import services.assignment_llm as llm

    root = dv.svc.store.storage_root
    _seed_draft(dv.env, dv.pid, PAID_WORDS)
    results = FORK.SimpleQueue()
    monkeypatch.setattr(llm, "assignment_llm_configured", lambda *a, **k: True)

    def model(**_kw):
        _finish([_start(_probe_locks, root, dv.pid, results)])
        return {"scope": "small", "content": _doc(PAID_WORDS + 5), "assistant_reply": "done"}, None

    monkeypatch.setattr(llm, "assignment_generate_json", model)
    res = dv.client.post(_url(dv.pid, "revision-chat"), json={"message": "Tighten the intro."})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert _drain(results) == [{BUNDLE_LOCK: True, BILLING_LOCK: True, DOCUMENT_LOCK: True}]
    assert _art(root, dv.pid)["draft"]["content"] == _doc(PAID_WORDS + 5).strip()


def test_32_conflicts_are_409_and_never_refund_evidence(env, monkeypatch):
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)

    def conflict(*_a, **_k):
        raise ProjectUpdateConflictError(pid, "test")

    monkeypatch.setattr(env.service, "save_chat_transcript", conflict)
    res = client.put(_url(pid, "chat-transcript"), json={"messages": [{"role": "user", "html": "x"}]})
    assert res.status_code == 409 and res.get_json()["error"] == "PROJECT_UPDATE_CONFLICT"
    assert "/" not in res.get_json()["message"]

    with pytest.raises(ProjectUpdateConflictError):
        with env.service._execution_boundary(pid, "writing"):
            raise ProjectUpdateConflictError(pid, "test")
    with pytest.raises(ProjectChangedError):
        with env.service._execution_boundary(pid, "writing"):
            raise ProjectChangedError()
    assert PROCESSING_FAILURE_KEY not in _art(env.root, pid)
