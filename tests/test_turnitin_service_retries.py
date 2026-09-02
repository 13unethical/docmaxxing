"""Turnitin / PlagDetect transient failure handling."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.turnitin_service.service import TurnitinService
from services.turnitin_service.store import TurnitinStore


class _FakeJobManager:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self._jobs: dict[str, SimpleNamespace] = {}

    def create(self, provider, operation, payload, *, max_retries=0):
        job_id = f"job-{len(self.created) + 1}"
        job = SimpleNamespace(
            id=job_id,
            status=SimpleNamespace(value="FAILED"),
            result=None,
            error="browser closed",
            error_code="STALE_PAGE",
            finished_at=None,
            is_terminal=True,
        )
        self._jobs[job_id] = job
        self.created.append(
            {
                "provider": provider,
                "operation": operation,
                "payload": payload,
                "max_retries": max_retries,
            }
        )
        return job

    def wait(self, job_id, timeout=None):
        return self._jobs[job_id]

    def get(self, job_id):
        return self._jobs.get(job_id)


def test_requeue_check_job_once(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.turnitin_service.store.DB_PATH", tmp_path / "turnitin.db"
    )
    monkeypatch.setattr(
        "services.turnitin_service.store.UPLOAD_ROOT", tmp_path / "uploads"
    )
    monkeypatch.setattr(
        "services.turnitin_service.store.REPORT_ROOT", tmp_path / "reports"
    )
    store = TurnitinStore()
    from services.turnitin_service import store as store_mod

    store_mod.init_db()

    upload_dir = tmp_path / "uploads" / "sub1"
    upload_dir.mkdir(parents=True)
    upload_file = upload_dir / "essay.docx"
    upload_file.write_bytes(b"doc")

    store.create(
        submission_id="sub1",
        user_id=7,
        filename="essay.docx",
        upload_path=str(upload_file),
        exclude_bibliography=False,
        exclude_quotes=False,
        job_id="job-0",
    )

    svc = TurnitinService(store=store)
    jm = _FakeJobManager()
    refund = MagicMock()

    assert svc._requeue_check_job(
        submission_id="sub1",
        user_id=7,
        cost=300,
        job_manager=jm,
        wallet=MagicMock(),
        refund_fn=refund,
    )
    assert len(jm.created) == 1
    assert jm.created[0]["max_retries"] == 3
    row = store.get("sub1")
    assert (row.get("meta") or {}).get("service_requeue_count") == 1
    # Fake job is already FAILED; the watcher thread may finish before this assert.
    assert row["status"] in ("queued", "running", "failed")

    assert not svc._requeue_check_job(
        submission_id="sub1",
        user_id=7,
        cost=300,
        job_manager=jm,
        wallet=MagicMock(),
        refund_fn=refund,
    )


def test_no_refund_when_plagdetect_already_has_row(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.turnitin_service.store.DB_PATH", tmp_path / "turnitin.db"
    )
    monkeypatch.setattr(
        "services.turnitin_service.store.UPLOAD_ROOT", tmp_path / "uploads"
    )
    monkeypatch.setattr(
        "services.turnitin_service.store.REPORT_ROOT", tmp_path / "reports"
    )
    from services.turnitin_service import store as store_mod

    store_mod.init_db()
    store = TurnitinStore()
    store.create(
        submission_id="sub-pd",
        user_id=7,
        filename="essay.docx",
        upload_path=str(tmp_path / "essay.docx"),
        exclude_bibliography=False,
        exclude_quotes=False,
        job_id="job-x",
    )
    store.update("sub-pd", external_id="132538")

    svc = TurnitinService(store=store)
    refund = MagicMock()
    job = SimpleNamespace(result={"external_id": "132538"}, finished_at=None)
    svc._maybe_refund(
        submission_id="sub-pd",
        user_id=7,
        cost=300,
        job=job,
        job_manager=MagicMock(),
        refund_fn=refund,
        error_message="Timed out waiting for PlagDetect results.",
        error_code="TIMEOUT",
    )
    refund.assert_not_called()
    row = store.get("sub-pd")
    assert row["status"] in ("completed", "running")
    assert row["external_id"] == "132538"


def test_no_refund_when_failed_job_carries_external_id(tmp_path, monkeypatch):
    """PlagDetect already took the slot even if the dashboard row says Failed."""
    monkeypatch.setattr(
        "services.turnitin_service.store.DB_PATH", tmp_path / "turnitin.db"
    )
    monkeypatch.setattr(
        "services.turnitin_service.store.UPLOAD_ROOT", tmp_path / "uploads"
    )
    monkeypatch.setattr(
        "services.turnitin_service.store.REPORT_ROOT", tmp_path / "reports"
    )
    from services.turnitin_service import store as store_mod

    store_mod.init_db()
    store = TurnitinStore()
    store.create(
        submission_id="sub-fail",
        user_id=7,
        filename="essay.docx",
        upload_path=str(tmp_path / "essay.docx"),
        exclude_bibliography=False,
        exclude_quotes=False,
        job_id="job-y",
    )
    svc = TurnitinService(store=store)
    refund = MagicMock()
    job = SimpleNamespace(
        result={"external_id": "99911", "success": False, "error": "Failed"},
        finished_at=None,
    )
    svc._maybe_refund(
        submission_id="sub-fail",
        user_id=7,
        cost=300,
        job=job,
        job_manager=MagicMock(),
        refund_fn=refund,
        error_message="External check failed",
        error_code="ERROR",
    )
    refund.assert_not_called()
    row = store.get("sub-fail")
    assert row["external_id"] == "99911"
    assert row["status"] in ("completed", "running")


def test_api_row_hides_operator_errors_from_users():
    from services.turnitin_service.service import public_error_message

    cred = (
        "Turnitin rejected the API credentials (HTTP 403). These Key/Secret "
        "pairs are often LTI keys. In Turnitin admin -> Integrations, use "
        "Generate TCA Scope (not LTI Scope)."
    )
    out = public_error_message(cred, error_code="403")
    assert out
    assert "HTTP 403" not in out
    assert ".env" not in out
    assert "TCA" not in out
    assert "TURNITIN_API" not in public_error_message(
        "Turnitin API credentials were rejected. Check `TURNITIN_API_KEY`."
    )
    login = public_error_message(
        "PlagDetect session is not logged in. Set PLAGDETECT_EMAIL in .env.",
        error_code="LOGIN_REQUIRED",
    )
    assert login
    assert "PLAGDETECT" not in login
    assert ".env" not in login
    timeout = public_error_message(
        "Timed out waiting for PlagDetect results.", error_code="TIMEOUT"
    )
    assert "timed out" in timeout.lower() or "too long" in timeout.lower()
