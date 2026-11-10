"""Standalone engine sessions are owner-only and never reach a project; delivery downloads come
from the project's persisted package; project timeline/status are owner-only."""

from __future__ import annotations

import pytest

from services import ai_detector, free_humanize
from services.ai_detection_engine.models import DetectionSession
from services.blueprint_engine.models import Blueprint
from services.delivery_engine.models import DeliveryPackage
from services.free_humanize import RateLimiter
from services.humanizer_engine.models import HumanizerSession
from services.project_engine import ProjectEngine, ProjectLifecycleStatus
from services.reviewer_engine.models import ReviewReport
from tests.test_security_paid_pipelines import _client, _priced_project, _signed_in, _user, economy  # noqa: F401
from tests.test_security_refund_integrity import (  # noqa: F401  (refund_app is a fixture)
    _admin_refund,
    _completed_project_with_delivery,
    _paid_project,
    _plan_and_blueprint,
    _url,
    refund_app,
)

PARAGRAPH = (
    "This ordinary paragraph of student prose is long enough for the detector and the humanizer "
    "to treat it as a real paragraph rather than a heading or a reference entry in the text. "
)
DRAFT = {"id": "d1", "title": "Essay", "content": PARAGRAPH * 2 + "\n\n" + PARAGRAPH * 2}


class _Tripwire:
    """Stands in for a paid provider: any call is recorded and fails the request."""

    VERSION = "tripwire"

    def __init__(self, calls: list[str], name: str) -> None:
        self._calls = calls
        self._name = name

    def __getattr__(self, attr):
        def call(*_args, **_kwargs):
            self._calls.append(f"{self._name}.{attr}")
            raise AssertionError(f"paid provider {self._name}.{attr} must not run")

        return call


@pytest.fixture()
def env(refund_app, tmp_path, monkeypatch):
    """Production wiring: the project service shares the app's humanizer/detection/delivery engines."""
    app_mod = refund_app.app
    calls: list[str] = []
    monkeypatch.setattr(refund_app.service, "humanizer", app_mod.humanizer_engine)
    monkeypatch.setattr(refund_app.service, "ai_detection", app_mod.ai_detection_engine)
    monkeypatch.setattr(refund_app.service, "project_engine", ProjectEngine(root_dir=tmp_path / "engine"))
    monkeypatch.setattr(app_mod.humanizer_engine, "humanizer", _Tripwire(calls, "stealthwriter"))
    monkeypatch.setattr(app_mod.humanizer_engine, "validator", _Tripwire(calls, "zerogpt_validator"))
    monkeypatch.setattr(app_mod.ai_detection_engine, "detector", _Tripwire(calls, "zerogpt"))
    for name in ("research_engine", "blueprint_engine", "reviewer_engine", "revision_engine"):
        monkeypatch.setattr(app_mod, name, _Tripwire(calls, name))
    monkeypatch.setattr(app_mod, "_standalone_humanizer_owners", app_mod._StandaloneSessionOwners())
    monkeypatch.setattr(app_mod, "_standalone_detection_owners", app_mod._StandaloneSessionOwners())
    monkeypatch.setattr(app_mod, "_standalone_session_rate_limiter", RateLimiter())
    refund_app.calls = calls
    return refund_app


def _detection_session(client, **extra):
    return client.post(
        "/api/ai-detection/session",
        json={"humanized_draft": DRAFT, "requirement_json": {"title": "Essay"}, **extra},
    )


def _humanizer_session(client, **extra):
    return client.post(
        "/api/humanizer/session",
        json={"draft": DRAFT, "requirement_json": {"title": "Essay"}, "blueprint": {"title": "Essay"}, **extra},
    )


# ------------------------------------------------------------ AI detection sessions


def test_detection_session_requires_a_verified_account(env):
    assert _detection_session(_client()).status_code == 401
    unverified = _signed_in(_client(), _user("new@example.com", verified=False))
    res = _detection_session(unverified)
    assert res.status_code == 403 and res.get_json()["error"] == "EMAIL_NOT_VERIFIED"
    assert env.calls == []


def test_detection_session_is_owner_only_and_never_calls_zerogpt(env):
    alice = _signed_in(_client(), _user("alice@example.com"))
    bob = _signed_in(_client(), _user("bob@example.com"))
    created = _detection_session(alice)
    assert created.status_code == 201, created.get_json()
    sid = created.get_json()["id"]
    base = f"/api/ai-detection/session/{sid}"

    assert alice.get(base).status_code == 200
    for method, path in (("get", base), ("post", base + "/advance"), ("post", base + "/finalize")):
        assert getattr(bob, method)(path).status_code == 404, path
        assert getattr(_client(), method)(path).status_code == 401, path
    advance = alice.post(base + "/advance")
    assert advance.status_code == 403 and advance.get_json()["code"] == "DETECTION_SESSION_API_DISABLED"
    assert alice.post(base + "/finalize").status_code == 200
    assert env.calls == []


def test_detection_session_rejects_a_project_id(env):
    owner = _user("victim@example.com")
    project_id, _coins = _paid_project(env, owner)
    attacker = _signed_in(_client(), _user("attacker@example.com"))

    res = _detection_session(attacker, project_id=project_id)

    assert res.status_code == 400
    assert env.app.ai_detection_engine.sessions.get_by_project(project_id) is None
    with pytest.raises(KeyError):
        env.service._load_detection_session(project_id)
    assert "detection_session" not in env.service.store.require_project(project_id).artifacts


def test_foreign_detection_session_in_memory_is_never_adopted_by_a_project(env):
    owner = _user("victim@example.com")
    project_id, _coins = _paid_project(env, owner)
    foreign = env.app.ai_detection_engine.create_session(
        humanized_draft=DRAFT, requirement_json={"title": "Essay"}, project_id=project_id
    )
    assert isinstance(foreign, DetectionSession)

    with pytest.raises(KeyError):
        env.service._load_detection_session(project_id)
    assert "detection_session" not in env.service.store.require_project(project_id).artifacts


def test_detection_session_creation_is_rate_limited(env):
    alice = _signed_in(_client(), _user("alice@example.com"))
    codes = [_detection_session(alice).status_code for _ in range(21)]
    assert codes[:20] == [201] * 20 and codes[20] == 429


def test_free_public_detector_keeps_its_quota(env, monkeypatch):
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
    first = guest.post("/api/detector/free", json={"text": text})
    assert first.status_code == 200, first.get_json()
    assert guest.post("/api/detector/free", json={"text": text}).status_code == 403
    assert env.calls == []


# ------------------------------------------------------------ Humanizer sessions


def test_humanizer_session_is_owner_only_and_never_calls_stealthwriter(env):
    assert _humanizer_session(_client()).status_code == 401
    alice = _signed_in(_client(), _user("alice@example.com"))
    bob = _signed_in(_client(), _user("bob@example.com"))
    created = _humanizer_session(alice)
    assert created.status_code == 201, created.get_json()
    sid = created.get_json()["id"]
    base = f"/api/humanizer/session/{sid}"

    assert alice.get(base).status_code == 200
    for method, path in (("get", base), ("post", base + "/advance"), ("post", base + "/merge")):
        assert getattr(bob, method)(path).status_code == 404, path
    advance = alice.post(base + "/advance")
    assert advance.status_code == 403 and advance.get_json()["code"] == "HUMANIZER_SESSION_API_DISABLED"
    assert alice.post(base + "/merge").status_code != 404
    assert env.calls == []


def test_humanizer_session_rejects_a_project_id(env):
    owner = _user("victim@example.com")
    project_id, _coins = _paid_project(env, owner)
    attacker = _signed_in(_client(), _user("attacker@example.com"))

    res = _humanizer_session(attacker, project_id=project_id)

    assert res.status_code == 400
    assert env.app.humanizer_engine.sessions.get_by_project(project_id) is None
    with pytest.raises(KeyError):
        env.service._load_humanizer_session(project_id)


def test_foreign_humanizer_session_in_memory_is_never_adopted_by_a_project(env):
    owner = _user("victim@example.com")
    project_id, _coins = _paid_project(env, owner)
    foreign = env.app.humanizer_engine.create_session(
        draft=DRAFT, requirement_json={"title": "Essay"}, blueprint={"title": "Essay"}, project_id=project_id
    )
    assert isinstance(foreign, HumanizerSession)

    with pytest.raises(KeyError):
        env.service._load_humanizer_session(project_id)
    assert "humanizer_session" not in env.service.store.require_project(project_id).artifacts
    owner_client = _signed_in(_client(), owner)
    assert owner_client.post(_url(project_id, "humanizer/advance"), json={}).status_code == 404
    assert env.calls == []


def test_assignment_humanizer_session_is_not_reachable_through_standalone_routes(env):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(env, owner)
    session = env.app.humanizer_engine.create_session(
        draft=DRAFT, requirement_json={"title": "Essay"}, blueprint={"title": "Essay"}, project_id=project_id
    )
    env.service._persist_humanizer_session(project_id, session)
    owner_client = _signed_in(_client(), owner)
    base = f"/api/humanizer/session/{session.id}"

    for client in (owner_client, _signed_in(_client(), _user("other@example.com"))):
        assert client.get(base).status_code == 404
        assert client.post(base + "/merge").status_code == 404

    assert _admin_refund(env, project_id).status_code == 200
    assert owner_client.get(base).status_code == 404
    assert owner_client.get(_url(project_id, "humanizer")).status_code == 404


def test_main_humanizer_free_quota_still_works(env, monkeypatch):
    import app as app_mod

    for name in ("FREE_HUMANIZE_GUEST_WORDS", "FREE_HUMANIZE_GUEST_IP_DAILY", "FREE_HUMANIZE_ENGINE",
                 "FREE_HUMANIZE_GUEST_RATE_PER_MIN", "HUMANIZE_MAX_WORDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_DAILY", "1")
    free_humanize.guest_rate_limiter.reset()

    def student(_text, *, rescue=False):
        return {"humanized_text": "Rewritten.", "elapsed_seconds": 1.0, "provider": "DocMaxxing",
                "engine": "docmaxxing-student-v1", "request_id": "r1"}

    def no_stealthwriter():
        raise AssertionError("StealthWriter must not run")

    monkeypatch.setattr(app_mod, "_student_humanize", student)
    monkeypatch.setattr(app_mod, "ensure_engine_started", no_stealthwriter)
    monkeypatch.setattr(app_mod, "_stealthwriter_down_until", 0.0)
    monkeypatch.setattr(app_mod, "health_monitor", None)
    guest = _client()
    url = "/api/browser/providers/stealthwriter/humanize"
    text = "Please rewrite this paragraph so it reads like a person wrote it."

    first = guest.post(url, json={"text": text})
    assert first.status_code == 200 and first.get_json()["free_run"] is True
    assert guest.post(url, json={"text": text}).status_code == 403


# ------------------------------------------------------------ Other standalone engines


@pytest.mark.parametrize(
    "path,code",
    [
        ("/api/research/plan", "RESEARCH_API_DISABLED"),
        ("/api/blueprint/build", "BLUEPRINT_API_DISABLED"),
        ("/api/reviewer/review", "REVIEWER_API_DISABLED"),
        ("/api/revision/revise", "REVISION_API_DISABLED"),
    ],
)
def test_standalone_llm_engines_are_closed(env, path, code):
    body = {"project_id": "x" * 36, "requirement_json": {}, "research_plan": {}, "blueprint": {},
            "draft": {}, "review_report": {}, "parsed_documents": []}
    assert _client().post(path, json=body).status_code == 401
    res = _signed_in(_client(), _user("alice@example.com")).post(path, json=body)
    assert res.status_code == 403 and res.get_json()["code"] == code
    assert env.calls == []


def test_memory_copies_never_replace_a_projects_stored_artifacts(env):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(env, owner)
    _plan_and_blueprint(env, project_id)
    stored = env.service.get_blueprint(project_id)
    plan = env.service._server_research_plan(project_id)

    forged = Blueprint.from_dict({**stored.to_dict(), "id": "forged-blueprint", "title": "Forged"})
    forged.project_id = project_id
    env.service.blueprint.store.save(forged)
    forged_plan = type(plan).from_dict({**plan.to_dict(), "id": "forged-plan"})
    forged_plan.project_id = project_id
    env.service.research.store.save(forged_plan)
    forged_review = ReviewReport.from_dict({"id": "forged-review", "project_id": project_id})
    env.service.reviewer.store.save(forged_review)

    assert env.service.get_blueprint(project_id).id == stored.id
    assert env.service._server_research_plan(project_id).id == plan.id
    with pytest.raises(KeyError):
        env.service._load_review_report(project_id)


# ------------------------------------------------------------ Delivery packages


def test_standalone_package_creation_is_closed(env):
    owner = _user("owner@example.com")
    project_id, package_id, _file = _completed_project_with_delivery(env, owner)
    body = {k: {"x": 1} for k in ("final_draft", "requirement_json", "research_plan", "blueprint",
                                  "review_report", "detection_report")}
    body["project_id"] = project_id

    assert _client().post("/api/delivery/package", json=body).status_code == 401
    for user in (_user("attacker@example.com"), owner):
        res = _signed_in(_client(), user).post("/api/delivery/package", json=body)
        assert res.status_code == 403 and res.get_json()["code"] == "DELIVERY_API_DISABLED"
    assert env.service.get_delivery_package(project_id).id == package_id


def _poison(env, project_id: str, tmp_path) -> tuple[str, str]:
    """What the old unauthenticated route did: a foreign package indexed under the victim's project."""
    evil = tmp_path / "evil.docx"
    evil.write_bytes(b"PK-attacker")
    package = DeliveryPackage.from_dict(
        {
            "id": "pkg-evil",
            "project_id": project_id,
            "status": "ready",
            "client_filename": "missing.docx",
            "files": [{"id": "file-evil", "filename": "evil.docx", "file_type": "final_assignment_docx",
                       "storage_path": str(evil), "ready": True}],
        }
    )
    env.service.delivery.store.save(package)
    return package.id, "file-evil"


def test_poisoned_memory_package_never_overrides_the_persisted_one(env, tmp_path):
    owner = _user("owner@example.com")
    project_id, package_id, file_id = _completed_project_with_delivery(env, owner)
    evil_package, evil_file = _poison(env, project_id, tmp_path)
    client = _signed_in(_client(), owner)

    assert env.service.get_delivery_package(project_id).id == package_id
    download = client.get(_url(project_id, "download"))
    assert download.status_code == 200 and download.data == b"PK-final-assignment"
    assert client.get(f"/api/delivery/packages/{package_id}/download").data == b"PK-final-assignment"
    assert client.get(f"/api/delivery/files/{file_id}").data == b"PK-final-assignment"
    assert client.get(f"/api/delivery/packages/{evil_package}/download").status_code == 404
    assert client.get(f"/api/delivery/files/{evil_file}").status_code == 404
    admin = _signed_in(_client(), _user("auditor@example.com", admin=True))
    assert admin.get(f"/api/delivery/files/{evil_file}").status_code == 404


def test_delivery_downloads_owner_only_refund_locked_admin_allowed(env):
    owner = _user("owner@example.com")
    project_id, package_id, file_id = _completed_project_with_delivery(env, owner)
    urls = (f"/api/delivery/packages/{package_id}/download", f"/api/delivery/files/{file_id}")
    owner_client = _signed_in(_client(), owner)
    intruder = _signed_in(_client(), _user("intruder@example.com"))

    for url in urls:
        assert owner_client.get(url).status_code == 200
        assert intruder.get(url).status_code == 404
        assert _client().get(url).status_code == 404

    assert _admin_refund(env, project_id).status_code == 200
    admin = _signed_in(_client(), _user("auditor@example.com", admin=True))
    unverified_admin = _signed_in(_client(), _user("half@example.com", admin=True, verified=False))
    for url in urls:
        assert owner_client.get(url).status_code == 404
        assert admin.get(url).status_code == 200
        assert unverified_admin.get(url).status_code == 404


# ------------------------------------------------------------ Timeline and status


def test_timeline_and_status_are_owner_only_and_sanitized(env):
    owner = _user("owner@example.com")
    project_id, _coins = _paid_project(env, owner)
    engine = env.service.project_engine
    engine.init_project(project_id)
    engine.stage_start(project_id, ProjectLifecycleStatus.RESEARCH_READY)
    engine.stage_finish(
        project_id,
        ProjectLifecycleStatus.RESEARCH_READY,
        success=False,
        error='Traceback (most recent call last): File "/srv/app.py" ValueError: secret prompt text',
    )
    urls = (f"/api/project/{project_id}/timeline", f"/api/project/{project_id}/status")
    owner_client = _signed_in(_client(), owner)
    intruder = _signed_in(_client(), _user("intruder@example.com"))
    missing = "/api/project/" + "0" * 36 + "/timeline"

    for url in urls:
        assert _client().get(url).status_code == 401
        denied = intruder.get(url)
        assert denied.status_code == 404 and denied.get_json() == intruder.get(missing).get_json()
        assert owner_client.get(url).status_code == 200
    timeline = owner_client.get(urls[0])
    text = timeline.get_data(as_text=True)
    assert "Traceback" not in text and "secret prompt" not in text and "/srv/app.py" not in text
    assert any(entry["error"] for entry in timeline.get_json()["timeline"])
    admin = _signed_in(_client(), _user("auditor@example.com", admin=True))
    assert admin.get(urls[1]).status_code == 200
    unverified_owner = _user("late@example.com", verified=False)
    project_b = _priced_project(env.service, user_id=str(unverified_owner["id"]))
    engine.init_project(project_b)
    assert _signed_in(_client(), unverified_owner).get(f"/api/project/{project_b}/status").status_code == 403
