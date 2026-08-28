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
    assert row["status"] == "queued"
    assert (row.get("meta") or {}).get("service_requeue_count") == 1

    assert not svc._requeue_check_job(
        submission_id="sub1",
        user_id=7,
        cost=300,
        job_manager=jm,
        wallet=MagicMock(),
        refund_fn=refund,
    )
