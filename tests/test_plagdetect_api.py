"""PlagDetect HTTP API client and service wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.plagdetect_api.client import (
    PlagDetectAPIClient,
    PlagDetectAPIError,
    parse_percent,
)
from services.plagdetect_api.config import is_configured, prefer_plagdetect_api
from services.turnitin_service.service import TurnitinService
from services.turnitin_service.store import TurnitinStore


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict | None = None,
        content: bytes = b"",
        headers: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        if payload is not None and not content:
            import json

            content = json.dumps(payload).encode()
        self.content = content
        self.text = content.decode("utf-8", errors="replace") if content else ""
        self.headers = headers or (
            {"Content-Type": "application/json"}
            if payload is not None
            else {"Content-Type": "application/pdf"}
        )

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.header_names: list[set[str]] = []

    def request(self, method, url, headers=None, json=None, data=None, files=None, timeout=None, stream=False):
        self.calls.append((method.upper(), url))
        self.header_names.append(set((headers or {}).keys()))
        path = url.split("/api/v1/", 1)[-1]
        method = method.upper()
        if method == "POST" and path == "submit":
            return _FakeResponse(
                200,
                {
                    "success": True,
                    "submission_id": 12345,
                    "filename": "essay.docx",
                    "status": "processing",
                },
            )
        if method == "GET" and path == "status/12345":
            return _FakeResponse(
                200,
                {
                    "success": True,
                    "submission_id": 12345,
                    "status": "completed",
                    "ai_percentage": "45%",
                    "plagiarism_percentage": "12%",
                    "word_count": 1523,
                },
            )
        if method == "GET" and path == "download/12345/plagiarism":
            return _FakeResponse(200, payload=None, content=b"%PDF-1.4 sim")
        if method == "GET" and path == "download/12345/ai":
            return _FakeResponse(200, payload=None, content=b"%PDF-1.4 ai")
        if method == "POST" and path == "highlights/12345":
            return _FakeResponse(
                200,
                {"success": True, "highlight_submission_id": 12346, "message": "queued"},
            )
        if method == "GET" and path == "highlights/12345/status":
            return _FakeResponse(
                200,
                {
                    "success": True,
                    "highlight_status": "completed",
                    "file_available": True,
                },
            )
        if method == "GET" and path == "download/12345/highlights":
            return _FakeResponse(200, payload=None, content=b"%PDF-1.4 hl")
        return _FakeResponse(404, {"message": f"unhandled {method} {path}"})


def test_prefer_plagdetect_api(monkeypatch):
    monkeypatch.delenv("PLAGDETECT_API_KEY", raising=False)
    monkeypatch.delenv("PLAGDETECT_API_SECRET", raising=False)
    monkeypatch.delenv("TURNITIN_API_KEY", raising=False)
    monkeypatch.delenv("TURNITIN_API_SECRET", raising=False)
    monkeypatch.delenv("TURNITIN_USE_BROWSER", raising=False)
    monkeypatch.delenv("TURNITIN_USE_TCA", raising=False)
    assert is_configured() is False
    assert prefer_plagdetect_api() is False
    monkeypatch.setenv("TURNITIN_API_KEY", "pd-key")
    monkeypatch.setenv("TURNITIN_API_SECRET", "pd-secret")
    assert is_configured() is True
    assert prefer_plagdetect_api() is True
    monkeypatch.setenv("TURNITIN_USE_TCA", "1")
    assert prefer_plagdetect_api() is False
    monkeypatch.delenv("TURNITIN_USE_TCA", raising=False)
    monkeypatch.setenv("TURNITIN_USE_BROWSER", "1")
    assert prefer_plagdetect_api() is False


def test_parse_percent():
    assert parse_percent("45%") == (45.0, False)
    assert parse_percent("12") == (12.0, True)
    assert parse_percent("*%") == (None, True)
    assert parse_percent(0) == (0.0, False)
    assert parse_percent(None) == (None, False)


def test_check_file_happy_path(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAGDETECT_API_KEY", "pd-key")
    monkeypatch.setenv("PLAGDETECT_API_SECRET", "pd-secret")
    upload = tmp_path / "essay.docx"
    upload.write_bytes(b"docx-bytes")
    reports = tmp_path / "reports"
    session = _FakeSession()
    client = PlagDetectAPIClient(
        session=session,
        poll_interval=0.01,
        check_timeout=2,
    )
    created: list[str] = []
    result = client.check_file(
        file_path=upload,
        filename="essay.docx",
        report_dir=reports,
        on_created=created.append,
    )
    assert created == ["12345"]
    assert result["external_id"] == "12345"
    assert result["similarity"] == 12
    assert result["similarity_display"] == "12%"
    assert result["ai_score"] == 45
    assert result["ai_score_display"] == "45%"
    assert result["provider"] == "plagdetect"
    assert (reports / "similarity_report.pdf").read_bytes().startswith(b"%PDF")
    assert (reports / "ai_report.pdf").read_bytes().startswith(b"%PDF")
    assert {"X-API-Key", "X-API-Secret"}.issubset(session.header_names[0])


def test_unauthorized_maps_to_error(monkeypatch):
    monkeypatch.setenv("PLAGDETECT_API_KEY", "bad")
    monkeypatch.setenv("PLAGDETECT_API_SECRET", "bad")
    session = MagicMock()
    session.request.return_value = _FakeResponse(401, {"message": "Unauthorized"})
    client = PlagDetectAPIClient(session=session, poll_interval=0.01)
    with pytest.raises(PlagDetectAPIError) as exc:
        client.get_status("1")
    assert exc.value.status_code == 401
    assert "credentials" in str(exc.value).lower()


def test_fetch_highlights(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAGDETECT_API_KEY", "pd-key")
    monkeypatch.setenv("PLAGDETECT_API_SECRET", "pd-secret")
    client = PlagDetectAPIClient(
        session=_FakeSession(),
        poll_interval=0.01,
        check_timeout=2,
    )
    result = client.fetch_highlights(submission_id="12345", report_dir=tmp_path)
    assert result["ai_highlights_display"] == "45%"
    assert (tmp_path / "ai_highlights_report.pdf").read_bytes().startswith(b"%PDF-1.4 hl")


def _init_store(tmp_path, monkeypatch):
    monkeypatch.setattr("services.turnitin_service.store.DB_PATH", tmp_path / "turnitin.db")
    monkeypatch.setattr("services.turnitin_service.store.UPLOAD_ROOT", tmp_path / "uploads")
    monkeypatch.setattr("services.turnitin_service.store.REPORT_ROOT", tmp_path / "reports")
    from services.turnitin_service import store as store_mod

    store_mod.init_db()
    return TurnitinStore()


def test_api_check_persists_and_refunds_on_auth_fail(tmp_path, monkeypatch):
    store = _init_store(tmp_path, monkeypatch)
    upload_dir = tmp_path / "uploads" / "sub1"
    upload_dir.mkdir(parents=True)
    upload_file = upload_dir / "essay.docx"
    upload_file.write_bytes(b"doc")
    store.create(
        submission_id="sub1",
        user_id=7,
        filename="essay.docx",
        upload_path=str(upload_file),
    )

    class BoomClient:
        @classmethod
        def from_env(cls):
            return cls()

        def check_file(self, **kwargs):
            raise PlagDetectAPIError("nope", status_code=401)

    monkeypatch.setattr("services.plagdetect_api.client.PlagDetectAPIClient", BoomClient)
    refund = MagicMock()
    svc = TurnitinService(store=store)
    svc._run_plagdetect_api_check(submission_id="sub1", user_id=7, cost=300, refund_fn=refund)
    refund.assert_called_once()
    row = store.get("sub1")
    assert row["status"] == "failed"
    assert row["meta"]["transport"] == "api"


def test_api_check_persists_scores(tmp_path, monkeypatch):
    store = _init_store(tmp_path, monkeypatch)
    upload_dir = tmp_path / "uploads" / "sub2"
    upload_dir.mkdir(parents=True)
    upload_file = upload_dir / "essay.docx"
    upload_file.write_bytes(b"doc")
    store.create(
        submission_id="sub2",
        user_id=7,
        filename="essay.docx",
        upload_path=str(upload_file),
    )

    class OkClient:
        @classmethod
        def from_env(cls):
            return cls()

        def check_file(self, **kwargs):
            kwargs["on_created"]("12345")
            return {
                "external_id": "12345",
                "similarity": 12,
                "similarity_display": "12%",
                "ai_score": 45,
                "ai_score_display": "45%",
                "similarity_report_path": None,
                "ai_report_path": None,
                "provider": "plagdetect",
            }

    monkeypatch.setattr("services.plagdetect_api.client.PlagDetectAPIClient", OkClient)
    refund = MagicMock()
    svc = TurnitinService(store=store)
    svc._run_plagdetect_api_check(submission_id="sub2", user_id=7, cost=300, refund_fn=refund)
    refund.assert_not_called()
    row = store.get("sub2")
    assert row["status"] == "completed"
    assert row["similarity"] == 12
    assert row["ai_score"] == 45
    api = svc.to_api_row(row)
    assert api["provider"] == "plagdetect"
    assert api["externalId"] == "12345"
