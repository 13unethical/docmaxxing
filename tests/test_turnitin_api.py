"""Official Turnitin Core API client and service wiring."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from services.turnitin_api.client import (
    TurnitinAPIError,
    TurnitinCoreClient,
    format_ai_display,
)
from services.turnitin_api.config import api_base, is_configured, prefer_official_api
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
        self.auth_headers: list[str | None] = []

    def request(self, method, url, headers=None, json=None, data=None, timeout=None):
        self.calls.append((method.upper(), url))
        self.auth_headers.append((headers or {}).get("Authorization"))
        path = url.split("/api/v1/", 1)[-1]
        method = method.upper()
        if method == "GET" and path.startswith("eula/latest"):
            return _FakeResponse(200, {"version": "v1beta"})
        if method == "POST" and "/accept" in path:
            return _FakeResponse(200, {})
        if method == "POST" and path.rstrip("/") == "submissions":
            return _FakeResponse(201, {"id": "sub-uuid-1"})
        if method == "PUT" and path.endswith("/original"):
            return _FakeResponse(202, {})
        if method == "GET" and path == "submissions/sub-uuid-1":
            return _FakeResponse(200, {"status": "COMPLETE"})
        if method == "PUT" and path.endswith("/similarity") and not path.endswith("/pdf"):
            return _FakeResponse(202, {})
        if method == "GET" and path.endswith("/similarity"):
            return _FakeResponse(
                200,
                {"status": "COMPLETE", "overall_match_percentage": 17},
            )
        if method == "POST" and path.endswith("/similarity/pdf"):
            return _FakeResponse(202, {"id": "pdf-1"})
        if method == "GET" and path.endswith("/similarity/pdf/pdf-1"):
            return _FakeResponse(
                200,
                payload=None,
                content=b"%PDF-1.4 fake",
                headers={"Content-Type": "application/pdf"},
            )
        return _FakeResponse(404, {"message": f"unhandled {method} {path}"})


def test_api_base_appends_v1(monkeypatch):
    monkeypatch.delenv("TURNITIN_API_BASE", raising=False)
    monkeypatch.delenv("TURNITIN_API_URL", raising=False)
    assert api_base() == "https://app-us.turnitin.com/api/v1"
    monkeypatch.setenv("TURNITIN_API_BASE", "https://contoso.turnitin.com")
    assert api_base() == "https://contoso.turnitin.com/api/v1"
    monkeypatch.setenv("TURNITIN_API_BASE", "https://api.turnitin.com/api/v1")
    assert api_base() == "https://api.turnitin.com/api/v1"
    monkeypatch.setenv("TURNITIN_API_BASE", "https://app-us.turnitin.com/api")
    assert api_base() == "https://app-us.turnitin.com/api/v1"


def test_prefer_official_api(monkeypatch):
    monkeypatch.delenv("TURNITIN_API_KEY", raising=False)
    monkeypatch.delenv("TURNITIN_API_SECRET", raising=False)
    monkeypatch.delenv("TURNITIN_USE_BROWSER", raising=False)
    monkeypatch.delenv("TURNITIN_USE_TCA", raising=False)
    assert is_configured() is False
    assert prefer_official_api() is False
    monkeypatch.setenv("TURNITIN_API_SECRET", "tca-secret")
    assert is_configured() is True
    assert prefer_official_api() is False
    monkeypatch.setenv("TURNITIN_USE_TCA", "1")
    assert prefer_official_api() is True
    monkeypatch.setenv("TURNITIN_USE_BROWSER", "1")
    assert prefer_official_api() is False


def test_api_token_prefers_secret_over_key(monkeypatch):
    from services.turnitin_api.config import api_token

    monkeypatch.setenv("TURNITIN_API_KEY", "key-id")
    monkeypatch.setenv("TURNITIN_API_SECRET", "the-secret")
    assert api_token() == "the-secret"
    monkeypatch.delenv("TURNITIN_API_SECRET", raising=False)
    assert api_token() == "key-id"


def test_check_file_happy_path(tmp_path, monkeypatch):
    monkeypatch.delenv("TURNITIN_API_KEY", raising=False)
    monkeypatch.delenv("TURNITIN_AUTH_SCHEME", raising=False)
    monkeypatch.setenv("TURNITIN_API_SECRET", "tca-secret")
    monkeypatch.setenv("TURNITIN_API_BASE", "https://api.turnitin.com")
    upload = tmp_path / "essay.docx"
    upload.write_bytes(b"docx-bytes")
    reports = tmp_path / "reports"
    session = _FakeSession()
    client = TurnitinCoreClient(
        session=session,
        poll_interval=0.01,
        upload_timeout=2,
        similarity_timeout=2,
    )
    created: list[str] = []
    result = client.check_file(
        file_path=upload,
        filename="essay.docx",
        owner_id="user_7",
        exclude_bibliography=True,
        exclude_quotes=True,
        report_dir=reports,
        on_created=created.append,
    )
    assert created == ["sub-uuid-1"]
    assert result["external_id"] == "sub-uuid-1"
    assert result["similarity"] == 17
    assert result["similarity_display"] == "17%"
    assert result.get("ai_score") is None
    assert not result.get("ai_unavailable")
    assert result["provider"] == "turnitin"
    pdf = reports / "similarity_report.pdf"
    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF")
    methods = [m for m, _ in session.calls]
    assert "PUT" in methods
    assert any(url.endswith("/original") for _, url in session.calls)
    assert session.auth_headers
    assert session.auth_headers[0] == "tca-secret"


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("TURNITIN_API_KEY", raising=False)
    monkeypatch.delenv("TURNITIN_API_SECRET", raising=False)
    with pytest.raises(TurnitinAPIError):
        TurnitinCoreClient(token="")


def _init_store(tmp_path, monkeypatch):
    monkeypatch.setattr("services.turnitin_service.store.DB_PATH", tmp_path / "turnitin.db")
    monkeypatch.setattr("services.turnitin_service.store.UPLOAD_ROOT", tmp_path / "uploads")
    monkeypatch.setattr("services.turnitin_service.store.REPORT_ROOT", tmp_path / "reports")
    from services.turnitin_service import store as store_mod

    store_mod.init_db()
    return TurnitinStore()


def test_tca_refunds_when_create_never_happens(tmp_path, monkeypatch):
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
    store.update("sub1", meta_json='{"provider": "turnitin"}')

    class BoomClient:
        @classmethod
        def from_env(cls):
            return cls()

        def check_file(self, **kwargs):
            raise TurnitinAPIError("credentials rejected", status_code=401)

    monkeypatch.setattr("services.turnitin_api.client.TurnitinCoreClient", BoomClient)
    refund = MagicMock()
    svc = TurnitinService(store=store)
    svc._run_tca_check(submission_id="sub1", user_id=7, cost=300, refund_fn=refund)
    refund.assert_called_once()
    row = store.get("sub1")
    assert row["status"] == "failed"


def test_tca_no_refund_after_submission_created(tmp_path, monkeypatch):
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

    class CreatedThenBoom:
        @classmethod
        def from_env(cls):
            return cls()

        def check_file(self, **kwargs):
            kwargs["on_created"]("tca-already-billed")
            raise TurnitinAPIError("processing failed")

    monkeypatch.setattr("services.turnitin_api.client.TurnitinCoreClient", CreatedThenBoom)
    refund = MagicMock()
    svc = TurnitinService(store=store)
    svc._run_tca_check(submission_id="sub2", user_id=7, cost=300, refund_fn=refund)
    refund.assert_not_called()
    row = store.get("sub2")
    assert row["external_id"] == "tca-already-billed"
    assert row["status"] == "failed"


def test_tca_check_persists_similarity(tmp_path, monkeypatch):
    store = _init_store(tmp_path, monkeypatch)
    upload_dir = tmp_path / "uploads" / "sub3"
    upload_dir.mkdir(parents=True)
    upload_file = upload_dir / "essay.docx"
    upload_file.write_bytes(b"doc")
    store.create(
        submission_id="sub3",
        user_id=7,
        filename="essay.docx",
        upload_path=str(upload_file),
    )

    class OkClient:
        @classmethod
        def from_env(cls):
            return cls()

        def check_file(self, **kwargs):
            kwargs["on_created"]("tca-ok")
            return {
                "external_id": "tca-ok",
                "similarity": 12,
                "similarity_display": "12%",
                "ai_score": None,
                "ai_score_display": None,
                "ai_unavailable": "no ai",
                "similarity_report_path": None,
                "provider": "turnitin",
            }

    monkeypatch.setattr("services.turnitin_api.client.TurnitinCoreClient", OkClient)
    refund = MagicMock()
    svc = TurnitinService(store=store)
    svc._run_tca_check(submission_id="sub3", user_id=7, cost=300, refund_fn=refund)
    refund.assert_not_called()
    row = store.get("sub3")
    assert row["status"] == "completed"
    assert row["similarity"] == 12
    api = svc.to_api_row(row)
    assert api["provider"] == "turnitin"
    assert api["aiUnavailable"]


def test_unauthorized_maps_to_error(monkeypatch):
    monkeypatch.setenv("TURNITIN_API_SECRET", "bad")
    session = MagicMock()
    session.request.return_value = _FakeResponse(401, {"message": "Unauthorized"})
    client = TurnitinCoreClient(session=session, poll_interval=0.01)
    with pytest.raises(TurnitinAPIError) as exc:
        client.get_submission("x")
    assert exc.value.status_code == 401
    session.request.assert_called_once()


def test_authorization_header_schemes(monkeypatch):
    from services.turnitin_api.config import authorization_header

    monkeypatch.setenv("TURNITIN_API_SECRET", "tca-secret")
    monkeypatch.delenv("TURNITIN_AUTH_SCHEME", raising=False)
    assert authorization_header() == "tca-secret"
    assert authorization_header("tca-secret", scheme="raw") == "tca-secret"
    assert authorization_header("tca-secret", scheme="bearer") == "Bearer tca-secret"
    assert authorization_header("tca-secret", scheme="token") == "Token tca-secret"


def test_retries_invalid_authorization_header_with_bearer(monkeypatch):
    monkeypatch.setenv("TURNITIN_API_SECRET", "tca-secret")
    monkeypatch.delenv("TURNITIN_API_KEY", raising=False)
    monkeypatch.delenv("TURNITIN_AUTH_SCHEME", raising=False)

    class SeqSession:
        def __init__(self) -> None:
            self.auth_headers: list[str | None] = []

        def request(self, method, url, headers=None, json=None, data=None, timeout=None):
            value = (headers or {}).get("Authorization")
            self.auth_headers.append(value)
            if value == "tca-secret":
                return _FakeResponse(403, {"message": "Invalid authorization header"})
            if value == "Bearer tca-secret":
                return _FakeResponse(200, {"id": "ok", "status": "COMPLETE"})
            return _FakeResponse(403, {"message": "Invalid authorization header"})

    session = SeqSession()
    client = TurnitinCoreClient(session=session, poll_interval=0.01)
    result = client.get_submission("x")
    assert result["id"] == "ok"
    assert session.auth_headers[0] == "tca-secret"
    assert session.auth_headers[1] == "Bearer tca-secret"
    assert client._auth_scheme == "bearer"

    result = client.get_submission("x")
    assert result["id"] == "ok"
    assert session.auth_headers[2] == "Bearer tca-secret"


def test_format_ai_display_hides_low_scores():
    assert format_ai_display(0) == "0%"
    assert format_ai_display(15) == "*%"
    assert format_ai_display(19.9) == "*%"
    assert format_ai_display(20) == "20%"
    assert format_ai_display(42) == "42%"
    assert format_ai_display(None, asterisk=True) == "*%"


class _AiSession(_FakeSession):
    def request(self, method, url, headers=None, json=None, data=None, timeout=None):
        path = url.split("/api/v1/", 1)[-1]
        method_u = method.upper()
        if method_u == "GET" and path.endswith("/ai-writing-report"):
            return _FakeResponse(
                200,
                {"status": "COMPLETE", "overall_match_percentage": 42},
            )
        if method_u == "POST" and path.endswith("/ai-writing-report/pdf"):
            return _FakeResponse(202, {"id": "ai-pdf-1"})
        if method_u == "GET" and path.endswith("/ai-writing-report/pdf/ai-pdf-1"):
            return _FakeResponse(
                200,
                payload=None,
                content=b"%PDF-1.4 ai-hl",
                headers={"Content-Type": "application/pdf"},
            )
        if method_u == "POST" and path.endswith("/viewer-url"):
            return _FakeResponse(200, {"viewer_url": "https://viewer.turnitin.com/launch/abc"})
        return super().request(method, url, headers=headers, json=json, data=data, timeout=timeout)


def test_check_file_fetches_ai_highlights_pdf(tmp_path, monkeypatch):
    monkeypatch.setenv("TURNITIN_API_SECRET", "tca-secret")
    monkeypatch.setenv("TURNITIN_API_BASE", "https://api.turnitin.com")
    upload = tmp_path / "essay.docx"
    upload.write_bytes(b"docx-bytes")
    reports = tmp_path / "reports"
    client = TurnitinCoreClient(
        session=_AiSession(),
        poll_interval=0.01,
        upload_timeout=2,
        similarity_timeout=2,
    )
    result = client.check_file(
        file_path=upload,
        filename="essay.docx",
        owner_id="user_7",
        report_dir=reports,
    )
    assert result["similarity"] == 17
    assert result["ai_score"] == 42
    assert result["ai_score_display"] == "42%"
    assert result["ai_highlights"] == 42
    pdf = reports / "ai_highlights_report.pdf"
    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF-1.4 ai")


def test_fetch_ai_highlights_opens_viewer_when_no_pdf(tmp_path, monkeypatch):
    monkeypatch.setenv("TURNITIN_API_SECRET", "tca-secret")
    monkeypatch.setenv("TURNITIN_API_BASE", "https://api.turnitin.com")

    class ViewerOnly(_FakeSession):
        def request(self, method, url, headers=None, json=None, data=None, timeout=None):
            path = url.split("/api/v1/", 1)[-1]
            if method.upper() == "GET" and path.endswith("/ai-writing-report"):
                return _FakeResponse(200, {"status": "COMPLETE", "overall_match_percentage": 15})
            if method.upper() == "POST" and path.endswith("/viewer-url"):
                return _FakeResponse(200, {"viewer_url": "https://viewer.example/hl"})
            return super().request(method, url, headers=headers, json=json, data=data, timeout=timeout)

    client = TurnitinCoreClient(
        session=ViewerOnly(),
        poll_interval=0.01,
        similarity_timeout=2,
    )
    result = client.fetch_ai_highlights(
        tca_submission_id="sub-uuid-1",
        owner_id="user_7",
        report_dir=tmp_path,
        include_viewer=True,
    )
    assert result["ai_highlights_display"] == "*%"
    assert result["viewer_url"] == "https://viewer.example/hl"


def test_tca_highlights_persists_pdf(tmp_path, monkeypatch):
    store = _init_store(tmp_path, monkeypatch)
    store.create(
        submission_id="sub-hl",
        user_id=7,
        filename="essay.docx",
        upload_path=str(tmp_path / "essay.docx"),
    )
    store.update("sub-hl", external_id="sub-uuid-1", meta_json='{"provider": "turnitin"}')

    class HlClient:
        @classmethod
        def from_env(cls):
            return cls()

        def fetch_ai_highlights(self, **kwargs):
            dest = tmp_path / "reports" / "sub-hl"
            dest.mkdir(parents=True, exist_ok=True)
            pdf = dest / "ai_highlights_report.pdf"
            pdf.write_bytes(b"%PDF-1.4 hl")
            return {
                "ai_score": 42,
                "ai_score_display": "42%",
                "ai_highlights": 42,
                "ai_highlights_display": "42%",
                "ai_highlights_report_path": str(pdf),
                "ai_report_path": str(pdf),
                "ai_unavailable": None,
                "viewer_url": "https://viewer.example/hl",
                "provider": "turnitin",
            }

    monkeypatch.setattr("services.turnitin_api.client.TurnitinCoreClient", HlClient)
    svc = TurnitinService(store=store)
    out = svc._run_tca_highlights(submission_id="sub-hl", user_id=7)
    assert out["success"] is True
    assert out["viewer_url"] == "https://viewer.example/hl"
    row = store.get("sub-hl")
    assert row["highlights_status"] == "completed"
    assert row["ai_highlights"] == 42
    api = svc.to_api_row(row)
    assert api["hasHighlightsReport"] is True

