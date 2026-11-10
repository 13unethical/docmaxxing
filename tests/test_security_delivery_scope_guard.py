"""Final delivery stays inside the paid scope: paid words x 1.2 + 200, counted on the delivered text.

The allowance comes from the payment cycle, never from project JSON or the request; downloads
serve only a package checked against the current document and payment. Grade gate, packager,
formatter and AI model are fakes; nothing leaves the machine.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from services.assignment_project.service import (
    DELIVERY_SCOPE_KEY,
    PAYMENT_CYCLE_KEY,
    PROCESSING_FAILURE_KEY,
    PaidScopeLimitExceededError,
)
from services.delivery_engine.models import DeliveryPackage
from services.writer_engine.models import count_words
from tests.assignment_helpers import current_quote_id
from tests.test_security_paid_pipelines import _client, _signed_in, _user, economy  # noqa: F401
from tests.test_security_payment_scope_integrity import _owner, _paid, _priced, _url, env  # noqa: F401
from tests.test_security_quote_scope_provenance import CAP, PAID_WORDS, _admin, _doc, _plan_blueprint, _seed_draft
from tests.test_security_refund_integrity import _auto_refund_as

ROUTES = ("assignment", "package", "file")


class _Packager:
    """Delivery engine fake: writes the delivered text into the project's delivery folder."""

    def __init__(self, service):
        self.service = service
        self.built: list[int] = []

    def __call__(self, *, final_draft, project_id, **_kwargs):
        content = str(final_draft.get("content") or "")
        self.built.append(count_words(content))
        folder = self.service.store.storage_root / project_id / "delivery"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"final-{len(self.built)}.docx"
        (folder / name).write_bytes(b"PK-" + content.encode("utf-8"))
        package = DeliveryPackage.from_dict(
            {
                "id": f"pkg-{uuid.uuid4().hex[:12]}",
                "project_id": project_id,
                "status": "ready",
                "client_filename": name,
                "files": [
                    {
                        "id": f"file-{uuid.uuid4().hex[:12]}",
                        "filename": name,
                        "file_type": "final_assignment_docx",
                        "storage_path": str(folder / name),
                        "ready": True,
                    }
                ],
            }
        )
        return self.service.delivery.store.save(package)


def _gate(grow_to: int | None = None):
    def run_grade_gate(*, content, **_kwargs):
        coverage = SimpleNamespace(to_dict=lambda: {}, overall_predicted_grade="A", criteria=[])
        return SimpleNamespace(
            content=_doc(grow_to) if grow_to else content,
            passed=True,
            export_blocked=False,
            iterations=0,
            repair_log=[],
            rubric_coverage=coverage,
            blocking_issues=[],
        )

    return run_grade_gate


def _no_rehumanizer(*_a, **_k):
    raise RuntimeError("the rehumanizer is not used in these tests")


@pytest.fixture()
def dv(env, monkeypatch):
    import services.assignment_spec as spec_mod

    monkeypatch.setattr(spec_mod, "run_grade_gate", _gate())
    monkeypatch.setattr(spec_mod, "build_assignment_spec", lambda *a, **k: SimpleNamespace(to_dict=lambda: {}))
    svc = env.service
    svc._load_review_report = lambda pid: SimpleNamespace(to_dict=lambda: {})
    svc._load_detection_report = lambda pid: SimpleNamespace(to_dict=lambda: {})
    svc._rehumanize_current_prose = _no_rehumanizer
    svc.run_formatting = lambda pid: None
    packager = _Packager(svc)
    svc.delivery.prepare_package = packager
    owner = _owner(env)
    pid, client, _ = _paid(env, owner)
    _plan_blueprint(env, pid)
    return SimpleNamespace(env=env, svc=svc, owner=owner, pid=pid, client=client, packager=packager)


def _deliver(dv, body=None):
    return dv.client.post(_url(dv.pid, "delivery"), json=body or {})


def _package_ids(dv) -> tuple[str, str]:
    package = dv.svc.store.require_project(dv.pid).artifacts["delivery_package"]
    return package["id"], package["files"][0]["id"]


def _download(dv, kind, ids=None, client=None):
    client = client or dv.client
    if kind == "assignment":
        return client.get(_url(dv.pid, "download"))
    package_id, file_id = ids or _package_ids(dv)
    if kind == "package":
        return client.get(f"/api/delivery/packages/{package_id}/download")
    return client.get(f"/api/delivery/files/{file_id}")


def _art(dv) -> dict:
    return dv.svc.store.require_project(dv.pid).artifacts


def _chat_model(monkeypatch, words: int) -> None:
    import services.assignment_llm as llm

    monkeypatch.setattr(llm, "assignment_llm_configured", lambda *a, **k: True)
    monkeypatch.setattr(
        llm,
        "assignment_generate_json",
        lambda **kw: ({"scope": "medium", "content": _doc(words), "assistant_reply": "done"}, None),
    )


def _assert_over_scope(res):
    assert res.status_code == 409, res.get_data(as_text=True)
    assert res.get_json()["error"] == "PAID_SCOPE_LIMIT_EXCEEDED"
    assert b"PK-" not in res.data


def _assert_stale(res):
    assert res.status_code == 409, res.get_data(as_text=True)
    assert res.get_json()["error"] == "DELIVERY_PACKAGE_STALE"
    assert b"PK-" not in res.data


# ------------------------------------------------------------------ the limit at delivery


@pytest.mark.parametrize("words", [PAID_WORDS - 100, CAP - 1, CAP], ids=["below", "one-below", "exactly-at"])
def test_document_within_the_limit_is_delivered_on_every_route(dv, words):
    content = _seed_draft(dv.env, dv.pid, words)
    res = _deliver(dv)
    assert res.status_code == 200, res.get_data(as_text=True)
    record = _art(dv)[DELIVERY_SCOPE_KEY]
    assert record["words"] == words and record["word_cap"] == CAP and record["paid_words"] == PAID_WORDS
    for kind in ROUTES:
        got = _download(dv, kind)
        assert got.status_code == 200 and got.data == b"PK-" + content.encode(), kind
    assert dv.packager.built == [words]


def test_one_word_over_the_limit_is_refused_untouched_and_not_refundable(dv):
    content = _seed_draft(dv.env, dv.pid, CAP + 1)
    balance = dv.env.wallet.get_balance(dv.owner["id"])
    _assert_over_scope(_deliver(dv))
    _assert_over_scope(dv.client.post(_url(dv.pid, "stages/delivery/retry"), json={}))
    _assert_over_scope(_download(dv, "assignment"))
    assert dv.packager.built == []
    art = _art(dv)
    assert "delivery_package" not in art and DELIVERY_SCOPE_KEY not in art
    # Nothing is cut to fit: the stored document is exactly what it was.
    assert dv.svc._load_draft(dv.pid).content == content and count_words(content) == CAP + 1
    # A scope refusal is the request's problem, not a processing failure: no automatic refund.
    assert PROCESSING_FAILURE_KEY not in art
    assert _auto_refund_as(dv.env.app, dv.owner, dv.pid) is None
    assert dv.env.wallet.get_balance(dv.owner["id"]) == balance


def test_legitimate_writer_overshoot_within_the_tolerance_is_delivered(dv):
    words = PAID_WORDS + 150  # longer than purchased, inside paid x 1.2 + 200
    content = _seed_draft(dv.env, dv.pid, words)
    assert _deliver(dv).status_code == 200
    assert _download(dv, "assignment").data == b"PK-" + content.encode()


def test_grade_gate_output_is_checked_again_before_packaging(dv, monkeypatch):
    import services.assignment_spec as spec_mod

    _seed_draft(dv.env, dv.pid, PAID_WORDS)
    monkeypatch.setattr(spec_mod, "run_grade_gate", _gate(grow_to=CAP + 50))
    _assert_over_scope(_deliver(dv))
    assert dv.packager.built == [] and "delivery_package" not in _art(dv)


def test_allowance_comes_from_the_payment_cycle_not_json_or_the_request(dv):
    _seed_draft(dv.env, dv.pid, CAP + 200)
    project = dv.svc.store.require_project(dv.pid)
    project.artifacts["pricing"] = {**project.artifacts["pricing"], "word_count": 20000}
    project.artifacts["paid_word_count"] = 20000
    dv.svc.store.save_project(project)
    res = _deliver(dv, {"word_count": 20000, "paid_words": 20000, "word_cap": 99999})
    _assert_over_scope(res)
    assert f"up to {CAP} words" in res.get_json()["message"]


def test_payment_without_a_cycle_uses_the_verified_paid_scope(env, dv):
    owner = _owner(env, email="legacy@example.com")
    pid, _client_ = _priced(env, owner)
    env.service.confirm_payment(pid, quote_id=current_quote_id(env.service, pid))  # no ledger cycle
    assert not env.service.store.require_project(pid).artifacts.get(PAYMENT_CYCLE_KEY)
    _plan_blueprint(env, pid)
    _seed_draft(env, pid, CAP + 1)
    with pytest.raises(PaidScopeLimitExceededError):
        env.service.run_delivery(pid)
    _seed_draft(env, pid, CAP)
    assert env.service.run_delivery(pid) is not None


# ------------------------------------------------------------------ chat edits on top of writer output


def test_chat_edits_combined_with_writer_output_stay_inside_the_limit(dv, monkeypatch):
    _seed_draft(dv.env, dv.pid, CAP - 20)
    assert _deliver(dv).status_code == 200
    _chat_model(monkeypatch, CAP)
    res = dv.client.post(_url(dv.pid, "revision-chat"), json={"message": "Expand the conclusion a little."})
    assert res.status_code == 200, res.get_data(as_text=True)
    edited = b"PK-" + _doc(CAP).strip().encode()
    assert dv.packager.built == [CAP - 20, CAP]
    assert _download(dv, "assignment").data == edited

    _chat_model(monkeypatch, CAP + 100)
    res = dv.client.post(_url(dv.pid, "revision-chat"), json={"message": "Add another section."})
    _assert_over_scope(res)
    assert dv.packager.built == [CAP - 20, CAP]
    for kind in ROUTES:
        assert _download(dv, kind).data == edited, kind


def test_writer_output_over_the_limit_is_delivered_only_after_a_chat_edit_shortens_it(dv, monkeypatch):
    _seed_draft(dv.env, dv.pid, CAP + 200)
    _assert_over_scope(_deliver(dv))
    _chat_model(monkeypatch, CAP - 100)
    res = dv.client.post(_url(dv.pid, "revision-chat"), json={"message": "Please shorten it."})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert dv.packager.built == [CAP - 100]
    assert _download(dv, "assignment").data == b"PK-" + _doc(CAP - 100).strip().encode()


# ------------------------------------------------------------------ stored packages


@pytest.mark.parametrize("kind", ["package", "file"])
def test_stale_package_is_refused_after_the_document_changes(dv, kind):
    _seed_draft(dv.env, dv.pid, PAID_WORDS)
    assert _deliver(dv).status_code == 200
    old = _package_ids(dv)
    assert _download(dv, kind, old).status_code == 200
    _seed_draft(dv.env, dv.pid, CAP + 50)  # another path rewrote the document after packaging
    _assert_stale(_download(dv, kind, old))
    assert dv.packager.built == [PAID_WORDS]


def test_project_download_rebuilds_a_stale_package_through_the_guard(dv):
    _seed_draft(dv.env, dv.pid, PAID_WORDS)
    assert _deliver(dv).status_code == 200
    old = _package_ids(dv)
    _seed_draft(dv.env, dv.pid, CAP + 50)
    _assert_over_scope(_download(dv, "assignment"))
    assert dv.packager.built == [PAID_WORDS]  # refused before packaging; the old file is not served

    content = _seed_draft(dv.env, dv.pid, CAP - 10)
    got = _download(dv, "assignment")
    assert got.status_code == 200 and got.data == b"PK-" + content.encode()
    assert dv.packager.built == [PAID_WORDS, CAP - 10]
    assert _download(dv, "package", old).status_code in (404, 409)
    for kind in ("package", "file"):
        assert _download(dv, kind).data == b"PK-" + content.encode()


@pytest.mark.parametrize("kind", ROUTES)
def test_package_without_a_check_record_is_not_served_as_is(dv, kind):
    content = _seed_draft(dv.env, dv.pid, PAID_WORDS)
    assert _deliver(dv).status_code == 200
    ids = _package_ids(dv)
    project = dv.svc.store.require_project(dv.pid)
    project.artifacts.pop(DELIVERY_SCOPE_KEY)  # a package built before the check existed
    dv.svc.store.save_project(project)
    res = _download(dv, kind, ids)
    if kind == "assignment":
        assert res.status_code == 200 and res.data == b"PK-" + content.encode()
        assert dv.packager.built == [PAID_WORDS, PAID_WORDS]
    else:
        _assert_stale(res)


@pytest.mark.parametrize("kind", ROUTES)
def test_package_built_under_another_payment_is_stale(dv, kind):
    _seed_draft(dv.env, dv.pid, PAID_WORDS)
    assert _deliver(dv).status_code == 200
    ids = _package_ids(dv)
    project = dv.svc.store.require_project(dv.pid)
    project.artifacts[DELIVERY_SCOPE_KEY] = {**project.artifacts[DELIVERY_SCOPE_KEY], "cycle_id": "another-cycle"}
    dv.svc.store.save_project(project)
    res = _download(dv, kind, ids)
    if kind == "assignment":
        assert res.status_code == 200 and dv.packager.built == [PAID_WORDS, PAID_WORDS]
    else:
        _assert_stale(res)


@pytest.mark.parametrize("kind", ROUTES)
def test_every_download_route_rechecks_the_words_against_the_cycle(dv, kind):
    _seed_draft(dv.env, dv.pid, PAID_WORDS)
    assert _deliver(dv).status_code == 200
    ids = _package_ids(dv)
    project = dv.svc.store.require_project(dv.pid)
    project.artifacts[DELIVERY_SCOPE_KEY] = {**project.artifacts[DELIVERY_SCOPE_KEY], "words": CAP + 1}
    dv.svc.store.save_project(project)
    _assert_over_scope(_download(dv, kind, ids))
    assert dv.packager.built == [PAID_WORDS]


def test_verified_admin_keeps_access_to_the_stored_package(dv):
    _seed_draft(dv.env, dv.pid, PAID_WORDS)
    assert _deliver(dv).status_code == 200
    ids = _package_ids(dv)
    _seed_draft(dv.env, dv.pid, CAP + 50)
    assert _download(dv, "package", ids, client=_admin()).status_code == 200
    _assert_stale(_download(dv, "package", ids))
