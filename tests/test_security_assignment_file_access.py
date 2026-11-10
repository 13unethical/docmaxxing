"""F-01: a project file is only ever read from that project's own files directory.

Every test plants a harmless sentinel file outside the project storage and arms an audit hook
that aborts the test the moment anything opens a path under that directory, so a reader that
bypasses ``services.project_files`` fails loudly even inside ``except Exception`` blocks.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import sys
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from PIL import Image

from services import assignment_figures, assignment_llm, project_files
from services.assignment_project import requirement_analyzer as ra
from services.assignment_project.models import ProjectFile, ProjectFileType
from services.assignment_project.service import ProjectService
from services.assignment_project.store import ProjectStore
from services.delivery_engine.packager import _build_docx_bytes
from services.research_engine import parsed_documents as pd
from tests.test_assignment_project import _StubBlueprintService, _StubResearchService
from tests.test_security_paid_pipelines import _client, _signed_in, _user, economy  # noqa: F401

SENTINEL = "SENTINEL-" + uuid.uuid4().hex
REQUIREMENT_REPLY = {
    "assignment_type": "Essay",
    "title": "Essay",
    "word_count": 1000,
    "citation_style": "APA 7",
    "required_sections": ["Introduction"],
    "rubric": [],
    "learning_outcomes": [],
    "minimum_sources": 3,
    "formatting": {},
    "missing_information": [],
}


# ------------------------------------------------------------------ unsafe-read trap
class UnsafeRead(BaseException):
    """BaseException so ``except Exception`` in a reader cannot swallow it."""


_FORBIDDEN: list[str] = []
_VIOLATIONS: list[str] = []


def _audit(event: str, args: tuple) -> None:
    if event != "open" or not _FORBIDDEN or not args or isinstance(args[0], int):
        return
    try:
        target = os.fsdecode(args[0])
    except (TypeError, ValueError):
        return
    for root in _FORBIDDEN:
        if target == root or target.startswith(root + os.sep):
            _VIOLATIONS.append(target)
            raise UnsafeRead(f"unsafe read of {target}")


sys.addaudithook(_audit)


@contextlib.contextmanager
def _disarmed():
    saved = list(_FORBIDDEN)
    _FORBIDDEN.clear()
    try:
        yield
    finally:
        _FORBIDDEN[:] = saved


@pytest.fixture()
def outside(tmp_path):
    """A directory beside the project storage holding sentinel files; opening anything in it fails."""
    root = tmp_path / "outside"
    root.mkdir()
    (root / "secret.txt").write_text(f"LEMON_SQUEEZY_WEBHOOK_SECRET={SENTINEL}\n", encoding="utf-8")
    (root / "secret.env").write_text(f"KEY={SENTINEL}\n", encoding="utf-8")
    Image.new("RGB", (8, 8), color=(1, 2, 3)).save(root / "secret.png", format="PNG")
    (root / "dir").mkdir()
    (root / "dir" / "secret.txt").write_text(SENTINEL, encoding="utf-8")
    _VIOLATIONS.clear()
    _FORBIDDEN[:] = sorted({str(root), str(root.resolve())})
    try:
        yield root
    finally:
        _FORBIDDEN.clear()
    assert not _VIOLATIONS, f"a reader opened a file outside the project: {_VIOLATIONS}"


# ------------------------------------------------------------------ providers
class _ProviderTraps:
    """Gemini and Claude stand-ins that record every prompt; the real clients refuse outright."""

    def __init__(self, monkeypatch) -> None:
        self.calls: list[tuple[str, str]] = []
        self._monkeypatch = monkeypatch
        monkeypatch.setattr(assignment_llm, "gemini_generate_json", self._fake("gemini"))
        monkeypatch.setattr(assignment_llm, "claude_generate_json", self._fake("claude"))
        from services import claude_client, gemini_client

        for module in (gemini_client, claude_client):
            for name in ("generate_json", "generate_text"):
                if hasattr(module, name):
                    monkeypatch.setattr(module, name, self._refuse(f"{module.__name__}.{name}"))
        self.use("gemini")

    def use(self, provider: str) -> None:
        self._monkeypatch.setattr(assignment_llm, "gemini_enabled", lambda: provider == "gemini")
        self._monkeypatch.setattr(assignment_llm, "claude_enabled", lambda: provider == "claude")

    def _fake(self, name: str):
        def fake(*, system_prompt, user_prompt, temperature=0.2, max_retries=2):
            self.calls.append((name, f"{system_prompt}\n{user_prompt}"))
            return dict(REQUIREMENT_REPLY), {}

        return fake

    def _refuse(self, name: str):
        def refuse(*_a, **_k):
            raise AssertionError(f"real provider client called: {name}")

        return refuse

    def prompts(self) -> str:
        return "\n".join(prompt for _, prompt in self.calls)


class _RecordingResearch(_StubResearchService):
    def __init__(self) -> None:
        super().__init__()
        self.documents: list = []

    def build_plan(self, *, requirement_json, parsed_documents, project_id=None):
        self.documents.extend(parsed_documents)
        return super().build_plan(
            requirement_json=requirement_json, parsed_documents=parsed_documents, project_id=project_id
        )


@pytest.fixture()
def env(economy, tmp_path, monkeypatch, outside):  # noqa: F811
    import app as app_mod

    storage = (tmp_path / "projects").resolve()
    monkeypatch.setenv("PROJECT_STORAGE_DIR", str(storage))
    research = _RecordingResearch()
    service = ProjectService(
        store=ProjectStore(root=storage),
        pipeline=app_mod.assignment_pipeline,
        analyzer=ra.GeminiRequirementAnalyzer(),
        research=research,  # type: ignore[arg-type]
        blueprint=_StubBlueprintService(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(app_mod, "project_service", service)
    monkeypatch.setattr(app_mod, "PROJECT_STORAGE_ROOT", storage)
    fetches: list = []
    monkeypatch.setattr(assignment_figures, "fetch_commons_figures", lambda **kw: fetches.append(kw) or [])
    from services.economy import disposable_email

    monkeypatch.setattr(disposable_email, "_remote_disposable_check", lambda _e: None)
    return SimpleNamespace(
        app=app_mod,
        service=service,
        storage=storage,
        outside=outside,
        research=research,
        providers=_ProviderTraps(monkeypatch),
        fetches=fetches,
    )


# ------------------------------------------------------------------ helpers
def _url(pid: str, suffix: str = "") -> str:
    return f"/api/assignment/projects/{pid}" + (f"/{suffix}" if suffix else "")


def _files_dir(env, pid: str) -> Path:
    path = env.storage / pid / "files"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _project(env, user) -> str:
    return env.service.create_project(user_id=str(user["id"]), title="Project").project.id


def _plant(env, pid: str, storage_path: str, *, name: str = "notes.txt", owner: str | None = None,
           file_type: ProjectFileType = ProjectFileType.ASSIGNMENT_BRIEF) -> ProjectFile:
    """A file record as an old build (or a tampered bundle) could have persisted it."""
    record = ProjectFile(
        id=str(uuid.uuid4()),
        project_id=owner or pid,
        file_type=file_type,
        filename=name,
        original_filename=name,
        storage_path=storage_path,
    )
    bundle_path = env.storage / pid / "bundle.json"
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    payload["files"].append(record.to_dict())
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")
    return record


def _legit(env, pid: str, name: str, text: str) -> str:
    path = _files_dir(env, pid) / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _persisted_text(env) -> str:
    chunks = []
    for path in env.storage.rglob("*"):
        if path.is_file() and not path.is_symlink():
            chunks.append(path.read_bytes().decode("utf-8", errors="ignore"))
    return "\n".join(chunks)


def _assert_no_sentinel(env, *texts: str, caplog=None) -> None:
    for text in texts:
        assert SENTINEL not in (text or "")
    assert SENTINEL not in env.providers.prompts()
    assert SENTINEL not in _persisted_text(env)
    if caplog is not None:
        assert SENTINEL not in caplog.text


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 12), color=(30, 90, 160)).save(buf, format="PNG")
    return buf.getvalue()


MALICIOUS_PATHS = [
    "/etc/passwd",
    "../../outside.txt",
    "files/../../outside.txt",
    "..\\..\\outside.txt",
    "C:\\Windows\\win.ini",
    "C:/Windows/win.ini",
    "\\\\server\\share\\secret.txt",
    "//server/share/secret.txt",
    "%2e%2e/%2e%2e/outside.txt",
    "..%2f..%2foutside.txt",
    "notes.txt\x00.png",
    "notes\n.txt",
    "",
]


# ------------------------------------------------------------------ 1-11: client-supplied paths
@pytest.mark.parametrize("value", MALICIOUS_PATHS + ["__OUTSIDE__", "__OWN_LEGIT__"])
def test_add_file_route_refuses_any_client_storage_path(env, value):
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    if value == "__OUTSIDE__":
        value = str(env.outside / "secret.txt")
    elif value == "__OWN_LEGIT__":
        value = _legit(env, pid, "mine.txt", "own file")
    before = [f.id for f in env.service.store.list_files(pid)]
    res = _signed_in(_client(), owner).post(
        _url(pid, "files"),
        json={"file_type": "assignment_brief", "original_filename": "notes.txt", "storage_path": value},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "STORAGE_PATH_NOT_ALLOWED"
    assert [f.id for f in env.service.store.list_files(pid)] == before
    assert env.providers.calls == []
    _assert_no_sentinel(env, res.get_data(as_text=True))


def test_add_file_route_without_storage_path_gets_a_server_location(env):
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    res = _signed_in(_client(), owner).post(
        _url(pid, "files"), json={"file_type": "assignment_brief", "original_filename": "../../brief.txt"}
    )
    assert res.status_code == 201
    stored = res.get_json()["storage_path"]
    assert project_files.relative_parts(pid, stored)[-1].endswith("_brief.txt")


@pytest.mark.parametrize("where", ["files", "upload_manifest"])
@pytest.mark.parametrize("value", ["/etc/passwd", "../../outside.txt", "__OUTSIDE__", "C:\\x.txt"])
def test_create_project_route_refuses_storage_path_in_files_and_manifest(env, where, value):
    owner = _user("owner@example.com")
    if value == "__OUTSIDE__":
        value = str(env.outside / "secret.txt")
    entry = {"file_type": "assignment_brief", "source": "assignment_brief", "original_filename": "b.txt",
             "name": "b.txt", "storage_path": value}
    body = {"title": "x", "files": [entry]} if where == "files" else {"title": "x", "upload_manifest": {"files": [entry]}}
    before = sorted(p.name for p in env.storage.iterdir()) if env.storage.exists() else []
    res = _signed_in(_client(), owner).post("/api/assignment/projects", json=body)
    assert res.status_code == 400
    assert res.get_json()["error"] == "STORAGE_PATH_NOT_ALLOWED"
    after = sorted(p.name for p in env.storage.iterdir()) if env.storage.exists() else []
    assert after == before
    assert env.providers.calls == []


@pytest.mark.parametrize("body", [{"files": ["/etc/passwd"]}, {"upload_manifest": {"files": "x"}},
                                  {"upload_manifest": {"files": [["/etc/passwd"]]}}])
def test_create_project_route_rejects_malformed_file_entries(env, body):
    owner = _user("owner@example.com")
    assert _signed_in(_client(), owner).post("/api/assignment/projects", json=body).status_code == 400


def test_create_project_route_without_paths_still_works(env):
    owner = _user("owner@example.com")
    res = _signed_in(_client(), owner).post(
        "/api/assignment/projects",
        json={"title": "x", "files": [{"file_type": "assignment_brief", "original_filename": "b.txt"}]},
    )
    assert res.status_code == 201
    pid = res.get_json()["project"]["id"]
    (record,) = env.service.store.list_files(pid)
    assert project_files.relative_parts(pid, record.storage_path)


def test_service_ignores_storage_path_inside_files_and_manifest(env):
    owner = _user("owner@example.com")
    evil = str(env.outside / "secret.txt")
    for kwargs in (
        {"files": [{"file_type": "assignment_brief", "original_filename": "b.txt", "storage_path": evil}]},
        {"upload_manifest": {"files": [{"source": "assignment_brief", "name": "b.txt", "storage_path": evil}]}},
    ):
        bundle = env.service.create_project(user_id=str(owner["id"]), **kwargs)
        (record,) = bundle.files
        assert record.storage_path != evil
        assert project_files.relative_parts(bundle.project.id, record.storage_path)
    _assert_no_sentinel(env)


@pytest.mark.parametrize("value", MALICIOUS_PATHS[:-1] + ["__OUTSIDE__", "__OTHER_PROJECT__"])
def test_trusted_add_file_refuses_locations_outside_the_project(env, value):
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    if value == "__OUTSIDE__":
        value = str(env.outside / "secret.txt")
    elif value == "__OTHER_PROJECT__":
        value = _legit(env, _project(env, owner), "theirs.txt", "x")
    with pytest.raises(ValueError, match="Invalid file location"):
        env.service.add_file(pid, file_type="assignment_brief", original_filename="n.txt", storage_path=value)


def test_multipart_upload_with_traversal_filename_stays_in_the_project(env):
    owner = _user("owner@example.com")
    res = _signed_in(_client(), owner).post(
        "/api/assignment/projects/upload",
        data={"assignment_brief": (io.BytesIO(b"Write 1500 words on ethics."), "../../../escape.txt")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 201
    pid = res.get_json()["project"]["id"]
    (record,) = env.service.store.list_files(pid)
    assert project_files.read_project_record(pid, record) == b"Write 1500 words on ethics."
    assert not (env.storage.parent / "escape.txt").exists()


# ------------------------------------------------------------------ path validation (unit)
@pytest.mark.parametrize("value", MALICIOUS_PATHS + [None, 5, ["a"], "x" * 5000])
def test_relative_parts_refuses_malformed_paths(env, value):
    pid = _project(env, _user("owner@example.com"))
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.relative_parts(pid, value)


def test_relative_parts_refuses_absolute_traversal_and_alternate_spellings(env):
    pid = _project(env, _user("owner@example.com"))
    files = str(_files_dir(env, pid))
    for value in (
        f"{files}/../../../outside/secret.txt",
        f"{files}/sub/../../x.txt",
        f"{files}/./notes.txt",
        f"{files}//notes.txt",
        f"{files}\\..\\x.txt",
        f"{files}/%2e%2e/x.txt",
        f"{files}",
        f"{files}/",
        str(env.storage / pid / "bundle.json"),
        str(env.storage / pid / "files_evil" / "x.txt"),
    ):
        with pytest.raises(project_files.ProjectFileDenied):
            project_files.relative_parts(pid, value)


@pytest.mark.parametrize("pid", ["", "..", "../x", "a/b", ".hidden", "x" * 200, None, "a\x00b"])
def test_forged_project_ids_are_refused(env, pid):
    legit = _legit(env, _project(env, _user("owner@example.com")), "a.txt", "x")
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.read_project_file(pid, legit)


def test_valid_project_paths_are_read(env):
    pid = _project(env, _user("owner@example.com"))
    files = _files_dir(env, pid)
    (files / "auto_figures").mkdir()
    (files / "auto_figures" / "a.png").write_bytes(b"png")
    assert project_files.read_project_file(pid, _legit(env, pid, "brief.txt", "hello")) == b"hello"
    assert project_files.read_project_file(pid, str(files / "auto_figures" / "a.png")) == b"png"


# ------------------------------------------------------------------ 12-16: project isolation
def test_user_cannot_attach_another_users_file(env):
    alice, bob = _user("alice@example.com"), _user("bob@example.com")
    a_pid, b_pid = _project(env, alice), _project(env, bob)
    bob_file = _legit(env, b_pid, "bob.txt", f"bob private {SENTINEL}")
    res = _signed_in(_client(), alice).post(
        _url(a_pid, "files"),
        json={"file_type": "assignment_brief", "original_filename": "x.txt", "storage_path": bob_file},
    )
    assert res.status_code == 400
    with pytest.raises(ValueError):
        env.service.add_file(a_pid, file_type="assignment_brief", original_filename="x.txt", storage_path=bob_file)


def test_user_cannot_read_another_users_project_file(env, caplog):
    alice, bob = _user("alice@example.com"), _user("bob@example.com")
    a_pid, b_pid = _project(env, alice), _project(env, bob)
    bob_file = _legit(env, b_pid, "bob.txt", f"bob private {SENTINEL}")
    _plant(env, a_pid, bob_file)
    res = _signed_in(_client(), alice).post(_url(a_pid, "analyze-requirements"))
    assert res.status_code == 200
    assert env.providers.calls
    assert SENTINEL not in env.providers.prompts()
    assert SENTINEL not in res.get_data(as_text=True)
    assert SENTINEL not in caplog.text
    assert _signed_in(_client(), alice).post(_url(b_pid, "analyze-requirements")).status_code in {403, 404}


def test_file_of_another_project_under_the_shared_parent_is_refused(env):
    owner = _user("owner@example.com")
    pid, other = _project(env, owner), _project(env, owner)
    other_file = _legit(env, other, "o.txt", SENTINEL)
    with pytest.raises(project_files.ProjectFileDenied) as exc:
        project_files.read_project_file(pid, other_file)
    assert exc.value.code == project_files.OUTSIDE_PROJECT
    assert not project_files.project_file_exists(pid, other_file)


def test_forged_project_id_cannot_unlock_a_path(env):
    owner = _user("owner@example.com")
    pid, other = _project(env, owner), _project(env, owner)
    own = _legit(env, pid, "a.txt", "mine")
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.read_project_file(other, own)
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.read_project_file(f"{pid}/../{other}", own)


def test_record_claiming_another_project_is_refused(env, caplog):
    owner = _user("owner@example.com")
    pid, other = _project(env, owner), _project(env, owner)
    foreign = "FOREIGN-" + uuid.uuid4().hex
    other_file = _legit(env, other, "o.txt", foreign)
    record = _plant(env, pid, other_file, owner=other)
    with pytest.raises(project_files.ProjectFileDenied) as exc:
        project_files.read_project_record(pid, record)
    assert exc.value.code in {project_files.FOREIGN_RECORD, project_files.OUTSIDE_PROJECT}
    res = _signed_in(_client(), owner).post(_url(pid, "analyze-requirements"))
    assert res.status_code == 200
    assert env.providers.calls
    for text in (env.providers.prompts(), res.get_data(as_text=True), caplog.text):
        assert foreign not in text


def test_forged_record_project_id_with_own_path_is_still_refused(env):
    owner = _user("owner@example.com")
    pid, other = _project(env, owner), _project(env, owner)
    record = SimpleNamespace(project_id=other, storage_path=_legit(env, pid, "a.txt", "x"))
    with pytest.raises(project_files.ProjectFileDenied) as exc:
        project_files.read_project_record(pid, record)
    assert exc.value.code == project_files.FOREIGN_RECORD


# ------------------------------------------------------------------ 17-22: filesystem escape
def test_symlink_to_outside_file_is_refused(env):
    pid = _project(env, _user("owner@example.com"))
    link = _files_dir(env, pid) / "link.txt"
    link.symlink_to(env.outside / "secret.txt")
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.read_project_file(pid, str(link))
    assert not project_files.project_file_exists(pid, str(link))


def test_symlink_inside_project_is_refused_too(env):
    pid = _project(env, _user("owner@example.com"))
    target = _legit(env, pid, "real.txt", "x")
    link = _files_dir(env, pid) / "alias.txt"
    link.symlink_to(target)
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.read_project_file(pid, str(link))


def test_nested_directory_symlink_escape_is_refused(env):
    pid = _project(env, _user("owner@example.com"))
    sub = _files_dir(env, pid) / "sub"
    sub.symlink_to(env.outside / "dir", target_is_directory=True)
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.read_project_file(pid, str(sub / "secret.txt"))


def test_symlinked_project_files_directory_is_refused(env):
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    files = env.storage / pid / "files"
    if files.exists():
        files.rmdir()
    files.symlink_to(env.outside / "dir", target_is_directory=True)
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.read_project_file(pid, str(files / "secret.txt"))


def test_swap_to_symlink_at_open_time_is_refused(env, monkeypatch):
    """The file becomes a symlink to the sentinel right before the final open: still refused."""
    pid = _project(env, _user("owner@example.com"))
    target = Path(_legit(env, pid, "swap.txt", "benign"))
    assert project_files.read_project_file(pid, str(target)) == b"benign"
    real_open = os.open

    def swapping_open(path, flags, *args, **kwargs):
        if path == target.name and kwargs.get("dir_fd") is not None:
            target.unlink()
            target.symlink_to(env.outside / "secret.txt")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(project_files.os, "open", swapping_open)
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.read_project_file(pid, str(target))


def test_swap_of_parent_directory_at_open_time_is_refused(env, monkeypatch):
    pid = _project(env, _user("owner@example.com"))
    sub = _files_dir(env, pid) / "sub"
    sub.mkdir()
    (sub / "secret.txt").write_text("benign", encoding="utf-8")
    real_open = os.open

    def swapping_open(path, flags, *args, **kwargs):
        if path == "sub" and kwargs.get("dir_fd") is not None and not sub.is_symlink():
            (sub / "secret.txt").unlink()
            sub.rmdir()
            sub.symlink_to(env.outside / "dir", target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(project_files.os, "open", swapping_open)
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.read_project_file(pid, str(sub / "secret.txt"))


def test_directory_fifo_and_missing_file_are_refused(env):
    pid = _project(env, _user("owner@example.com"))
    files = _files_dir(env, pid)
    (files / "folder.txt").mkdir()
    os.mkfifo(files / "pipe.txt")
    for name, code in (("folder.txt", project_files.NOT_A_FILE), ("pipe.txt", project_files.NOT_A_FILE),
                       ("missing.txt", project_files.FILE_MISSING)):
        with pytest.raises(project_files.ProjectFileDenied) as exc:
            project_files.read_project_file(pid, str(files / name))
        assert exc.value.code == code


def test_oversized_file_is_refused(env):
    pid = _project(env, _user("owner@example.com"))
    path = _legit(env, pid, "big.txt", "12345")
    assert project_files.read_project_file(pid, path, max_bytes=5) == b"12345"
    with pytest.raises(project_files.ProjectFileDenied) as exc:
        project_files.read_project_file(pid, path, max_bytes=4)
    assert exc.value.code == project_files.FILE_TOO_LARGE


def test_stale_path_from_an_old_storage_root_is_refused(env):
    pid = _project(env, _user("owner@example.com"))
    old = env.outside / "old-root" / "data" / "projects" / pid / "files"
    with _disarmed():
        old.mkdir(parents=True)
        (old / "brief.txt").write_text(SENTINEL, encoding="utf-8")
    with pytest.raises(project_files.ProjectFileDenied) as exc:
        project_files.read_project_file(pid, str(old / "brief.txt"))
    assert exc.value.code == project_files.OUTSIDE_PROJECT


# ------------------------------------------------------------------ 23-26: persisted legacy data
@pytest.mark.parametrize("provider", ["gemini", "claude"])
def test_malicious_path_in_stored_bundle_never_reaches_the_provider(env, provider, caplog):
    env.providers.use(provider)
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    _plant(env, pid, str(env.outside / "secret.txt"))
    _plant(env, pid, str(env.outside / "secret.png"), name="photo.png", file_type=ProjectFileType.ADDITIONAL_FILE)
    res = _signed_in(_client(), owner).post(_url(pid, "analyze-requirements"))
    assert res.status_code == 200
    assert [name for name, _ in env.providers.calls] and {n for n, _ in env.providers.calls} == {provider}
    assert "file content unavailable" in env.providers.prompts()
    assert "assignment_images" not in env.service.store.require_project(pid).artifacts
    _assert_no_sentinel(env, res.get_data(as_text=True), caplog=caplog)


def test_malicious_path_in_old_upload_manifest_is_never_read(env, caplog):
    owner = _user("owner@example.com")
    evil = str(env.outside / "secret.txt")
    bundle = env.service.create_project(
        user_id=str(owner["id"]),
        upload_manifest={"files": [{"source": "assignment_brief", "name": "b.txt", "storage_path": evil}]},
    )
    pid = bundle.project.id
    pipeline_project = env.app.assignment_pipeline.get_project(pid)
    assert all("storage_path" not in item for item in pipeline_project.upload_manifest["files"])
    pipeline_project.upload_manifest["files"][0]["storage_path"] = evil
    res = _signed_in(_client(), owner).post(_url(pid, "analyze-requirements"))
    assert res.status_code == 200
    _assert_no_sentinel(env, res.get_data(as_text=True), caplog=caplog)


def test_legacy_relative_and_absolute_valid_files_remain_readable(env):
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    _legit(env, pid, "old.txt", "Legacy brief: 1200 words on supply chains.")
    _plant(env, pid, f"data/projects/{pid}/files/old.txt", name="old.txt")
    _plant(env, pid, _legit(env, pid, "new.txt", "Current rubric text."), name="new.txt",
           file_type=ProjectFileType.RUBRIC)
    res = _signed_in(_client(), owner).post(_url(pid, "analyze-requirements"))
    assert res.status_code == 200
    prompts = env.providers.prompts()
    assert "Legacy brief: 1200 words on supply chains." in prompts
    assert "Current rubric text." in prompts


def test_legacy_relative_path_of_another_project_is_refused(env):
    owner = _user("owner@example.com")
    pid, other = _project(env, owner), _project(env, owner)
    _legit(env, other, "o.txt", SENTINEL)
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.read_project_file(pid, f"data/projects/{other}/files/o.txt")
    with pytest.raises(project_files.ProjectFileDenied):
        project_files.read_project_file(pid, f"data/projects/{pid}/files/../../{other}/files/o.txt")


def test_one_malicious_and_one_legitimate_file(env, caplog):
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    _plant(env, pid, str(env.outside / "secret.txt"), name="evil.txt")
    _plant(env, pid, _legit(env, pid, "brief.txt", "Real brief: compare two theories."), name="brief.txt")
    res = _signed_in(_client(), owner).post(_url(pid, "analyze-requirements"))
    assert res.status_code == 200
    assert "Real brief: compare two theories." in env.providers.prompts()
    _assert_no_sentinel(env, res.get_data(as_text=True), caplog=caplog)


def test_stored_records_are_not_rewritten_or_deleted(env):
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    evil = str(env.outside / "secret.txt")
    record = _plant(env, pid, evil)
    assert _signed_in(_client(), owner).post(_url(pid, "analyze-requirements")).status_code == 200
    stored = {f.id: f.storage_path for f in env.service.store.list_files(pid)}
    assert stored[record.id] == evil
    with _disarmed():
        assert (env.outside / "secret.txt").read_text(encoding="utf-8").endswith(f"{SENTINEL}\n")


# ------------------------------------------------------------------ 27-32: every reader
def test_requirement_analyzer_reader_refuses_outside_paths(env):
    pid = _project(env, _user("owner@example.com"))
    record = SimpleNamespace(project_id=pid, storage_path=str(env.outside / "secret.txt"),
                             file_type=ProjectFileType.ASSIGNMENT_BRIEF, original_filename="b.txt")
    assert SENTINEL not in ra._extract_file_text(record, pid)
    legit = SimpleNamespace(project_id=pid, storage_path=_legit(env, pid, "b.txt", "hello brief"),
                            file_type=ProjectFileType.ASSIGNMENT_BRIEF, original_filename="b.txt")
    assert ra._extract_file_text(legit, pid) == "hello brief"


def test_research_and_writer_readers_refuse_outside_paths(env):
    pid = _project(env, _user("owner@example.com"))
    files = [
        SimpleNamespace(id="1", project_id=pid, storage_path=str(env.outside / "secret.txt"),
                        file_type="assignment_brief", original_filename="evil.txt"),
        SimpleNamespace(id="2", project_id=pid, storage_path=_legit(env, pid, "r.txt", "rubric body"),
                        file_type="rubric", original_filename="r.txt"),
    ]
    docs = pd.build_parsed_documents(files, project_id=pid)
    material = pd.writer_source_material(files, project_id=pid)
    assert SENTINEL not in " ".join(d.text for d in docs) + material
    assert "rubric body" in material and any("rubric body" in d.text for d in docs)


def test_research_stage_never_receives_outside_content(env):
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    _plant(env, pid, str(env.outside / "secret.txt"))
    _plant(env, pid, _legit(env, pid, "brief.txt", "Brief for research."), name="brief.txt")
    from tests.assignment_helpers import prepare_project_for_research

    prepare_project_for_research(env.service, pid)
    env.service.run_research(pid)
    texts = " ".join(doc.text for doc in env.research.documents)
    assert "Brief for research." in texts
    assert SENTINEL not in texts


def test_image_collection_ignores_outside_and_foreign_images(env):
    owner = _user("owner@example.com")
    pid, other = _project(env, owner), _project(env, owner)
    own_png = _files_dir(env, pid) / "own.png"
    own_png.write_bytes(_png_bytes())
    other_png = _files_dir(env, other) / "theirs.png"
    other_png.write_bytes(_png_bytes())
    files = [
        SimpleNamespace(id="a", project_id=pid, storage_path=str(env.outside / "secret.png"), original_filename="a.png"),
        SimpleNamespace(id="b", project_id=pid, storage_path=str(other_png), original_filename="b.png"),
        SimpleNamespace(id="c", project_id=pid, storage_path=str(own_png), original_filename="own.png"),
    ]
    images = assignment_figures.collect_assignment_images(files, project_id=pid)
    assert [i["storage_path"] for i in images] == [str(own_png)]


def test_image_merge_and_lookup_ignore_outside_images(env):
    pid = _project(env, _user("owner@example.com"))
    own_png = _files_dir(env, pid) / "own.png"
    own_png.write_bytes(_png_bytes())
    evil = {"filename": "evil.png", "storage_path": str(env.outside / "secret.png")}
    own = {"filename": "own.png", "storage_path": str(own_png)}
    merged = assignment_figures.merge_image_lists([evil, own], [evil], project_id=pid)
    assert [i["storage_path"] for i in merged] == [str(own_png)]
    mapping = assignment_figures.images_by_filename([evil, own], project_id=pid)
    assert set(mapping.values()) == {str(own_png)}
    marked = assignment_figures.ensure_figure_markers("## Intro\n\nText.", [evil], project_id=pid)
    assert "FIGURE" not in marked


def test_stale_image_list_in_artifacts_is_dropped_before_use(env):
    pid = _project(env, _user("owner@example.com"))
    project = env.service.store.require_project(pid)
    project.artifacts["assignment_images"] = [{"filename": "evil.png", "storage_path": str(env.outside / "secret.png")}]
    env.service.store.save_project(project)
    assert env.service._project_images(pid, project.artifacts["assignment_images"]) == []
    assert env.service._sync_assignment_images(pid) == []


def _docx_with_marker(name: str) -> bytes:
    doc = Document()
    doc.add_paragraph("Before.")
    doc.add_paragraph(f"[[FIGURE:{name}|Caption]]")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _has_picture(docx_bytes: bytes) -> bool:
    return any(p._element.xpath(".//a:blip") for p in Document(io.BytesIO(docx_bytes)).paragraphs)


def test_docx_embedding_never_reads_outside_images(env):
    pid = _project(env, _user("owner@example.com"))
    evil = [{"filename": "secret.png", "storage_path": str(env.outside / "secret.png")}]
    out = assignment_figures.embed_figures_in_docx_bytes(_docx_with_marker("secret.png"), evil, project_id=pid)
    assert not _has_picture(out)
    assert not _has_picture(_build_docx_bytes("T", "[[FIGURE:secret.png|c]]", images=evil, project_id=pid))
    assert not _has_picture(_build_docx_bytes("T", "[[FIGURE:secret.png|c]]", images=evil))


def test_docx_embedding_of_own_image_still_works(env):
    pid = _project(env, _user("owner@example.com"))
    own_png = _files_dir(env, pid) / "own.png"
    own_png.write_bytes(_png_bytes())
    images = [{"filename": "own.png", "storage_path": str(own_png)}]
    assert _has_picture(assignment_figures.embed_figures_in_docx_bytes(_docx_with_marker("own.png"), images,
                                                                       project_id=pid))
    assert _has_picture(_build_docx_bytes("T", "[[FIGURE:own.png|c]]", images=images, project_id=pid))


def test_docx_embedding_refuses_an_image_swapped_for_a_symlink(env):
    pid = _project(env, _user("owner@example.com"))
    link = _files_dir(env, pid) / "own.png"
    link.symlink_to(env.outside / "secret.png")
    images = [{"filename": "own.png", "storage_path": str(link)}]
    assert not _has_picture(assignment_figures.embed_figures_in_docx_bytes(_docx_with_marker("own.png"), images,
                                                                           project_id=pid))


def test_docx_embedding_rechecks_an_image_swapped_after_lookup(env, monkeypatch):
    pid = _project(env, _user("owner@example.com"))
    own_png = _files_dir(env, pid) / "own.png"
    own_png.write_bytes(_png_bytes())
    lookup = assignment_figures.images_by_filename

    def lookup_then_swap(images, *, project_id):
        mapping = lookup(images, project_id=project_id)
        own_png.unlink()
        own_png.symlink_to(env.outside / "secret.png")
        return mapping

    monkeypatch.setattr(assignment_figures, "images_by_filename", lookup_then_swap)
    images = [{"filename": "own.png", "storage_path": str(own_png)}]
    assert not _has_picture(assignment_figures.embed_figures_in_docx_bytes(_docx_with_marker("own.png"), images,
                                                                           project_id=pid))


def _docx_with_external_parts(target: Path) -> bytes:
    """A DOCX whose body declares an XXE entity and an external image relationship to ``target``."""
    base = io.BytesIO()
    Document().save(base)
    src = zipfile.ZipFile(io.BytesIO(base.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/document.xml":
                text = data.decode("utf-8")
                text = text.replace(
                    "<w:document",
                    f'<!DOCTYPE w:document [<!ENTITY xxe SYSTEM "file://{target}">]><w:document',
                    1,
                )
                text = text.replace(
                    "<w:body>",
                    '<w:body><w:p><w:r><w:t>Visible &xxe; text</w:t></w:r></w:p>'
                    '<w:p><w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/'
                    'wordprocessingDrawing"><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/'
                    'main"><a:graphicData><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/'
                    'picture"><pic:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
                    'relationships" r:link="rIdEvil"/></pic:blipFill></pic:pic></a:graphicData></a:graphic>'
                    "</wp:inline></w:drawing></w:r></w:p>",
                    1,
                )
                data = text.encode("utf-8")
            elif item.filename == "word/_rels/document.xml.rels":
                text = data.decode("utf-8").replace(
                    "</Relationships>",
                    '<Relationship Id="rIdEvil" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                    f'relationships/image" Target="file://{target}" TargetMode="External"/></Relationships>',
                )
                data = text.encode("utf-8")
            dst.writestr(item, data)
    return out.getvalue()


def test_uploaded_docx_cannot_pull_in_external_files(env, caplog):
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    payload = _docx_with_external_parts(env.outside / "secret.txt")
    path = _files_dir(env, pid) / "brief.docx"
    path.write_bytes(payload)
    _plant(env, pid, str(path), name="brief.docx")
    res = _signed_in(_client(), owner).post(_url(pid, "analyze-requirements"))
    assert res.status_code == 200
    docs = pd.build_parsed_documents(env.service.store.list_files(pid), project_id=pid)
    assert all(SENTINEL not in d.text for d in docs)
    _assert_no_sentinel(env, res.get_data(as_text=True), caplog=caplog)


_READER_MODULES = (ra, pd, assignment_figures)


def test_readers_have_no_direct_filesystem_reads():
    """Uploaded files are opened only through services.project_files in the reader modules."""
    for module in _READER_MODULES:
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            assert name not in {"read_bytes", "read_text", "open"} or (
                name == "open"
                and isinstance(func, ast.Attribute)
                and getattr(func.value, "id", "") == "Image"
                and node.args
                and isinstance(node.args[0], ast.Call)
                and getattr(node.args[0].func, "attr", "") == "BytesIO"
            ), f"{module.__name__}:{node.lineno} reads the filesystem directly"
            if name == "add_picture":
                arg = node.args[0]
                assert isinstance(arg, ast.Call), f"{module.__name__}:{node.lineno} add_picture from a path"


# ------------------------------------------------------------------ 33-35: providers
@pytest.mark.parametrize("provider", ["gemini", "claude"])
def test_refused_client_path_never_calls_a_provider(env, provider):
    env.providers.use(provider)
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    client = _signed_in(_client(), owner)
    res = client.post(_url(pid, "files"), json={"file_type": "assignment_brief", "original_filename": "x.txt",
                                                "storage_path": str(env.outside / "secret.txt")})
    assert res.status_code == 400
    assert env.providers.calls == []


@pytest.mark.parametrize("provider", ["gemini", "claude"])
def test_provider_never_receives_the_sentinel(env, provider, caplog):
    env.providers.use(provider)
    owner = _user("owner@example.com")
    pid = _project(env, owner)
    for target in ("secret.txt", "secret.env", "dir/secret.txt"):
        _plant(env, pid, str(env.outside / target))
    _plant(env, pid, f"{_files_dir(env, pid)}/../../../outside/secret.txt")
    _plant(env, pid, "../outside/secret.txt")
    res = _signed_in(_client(), owner).post(_url(pid, "analyze-requirements"))
    assert res.status_code == 200
    assert env.providers.calls and {n for n, _ in env.providers.calls} == {provider}
    _assert_no_sentinel(env, res.get_data(as_text=True), caplog=caplog)


def test_legitimate_upload_reaches_the_provider(env):
    owner = _user("owner@example.com")
    client = _signed_in(_client(), owner)
    res = client.post(
        "/api/assignment/projects/upload",
        data={"assignment_brief": (io.BytesIO(b"Write a 1500 word essay on renewable energy policy."), "brief.txt")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 201
    pid = res.get_json()["project"]["id"]
    assert client.post(_url(pid, "analyze-requirements")).status_code == 200
    assert "Write a 1500 word essay on renewable energy policy." in env.providers.prompts()
