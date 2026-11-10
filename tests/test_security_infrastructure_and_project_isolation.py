"""Browser/infrastructure endpoints are admin-only, the AI orchestrator is closed, project
artifacts can't be swapped through the shared engine stores, downloads follow the wallet
ledger, and free brief parsing is metered."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from services import ai_detector, free_humanize
from services.assignment_project.service import PAYMENT_CYCLE_KEY
from services.browser.jobs.models import Job, JobStatus
from services.economy import assignment_payments as payment_ledger
from services.research_engine.models import ResearchPlan
from services.reviewer_engine.models import ReviewReport
from tests.test_security_paid_pipelines import _client, _signed_in, _user, economy  # noqa: F401
from tests.test_security_refund_integrity import (  # noqa: F401  (refund_app is a fixture)
    _completed_project_with_delivery,
    _paid_project,
    _plan_and_blueprint,
    _refund_rows,
    _url,
    _write_everything,
    refund_app,
)


class _Tripwire:
    """Stands in for a paid provider or the shared browser: any use is recorded and fails."""

    def __init__(self, calls: list[str], name: str) -> None:
        self._calls = calls
        self._name = name

    def __call__(self, *_args, **_kwargs):
        self._calls.append(self._name)
        raise AssertionError(f"{self._name} must not run")

    def __getattr__(self, attr):
        def call(*_args, **_kwargs):
            self._calls.append(f"{self._name}.{attr}")
            raise AssertionError(f"{self._name}.{attr} must not run")

        return call


@pytest.fixture()
def traps(economy, monkeypatch):
    import app as app_mod

    calls: list[str] = []
    monkeypatch.setattr(app_mod, "zerogpt_client", _Tripwire(calls, "zerogpt"))
    monkeypatch.setattr(app_mod, "_browser_submit", _Tripwire(calls, "browser_submit"))
    monkeypatch.setattr(app_mod, "ensure_engine_started", _Tripwire(calls, "ensure_engine_started"))
    return SimpleNamespace(app=app_mod, calls=calls)


# ------------------------------------------------------------ AI orchestrator

ORCHESTRATOR = "/api/ai/orchestrator/review"
ESSAY = "This essay discusses artificial intelligence in higher education and its effects on study habits."


def test_anonymous_orchestrator_request_never_reaches_zerogpt(traps):
    res = _client().post(ORCHESTRATOR, json={"text": ESSAY})
    assert res.status_code == 401
    assert traps.calls == []


def test_orchestrator_is_closed_for_signed_in_users_and_projects(traps, refund_app):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(refund_app, owner)
    for user in (owner, _user("other@example.com"), _user("boss@example.com", admin=True)):
        client = _signed_in(_client(), user)
        for body in ({"text": ESSAY}, {"text": ESSAY, "project_id": project_id}, {"text": ESSAY * 5000}):
            res = client.post(ORCHESTRATOR, json=body)
            assert res.status_code == 403 and res.get_json()["code"] == "ORCHESTRATOR_API_DISABLED"
    assert traps.calls == []
    assert "orchestrator" not in str(refund_app.service.store.require_project(project_id).artifacts)


def test_public_free_detector_still_works(traps, monkeypatch):
    for name in ("FREE_DETECT_GUEST_WORDS", "FREE_DETECT_USER_WORDS", "FREE_DETECT_USER_DAILY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FREE_DETECT_GUEST_DAILY", "1")
    monkeypatch.setattr(ai_detector, "_score_remote", lambda texts: ([0.1] * len(texts), "test-v1"))
    text = (
        "I walked to the library on Tuesday because the printer at home had died again. "
        "The queue was long, so I read the first chapter while I waited. "
        "By the time my pages came out, I had already changed my mind about the introduction."
    )
    guest = _client()
    assert guest.post("/api/detector/free", json={"text": text}).status_code == 200
    assert guest.post("/api/detector/free", json={"text": text}).status_code == 403
    assert traps.calls == []


# ------------------------------------------------------------ Browser infrastructure

BROWSER_ROUTES = [
    ("post", "/api/browser/runtime-test"),
    ("get", "/api/browser/health"),
    ("post", "/api/browser/cdp-diagnostics"),
    ("post", "/api/browser/connect"),
    ("get", "/api/browser/metrics"),
    ("post", "/api/browser/providers/stealthwriter/health"),
    ("post", "/api/browser/providers/stealthwriter/session"),
    ("post", "/api/browser/providers/stealthwriter/login"),
    ("post", "/api/browser/providers/stealthwriter/check-login"),
    ("post", "/api/browser/providers/stealthwriter/status"),
    ("post", "/api/browser/providers/stealthwriter/open"),
    ("post", "/api/browser/providers/stealthwriter/verify-production"),
    ("get", "/api/browser/providers/plagdetect/config"),
    ("post", "/api/browser/providers/plagdetect/status"),
    ("post", "/api/browser/providers/plagdetect/login"),
]


@pytest.mark.parametrize("method,path", BROWSER_ROUTES)
def test_browser_management_is_hidden_from_everyone_but_verified_admins(traps, method, path):
    callers = (
        _client(),
        _signed_in(_client(), _user("student@example.com")),
        _signed_in(_client(), _user("half-admin@example.com", admin=True, verified=False)),
    )
    for client in callers:
        res = getattr(client, method)(path, headers={"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"})
        assert res.status_code == 404, path
        assert "traceback" not in res.get_data(as_text=True).lower()
    restart = _client().post("/api/browser/restart", environ_base={"REMOTE_ADDR": "127.0.0.1"})
    assert restart.status_code == 404
    assert traps.calls == []


def test_verified_admin_reaches_browser_management_without_tracebacks(traps, monkeypatch):
    admin = _signed_in(_client(), _user("ops@example.com", admin=True))
    config = admin.get("/api/browser/providers/plagdetect/config")
    assert config.status_code == 200 and config.get_json()["success"] is True

    monkeypatch.setattr(
        traps.app,
        "_browser_submit",
        lambda fn, timeout=None: {"logged_in": True, "current_url": "https://example.test", "plan": "x", "username": "u"},
    )
    status = admin.post("/api/browser/providers/stealthwriter/status")
    assert status.status_code == 200 and status.get_json()["logged_in"] is True

    def broken(fn, timeout=None):
        raise RuntimeError("cdp socket closed at /srv/chrome/profile")

    monkeypatch.setattr(traps.app, "_browser_submit", broken)
    failed = admin.post("/api/browser/providers/stealthwriter/status")
    assert failed.status_code == 500
    assert "traceback" not in failed.get_data(as_text=True).lower()
    assert traps.calls == []


def _paying_user_humanizer(app_mod, monkeypatch, job: Job):
    monkeypatch.setenv("FREE_HUMANIZE_USER_DAILY", "0")
    monkeypatch.setattr(app_mod, "_student_humanize", lambda *_a, **_k: None)
    monkeypatch.setattr(app_mod, "_student_rescue_after", lambda *_a, **_k: None)
    monkeypatch.setattr(app_mod, "_stealthwriter_down_until", 0.0)
    monkeypatch.setattr(app_mod, "health_monitor", None)
    monkeypatch.setattr(app_mod, "ensure_engine_started", lambda: None)
    monkeypatch.setattr(app_mod, "browser_worker", SimpleNamespace(job_timeout=1))

    class _JM:
        def create(self, *_args, **_kwargs):
            return job

        def wait(self, *_args, **_kwargs):
            return job

        def get(self, _job_id):
            return job

    monkeypatch.setattr(app_mod, "job_manager", _JM())
    user = _user("writer@example.com")
    app_mod.wallet.credit(user["id"], 10_000, "test_topup")
    return user


def test_public_humanizer_works_and_hides_shared_browser_state(economy, monkeypatch):
    import app as app_mod

    job = Job(provider="stealthwriter", operation="humanize", payload={"text": "x"}, max_retries=0)
    job.status = JobStatus.COMPLETED
    job.result = {"humanized_text": "Rewritten by the humanizer.", "elapsed_seconds": 0.2}
    user = _paying_user_humanizer(app_mod, monkeypatch, job)
    client = _signed_in(_client(), user)
    url = "/api/browser/providers/stealthwriter/humanize"
    text = "Please rewrite this paragraph so it reads like a person wrote it."

    ok = client.post(url, json={"text": text})
    assert ok.status_code == 200 and ok.get_json()["humanized_text"] == "Rewritten by the humanizer."

    balance = app_mod.wallet.get_balance(user["id"])
    job.status = JobStatus.FAILED
    job.error = "Selector #output not found on https://app.stealthwriter.ai/dashboard?session=abc"
    job.error_code = "AUTOMATION_ERROR"
    job.error_details = {"current_url": "https://app.stealthwriter.ai/dashboard?session=abc",
                         "dom_snippet": "<div>account@ops</div>", "visible_buttons": ["Humanize"]}
    failed = client.post(url, json={"text": text})
    body = failed.get_data(as_text=True)
    assert failed.status_code == 422 and failed.get_json()["error"] == "AUTOMATION_ERROR"
    for leak in ("stealthwriter.ai", "dom_snippet", "account@ops", "Selector", "visible_buttons"):
        assert leak not in body
    assert app_mod.wallet.get_balance(user["id"]) == balance

    def explode(*_args, **_kwargs):
        raise RuntimeError("worker crashed in /srv/docmaxxing/services/browser/worker.py")

    monkeypatch.setattr(app_mod, "ensure_engine_started", explode)
    crashed = client.post(url, json={"text": text})
    body = crashed.get_data(as_text=True)
    assert crashed.status_code == 500 and crashed.get_json()["error"] == "HUMANIZE_FAILED"
    assert "traceback" not in body.lower() and "/srv/" not in body
    assert app_mod.wallet.get_balance(user["id"]) == balance


# ------------------------------------------------------------ Shared store isolation


def test_client_plan_with_another_projects_id_gets_a_server_id(refund_app):
    victim = _user("victim@example.com")
    project_a, _ = _paid_project(refund_app, victim)
    _plan_and_blueprint(refund_app, project_a)
    victim_plan = refund_app.service._server_research_plan(project_a)
    attacker = _user("attacker@example.com")
    project_b, _ = _paid_project(refund_app, attacker)

    seed = {**victim_plan.to_dict(), "id": victim_plan.id, "project_id": project_a, "assignment_topic": "FORGED"}
    res = _signed_in(_client(), attacker).post(_url(project_b, "blueprint"), json={"research_plan": seed})
    assert res.status_code == 200, res.get_data(as_text=True)

    adopted = refund_app.service._server_research_plan(project_b)
    assert adopted.id != victim_plan.id and adopted.project_id == project_b
    assert refund_app.service.store.require_project(project_b).artifacts["research_plan_id"] == adopted.id
    seen = refund_app.service._server_research_plan(project_a)
    assert seen.id == victim_plan.id and seen.project_id == project_a
    assert seen.to_dict() == victim_plan.to_dict()


def test_client_review_with_another_projects_id_cannot_replace_it(refund_app):
    victim = _user("victim@example.com")
    project_a, _ = _paid_project(refund_app, victim)
    victim_review = refund_app.service._persist_review_report(
        project_a, ReviewReport.from_dict({"id": "review-a", "passed": False, "issues": []})
    )
    attacker = _user("attacker@example.com")
    project_b, _ = _paid_project(refund_app, attacker)
    _plan_and_blueprint(refund_app, project_b)
    _write_everything(refund_app, project_b)

    seed = {"id": victim_review.id, "project_id": project_a, "passed": True, "issues": []}
    res = _signed_in(_client(), attacker).post(_url(project_b, "revision"), json={"review_report": seed})
    assert res.status_code == 200, res.get_data(as_text=True)

    adopted = refund_app.service._load_review_report(project_b)
    assert adopted.id != victim_review.id and adopted.project_id == project_b
    seen = refund_app.service._load_review_report(project_a)
    assert seen.id == "review-a" and seen.project_id == project_a and seen.passed is False


def test_memory_object_of_another_project_is_rejected(refund_app):
    owner = _user("owner@example.com")
    project_a, _ = _paid_project(refund_app, owner)
    project_b, _ = _paid_project(refund_app, _user("other@example.com"))
    _plan_and_blueprint(refund_app, project_a)
    stored = refund_app.service._server_research_plan(project_a)
    service = refund_app.service

    impostor = ResearchPlan.from_dict({**stored.to_dict(), "project_id": project_b, "assignment_topic": "B"})
    service._vouch(impostor)  # trusted, but for project B
    service.research.store._plans[impostor.id] = impostor
    service.research.store._by_project[project_a] = impostor.id

    loaded = service._server_research_plan(project_a)
    assert loaded.project_id == project_a and loaded.to_dict() == stored.to_dict()
    assert not service._vouched(impostor, project_a)


def test_trusted_artifacts_survive_a_worker_restart_without_a_bypass(refund_app):
    owner = _user("owner@example.com")
    project_id, _ = _paid_project(refund_app, owner)
    _plan_and_blueprint(refund_app, project_id)
    service = refund_app.service
    plan_id = service._server_research_plan(project_id).id
    blueprint_id = service.get_blueprint(project_id).id

    # A new worker: empty memory stores and an empty trust registry.
    service.research.store._plans.clear()
    service.research.store._by_project.clear()
    service.blueprint.store._by_project.clear()
    with service._vouched_lock:
        service._vouched_keys.clear()
    assert service._server_research_plan(project_id).id == plan_id
    assert service.get_blueprint(project_id).id == blueprint_id

    other, _ = _paid_project(refund_app, _user("fresh@example.com"))
    stray = ResearchPlan.from_dict({**service._server_research_plan(project_id).to_dict(), "id": "stray", "project_id": other})
    service.research.store.save(stray)
    with service._vouched_lock:
        service._vouched_keys.clear()
    assert service._server_research_plan(other) is None


# ------------------------------------------------------------ Delivery and the ledger

DOWNLOADS = ("assignment", "package", "file")


def _download(client, kind: str, project_id: str, package_id: str, file_id: str):
    if kind == "assignment":
        return client.get(_url(project_id, "download"))
    if kind == "package":
        return client.get(f"/api/delivery/packages/{package_id}/download")
    return client.get(f"/api/delivery/files/{file_id}")


@pytest.mark.parametrize("kind", DOWNLOADS)
def test_ledger_refund_blocks_downloads_even_with_stale_project_json(refund_app, kind):
    owner = _user("owner@example.com")
    project_id, package_id, file_id = _completed_project_with_delivery(refund_app, owner)
    client = _signed_in(_client(), owner)
    assert _download(client, kind, project_id, package_id, file_id).data == b"PK-final-assignment"

    cycle_id = refund_app.service.store.require_project(project_id).artifacts[PAYMENT_CYCLE_KEY]
    payment_ledger.close_cycle(project_id, cycle_id, user_id=owner["id"], kind="admin", reason="out of band")
    artifacts = refund_app.service.store.require_project(project_id).artifacts
    assert artifacts["payment_confirmed"] is True and not artifacts.get("payment_refunded")
    balance = refund_app.wallet.get_balance(owner["id"])
    rows = len(_refund_rows(project_id))

    for _ in range(2):
        assert _download(client, kind, project_id, package_id, file_id).status_code == 404
    assert refund_app.service.store.require_project(project_id).artifacts["payment_refunded"] is True
    assert refund_app.wallet.get_balance(owner["id"]) == balance
    assert len(_refund_rows(project_id)) == rows

    admin = _signed_in(_client(), _user("auditor@example.com", admin=True))
    assert _download(admin, kind, project_id, package_id, file_id).data == b"PK-final-assignment"


@pytest.mark.parametrize("kind", DOWNLOADS)
def test_downloads_fail_closed_when_the_ledger_is_unreadable(refund_app, monkeypatch, kind):
    owner = _user("owner@example.com")
    project_id, package_id, file_id = _completed_project_with_delivery(refund_app, owner)

    def down(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(payment_ledger, "get_cycle", down)
    denied = _download(_signed_in(_client(), owner), kind, project_id, package_id, file_id)
    # The assignment route is refused by the project guard (PROJECT_UNAVAILABLE) before the view.
    assert denied.status_code == 503 and denied.get_json()["error"] in {"DOWNLOAD_UNAVAILABLE", "PROJECT_UNAVAILABLE"}
    assert b"PK-final-assignment" not in denied.data
    admin = _signed_in(_client(), _user("auditor@example.com", admin=True))
    assert _download(admin, kind, project_id, package_id, file_id).data == b"PK-final-assignment"


def test_paid_owner_downloads_keep_working(refund_app):
    owner = _user("owner@example.com")
    project_id, package_id, file_id = _completed_project_with_delivery(refund_app, owner)
    client = _signed_in(_client(), owner)
    stranger = _signed_in(_client(), _user("stranger@example.com"))
    for kind in DOWNLOADS:
        assert _download(client, kind, project_id, package_id, file_id).data == b"PK-final-assignment"
        assert _download(stranger, kind, project_id, package_id, file_id).status_code in (403, 404)
    assert refund_app.service.store.require_project(project_id).artifacts["payment_confirmed"] is True


# ------------------------------------------------------------ Brief parsing (Formatter V2)

BRIEF_URL = "/api/extract-requirements-v2"
BRIEF = {"requirements_text": "Font: Times New Roman, 12 pt. Line spacing: double.", "format_style": "apa7"}


@pytest.fixture()
def smartform(economy, monkeypatch):
    import app as app_mod
    from formatter_v2 import smartform as smartform_mod
    from formatter_v2.smartform import gemini_client
    from formatter_v2.spec import UserOverrides

    calls: list[str] = []

    def fake_extract(brief, client):
        calls.append("gemini")
        return SimpleNamespace(style=None, warnings=[], unsupported=[])

    def fake_overrides(extracted, profile):
        return SimpleNamespace(overrides=UserOverrides(font_size_pt=12), evidence_by_field={})

    class _NoGemini:
        def generate(self, **_kwargs):
            raise AssertionError("real Gemini must not run")

    for name in ("SMARTFORM_GUEST_DAILY", "SMARTFORM_GUEST_IP_DAILY", "SMARTFORM_USER_DAILY",
                 "SMARTFORM_RATE_PER_MIN", "SMARTFORM_BRIEF_MAX_CHARS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FORMATTER_V2_ENABLED", "1")
    monkeypatch.setattr(smartform_mod, "extract_requirements", fake_extract)
    monkeypatch.setattr(smartform_mod, "to_user_overrides", fake_overrides)
    monkeypatch.setattr(gemini_client, "GeminiSmartformClient", _NoGemini)
    return calls


def test_guest_brief_parsing_has_a_daily_allowance(smartform, monkeypatch):
    monkeypatch.setenv("SMARTFORM_GUEST_DAILY", "1")
    monkeypatch.setenv("SMARTFORM_GUEST_IP_DAILY", "1")
    guest = _client()
    first = guest.post(BRIEF_URL, data=BRIEF)
    assert first.status_code == 200 and first.get_json()["overrides"]["font_size_pt"] == 12
    second = guest.post(BRIEF_URL, data=BRIEF)
    assert second.status_code == 403 and second.get_json()["error"] == "REGISTER_REQUIRED"
    assert _client().post(BRIEF_URL, data=BRIEF).status_code == 403  # same IP, fresh cookies
    assert smartform == ["gemini"]


def test_brief_parsing_is_rate_limited_and_size_capped(smartform, monkeypatch):
    monkeypatch.setenv("SMARTFORM_RATE_PER_MIN", "2")
    monkeypatch.setenv("SMARTFORM_BRIEF_MAX_CHARS", "200")
    user = _signed_in(_client(), _user("student@example.com"))
    too_long = user.post(BRIEF_URL, data={**BRIEF, "requirements_text": "x" * 201})
    assert too_long.status_code == 400 and too_long.get_json()["error"] == "BRIEF_TOO_LONG"
    codes = [user.post(BRIEF_URL, data=BRIEF).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert smartform == ["gemini", "gemini"]


def test_brief_parsing_failure_returns_the_allowance_and_hides_the_error(smartform, monkeypatch):
    from formatter_v2 import smartform as smartform_mod

    monkeypatch.setenv("SMARTFORM_USER_DAILY", "1")

    def failing(brief, client):
        raise RuntimeError("Gemini 500: key AIza-secret at /srv/app.py")

    monkeypatch.setattr(smartform_mod, "extract_requirements", failing)
    user_row = _user("student@example.com")
    user = _signed_in(_client(), user_row)
    res = user.post(BRIEF_URL, data=BRIEF)
    assert res.status_code == 502
    assert "AIza" not in res.get_data(as_text=True) and "/srv/" not in res.get_data(as_text=True)
    assert free_humanize.used_today(f"brief:user:{int(user_row['id'])}") == 0


def test_brief_parsing_stays_off_when_formatter_v2_is_disabled(smartform, monkeypatch):
    monkeypatch.setenv("FORMATTER_V2_ENABLED", "0")
    assert _client().post(BRIEF_URL, data=BRIEF).status_code == 404
    assert smartform == []
