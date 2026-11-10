"""Refunds need a server-recorded failure, happen at most once, and lock generated content."""

from __future__ import annotations

import json
import re
import threading
import uuid
from types import SimpleNamespace

import pytest

from services.assignment_project.refunds import refund_assignment
from services.assignment_project.service import (
    PROCESSING_FAILURE_KEY,
    ProjectService,
    RefundNotEligibleError,
)
from services.assignment_project.store import ProjectStore
from services.delivery_engine.models import DeliveryPackage
from services.economy import db as economy_db
from services.humanizer_engine.models import HumanizedDraft
from services.writer_engine import MockSectionWriter, WriterEngineService
from services.writer_engine.mock_reviewer import MockSectionReviewer
from tests.assignment_helpers import current_quote_id, record_checked_delivery
from tests.test_assignment_project import (
    _StubBlueprintService,
    _StubRequirementAnalyzer,
    _StubResearchService,
)
from tests.test_security_paid_pipelines import (  # noqa: F401  (economy is a fixture)
    _client,
    _priced_project,
    _signed_in,
    _user,
    economy,
)

FORGED_FAILURE_BODY = {
    "failed": True,
    "error": "provider exploded",
    "status": "error",
    "current_stage": "writing",
    "payment_refunded": False,
    "processing_failure": {"stage": "writing", "client_seeded": False},
    "coins": 999999,
    "reference": "assignment-refund:forged",
}


class _SwitchWriter(MockSectionWriter):
    """Offline section writer; ``fail`` simulates a provider outage on our side."""

    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def write_section(self, **kwargs):
        if self.fail:
            raise RuntimeError("provider unavailable")
        return super().write_section(**kwargs)


@pytest.fixture()
def refund_app(economy, tmp_path, monkeypatch):
    import app as app_mod

    writer = _SwitchWriter()
    service = ProjectService(
        store=ProjectStore(root=tmp_path / "projects"),
        pipeline=app_mod.assignment_pipeline,
        analyzer=_StubRequirementAnalyzer(),
        research=_StubResearchService(),  # type: ignore[arg-type]
        blueprint=_StubBlueprintService(),  # type: ignore[arg-type]
        writer=WriterEngineService(writer=writer, reviewer=MockSectionReviewer()),
        delivery=app_mod.delivery_engine,
    )
    monkeypatch.setattr(app_mod, "project_service", service)
    monkeypatch.setattr(app_mod, "PROJECT_STORAGE_ROOT", tmp_path / "projects")
    return SimpleNamespace(app=app_mod, service=service, writer=writer, wallet=app_mod.wallet)


def _url(project_id: str, suffix: str = "") -> str:
    return f"/api/assignment/projects/{project_id}" + (f"/{suffix}" if suffix else "")


def _paid_project(env, owner) -> tuple[str, int]:
    """Project paid through the real confirm-payment route; returns (project_id, coins charged)."""
    project_id = _priced_project(env.service, user_id=str(owner["id"]))
    env.wallet.credit(owner["id"], 1_000_000, "test_topup")
    res = _signed_in(_client(), owner).post(
        _url(project_id, "confirm-payment"), json={"quote_id": current_quote_id(env.service, project_id)}
    )
    assert res.status_code == 200, res.get_data(as_text=True)
    coins = int(res.get_json()["coins_charged"])
    assert coins > 0
    return project_id, coins


def _plan_and_blueprint(env, project_id: str) -> None:
    env.service.run_research(project_id)
    env.service.run_blueprint(project_id)


def _write_everything(env, project_id: str) -> None:
    env.service.start_writer(project_id)
    for _ in range(30):
        session = env.service.get_writer_session(project_id)
        if all(s.status.value == "completed" for s in session.sections):
            break
        env.service.advance_writer(project_id)
    env.service.merge_writer_draft(project_id)


def _fail_writer_via_route(env, owner, project_id: str):
    env.service.start_writer(project_id)
    env.writer.fail = True
    res = _signed_in(_client(), owner).post(_url(project_id, "writer/advance"), json={})
    env.writer.fail = False
    assert res.status_code == 502, res.get_data(as_text=True)
    return res


def _refund(client, project_id: str, body: dict | None = None):
    return client.post(_url(project_id, "refund-failed"), json=body or {})


def _refund_rows(project_id: str) -> list[dict]:
    with economy_db.connect() as conn:
        rows = conn.execute(
            "SELECT amount, ref_id, meta_json FROM transactions "
            "WHERE kind = 'refund' AND feature = 'assignment' AND ref_id LIKE ?",
            (f"assignment-refund:{project_id}:%",),
        ).fetchall()
    return [dict(row) for row in rows]


# ------------------------------------------------------------ A. eligibility


def test_successful_paid_project_cannot_claim_refund(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _write_everything(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    res = _refund(_signed_in(_client(), owner), project_id)

    assert res.status_code == 400
    assert res.get_json()["reason"] == "OUTPUT_GENERATED"
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    assert _refund_rows(project_id) == []
    assert refund_app.service.store.require_project(project_id).artifacts["payment_confirmed"] is True


def test_paid_incomplete_project_without_recorded_failure_is_refused(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    res = _refund(_signed_in(_client(), owner), project_id)

    assert res.status_code == 400
    body = res.get_json()
    assert body["reason"] == "NO_RECORDED_FAILURE"
    assert "Traceback" not in json.dumps(body) and "provider" not in body["message"]
    assert refund_app.wallet.get_balance(owner["id"]) == balance


def test_client_supplied_failure_state_does_not_authorize_refund(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    client = _signed_in(_client(), owner)
    balance = refund_app.wallet.get_balance(owner["id"])

    # The client-driven pipeline endpoints only touch in-memory UI state.
    client.post(_url(project_id, "stages/writing/start"), json=FORGED_FAILURE_BODY)
    client.post(_url(project_id, "stages/writing/fail"), json=FORGED_FAILURE_BODY)
    res = _refund(client, project_id, FORGED_FAILURE_BODY)

    assert res.status_code == 400
    assert res.get_json()["reason"] == "NO_RECORDED_FAILURE"
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    assert PROCESSING_FAILURE_KEY not in refund_app.service.store.require_project(project_id).artifacts


def test_client_session_snapshot_is_ignored_and_failure_judged_on_server_state(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    session = refund_app.service.start_writer(project_id).to_dict()
    session["updated_at"] = "2999-01-01T00:00:00+00:00"
    refund_app.writer.fail = True
    res = _signed_in(_client(), owner).post(_url(project_id, "writer/advance"), json={"writer_session": session})
    refund_app.writer.fail = False
    assert res.status_code == 502

    artifacts = refund_app.service.store.require_project(project_id).artifacts
    assert artifacts["writer_session"]["updated_at"] != "2999-01-01T00:00:00+00:00"
    failure = artifacts[PROCESSING_FAILURE_KEY]
    assert failure["client_seeded"] is False and failure["classification"] == "execution"


def test_genuine_server_recorded_failure_authorizes_refund(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    failure = refund_app.service.store.require_project(project_id).artifacts[PROCESSING_FAILURE_KEY]
    assert failure["stage"] == "writing" and failure["client_seeded"] is False
    balance = refund_app.wallet.get_balance(owner["id"])

    res = _refund(_signed_in(_client(), owner), project_id)

    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert body["refunded"] is True and body["coins_refunded"] == coins
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins
    artifacts = refund_app.service.store.require_project(project_id).artifacts
    assert artifacts["payment_refunded"] is True and artifacts["payment_confirmed"] is False
    assert artifacts["payment_refund_coins"] == coins


def test_failure_resolved_by_a_later_success_is_not_refundable(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    refund_app.service.advance_writer(project_id)

    assert PROCESSING_FAILURE_KEY not in refund_app.service.store.require_project(project_id).artifacts
    res = _refund(_signed_in(_client(), owner), project_id)
    assert res.status_code == 400
    assert res.get_json()["reason"] in {"NO_RECORDED_FAILURE", "OUTPUT_GENERATED"}
    assert _refund_rows(project_id) == []


def test_delivered_project_cannot_be_refunded(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    project = refund_app.service.store.require_project(project_id)
    project.artifacts["delivery_package"] = {"id": "pkg-x"}
    project.artifacts[PROCESSING_FAILURE_KEY] = {
        "stage": "delivery",
        "client_seeded": False,
        "payment_confirmed_at": project.artifacts.get("payment_confirmed_at"),
    }
    refund_app.service.store.save_project(project)
    balance = refund_app.wallet.get_balance(owner["id"])

    res = _refund(_signed_in(_client(), owner), project_id)

    assert res.status_code == 400 and res.get_json()["reason"] == "DELIVERED"
    assert refund_app.wallet.get_balance(owner["id"]) == balance


def test_already_refunded_project_cannot_be_refunded_again(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    client = _signed_in(_client(), owner)
    assert _refund(client, project_id).status_code == 200
    balance = refund_app.wallet.get_balance(owner["id"])

    again = _refund(client, project_id)

    assert again.status_code == 409 and again.get_json()["reason"] == "ALREADY_REFUNDED"
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    assert [row["amount"] for row in _refund_rows(project_id)] == [coins]


def test_unpaid_project_has_nothing_to_refund(refund_app):
    owner = _user("owner@example.com")
    project_id = _priced_project(refund_app.service, user_id=str(owner["id"]))
    res = _refund(_signed_in(_client(), owner), project_id, FORGED_FAILURE_BODY)
    assert res.status_code == 400 and res.get_json()["reason"] == "NOT_PAID"


# ------------------------------------------------------------ B. content access


def _completed_project_with_delivery(env, owner) -> tuple[str, str, str]:
    """Paid project with draft, humanized draft and a delivered file; returns (project, package, file) ids."""
    project_id, _coins = _paid_project(env, owner)
    _plan_and_blueprint(env, project_id)
    _write_everything(env, project_id)
    draft = env.service.get_draft(project_id)
    env.service._persist_humanized_draft(
        project_id,
        HumanizedDraft.from_dict(
            {"id": f"hd-{project_id}", "session_id": "hs", "source_draft_id": draft.id, "content": draft.content}
        ),
    )
    delivery_dir = env.service.store.storage_root / project_id / "delivery"
    delivery_dir.mkdir(parents=True, exist_ok=True)
    (delivery_dir / "final.docx").write_bytes(b"PK-final-assignment")
    package = DeliveryPackage.from_dict(
        {
            "id": f"pkg-{project_id}",
            "project_id": project_id,
            "status": "ready",
            "client_filename": "final.docx",
            "files": [
                {
                    "id": f"file-{project_id}",
                    "filename": "final.docx",
                    "file_type": "final_assignment_docx",
                    "storage_path": str(delivery_dir / "final.docx"),
                    "ready": True,
                }
            ],
        }
    )
    env.service.delivery.store.save(package)
    project = env.service.store.require_project(project_id)
    project.artifacts["delivery_package"] = package.to_dict()
    project.artifacts["delivery_package_id"] = package.id
    env.service.store.save_project(project)
    record_checked_delivery(env.service, project_id, package.id)
    return project_id, package.id, f"file-{project_id}"


CONTENT_ROUTES = [
    ("get", "draft"),
    ("get", "writer"),
    ("get", "humanized-draft"),
    ("get", "research-plan"),
    ("get", "blueprint"),
    ("get", "delivery-package"),
    ("get", "download"),
    ("get", "revision-history"),
    ("get", "pipeline"),
    ("get", "revision-chat"),
]


def _draft_marker(env, project_id: str) -> str:
    """A line of the generated draft that appears verbatim in any JSON body that leaks it."""
    lines = [line.strip() for line in env.service.get_draft(project_id).content.splitlines()]
    marker = max((line for line in lines if re.fullmatch(r"[A-Za-z0-9 ,.:;()'-]+", line)), key=len)
    assert len(marker) >= 25
    return marker


def _admin_refund(env, project_id: str, reason: str = "provider outage after delivery"):
    admin = _user(f"admin-{uuid.uuid4().hex[:10]}@example.com", admin=True)
    return _signed_in(_client(), admin).post(
        f"/api/admin/assignment/projects/{project_id}/refund", json={"reason": reason}
    )


def _call(client, method: str, path: str):
    return getattr(client, method)(path)


def test_content_routes_work_before_refund_and_are_blocked_after(refund_app):
    owner = _user("owner@example.com")
    project_id, _pkg, _file = _completed_project_with_delivery(refund_app, owner)
    client = _signed_in(_client(), owner)
    draft_text = _draft_marker(refund_app, project_id)
    assert draft_text in client.get(_url(project_id, "draft")).get_data(as_text=True)

    for method, suffix in CONTENT_ROUTES:
        res = _call(client, method, _url(project_id, suffix))
        assert res.status_code == 200, (suffix, res.status_code)

    assert _admin_refund(refund_app, project_id).status_code == 200

    for method, suffix in CONTENT_ROUTES:
        res = _call(client, method, _url(project_id, suffix))
        assert res.status_code == 404, (suffix, res.status_code)
        assert draft_text not in res.get_data(as_text=True)
    restore = client.post(_url(project_id, "draft/restore"), json={"version": 1})
    assert restore.status_code == 404


def test_project_payload_and_list_hide_generated_content_after_refund(refund_app):
    owner = _user("owner@example.com")
    project_id, _pkg, _file = _completed_project_with_delivery(refund_app, owner)
    client = _signed_in(_client(), owner)
    draft_text = _draft_marker(refund_app, project_id)
    assert draft_text in client.get(_url(project_id)).get_data(as_text=True)

    assert _admin_refund(refund_app, project_id).status_code == 200

    res = client.get(_url(project_id))
    assert res.status_code == 200
    body = res.get_json()
    assert body["content_locked"] is True
    for key in ("draft", "humanized_draft", "writer_session", "delivery_package", "blueprint", "pipeline"):
        assert body[key] is None
    assert body["project"]["artifacts"]["payment_refunded"] is True
    assert "draft" not in body["project"]["artifacts"]
    assert draft_text not in res.get_data(as_text=True)

    listing = client.get("/api/assignment/projects")
    assert listing.status_code == 200
    assert draft_text not in listing.get_data(as_text=True)
    item = next(p for p in listing.get_json()["projects"] if p["id"] == project_id)
    assert item["can_download"] is False and item["has_delivery"] is False


def test_refunded_project_keeps_stored_content_for_audit(refund_app):
    owner = _user("owner@example.com")
    project_id, _pkg, _file = _completed_project_with_delivery(refund_app, owner)
    before = refund_app.service.get_draft(project_id).content
    assert _admin_refund(refund_app, project_id).status_code == 200

    artifacts = refund_app.service.store.require_project(project_id).artifacts
    assert refund_app.service.get_draft(project_id).content == before
    assert artifacts["humanized_draft"] and artifacts["delivery_package"]
    assert (refund_app.service.store.storage_root / project_id / "delivery" / "final.docx").is_file()


def test_alternative_download_routes_respect_ownership_and_refund(refund_app):
    owner = _user("owner@example.com")
    project_id, package_id, file_id = _completed_project_with_delivery(refund_app, owner)
    package_url = f"/api/delivery/packages/{package_id}/download"
    file_url = f"/api/delivery/files/{file_id}"
    client = _signed_in(_client(), owner)
    intruder = _signed_in(_client(), _user("intruder@example.com"))

    assert client.get(package_url).status_code == 200
    assert client.get(file_url).status_code == 200
    for other in (intruder, _client()):
        assert other.get(package_url).status_code == 404
        assert other.get(file_url).status_code == 404
    assert client.get("/api/delivery/packages/does-not-exist/download").get_json() == {"error": "Not found"}

    assert _admin_refund(refund_app, project_id).status_code == 200

    assert client.get(package_url).status_code == 404
    assert client.get(file_url).status_code == 404
    assert client.get(_url(project_id, "download")).status_code == 404


def test_user_a_cannot_read_user_b_content(refund_app):
    owner = _user("owner@example.com")
    project_id, _pkg, _file = _completed_project_with_delivery(refund_app, owner)
    intruder = _signed_in(_client(), _user("intruder@example.com"))
    for method, suffix in CONTENT_ROUTES:
        assert _call(intruder, method, _url(project_id, suffix)).status_code == 403, suffix
    assert intruder.get(_url(project_id)).status_code == 403


def test_verified_admin_can_review_refunded_content(refund_app):
    owner = _user("owner@example.com")
    project_id, package_id, _file = _completed_project_with_delivery(refund_app, owner)
    assert _admin_refund(refund_app, project_id).status_code == 200

    admin = _signed_in(_client(), _user("auditor@example.com", admin=True))
    assert admin.get(_url(project_id, "draft")).status_code == 200
    assert admin.get(f"/api/delivery/packages/{package_id}/download").status_code == 200
    assert admin.get(_url(project_id)).get_json().get("draft") is not None

    unverified_admin = _signed_in(_client(), _user("half-admin@example.com", admin=True, verified=False))
    assert unverified_admin.get(_url(project_id, "draft")).status_code in (403, 404)
    assert unverified_admin.get(f"/api/delivery/packages/{package_id}/download").status_code == 404


def test_refunded_owner_keeps_non_content_actions(refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _fail_writer_via_route(refund_app, owner, project_id)
    client = _signed_in(_client(), owner)
    assert client.get(_url(project_id, "writer")).status_code == 200
    assert _refund(client, project_id).status_code == 200

    assert client.get(_url(project_id, "writer")).status_code == 404
    assert client.get(_url(project_id)).status_code == 200
    saved = client.put(_url(project_id, "chat-transcript"), json={"messages": [{"role": "user", "text": "hi"}]})
    assert saved.status_code == 200


# ------------------------------------------------------------ C. integrity


def _refundable_project(env, owner) -> tuple[str, int]:
    project_id, coins = _paid_project(env, owner)
    _plan_and_blueprint(env, project_id)
    _fail_writer_via_route(env, owner, project_id)
    return project_id, coins


def test_concurrent_refund_requests_refund_once(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _refundable_project(refund_app, owner)
    balance = refund_app.wallet.get_balance(owner["id"])
    clients = [_signed_in(_client(), owner) for _ in range(8)]
    barrier = threading.Barrier(len(clients))
    statuses: list[int] = []
    lock = threading.Lock()

    def hit(client):
        barrier.wait()
        res = _refund(client, project_id)
        with lock:
            statuses.append(res.status_code)

    threads = [threading.Thread(target=hit, args=(c,)) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(statuses) == [200] + [409] * (len(clients) - 1)
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins
    assert [row["amount"] for row in _refund_rows(project_id)] == [coins]


def test_concurrent_service_calls_refund_once(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _refundable_project(refund_app, owner)
    balance = refund_app.wallet.get_balance(owner["id"])
    barrier = threading.Barrier(6)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt():
        barrier.wait()
        try:
            refund_assignment(refund_app.service, refund_app.wallet, project_id, reason="race")
            result = "ok"
        except RefundNotEligibleError as exc:
            result = exc.code
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count("ok") == 1
    assert set(outcomes) - {"ok"} <= {"ALREADY_REFUNDED"}
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins


def test_ledger_reference_blocks_a_second_credit_even_without_the_lock(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _refundable_project(refund_app, owner)
    reference = refund_app.service.refund_reference(project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    first = refund_app.wallet.refund_once(owner["id"], coins, "assignment", ref_id=reference)
    second = refund_app.wallet.refund_once(owner["id"], coins, "assignment", ref_id=reference)

    assert first is not None and second is None
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins


def test_interrupted_refund_is_completed_without_a_second_credit(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _refundable_project(refund_app, owner)
    reference = refund_app.service.refund_reference(project_id)
    balance = refund_app.wallet.get_balance(owner["id"])
    # Ledger row written, then the worker died before the project was marked.
    refund_app.wallet.refund_once(owner["id"], coins, "assignment", ref_id=reference)

    res = _refund(_signed_in(_client(), owner), project_id)

    # The project guard reconciles with the ledger before the route runs.
    assert res.status_code == 409 and res.get_json()["reason"] == "ALREADY_REFUNDED"
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins
    assert len(_refund_rows(project_id)) == 1
    artifacts = refund_app.service.store.require_project(project_id).artifacts
    assert artifacts["payment_refunded"] is True and artifacts["payment_refund_coins"] == coins
    assert artifacts["refund_history"][-1]["kind"] == "reconciled"


def test_refund_amount_and_audit_history_are_consistent(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _refundable_project(refund_app, owner)
    assert _refund(_signed_in(_client(), owner), project_id).status_code == 200

    rows = _refund_rows(project_id)
    assert len(rows) == 1 and rows[0]["amount"] == coins
    assert json.loads(rows[0]["meta_json"])["reason"] == "user-refund-failed-assignment"
    artifacts = refund_app.service.store.require_project(project_id).artifacts
    (entry,) = artifacts["refund_history"]
    assert entry["coins"] == coins and entry["reference"] == rows[0]["ref_id"]
    assert entry["kind"] == "failure" and entry["failure"]["stage"] == "writing"
    assert artifacts["coins_charged"] == coins


def test_repaid_project_gets_a_new_reference_and_keeps_history(refund_app):
    owner = _user("owner@example.com")
    project_id, coins = _refundable_project(refund_app, owner)
    client = _signed_in(_client(), owner)
    assert _refund(client, project_id).status_code == 200
    first_ref = refund_app.service.store.require_project(project_id).artifacts["refund_history"][0]["reference"]

    repay = client.post(
        _url(project_id, "confirm-payment"),
        json={"quote_id": current_quote_id(refund_app.service, project_id)},
    )
    assert repay.status_code == 200
    assert PROCESSING_FAILURE_KEY not in refund_app.service.store.require_project(project_id).artifacts
    assert _refund(client, project_id).get_json()["reason"] == "NO_RECORDED_FAILURE"

    refund_app.writer.fail = True
    client.post(_url(project_id, "writer/advance"), json={})
    refund_app.writer.fail = False
    assert _refund(client, project_id).status_code == 200

    history = refund_app.service.store.require_project(project_id).artifacts["refund_history"]
    assert len(history) == 2 and history[1]["reference"] != first_ref
    assert len(_refund_rows(project_id)) == 2


def test_admin_refund_requires_verified_admin_and_reason(refund_app):
    owner = _user("owner@example.com")
    project_id, _pkg, _file = _completed_project_with_delivery(refund_app, owner)
    url = f"/api/admin/assignment/projects/{project_id}/refund"

    assert _signed_in(_client(), owner).post(url, json={"reason": "please"}).status_code == 404
    assert _client().post(url, json={"reason": "x"}).status_code == 404
    half_admin = _signed_in(_client(), _user("half@example.com", admin=True, verified=False))
    assert half_admin.post(url, json={"reason": "x"}).status_code == 404
    assert _admin_refund(refund_app, project_id, reason="").status_code == 400

    balance = refund_app.wallet.get_balance(owner["id"])
    res = _admin_refund(refund_app, project_id)
    assert res.status_code == 200
    coins = res.get_json()["coins_refunded"]
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins
    (row,) = _refund_rows(project_id)
    meta = json.loads(row["meta_json"])
    assert meta["admin_id"] and meta["reason"].startswith("admin: ")
    entry = refund_app.service.store.require_project(project_id).artifacts["refund_history"][0]
    assert entry["kind"] == "admin" and entry["admin_id"] == meta["admin_id"]
    assert _admin_refund(refund_app, project_id).status_code == 409


# ------------------------------------------------------------ D. automatic refunds


def _stub_humanizer_failure(env, monkeypatch, message: str) -> None:
    monkeypatch.setattr(env.service, "_load_humanizer_session", lambda _pid, seed=None: SimpleNamespace(id="hs"))

    def advance_paragraph(_session_id):
        raise ValueError(message)

    monkeypatch.setattr(env.service, "humanizer", SimpleNamespace(advance_paragraph=advance_paragraph))


def test_auto_refund_runs_for_a_recorded_failure_before_any_output(refund_app, monkeypatch):
    owner = _user("owner@example.com")
    project_id, coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _stub_humanizer_failure(refund_app, monkeypatch, "LOGIN_REQUIRED")
    balance = refund_app.wallet.get_balance(owner["id"])

    res = _signed_in(_client(), owner).post(_url(project_id, "humanizer/advance"), json={})

    assert res.status_code == 502
    assert res.get_json()["refunded"] is True
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins
    assert len(_refund_rows(project_id)) == 1


def test_auto_refund_never_fires_once_text_was_generated(refund_app, monkeypatch):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _write_everything(refund_app, project_id)
    _stub_humanizer_failure(refund_app, monkeypatch, "LOGIN_REQUIRED")
    balance = refund_app.wallet.get_balance(owner["id"])

    res = _signed_in(_client(), owner).post(_url(project_id, "humanizer/advance"), json={})

    assert res.status_code == 502
    assert "refunded" not in res.get_json()
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    assert _refund_rows(project_id) == []
    assert refund_app.service.store.require_project(project_id).artifacts["payment_confirmed"] is True


def test_auto_refund_needs_recorded_evidence_not_just_an_exception(refund_app, monkeypatch):
    import app as app_mod

    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)

    def undecorated_failure(_project_id, *, humanizer_session=None):
        raise ValueError("LOGIN_REQUIRED")

    monkeypatch.setattr(refund_app.service, "advance_humanizer", undecorated_failure)
    balance = refund_app.wallet.get_balance(owner["id"])

    res = _signed_in(_client(), owner).post(_url(project_id, "humanizer/advance"), json={})

    assert res.status_code == 502 and "refunded" not in res.get_json()
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    assert _auto_refund_as(app_mod, owner, project_id) is None
    assert refund_app.wallet.get_balance(owner["id"]) == balance


def _auto_refund_as(app_mod, user, project_id: str):
    from flask import session

    from services.economy import auth as economy_auth

    with app_mod.app.test_request_context():
        session[economy_auth.SESSION_KEY] = user["id"]
        session[economy_auth.AUTH_SID_KEY] = economy_auth.register_session(user["id"])
        assert economy_auth.current_user_id() == user["id"]
        return app_mod._assignment_auto_refund(project_id, reason="generic")


def test_auto_refund_ignores_successful_projects(refund_app):
    import app as app_mod

    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    _write_everything(refund_app, project_id)
    balance = refund_app.wallet.get_balance(owner["id"])

    assert _auto_refund_as(app_mod, owner, project_id) is None
    assert refund_app.wallet.get_balance(owner["id"]) == balance


def test_auto_refund_with_recorded_failure_refunds_the_owner_once(refund_app):
    import app as app_mod

    owner = _user("owner@example.com")
    project_id, coins = _refundable_project(refund_app, owner)
    balance = refund_app.wallet.get_balance(owner["id"])

    first = _auto_refund_as(app_mod, owner, project_id)
    second = _auto_refund_as(app_mod, owner, project_id)

    assert first["coins_refunded"] == coins and second is None
    assert refund_app.wallet.get_balance(owner["id"]) == balance + coins
