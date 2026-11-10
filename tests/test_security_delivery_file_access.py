"""F-01 follow-up: delivery downloads, the Format Engine DOCX and packaging read only their own outputs.

Every name or path in a delivery package, a formatted-document record or an image list is persisted
JSON. These tests plant sentinel files beside the project storage, arm the open() audit trap from the
F-01 suite, and poison those records the ways a stale or tampered bundle could.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from services import project_files
from services.assignment_formatting import AssignmentFormatEngine
from services.assignment_project.service import ProjectService
from services.delivery_engine import DeliveryEngineService
from services.delivery_engine.models import DeliveryPackage
from tests.test_security_assignment_file_access import (  # noqa: F401  (outside is a fixture)
    SENTINEL,
    _disarmed,
    _png_bytes,
    _ProviderTraps,
    outside,
)
from tests.test_security_paid_pipelines import _client, _signed_in, _user
from tests.test_security_refund_integrity import (  # noqa: F401  (economy, refund_app are fixtures)
    _admin_refund,
    _completed_project_with_delivery,
    _url,
    economy,
    refund_app,
)

LEGIT = b"PK-final-assignment"
ROUTES = ("assignment", "package", "file")


def _docx_file(path: Path, text: str) -> None:
    doc = Document()
    doc.add_paragraph(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))


def _docx_text(path: str) -> str:
    return "\n".join(p.text for p in Document(path).paragraphs)


def _has_picture(path: str) -> bool:
    return any(p._element.xpath(".//a:blip") for p in Document(path).paragraphs)


@pytest.fixture()
def dl(refund_app, outside, monkeypatch):
    storage = refund_app.service.store.storage_root
    monkeypatch.setenv("PROJECT_STORAGE_DIR", str(storage))
    providers = _ProviderTraps(monkeypatch)
    with _disarmed():
        _docx_file(outside / "secret.docx", SENTINEL)
        (outside / "secret.pdf").write_bytes(b"%PDF-1.4 " + SENTINEL.encode())
        _docx_file(outside / "deliv" / "final.docx", SENTINEL)
    owner = _user("owner@example.com")
    pid, package_id, file_id = _completed_project_with_delivery(refund_app, owner)
    rebuilds: list[str] = []

    def no_rebuild(project_id):
        rebuilds.append(project_id)
        raise RuntimeError("rebuild disabled in this test")

    monkeypatch.setattr(refund_app.service, "run_delivery", no_rebuild)
    return SimpleNamespace(
        app=refund_app.app,
        env=refund_app,
        service=refund_app.service,
        storage=storage,
        outside=outside,
        owner=owner,
        pid=pid,
        package_id=package_id,
        file_id=file_id,
        delivery=storage / pid / "delivery",
        formatted=storage / pid / "formatted",
        rebuilds=rebuilds,
        providers=providers,
        client=_signed_in(_client(), owner),
    )


def _get(dl, kind: str, client=None, *, package_id=None, file_id=None):
    client = client or dl.client
    if kind == "assignment":
        return client.get(_url(dl.pid, "download"))
    if kind == "package":
        return client.get(f"/api/delivery/packages/{package_id or dl.package_id}/download")
    return client.get(f"/api/delivery/files/{file_id or dl.file_id}")


def _poison(dl, *, client_filename=None, storage_path=None) -> None:
    """Rewrite the persisted package (and the worker's memory copy) as a tampered bundle would."""
    project = dl.service.store.require_project(dl.pid)
    snapshot = dict(project.artifacts["delivery_package"])
    if client_filename is not None:
        snapshot["client_filename"] = client_filename
    if storage_path is not None:
        snapshot["files"] = [{**snapshot["files"][0], "storage_path": storage_path}]
    project.artifacts["delivery_package"] = snapshot
    dl.service.store.save_project(project)
    dl.service.delivery.store.save(DeliveryPackage.from_dict({**snapshot, "project_id": dl.pid}))


def _assert_refused(res, *markers: bytes) -> None:
    assert res.status_code in (401, 403, 404, 503), res.status_code
    for marker in (LEGIT, SENTINEL.encode(), *markers):
        assert marker not in res.data
    assert b"/" + b"outside" not in res.data


# ------------------------------------------------------------------ 1-4: access control
@pytest.mark.parametrize("kind", ROUTES)
def test_paid_owner_downloads_the_delivery_file(dl, kind):
    res = _get(dl, kind)
    assert res.status_code == 200 and res.data == LEGIT
    assert "final.docx" in res.headers["Content-Disposition"]


@pytest.mark.parametrize("kind", ROUTES)
def test_non_owner_and_anonymous_cannot_download(dl, kind):
    intruder = _signed_in(_client(), _user("intruder@example.com"))
    for client in (intruder, _client()):
        _assert_refused(_get(dl, kind, client))


@pytest.mark.parametrize("kind", ROUTES)
def test_refunded_owner_cannot_download(dl, kind):
    assert _admin_refund(dl.env, dl.pid).status_code == 200
    res = _get(dl, kind)
    assert res.status_code == 404
    _assert_refused(res)


@pytest.mark.parametrize("kind", ROUTES)
def test_ledger_reconciliation_failure_returns_503(dl, kind, monkeypatch):
    def locked(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(dl.service, "reconcile_payment_state", locked)
    res = _get(dl, kind)
    assert res.status_code == 503
    _assert_refused(res)


# ------------------------------------------------------------------ 5-9: delivery paths
def _escapes(dl) -> list[tuple[str | None, str | None]]:
    outside_docx = str(dl.outside / "secret.docx")
    return [
        ("../../../outside/secret.docx", None),
        (outside_docx, None),
        ("..", None),
        ("secret.docx\x00.docx", None),
        ("..\\..\\..\\outside\\secret.docx", None),
        ("%2e%2e/%2e%2e/%2e%2e/outside/secret.docx", None),
        (None, outside_docx),
        (None, f"{dl.delivery}/../../../outside/secret.docx"),
        (None, "../../../outside/secret.docx"),
        (None, f"data/projects/{dl.pid}/delivery/../../../../outside/secret.docx"),
        (None, f"{dl.delivery}/debug/requirement.json"),
        (None, "C:\\outside\\secret.docx"),
    ]


@pytest.mark.parametrize("kind", ROUTES)
def test_delivery_path_traversal_and_outside_paths_are_refused(dl, kind):
    debug = dl.delivery / "debug" / "requirement.json"
    debug.parent.mkdir()
    debug.write_text('{"debug": "DEBUG-MARKER"}', encoding="utf-8")
    (dl.delivery / "final.docx").unlink()
    for client_filename, storage_path in _escapes(dl):
        _poison(dl, client_filename=client_filename or "final.docx", storage_path=storage_path)
        res = _get(dl, kind)
        assert res.status_code == 404, (client_filename, storage_path, res.status_code)
        _assert_refused(res, b"DEBUG-MARKER")


@pytest.mark.parametrize("kind", ROUTES)
def test_delivery_symlink_to_outside_file_is_refused(dl, kind):
    target = dl.delivery / "final.docx"
    target.unlink()
    target.symlink_to(dl.outside / "secret.docx")
    res = _get(dl, kind)
    assert res.status_code == 404
    _assert_refused(res)


@pytest.mark.parametrize("kind", ROUTES)
def test_symlinked_delivery_directory_is_refused(dl, kind):
    for item in dl.delivery.rglob("*"):
        if item.is_file():
            item.unlink()
    for item in sorted(dl.delivery.rglob("*"), reverse=True):
        item.rmdir()
    dl.delivery.rmdir()
    dl.delivery.symlink_to(dl.outside / "deliv", target_is_directory=True)
    res = _get(dl, kind)
    assert res.status_code == 404
    _assert_refused(res)


def _fifo_feeder(path: Path, stop: threading.Event) -> threading.Thread:
    """Answers any reader that blocks on the FIFO, so a reader that opened it fails instead of hanging."""

    def feed() -> None:
        while not stop.wait(0.05):
            try:
                fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
            except OSError:
                continue
            try:
                with os.fdopen(fd, "wb") as pipe:
                    pipe.write(b"FIFO-MARKER")
            except OSError:
                pass

    thread = threading.Thread(target=feed, daemon=True)
    thread.start()
    return thread


@pytest.mark.parametrize("kind", ROUTES)
def test_non_regular_delivery_entries_are_refused(dl, kind):
    target = dl.delivery / "final.docx"
    target.unlink()
    target.mkdir()
    res = _get(dl, kind)
    assert res.status_code == 404
    target.rmdir()
    os.mkfifo(target)
    stop = threading.Event()
    feeder = _fifo_feeder(target, stop)
    try:
        res = _get(dl, kind)
    finally:
        stop.set()
        feeder.join(timeout=5)
    assert res.status_code == 404
    _assert_refused(res, b"FIFO-MARKER")


@pytest.mark.parametrize("kind", ROUTES)
def test_foreign_project_delivery_file_is_refused(dl, kind):
    other_owner = _user("other@example.com")
    other, _pkg, _file = _completed_project_with_delivery(dl.env, other_owner)
    foreign = dl.storage / other / "delivery" / "final.docx"
    foreign.write_bytes(b"PK-FOREIGN-MARKER")
    (dl.delivery / "final.docx").unlink()
    for client_filename, storage_path in [
        (f"../../{other}/delivery/final.docx", None),
        (None, str(foreign)),
        (None, f"data/projects/{other}/delivery/final.docx"),
        (None, f"{dl.delivery}/../../{other}/delivery/final.docx"),
    ]:
        _poison(dl, client_filename=client_filename or "final.docx", storage_path=storage_path)
        res = _get(dl, kind)
        assert res.status_code == 404
        _assert_refused(res, b"PK-FOREIGN-MARKER")


def test_stale_delivery_metadata_cannot_redirect_the_reader(dl):
    stale_root = f"/srv/old-root/projects/{dl.pid}/delivery/final.docx"
    _poison(dl, client_filename="../../../outside/secret.docx", storage_path=str(dl.outside / "secret.docx"))
    for kind in ("assignment", "package"):
        res = _get(dl, kind)
        assert res.status_code == 200 and res.data == LEGIT
    _assert_refused(_get(dl, "file"))

    _poison(dl, client_filename="final.docx", storage_path=stale_root)
    assert _get(dl, "assignment").data == LEGIT
    res = _get(dl, "file")
    assert res.status_code == 404
    assert b"old-root" not in res.data
    assert dl.service.store.require_project(dl.pid).artifacts["delivery_package"]["files"][0]["storage_path"] == stale_root


@pytest.mark.parametrize("kind", ROUTES)
def test_delivery_file_swapped_for_a_symlink_at_open_time_is_refused(dl, kind, monkeypatch):
    target = dl.delivery / "final.docx"
    real_open = os.open

    def swapping_open(path, flags, *args, **kwargs):
        if path == "final.docx" and kwargs.get("dir_fd") is not None and not target.is_symlink():
            target.unlink()
            target.symlink_to(dl.outside / "secret.docx")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(project_files.os, "open", swapping_open)
    res = _get(dl, kind)
    assert res.status_code == 404
    _assert_refused(res)


@pytest.mark.parametrize("kind", ROUTES)
def test_delivery_directory_swapped_for_a_symlink_at_open_time_is_refused(dl, kind, monkeypatch):
    real_open = os.open

    def swapping_open(path, flags, *args, **kwargs):
        if path == "delivery" and kwargs.get("dir_fd") is not None and not dl.delivery.is_symlink():
            for item in sorted(dl.delivery.rglob("*"), reverse=True):
                item.unlink() if item.is_file() else item.rmdir()
            dl.delivery.rmdir()
            dl.delivery.symlink_to(dl.outside / "deliv", target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(project_files.os, "open", swapping_open)
    res = _get(dl, kind)
    assert res.status_code == 404
    _assert_refused(res)


# ------------------------------------------------------------------ 10-16: formatted outputs
def _package(dl, *, formatted_path=None, images=None, content="Plain draft body."):
    return DeliveryEngineService().prepare_package(
        final_draft={"id": "d1", "title": "Final", "content": content},
        requirement_json={"assignment_type": "Essay"},
        research_plan={"x": 1},
        blueprint={"x": 1},
        review_report={"overall_score": 80},
        detection_report={"overall_ai_score": 1.0},
        project_id=dl.pid,
        formatted_document_path=formatted_path,
        assignment_images=images,
    )


def _delivered(package) -> str:
    entry = package.files[0]
    assert Path(entry.storage_path).parent.name == "delivery"
    return entry.storage_path


def test_owners_formatted_document_is_used(dl):
    path = dl.formatted / "formatted.docx"
    _docx_file(path, "FORMATTED-OK")
    record = {"project_id": dl.pid, "path": str(path)}
    chosen = ProjectService._delivery_formatted_path(dl.pid, record)
    package = _package(dl, formatted_path=chosen)
    assert package.files[0].label == "Formatted Assignment"
    assert "FORMATTED-OK" in _docx_text(_delivered(package))
    legacy = _package(dl, formatted_path=f"data/projects/{dl.pid}/formatted/formatted.docx")
    assert legacy.files[0].label == "Formatted Assignment"


def test_client_cannot_supply_a_formatted_path(dl):
    evil = {"project_id": dl.pid, "path": str(dl.outside / "secret.docx")}
    before = dl.service.store.require_project(dl.pid).artifacts.get("formatted_document")
    res = dl.client.post(
        _url(dl.pid, "stages/formatting/complete"),
        json={"output": {"path": evil["path"]}, "artifacts": {"formatted_document": evil}},
    )
    assert res.status_code == 200
    stored = dl.service.store.require_project(dl.pid).artifacts.get("formatted_document")
    assert stored == before
    assert ProjectService._delivery_formatted_path(dl.pid, stored) is None


def _formatted_escapes(dl) -> list[str]:
    return [
        str(dl.outside / "secret.docx"),
        f"{dl.formatted}/../../../outside/secret.docx",
        "../../outside/secret.docx",
        f"data/projects/{dl.pid}/formatted/../../../../outside/secret.docx",
        f"{dl.formatted}\\..\\..\\..\\outside\\secret.docx",
        f"{dl.formatted}/%2e%2e/%2e%2e/%2e%2e/outside/secret.docx",
        f"{dl.formatted}/formatted.docx\x00",
    ]


def test_malicious_persisted_formatted_path_is_refused(dl):
    for evil in _formatted_escapes(dl):
        project = dl.service.store.require_project(dl.pid)
        project.artifacts["formatted_document"] = {"project_id": dl.pid, "path": evil}
        dl.service.store.save_project(project)
        stored = dl.service.store.require_project(dl.pid).artifacts["formatted_document"]
        package = _package(dl, formatted_path=ProjectService._delivery_formatted_path(dl.pid, stored))
        assert package.files[0].label == "Final Assignment", evil
        assert SENTINEL not in _docx_text(_delivered(package))


def test_paths_outside_the_formatted_root_are_refused(dl):
    (dl.storage / dl.pid / "files").mkdir(parents=True, exist_ok=True)
    for path in (
        dl.storage / dl.pid / "files" / "brief.docx",
        dl.formatted / "nested" / "formatted.docx",
        dl.delivery / "final-copy.docx",
        dl.storage / dl.pid / "formatted.docx",
    ):
        _docx_file(path, "WRONG-AREA")
        package = _package(dl, formatted_path=str(path))
        assert package.files[0].label == "Final Assignment", path
        assert "WRONG-AREA" not in _docx_text(_delivered(package))


def test_formatted_symlink_escapes_are_refused(dl):
    link = dl.formatted / "formatted.docx"
    link.parent.mkdir(parents=True)
    link.symlink_to(dl.outside / "secret.docx")
    package = _package(dl, formatted_path=str(link))
    assert package.files[0].label == "Final Assignment"
    link.unlink()
    dl.formatted.rmdir()
    dl.formatted.symlink_to(dl.outside, target_is_directory=True)
    package = _package(dl, formatted_path=str(dl.formatted / "secret.docx"))
    assert package.files[0].label == "Final Assignment"
    assert SENTINEL not in _docx_text(_delivered(package))


def test_foreign_projects_formatted_file_is_refused(dl):
    other = dl.service.create_project(user_id=str(_user("other@example.com")["id"]), title="Other").project.id
    foreign = dl.storage / other / "formatted" / "formatted.docx"
    _docx_file(foreign, "FOREIGN-FORMATTED")
    for path in (str(foreign), f"data/projects/{other}/formatted/formatted.docx",
                 f"{dl.formatted}/../../{other}/formatted/formatted.docx"):
        package = _package(dl, formatted_path=path)
        assert "FOREIGN-FORMATTED" not in _docx_text(_delivered(package))
    record = {"project_id": other, "path": f"{dl.formatted}/formatted.docx"}
    assert ProjectService._delivery_formatted_path(dl.pid, record) is None


def test_stale_formatted_json_cannot_redirect_the_reader(dl):
    _docx_file(dl.formatted / "formatted.docx", "CURRENT-FORMATTED")
    for stale in (f"/srv/old-root/projects/{dl.pid}/formatted/formatted.docx", str(dl.outside / "secret.docx")):
        record = {"project_id": dl.pid, "path": stale, "id": "old"}
        package = _package(dl, formatted_path=ProjectService._delivery_formatted_path(dl.pid, record))
        text = _docx_text(_delivered(package))
        assert SENTINEL not in text and "CURRENT-FORMATTED" not in text
        assert package.files[0].label == "Final Assignment"


# ------------------------------------------------------------------ 17-21: packaging
def _image(dl, name: str = "own.png") -> Path:
    files = dl.storage / dl.pid / "files"
    files.mkdir(parents=True, exist_ok=True)
    path = files / name
    path.write_bytes(_png_bytes())
    return path


def test_valid_project_image_is_embedded(dl):
    own = _image(dl)
    images = [{"filename": "own.png", "storage_path": str(own)}]
    package = _package(dl, images=images, content="Intro.\n\n[[FIGURE:own.png|Caption]]")
    assert _has_picture(_delivered(package))
    _docx_file(dl.formatted / "formatted.docx", "[[FIGURE:own.png|Caption]]")
    package = _package(dl, formatted_path=str(dl.formatted / "formatted.docx"), images=images)
    assert package.files[0].label == "Formatted Assignment" and _has_picture(_delivered(package))


def test_external_image_path_is_refused(dl):
    images = [{"filename": "secret.png", "storage_path": str(dl.outside / "secret.png")}]
    package = _package(dl, images=images, content="[[FIGURE:secret.png|c]]")
    assert not _has_picture(_delivered(package))
    _docx_file(dl.formatted / "formatted.docx", "[[FIGURE:secret.png|c]]")
    package = _package(dl, formatted_path=str(dl.formatted / "formatted.docx"), images=images)
    assert not _has_picture(_delivered(package))


def test_symlinked_image_source_is_refused(dl):
    link = dl.storage / dl.pid / "files" / "own.png"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(dl.outside / "secret.png")
    images = [{"filename": "own.png", "storage_path": str(link)}]
    package = _package(dl, images=images, content="[[FIGURE:own.png|c]]")
    assert not _has_picture(_delivered(package))


def test_stale_image_reference_cannot_escape_the_project(dl):
    own = _image(dl)
    other = dl.service.create_project(user_id=str(_user("other@example.com")["id"]), title="Other").project.id
    theirs = dl.storage / other / "files" / "theirs.png"
    theirs.parent.mkdir(parents=True)
    theirs.write_bytes(_png_bytes())
    for entry in (
        {"filename": "own.png", "storage_path": f"/srv/old-root/projects/{dl.pid}/files/own.png"},
        {"filename": "own.png", "storage_path": f"{own.parent}/../../{other}/files/theirs.png"},
        {"filename": "own.png", "storage_path": str(theirs)},
        {"filename": "own.png", "storage_path": str(own), "project_id": other},
    ):
        package = _package(dl, images=[entry], content="[[FIGURE:own.png|c]]")
        assert not _has_picture(_delivered(package)), entry


def test_rejected_sources_are_never_consumed(dl):
    link = dl.storage / dl.pid / "files" / "linked.png"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(dl.outside / "secret.png")
    images = [
        {"filename": "secret.png", "storage_path": str(dl.outside / "secret.png")},
        {"filename": "linked.png", "storage_path": str(link)},
    ]
    _package(dl, formatted_path=str(dl.outside / "secret.docx"), images=images,
             content="[[FIGURE:secret.png|a]]\n\n[[FIGURE:linked.png|b]]")
    for path in dl.storage.rglob("*"):
        if path.is_file() and not path.is_symlink():
            assert SENTINEL.encode() not in path.read_bytes(), path
    assert dl.providers.calls == []


# ------------------------------------------------------------------ 22-24: pipeline artifacts
def _evil_stage_body(dl) -> dict:
    outside_docx = str(dl.outside / "secret.docx")
    image = {"filename": "secret.png", "storage_path": str(dl.outside / "secret.png")}
    return {
        "output": {"path": outside_docx, "storage_path": outside_docx},
        "artifacts": {
            "formatted_document": {"project_id": dl.pid, "path": outside_docx},
            "delivery_package": {
                "id": "pkg-evil",
                "project_id": dl.pid,
                "client_filename": "../../../outside/secret.docx",
                "files": [{"id": "file-evil", "filename": "x.docx", "file_type": "final_assignment_docx",
                           "storage_path": outside_docx}],
            },
            "delivery_package_id": "pkg-evil",
            "assignment_images": [image],
        },
        "requirement_json": {"title": "x", "assignment_images": [image], "include_assignment_images": True},
        "pricing": {"price": 0},
    }


@pytest.mark.parametrize("stage", ["formatting", "delivery", "writing", "upload"])
def test_stage_complete_artifacts_never_become_file_reads(dl, stage):
    keys = ("formatted_document", "delivery_package", "delivery_package_id", "assignment_images")
    before = {k: dl.service.store.require_project(dl.pid).artifacts.get(k) for k in keys}
    requirement = dl.service.store.require_bundle(dl.pid).requirement.to_dict()

    res = dl.client.post(_url(dl.pid, f"stages/{stage}/complete"), json=_evil_stage_body(dl))
    assert res.status_code == 200

    bundle = dl.service.store.require_bundle(dl.pid)
    assert {k: bundle.project.artifacts.get(k) for k in keys} == before
    assert bundle.requirement.to_dict() == requirement
    for kind in ROUTES:
        assert _get(dl, kind).data == LEGIT
    _assert_refused(_get(dl, "package", package_id="pkg-evil"))
    _assert_refused(_get(dl, "file", file_id="file-evil"))
    assert dl.service._project_images(dl.pid, bundle.project.artifacts.get("assignment_images")) == []
    assert ProjectService._delivery_formatted_path(dl.pid, bundle.project.artifacts.get("formatted_document")) is None
    assert SENTINEL not in dl.client.get(_url(dl.pid)).get_data(as_text=True)


def test_path_bearing_requirement_images_are_refused_before_file_access(dl):
    image = {"filename": "secret.png", "storage_path": str(dl.outside / "secret.png")}
    formatted = AssignmentFormatEngine().format_draft(
        draft={"id": "d1", "title": "T", "content": "## Intro\n\n[[FIGURE:secret.png|c]]"},
        requirement_json={"assignment_images": [image], "include_assignment_images": True},
        project_id=dl.pid,
    )
    assert Path(formatted["path"]).parent == dl.formatted
    assert not _has_picture(formatted["path"])


def test_legitimate_stage_completion_still_works(dl):
    assert dl.client.post(_url(dl.pid, "stages/pricing/start")).status_code == 200
    res = dl.client.post(_url(dl.pid, "stages/pricing/complete"), json={"output": {"ok": True}})
    assert res.status_code == 200
    stages = {s["stage"]: s for s in res.get_json()["stages"]}
    assert stages["pricing"]["status"] == "completed" and stages["pricing"]["output"] == {"ok": True}
    assert _get(dl, "assignment").data == LEGIT


def test_unknown_area_and_names_are_refused():
    pid = "p" + uuid.uuid4().hex[:8]
    for area in ("files", "debug", "", "../delivery"):
        with pytest.raises(project_files.ProjectFileDenied):
            project_files.read_project_output_name(pid, area, "x.docx")
    for name in ("", ".", "..", "a/b", "a\\b", "x\x00", "%2e%2e", "x" * 300, None, 5):
        with pytest.raises(project_files.ProjectFileDenied):
            project_files.read_project_output_name(pid, project_files.DELIVERY_AREA, name)
