"""Debug/test endpoints, the jobs API and project file writes must not be reachable by the public."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.browser.jobs.job_manager import JobManager
from services.browser.jobs.models import JobStatus
from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.free_humanize import GUEST_SESSION_KEY
from services.safe_paths import UnsafePathError, safe_child_path, upload_basename

DEBUG_ROUTES = [
    ("get", "/api/debug/blueprint/p123456789012"),
    ("get", "/api/debug/draft/p123456789012"),
    ("get", "/api/debug/section-review/p123456789012"),
    ("post", "/api/debug/full-pipeline"),
    ("post", "/api/debug/run-stage"),
    ("get", "/api/debug/project/p123456789012"),
    ("post", "/api/test/zerogpt"),
    ("post", "/api/test/zerogpt-humanizer"),
    ("get", "/api/test/env"),
    ("post", "/api/test/gemini"),
]


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.delenv("INTERNAL_TOOLS_ENABLED", raising=False)
    economy_db.init_db()
    return tmp_path


@pytest.fixture()
def no_pipeline(monkeypatch):
    """Fail the test if a guarded endpoint reaches project, AI or browser code."""
    import app as app_mod

    def boom(*_args, **_kwargs):
        raise AssertionError("guarded endpoint ran internal code")

    class _Untouchable:
        def __getattr__(self, _name):
            return boom

    for name in ("_prepare_debug_project", "_debug_run_stage", "_collect_debug_input_payload", "_browser_submit"):
        monkeypatch.setattr(app_mod, name, boom)
    monkeypatch.setattr(app_mod, "project_service", _Untouchable())
    monkeypatch.setattr(app_mod, "ensure_engine_started", boom)


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


def _call(client, method, path):
    if method == "post":
        return client.post(path, json={"stage": "requirement", "assignment_brief": "x"})
    return client.get(path)


# --------------------------------------------------------------- debug / test endpoints


@pytest.mark.parametrize("method,path", DEBUG_ROUTES)
def test_anonymous_gets_404_from_internal_routes(economy, no_pipeline, monkeypatch, method, path):
    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    res = _call(_client(), method, path)
    assert res.status_code == 404
    assert "traceback" not in res.get_data(as_text=True).lower()


@pytest.mark.parametrize("method,path", DEBUG_ROUTES)
def test_ordinary_user_gets_404_from_internal_routes(economy, no_pipeline, monkeypatch, method, path):
    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    client = _signed_in(_client(), _user("plain@example.com"))
    assert _call(client, method, path).status_code == 404


@pytest.mark.parametrize("method,path", DEBUG_ROUTES)
def test_admin_gets_404_while_internal_tools_are_disabled(economy, no_pipeline, method, path):
    client = _signed_in(_client(), _user("admin@example.com", admin=True))
    assert _call(client, method, path).status_code == 404


def test_unverified_admin_gets_404(economy, no_pipeline, monkeypatch):
    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    client = _signed_in(_client(), _user("admin2@example.com", admin=True, verified=False))
    assert client.get("/api/test/env").status_code == 404


def test_test_env_reveals_nothing_even_to_an_enabled_admin(economy, monkeypatch):
    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    client = _signed_in(_client(), _user("admin@example.com", admin=True))
    res = client.get("/api/test/env")
    assert res.status_code == 200
    assert res.get_json() == {"success": True}
    body = res.get_data(as_text=True)
    assert os.getcwd() not in body
    assert "exists" not in body and "dotenv" not in body


def test_flag_must_be_exactly_one(economy, no_pipeline, monkeypatch):
    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "true")
    client = _signed_in(_client(), _user("admin@example.com", admin=True))
    assert client.get("/api/test/env").status_code == 404


def test_browser_restart_is_admin_only(economy, no_pipeline):
    assert _client().post("/api/browser/restart").status_code == 404
    client = _signed_in(_client(), _user("plain@example.com"))
    assert client.post("/api/browser/restart").status_code == 404


def test_browser_restart_failure_has_no_traceback(economy, monkeypatch):
    import app as app_mod

    def fail(*_args, **_kwargs):
        raise RuntimeError("chrome is gone at /root/secret/path")

    monkeypatch.setattr(app_mod, "ensure_engine_started", lambda: None)
    monkeypatch.setattr(app_mod, "_browser_submit", fail)
    client = _signed_in(_client(), _user("admin@example.com", admin=True))
    res = client.post("/api/browser/restart")
    assert res.status_code == 500
    body = res.get_data(as_text=True)
    assert "traceback" not in body.lower() and "/root/secret/path" not in body


# --------------------------------------------------------------- no free paid pipeline


class _Project:
    def __init__(self, paid: bool):
        self.calls: list[str] = []
        self.paid = paid

    def get_project(self, project_id):
        self.calls.append("get_project")
        artifacts = {"payment_confirmed": True} if self.paid else {}
        return SimpleNamespace(project=SimpleNamespace(id=project_id, artifacts=artifacts))

    def calculate_pricing(self, *_args, **_kwargs):
        self.calls.append("calculate_pricing")

    def confirm_payment(self, *_args, **_kwargs):
        self.calls.append("confirm_payment")

    def run_research(self, project_id):
        self.calls.append("run_research")
        return SimpleNamespace(to_dict=lambda: {"engine_version": "test"})


def test_debug_research_stage_never_confirms_payment(economy, monkeypatch):
    import app as app_mod

    fake = _Project(paid=False)
    monkeypatch.setattr(app_mod, "project_service", fake)
    result = app_mod._debug_run_stage("research", "p123456789012")
    assert result["success"] is False
    assert "not confirmed" in result["error"]["error"]
    assert "traceback" not in json.dumps(result).lower()
    assert "confirm_payment" not in fake.calls
    assert "calculate_pricing" not in fake.calls
    assert "run_research" not in fake.calls


def test_debug_research_stage_runs_for_an_already_paid_project(economy, monkeypatch):
    import app as app_mod

    fake = _Project(paid=True)
    monkeypatch.setattr(app_mod, "project_service", fake)
    result = app_mod._debug_run_stage("research", "p123456789012")
    assert result["success"] is True
    assert fake.calls == ["get_project", "run_research"]


def test_anonymous_run_stage_does_not_touch_projects(economy, no_pipeline, monkeypatch):
    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    res = _client().post("/api/debug/run-stage", json={"stage": "research", "project_id": "p123456789012"})
    assert res.status_code == 404


# --------------------------------------------------------------- path traversal


@pytest.mark.parametrize(
    "name",
    [
        "../../evil.txt",
        "../evil.txt",
        "sub/evil.txt",
        "/etc/passwd",
        "..\\..\\evil.txt",
        "..",
        ".",
        "",
        "evil\x00.txt",
    ],
)
def test_safe_child_path_rejects_escapes(tmp_path, name):
    with pytest.raises(UnsafePathError):
        safe_child_path(tmp_path / "base", name)


def test_safe_child_path_rejects_symlink_escape(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    (base / "link.txt").symlink_to(outside)
    with pytest.raises(UnsafePathError):
        safe_child_path(base, "link.txt")
    assert outside.read_text(encoding="utf-8") == "keep"


def test_safe_child_path_accepts_plain_names(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    path = safe_child_path(base, "assignment brief (v2).txt")
    assert path.parent == base.resolve()


def test_upload_basename_keeps_only_the_file_name():
    assert upload_basename("C:\\fakepath\\brief.docx") == "brief.docx"
    assert upload_basename("../../etc/passwd") == "passwd"
    assert upload_basename("..") == "upload"
    assert upload_basename("") == "upload"


@pytest.fixture()
def project_dir(tmp_path, monkeypatch):
    import app as app_mod

    root = tmp_path / "projects"
    monkeypatch.setattr(app_mod, "project_files_dir", lambda project_id: root / project_id / "files")
    return root / "p1" / "files"


def test_debug_text_file_rejects_traversal(tmp_path, project_dir):
    import app as app_mod

    for name in ("../../evil.txt", str(tmp_path / "abs-evil.txt")):
        with pytest.raises(ValueError):
            app_mod._write_debug_text_file("p1", name, "pwned")
    assert not (tmp_path / "abs-evil.txt").exists()
    assert not (project_dir.parent.parent / "evil.txt").exists()
    assert not any(Path(tmp_path).rglob("evil.txt"))


def test_debug_text_file_writes_normal_names_inside_the_project(project_dir):
    import app as app_mod

    stored = Path(app_mod._write_debug_text_file("p1", "rubric.txt", "criteria"))
    assert stored.parent == project_dir.resolve()
    assert stored.read_text(encoding="utf-8") == "criteria"


@pytest.mark.parametrize(
    "name,suffix",
    [
        ("brief.docx", "_brief.docx"),
        ("C:\\fakepath\\brief.docx", "_brief.docx"),
        ("../../evil.docx", "_evil.docx"),
        ("/etc/passwd", "_passwd"),
    ],
)
def test_binary_upload_always_lands_inside_the_project(project_dir, name, suffix):
    import app as app_mod

    stored = Path(app_mod._write_project_binary_file("p1", name, b"data"))
    assert stored.parent == project_dir.resolve()
    assert stored.name.endswith(suffix)
    assert stored.read_bytes() == b"data"


def test_enabled_admin_full_pipeline_rejects_traversal_filename(economy, project_dir, monkeypatch, tmp_path):
    import app as app_mod

    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    added: list[str] = []
    fake = SimpleNamespace(
        create_project=lambda **_kw: SimpleNamespace(project=SimpleNamespace(id="p1")),
        add_file=lambda project_id, **kw: added.append(kw["storage_path"]),
    )
    monkeypatch.setattr(app_mod, "project_service", fake)
    monkeypatch.setattr(app_mod, "_debug_run_stage", lambda *_a, **_k: pytest.fail("pipeline must not start"))
    client = _signed_in(_client(), _user("admin@example.com", admin=True))
    res = client.post(
        "/api/debug/full-pipeline",
        json={"uploaded_files": [{"filename": "../../../evil.txt", "text": "pwned"}]},
    )
    assert res.status_code == 400
    assert added == []
    assert not any(Path(tmp_path).rglob("evil.txt"))


# --------------------------------------------------------------- jobs API


@pytest.fixture()
def jobs(monkeypatch):
    import app as app_mod

    manager = JobManager(enqueue=None)
    monkeypatch.setattr(app_mod, "job_manager", manager)
    monkeypatch.setattr(app_mod, "ensure_engine_started", lambda: pytest.fail("jobs API must not start the engine"))
    return manager


def _job(manager, owner):
    job = manager.create("stealthwriter", "humanize", {"text": "SECRET ESSAY TEXT"}, owner=owner)
    job.result = {"humanized_text": "SECRET HUMANIZED TEXT"}
    return job


def test_anonymous_cannot_list_jobs(economy, jobs):
    _job(jobs, "user:1")
    res = _client().get("/api/jobs")
    assert res.status_code == 401
    assert "SECRET" not in res.get_data(as_text=True)


def test_user_lists_only_own_jobs_without_text(economy, jobs):
    a, b = _user("a@example.com"), _user("b@example.com")
    mine = _job(jobs, f"user:{a['id']}")
    _job(jobs, f"user:{b['id']}")
    _job(jobs, None)
    res = _signed_in(_client(), a).get("/api/jobs")
    assert res.status_code == 200
    assert [j["id"] for j in res.get_json()["jobs"]] == [mine.id]
    body = res.get_data(as_text=True)
    assert "SECRET" not in body and "payload" not in body and "logs" not in body


def test_user_cannot_read_another_users_job(economy, jobs):
    a, b = _user("a@example.com"), _user("b@example.com")
    theirs = _job(jobs, f"user:{b['id']}")
    res = _signed_in(_client(), a).get(f"/api/jobs/{theirs.id}")
    assert res.status_code == 404
    assert "SECRET" not in res.get_data(as_text=True)


def test_user_cannot_cancel_another_users_job(economy, jobs):
    a, b = _user("a@example.com"), _user("b@example.com")
    theirs = _job(jobs, f"user:{b['id']}")
    res = _signed_in(_client(), a).delete(f"/api/jobs/{theirs.id}")
    assert res.status_code == 404
    assert jobs.get(theirs.id).status == JobStatus.QUEUED
    assert not jobs.get(theirs.id).cancel_requested


def test_owner_reads_status_and_cancels_own_job(economy, jobs):
    a = _user("a@example.com")
    mine = _job(jobs, f"user:{a['id']}")
    client = _signed_in(_client(), a)
    res = client.get(f"/api/jobs/{mine.id}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["id"] == mine.id and data["status"] == "QUEUED"
    assert "SECRET" not in res.get_data(as_text=True)
    cancel = client.delete(f"/api/jobs/{mine.id}")
    assert cancel.status_code == 200 and cancel.get_json()["success"] is True
    assert jobs.get(mine.id).status == JobStatus.CANCELLED


def test_guest_sees_only_the_job_from_their_own_session(economy, jobs):
    sid = "g" * 22
    mine = _job(jobs, f"guest:{sid}")
    other = _job(jobs, f"guest:{'h' * 22}")
    client = _client()
    with client.session_transaction() as sess:
        sess[GUEST_SESSION_KEY] = sid
    assert client.get(f"/api/jobs/{mine.id}").status_code == 200
    assert client.get(f"/api/jobs/{other.id}").status_code == 404
    assert client.delete(f"/api/jobs/{other.id}").status_code == 404
    assert _client().get(f"/api/jobs/{mine.id}").status_code == 404


def test_unowned_jobs_are_admin_only(economy, jobs):
    orphan = _job(jobs, None)
    user_client = _signed_in(_client(), _user("a@example.com"))
    assert user_client.get(f"/api/jobs/{orphan.id}").status_code == 404
    admin_client = _signed_in(_client(), _user("admin@example.com", admin=True))
    assert admin_client.get(f"/api/jobs/{orphan.id}").status_code == 200
    listed = admin_client.get("/api/jobs").get_json()["jobs"]
    assert [j["id"] for j in listed] == [orphan.id]
    assert "SECRET" not in admin_client.get("/api/jobs").get_data(as_text=True)


def test_jobs_api_without_a_running_engine_lists_nothing(economy, monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod, "job_manager", None)
    monkeypatch.setattr(app_mod, "ensure_engine_started", lambda: pytest.fail("must not start the engine"))
    client = _signed_in(_client(), _user("a@example.com"))
    assert client.get("/api/jobs").get_json() == {"jobs": []}
    assert client.get("/api/jobs/abc").status_code == 404
    assert client.delete("/api/jobs/abc").status_code == 404


def test_job_owner_is_the_signed_in_user_or_the_guest_session(economy):
    import app as app_mod

    user = _user("a@example.com")
    with app_mod.app.test_request_context("/"):
        from flask import session

        session[economy_auth.SESSION_KEY] = user["id"]
        session[economy_auth.AUTH_SID_KEY] = economy_auth.register_session(user["id"])
        assert app_mod._job_owner() == f"user:{user['id']}"
    with app_mod.app.test_request_context("/"):
        from flask import session

        owner = app_mod._job_owner()
        assert owner == f"guest:{session[GUEST_SESSION_KEY]}"


def test_humanize_job_is_stamped_with_its_owner(economy, monkeypatch):
    import app as app_mod

    captured: dict = {}

    class _JM:
        def create(self, *_args, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop after create")

    monkeypatch.setattr(app_mod, "ensure_engine_started", lambda: None)
    monkeypatch.setattr(app_mod, "job_manager", _JM())
    monkeypatch.setattr(app_mod, "browser_worker", SimpleNamespace(job_timeout=1))
    monkeypatch.setattr(app_mod, "_student_humanize", lambda *_a, **_k: None)
    monkeypatch.setattr(app_mod, "_stealthwriter_down", lambda: False)
    user = _user("a@example.com")
    with app_mod.app.test_request_context("/"):
        from flask import session

        session[economy_auth.SESSION_KEY] = user["id"]
        session[economy_auth.AUTH_SID_KEY] = economy_auth.register_session(user["id"])
        with pytest.raises(RuntimeError, match="stop after create"):
            app_mod._run_stealthwriter_humanize_job("some text")
    assert captured["owner"] == f"user:{user['id']}"
