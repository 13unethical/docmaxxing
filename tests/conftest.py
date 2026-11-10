"""Shared test helpers."""

from __future__ import annotations

import contextlib
import secrets

import flask
import pytest
from docx import Document
from flask.testing import FlaskClient
from werkzeug.datastructures import Headers

from formatter import FormatJob, format_document_full
from formatter.document_reconstruction import reconstruct_document_before_format
from formatter.heading_plan import ParagraphHeadingAssignment


def register_test_sign_in(sess) -> None:
    """A test that writes ``user_id`` into the session means "signed in": give it the
    server-side sign-in record a real login creates (cookies without one are refused)."""
    from services.economy import auth as economy_auth

    uid = sess.get(economy_auth.SESSION_KEY)
    if not uid or sess.get(economy_auth.AUTH_SID_KEY):
        return
    try:
        sess[economy_auth.AUTH_SID_KEY] = economy_auth.register_session(int(uid))
    except Exception:  # noqa: BLE001  (test without an initialised economy DB)
        pass


class SessionCsrfClient(FlaskClient):
    """Sends the session's CSRF token like the real pages do, so CSRF stays enforced in every test.

    tests/test_security_csrf_sessions_admin.py uses the plain FlaskClient to test the check itself.
    """

    @contextlib.contextmanager
    def session_transaction(self, *args, **kwargs):
        with super().session_transaction(*args, **kwargs) as sess:
            yield sess
            register_test_sign_in(sess)

    def open(self, *args, **kwargs):
        method = str(kwargs.get("method") or "GET").upper()
        if (
            method not in {"GET", "HEAD", "OPTIONS", "TRACE"}
            and args
            and isinstance(args[0], str)
            and getattr(self, "_cookies", None) is not None
        ):
            headers = Headers(kwargs.get("headers") or {})
            if "X-CSRF-Token" not in headers:
                tx_kwargs = {"base_url": kwargs["base_url"]} if "base_url" in kwargs else {}
                with self.session_transaction(**tx_kwargs) as sess:
                    token = sess.get("_csrf_token")
                    if not token:
                        token = sess["_csrf_token"] = secrets.token_urlsafe(32)
                headers["X-CSRF-Token"] = token
                kwargs["headers"] = headers
        return super().open(*args, **kwargs)


flask.Flask.test_client_class = SessionCsrfClient


@pytest.fixture(autouse=True)
def _legacy_pages_render(monkeypatch):
    """Page tests exercise the old templates; test_new_app_redirects turns this off."""
    monkeypatch.setenv("LEGACY_UI", "1")


@pytest.fixture(autouse=True)
def _guest_landing_pages(monkeypatch):
    monkeypatch.setenv("GUEST_LANDING_PAGES", "1")


@pytest.fixture(autouse=True)
def _fresh_guest_rate_limit():
    from services.free_humanize import guest_rate_limiter

    guest_rate_limiter.reset()
    yield
    guest_rate_limiter.reset()


def run_format_pipeline(
    doc: Document,
    job: FormatJob,
    *,
    document_type: str | None = None,
    required_sections: list[str] | None = None,
    paragraph_assignments: list[ParagraphHeadingAssignment] | None = None,
):
    """Reconstruct structure then format — matches production /api/format path.

    Tests force prefer_ai=False so heading detection stays deterministic.
    """
    if job.auto_headings or job.requirement_headings:
        recon = reconstruct_document_before_format(
            doc,
            document_type=document_type,
            required_sections=required_sections,
            prefer_ai=False,
        )
        paragraph_assignments = recon.assignments
    return format_document_full(doc, job, paragraph_assignments)
