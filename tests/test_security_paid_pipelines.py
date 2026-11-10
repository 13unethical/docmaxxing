"""Paid AI stages must never run without server-confirmed payment or for someone else's session."""

from __future__ import annotations

import json

import pytest

from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project.service import PaymentRequiredError, ProjectService
from services.assignment_project.store import ProjectStore
from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.writer_engine import MockSectionWriter, WriterEngineService
from services.writer_engine.mock_reviewer import MockSectionReviewer
from tests.assignment_helpers import current_quote_id
from tests.test_assignment_project import (
    _StubBlueprintService,
    _StubRequirementAnalyzer,
    _StubResearchService,
)

PAID_ENGINES = (
    "research",
    "blueprint",
    "writer",
    "reviewer",
    "revision",
    "humanizer",
    "ai_detection",
    "delivery",
    "citation_engine",
    "format_engine",
    "requirement_validator",
)

FORGED_PAYMENT = {"payment_confirmed": True, "artifacts": {"payment_confirmed": True}}


class _Forbidden:
    """Stands in for an AI engine; any use is recorded and fails the test."""

    def __init__(self, name: str, calls: list[str]) -> None:
        self._name = name
        self._calls = calls

    VERSION = "forbidden-mock"

    def __getattr__(self, attr: str):
        self._calls.append(f"{self._name}.{attr}")
        raise AssertionError(f"{self._name}.{attr} was reached without payment")


class _CountingWriter(MockSectionWriter):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def write_section(self, **kwargs):
        self.calls += 1
        return super().write_section(**kwargs)


def _guarded_service(tmp_path, calls: list[str]) -> ProjectService:
    engines = {name: _Forbidden(name, calls) for name in PAID_ENGINES}
    return ProjectService(
        store=ProjectStore(root=tmp_path / "projects"),
        pipeline=AssignmentPipelineService(),
        analyzer=_StubRequirementAnalyzer(),
        **engines,
    )


def _priced_project(service: ProjectService, user_id: str | None = None) -> str:
    bundle = service.create_project(
        user_id=user_id,
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    service.analyze_requirements(bundle.project.id)
    service.calculate_pricing(bundle.project.id)
    return bundle.project.id


SEED_PLAN = {
    "id": "plan-forged",
    "project_id": "x",
    "assignment_topic": "Forged",
    "section_list": [{"title": "Introduction", "purpose": "x", "estimated_words": 100}],
    **FORGED_PAYMENT,
}
SEED_SESSION = {"id": "ws-forged", "sections": [], **FORGED_PAYMENT}

SERVICE_STAGES = [
    ("run_blueprint", {}),
    ("run_blueprint", {"research_plan": SEED_PLAN}),
    ("start_writer", {}),
    ("advance_writer", {}),
    ("advance_writer", {"writer_session": SEED_SESSION}),
    ("revise_writer_section", {"section_id": "introduction", "writer_session": SEED_SESSION}),
    ("merge_writer_draft", {"writer_session": SEED_SESSION}),
    ("run_academic_review", {}),
    ("run_revision", {"review_report": {"id": "rr-forged", **FORGED_PAYMENT}}),
    ("start_humanizer", {}),
    ("advance_humanizer", {"humanizer_session": {"id": "hs-forged", **FORGED_PAYMENT}}),
    ("merge_humanized_draft", {"humanizer_session": {"id": "hs-forged", **FORGED_PAYMENT}}),
    ("run_citation_generation", {}),
    ("run_formatting", {}),
    ("run_requirement_validation", {}),
    ("start_ai_detection", {}),
    ("advance_ai_detection", {"detection_session": {"id": "ds-forged", **FORGED_PAYMENT}}),
    ("finalize_ai_detection", {"detection_session": {"id": "ds-forged", **FORGED_PAYMENT}}),
    ("run_delivery", {}),
    ("retry_stage", {"stage": "writing"}),
    ("retry_stage", {"stage": "humanization"}),
    ("apply_client_revision", {"message": "Make it longer"}),
]


# --------------------------------------------------------------- service layer


@pytest.mark.parametrize("method,kwargs", SERVICE_STAGES, ids=[f"{m}-{i}" for i, (m, _) in enumerate(SERVICE_STAGES)])
def test_unpaid_project_cannot_run_paid_stage(tmp_path, method, kwargs):
    calls: list[str] = []
    service = _guarded_service(tmp_path, calls)
    project_id = _priced_project(service)
    before = dict(service.store.require_project(project_id).artifacts)

    with pytest.raises(PaymentRequiredError):
        getattr(service, method)(project_id, **kwargs)

    assert calls == []
    after = service.store.require_project(project_id).artifacts
    assert after == before
    assert after.get("payment_confirmed") is not True


def test_seeded_research_plan_does_not_imply_payment(tmp_path):
    calls: list[str] = []
    service = _guarded_service(tmp_path, calls)
    project_id = _priced_project(service)

    with pytest.raises(PaymentRequiredError):
        service.run_blueprint(project_id, research_plan=SEED_PLAN)
    with pytest.raises(PaymentRequiredError):
        service.start_writer(project_id)

    assert calls == []
    artifacts = service.store.require_project(project_id).artifacts
    assert "research_plan_id" not in artifacts
    assert "blueprint_id" not in artifacts


@pytest.mark.parametrize("flag", [False, None, "true", 1, "yes"])
def test_only_a_real_server_confirmation_counts(tmp_path, flag):
    calls: list[str] = []
    service = _guarded_service(tmp_path, calls)
    project_id = _priced_project(service)
    project = service.store.require_project(project_id)
    project.artifacts["payment_confirmed"] = flag
    service.store.save_project(project)

    with pytest.raises(PaymentRequiredError):
        service.start_writer(project_id)
    assert calls == []


def test_refunded_project_cannot_continue_paid_stages(tmp_path):
    calls: list[str] = []
    service = _guarded_service(tmp_path, calls)
    project_id = _priced_project(service)
    service.confirm_payment(project_id, quote_id=current_quote_id(service, project_id))
    service.mark_assignment_refunded(project_id, 100)

    with pytest.raises(PaymentRequiredError):
        service.advance_writer(project_id)
    with pytest.raises(PaymentRequiredError):
        service.retry_stage(project_id, "writing")
    assert calls == []


def test_paid_project_runs_blueprint_and_writer(tmp_path):
    writer = _CountingWriter()
    service = ProjectService(
        store=ProjectStore(root=tmp_path / "projects"),
        pipeline=AssignmentPipelineService(),
        research=_StubResearchService(),  # type: ignore[arg-type]
        blueprint=_StubBlueprintService(),  # type: ignore[arg-type]
        writer=WriterEngineService(writer=writer, reviewer=MockSectionReviewer()),
        analyzer=_StubRequirementAnalyzer(),
    )
    project_id = _priced_project(service)
    service.confirm_payment(project_id, quote_id=current_quote_id(service, project_id))

    service.run_research(project_id)
    service.run_blueprint(project_id)
    session = service.start_writer(project_id)
    service.advance_writer(project_id)

    assert session.project_id == project_id
    assert writer.calls >= 1


# --------------------------------------------------------------- HTTP layer


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.delenv("INTERNAL_TOOLS_ENABLED", raising=False)
    economy_db.init_db()
    return tmp_path


def _client():
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


def _user(email, *, admin=False, verified=True):
    user = economy_auth.create_user(email, "secret123")
    if verified:
        economy_auth.mark_email_verified(user["id"], user["email"])
    if admin:
        with economy_db.connect() as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user["id"],))
    return economy_auth.get_user(user["id"])


def _signed_in(client, user):
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    return client


@pytest.fixture()
def guarded_app(economy, tmp_path, monkeypatch):
    import app as app_mod

    calls: list[str] = []
    service = _guarded_service(tmp_path, calls)
    monkeypatch.setattr(app_mod, "project_service", service)
    return app_mod, service, calls


PAID_ROUTES = [
    ("post", "blueprint"),
    ("post", "writer/start"),
    ("post", "writer/advance"),
    ("post", "writer/revise"),
    ("post", "writer/merge"),
    ("post", "review"),
    ("post", "revision"),
    ("post", "humanizer/start"),
    ("post", "humanizer/advance"),
    ("post", "humanizer/merge"),
    ("post", "ai-detection/start"),
    ("post", "ai-detection/advance"),
    ("post", "ai-detection/finalize"),
    ("post", "citations/generate"),
    ("post", "format"),
    ("post", "validate-requirements"),
    ("post", "stages/writing/retry"),
    ("post", "delivery"),
    ("post", "revision-chat"),
]

FORGED_BODY = {
    **FORGED_PAYMENT,
    "research_plan": SEED_PLAN,
    "writer_session": SEED_SESSION,
    "section_id": "introduction",
    "message": "Make it longer",
    "paid": True,
    "coins": 0,
}


def _hit(client, method, project_id, suffix):
    path = f"/api/assignment/projects/{project_id}/{suffix}"
    if method == "get":
        return client.get(path)
    return client.post(path, json=FORGED_BODY)


@pytest.mark.parametrize("method,suffix", PAID_ROUTES)
def test_owner_of_unpaid_project_is_refused_before_any_ai(guarded_app, method, suffix):
    app_mod, service, calls = guarded_app
    owner = _user("owner@example.com")
    project_id = _priced_project(service, user_id=str(owner["id"]))
    client = _signed_in(_client(), owner)
    balance = app_mod.wallet.get_balance(owner["id"])

    res = _hit(client, method, project_id, suffix)

    assert res.status_code == 400, res.get_data(as_text=True)
    assert "Payment must be confirmed" in res.get_json()["error"]
    assert calls == []
    artifacts = service.store.require_project(project_id).artifacts
    assert artifacts.get("payment_confirmed") is not True
    assert not artifacts.get("payment_refunded")
    assert app_mod.wallet.get_balance(owner["id"]) == balance


class _NoPackageDelivery:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def get_package_by_project(self, _project_id):
        raise KeyError("no package")

    def prepare_package(self, **_kwargs):
        self._calls.append("delivery.prepare_package")
        raise AssertionError("delivery packaging reached without payment")


def test_download_of_unpaid_project_does_not_build_a_package(guarded_app):
    _app_mod, service, calls = guarded_app
    service.delivery = _NoPackageDelivery(calls)
    owner = _user("owner@example.com")
    project_id = _priced_project(service, user_id=str(owner["id"]))
    client = _signed_in(_client(), owner)

    res = client.get(f"/api/assignment/projects/{project_id}/download")

    assert res.status_code == 400
    assert "Payment must be confirmed" in res.get_json()["error"]
    assert calls == []


@pytest.mark.parametrize("suffix", ["blueprint", "writer/start", "writer/advance", "revision-chat"])
def test_other_users_project_is_forbidden(guarded_app, suffix):
    _app_mod, service, calls = guarded_app
    owner = _user("owner@example.com")
    project_id = _priced_project(service, user_id=str(owner["id"]))
    project = service.store.require_project(project_id)
    project.artifacts["payment_confirmed"] = True
    service.store.save_project(project)

    intruder = _signed_in(_client(), _user("intruder@example.com"))
    assert _hit(intruder, "post", project_id, suffix).status_code == 403
    assert _hit(_client(), "post", project_id, suffix).status_code == 401
    assert calls == []


def test_unverified_owner_cannot_reach_paid_routes(guarded_app):
    _app_mod, service, calls = guarded_app
    owner = _user("late@example.com", verified=False)
    project_id = _priced_project(service, user_id=str(owner["id"]))
    client = _signed_in(_client(), owner)
    assert _hit(client, "post", project_id, "writer/start").status_code == 403
    assert calls == []


def test_debug_stage_runner_cannot_bypass_payment(guarded_app, monkeypatch):
    app_mod, service, calls = guarded_app
    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    admin = _user("admin@example.com", admin=True)
    project_id = _priced_project(service, user_id=str(admin["id"]))
    client = _signed_in(_client(), admin)

    for stage in ("research", "blueprint", "writer"):
        res = client.post("/api/debug/run-stage", json={"stage": stage, "project_id": project_id, **FORGED_PAYMENT})
        body = res.get_json()
        assert body["success"] is False, stage
        assert "Payment" in body["errors"][0]["error"]
        assert "traceback" not in json.dumps(body).lower()
    assert calls == []
    assert service.store.require_project(project_id).artifacts.get("payment_confirmed") is not True


def test_admin_route_access_does_not_imply_payment(guarded_app):
    _app_mod, service, calls = guarded_app
    admin = _user("admin@example.com", admin=True)
    project_id = _priced_project(service, user_id="someone-else")
    client = _signed_in(_client(), admin)
    res = _hit(client, "post", project_id, "writer/start")
    assert res.status_code == 400
    assert calls == []


def test_confirm_payment_charges_once_and_unlocks_writer(guarded_app):
    app_mod, service, _calls = guarded_app
    owner = _user("payer@example.com")
    project_id = _priced_project(service, user_id=str(owner["id"]))
    app_mod.wallet.credit(owner["id"], 1_000_000, "test_topup")
    start = app_mod.wallet.get_balance(owner["id"])
    client = _signed_in(_client(), owner)

    quote = {"quote_id": current_quote_id(service, project_id)}
    first = client.post(f"/api/assignment/projects/{project_id}/confirm-payment", json=quote)
    assert first.status_code == 200, first.get_data(as_text=True)
    after_first = app_mod.wallet.get_balance(owner["id"])
    second = client.post(f"/api/assignment/projects/{project_id}/confirm-payment", json=quote)
    assert second.status_code == 200
    assert second.get_json()["coins_charged"] == first.get_json()["coins_charged"] == start - after_first
    assert second.get_json()["charged_now"] == 0

    assert after_first < start
    assert app_mod.wallet.get_balance(owner["id"]) == after_first
    assert service.store.require_project(project_id).artifacts.get("payment_confirmed") is True
    service._require_payment(project_id, "writing")


# --------------------------------------------------------------- standalone writer API


@pytest.fixture()
def standalone_writer(economy, monkeypatch):
    import app as app_mod

    calls: list[str] = []
    engine = WriterEngineService(writer=_Forbidden("writer", calls), reviewer=_Forbidden("reviewer", calls))
    monkeypatch.setattr(app_mod, "writer_engine", engine)
    monkeypatch.setattr(app_mod, "_standalone_writer_owners", {})
    return app_mod, engine, calls


def _writer_payload(**extra):
    return {
        "requirement_json": {"assignment_type": "Essay", "word_count": 500},
        "research_plan": {"assignment_topic": "Topic"},
        "blueprint": {
            "writing_order": ["intro"],
            "sections": [{"id": "intro", "title": "Introduction", "estimated_words": 200}],
        },
        **extra,
    }


def _create_session(client):
    res = client.post("/api/writer/session", json=_writer_payload())
    assert res.status_code == 201, res.get_data(as_text=True)
    return res.get_json()["id"]


WRITER_OPS = [
    ("post", "advance", {}),
    ("post", "revise", {"section_id": "intro"}),
    ("post", "merge", {"title": "T"}),
]


def test_anonymous_cannot_use_standalone_writer(standalone_writer):
    _app_mod, engine, calls = standalone_writer
    client = _client()
    assert client.post("/api/writer/session", json=_writer_payload()).status_code == 401
    assert client.get("/api/writer/session/anything").status_code == 401
    for _method, op, body in WRITER_OPS:
        assert client.post(f"/api/writer/session/anything/{op}", json=body).status_code == 401
    assert engine.sessions._sessions == {}
    assert calls == []


def test_unverified_user_cannot_use_standalone_writer(standalone_writer):
    _app_mod, _engine, calls = standalone_writer
    client = _signed_in(_client(), _user("u@example.com", verified=False))
    assert client.post("/api/writer/session", json=_writer_payload()).status_code == 403
    assert calls == []


def test_verified_user_can_prepare_and_read_own_draft_session(standalone_writer):
    _app_mod, _engine, calls = standalone_writer
    client = _signed_in(_client(), _user("a@example.com"))
    session_id = _create_session(client)
    res = client.get(f"/api/writer/session/{session_id}")
    assert res.status_code == 200
    assert res.get_json()["id"] == session_id
    assert calls == []


@pytest.mark.parametrize("method,op,body", WRITER_OPS)
def test_paid_writer_operations_are_disabled_for_owner(standalone_writer, method, op, body):
    app_mod, _engine, calls = standalone_writer
    user = _user("a@example.com")
    client = _signed_in(_client(), user)
    session_id = _create_session(client)
    balance = app_mod.wallet.get_balance(user["id"])

    res = client.post(f"/api/writer/session/{session_id}/{op}", json=body)

    assert res.status_code == 403
    assert res.get_json()["code"] == "WRITER_API_DISABLED"
    assert calls == []
    assert app_mod.wallet.get_balance(user["id"]) == balance


@pytest.mark.parametrize("method,op,body", WRITER_OPS)
def test_user_b_cannot_touch_user_a_writer_session(standalone_writer, method, op, body):
    _app_mod, _engine, calls = standalone_writer
    session_id = _create_session(_signed_in(_client(), _user("a@example.com")))
    other = _signed_in(_client(), _user("b@example.com"))

    assert other.get(f"/api/writer/session/{session_id}").status_code == 404
    assert other.post(f"/api/writer/session/{session_id}/{op}", json=body).status_code == 404
    assert calls == []


def test_admin_cannot_read_or_drive_someone_elses_writer_session(standalone_writer):
    _app_mod, _engine, calls = standalone_writer
    session_id = _create_session(_signed_in(_client(), _user("a@example.com")))
    admin = _signed_in(_client(), _user("admin@example.com", admin=True))
    assert admin.get(f"/api/writer/session/{session_id}").status_code == 404
    assert admin.post(f"/api/writer/session/{session_id}/advance").status_code == 404
    assert calls == []


def test_assignment_pipeline_sessions_are_not_exposed(standalone_writer):
    _app_mod, engine, calls = standalone_writer
    pipeline_session = engine.create_session(project_id="project-123", **_writer_payload())
    client = _signed_in(_client(), _user("a@example.com"))
    assert client.get(f"/api/writer/session/{pipeline_session.id}").status_code == 404
    assert client.post(f"/api/writer/session/{pipeline_session.id}/advance").status_code == 404
    assert calls == []


def test_client_project_id_cannot_hijack_assignment_session(standalone_writer):
    _app_mod, engine, calls = standalone_writer
    pipeline_session = engine.create_session(project_id="project-123", **_writer_payload())
    client = _signed_in(_client(), _user("a@example.com"))

    res = client.post("/api/writer/session", json=_writer_payload(project_id="project-123"))

    assert res.status_code == 400
    assert engine.sessions.get_by_project("project-123").id == pipeline_session.id
    assert calls == []
