"""Turnitin Core API HTTP client.

Auth is a single API key in the Authorization header (the admin UI often
calls that key a Secret). Flow:

1. Accept EULA for the owner
2. POST /submissions
3. PUT /submissions/{id}/original
4. Wait until submission status is COMPLETE
5. PUT /submissions/{id}/similarity
6. Wait until similarity status is COMPLETE
7. POST + GET similarity PDF
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .config import (
    add_to_index,
    api_base,
    api_key,
    api_secret,
    api_token,
    authorization_header,
    integration_name,
    integration_version,
)

log = logging.getLogger(__name__)

_COMPLETE_STATUSES = frozenset({"COMPLETE", "COMPLETED", "SUCCESS"})
_ERROR_STATUSES = frozenset({"ERROR", "FAILED", "FAILURE"})
_MISSING_STATUSES = frozenset({404, 405, 501})
_AI_RESOURCE_PATHS = ("ai-writing-report", "ai-writing", "ai_writing")
_AI_ONLY_SCORE_PATHS = (
    "ai_match_percentage",
    "ai_writing_percentage",
    "ai_writing_feedback.overall_match_percentage",
    "ai_writing_feedback.result.percentage",
    "ai_writing.percentage",
    "submission_stats.ai_writing_feedback.result.percentage",
    "result.percentage",
)
_AI_RESOURCE_SCORE_PATHS = (
    "overall_match_percentage",
    "percentage",
    "score",
) + _AI_ONLY_SCORE_PATHS


class TurnitinAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ascii_filename(name: str) -> str:
    base = Path(name or "submission").name or "submission"
    cleaned = re.sub(r"[^\w.\- ]+", "_", base, flags=re.ASCII).strip(" ._")
    return cleaned or "submission"


def _is_complete(status: Any) -> bool:
    return str(status or "").strip().upper() in _COMPLETE_STATUSES


def _is_error(status: Any) -> bool:
    return str(status or "").strip().upper() in _ERROR_STATUSES


def _nested_get(data: Any, *paths: str) -> Any:
    if not isinstance(data, dict):
        return None
    for path in paths:
        cur: Any = data
        ok = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return None


def _as_percent(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"*", "*%", "asterisk"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _looks_asterisk(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    for key in ("display", "indicator", "ai_score_display", "result_state"):
        raw = str(data.get(key) or "").strip().lower()
        if raw in {"*", "*%", "asterisk"}:
            return True
    return False


def format_ai_display(percent: float | None, *, asterisk: bool = False) -> str | None:
    """Turnitin hides 1–19% behind *% to avoid false-positive over-reads."""
    if asterisk:
        return "*%"
    if percent is None:
        return None
    if 0 < percent < 20:
        return "*%"
    return f"{percent:g}%"


def _extract_ai_percent(
    data: dict[str, Any] | None,
    *,
    from_ai_resource: bool = False,
) -> tuple[float | None, bool]:
    if not data:
        return None, False
    asterisk = _looks_asterisk(data)
    paths = _AI_RESOURCE_SCORE_PATHS if from_ai_resource else _AI_ONLY_SCORE_PATHS
    percent = _as_percent(_nested_get(data, *paths))
    return percent, asterisk or (percent is not None and 0 < percent < 20)


class TurnitinCoreClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 60.0,
        poll_interval: float | None = None,
        upload_timeout: float | None = None,
        similarity_timeout: float | None = None,
    ) -> None:
        self.token = (token if token is not None else api_token()).strip()
        if not self.token:
            raise TurnitinAPIError("TURNITIN_API_KEY / TURNITIN_API_SECRET is not set.")
        self._alt_token = ""
        if token is None:
            key = api_key()
            secret = api_secret()
            if key and secret and key != secret:
                self._alt_token = key if self.token == secret else secret
        self._auth_scheme = (os.environ.get("TURNITIN_AUTH_SCHEME") or "raw").strip().lower() or "raw"
        self.base_url = (base_url or api_base()).rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.poll_interval = (
            poll_interval
            if poll_interval is not None
            else float(os.environ.get("TURNITIN_POLL_INTERVAL", "3") or 3)
        )
        self.upload_timeout = (
            upload_timeout
            if upload_timeout is not None
            else float(os.environ.get("TURNITIN_UPLOAD_TIMEOUT", "180") or 180)
        )
        self.similarity_timeout = (
            similarity_timeout
            if similarity_timeout is not None
            else float(os.environ.get("TURNITIN_SIMILARITY_TIMEOUT", "300") or 300)
        )

    @classmethod
    def from_env(cls, **kwargs: Any) -> TurnitinCoreClient:
        return cls(**kwargs)

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": authorization_header(self.token, scheme=self._auth_scheme),
            "X-Turnitin-Integration-Name": integration_name(),
            "X-Turnitin-Integration-Version": integration_version(),
        }
        if extra:
            headers.update(extra)
        return headers

    def _auth_fallbacks(self) -> list[tuple[str, str]]:
        seen: set[tuple[str, str]] = set()
        out: list[tuple[str, str]] = []
        for scheme in (self._auth_scheme, "raw", "bearer", "token"):
            for tok in (self.token, self._alt_token):
                if not tok:
                    continue
                item = (scheme, tok)
                if item in seen:
                    continue
                seen.add(item)
                out.append(item)
        return out

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected: tuple[int, ...] = (200, 201, 202),
        json_body: Any = None,
        data: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
        accept: str | None = None,
    ) -> requests.Response:
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        last_error: TurnitinAPIError | None = None
        for scheme, tok in self._auth_fallbacks():
            self._auth_scheme = scheme
            prev_token = self.token
            self.token = tok
            headers = self._headers(extra_headers)
            if accept:
                headers["Accept"] = accept
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    data=data,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                self.token = prev_token
                raise TurnitinAPIError(f"Turnitin API request failed: {exc}") from exc
            if response.status_code in expected:
                if last_error is not None:
                    log.info("Turnitin API accepted Authorization scheme=%s", scheme)
                return response
            detail = (response.text or "").strip().replace("\n", " ")[:400]
            last_error = TurnitinAPIError(
                f"Turnitin API {method} {path} returned {response.status_code}"
                + (f": {detail}" if detail else "."),
                status_code=response.status_code,
            )
            lowered = detail.lower()
            retryable = response.status_code in (401, 403) and (
                "invalid authorization header" in lowered
                or "malformed authorization" in lowered
            )
            if not retryable:
                raise last_error
            log.info("Turnitin API retrying Authorization after scheme=%s", scheme)
        assert last_error is not None
        raise last_error

    def _try_json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        try:
            return self._json(method, path, **kwargs)
        except TurnitinAPIError as exc:
            if exc.status_code in _MISSING_STATUSES:
                return None
            raise

    def _json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = self._request(method, path, **kwargs)
        if not response.content:
            return {}
        ctype = (response.headers.get("Content-Type") or "").lower()
        if "json" not in ctype and not response.content[:1] in (b"{", b"["):
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise TurnitinAPIError(f"Turnitin API returned non-JSON from {path}") from exc
        return payload if isinstance(payload, dict) else {}

    def features_enabled(self) -> dict[str, Any]:
        return self._json("GET", "features-enabled")

    def latest_eula_version(self) -> str | None:
        try:
            payload = self._json(
                "GET",
                "eula/latest?lang=en-US",
                extra_headers={"Accept": "application/json"},
            )
        except TurnitinAPIError as exc:
            log.warning("Turnitin EULA lookup skipped: %s", exc)
            return None
        version = str(payload.get("version") or "").strip()
        return version or None

    def accept_eula(self, *, person_id: str, version: str | None = None) -> str | None:
        eula_version = version or self.latest_eula_version()
        if not eula_version:
            return None
        try:
            self._json(
                "POST",
                f"eula/{eula_version}/accept",
                expected=(200, 201, 204),
                extra_headers={"Content-Type": "application/json"},
                json_body={
                    "user_id": person_id,
                    "accepted_timestamp": _now_iso(),
                    "language": "en-US",
                },
            )
        except TurnitinAPIError as exc:
            # Already accepted (or tenant does not require a second accept).
            if exc.status_code not in (409, 422):
                log.warning("Turnitin EULA accept failed: %s", exc)
        return eula_version

    def create_submission(
        self,
        *,
        owner_id: str,
        title: str,
        submitter_id: str | None = None,
        eula_version: str | None = None,
    ) -> str:
        submitter = submitter_id or owner_id
        body: dict[str, Any] = {
            "owner": owner_id,
            "title": title[:200] or "submission",
            "submitter": submitter,
            "owner_default_permission_set": "INSTRUCTOR",
            "submitter_default_permission_set": "INSTRUCTOR",
        }
        if eula_version:
            body["eula"] = {
                "accepted_timestamp": _now_iso(),
                "language": "en-US",
                "version": eula_version,
            }
        payload = self._json(
            "POST",
            "submissions",
            expected=(200, 201),
            extra_headers={"Content-Type": "application/json"},
            json_body=body,
        )
        submission_id = str(payload.get("id") or "").strip()
        if not submission_id:
            raise TurnitinAPIError("Turnitin create submission returned no id.")
        return submission_id

    def upload_original(self, submission_id: str, filename: str, data: bytes) -> None:
        safe = _ascii_filename(filename)
        self._request(
            "PUT",
            f"submissions/{submission_id}/original",
            expected=(200, 202),
            extra_headers={
                "Content-Type": "binary/octet-stream",
                "Content-Disposition": f'inline; filename="{safe}"',
            },
            data=data,
        )

    def get_submission(self, submission_id: str) -> dict[str, Any]:
        return self._json("GET", f"submissions/{submission_id}")

    def request_similarity(
        self,
        submission_id: str,
        *,
        exclude_bibliography: bool = False,
        exclude_quotes: bool = False,
    ) -> None:
        body = {
            "indexing_settings": {"add_to_index": add_to_index()},
            "generation_settings": {
                "search_repositories": [
                    "INTERNET",
                    "SUBMITTED_WORK",
                    "PUBLICATION",
                    "CROSSREF",
                    "CROSSREF_POSTED_CONTENT",
                ],
                "auto_exclude_self_matching_scope": "ALL",
                "priority": "HIGH",
            },
            "view_settings": {
                "exclude_quotes": bool(exclude_quotes),
                "exclude_bibliography": bool(exclude_bibliography),
            },
        }
        self._json(
            "PUT",
            f"submissions/{submission_id}/similarity",
            expected=(200, 202),
            extra_headers={"Content-Type": "application/json"},
            json_body=body,
        )

    def get_similarity(self, submission_id: str) -> dict[str, Any]:
        return self._json("GET", f"submissions/{submission_id}/similarity")

    def request_similarity_pdf(self, submission_id: str) -> str:
        payload = self._json(
            "POST",
            f"submissions/{submission_id}/similarity/pdf",
            expected=(200, 201, 202),
            extra_headers={"Content-Type": "application/json"},
            json_body={},
        )
        pdf_id = str(payload.get("id") or payload.get("pdf_id") or "").strip()
        if not pdf_id:
            raise TurnitinAPIError("Turnitin PDF request returned no id.")
        return pdf_id

    def wait_until(
        self,
        fetch: Callable[[], dict[str, Any]],
        *,
        timeout: float,
        label: str,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: dict[str, Any] = {}
        while True:
            last = fetch() or {}
            status = last.get("status")
            if _is_complete(status):
                return last
            if _is_error(status):
                message = (
                    last.get("error_code")
                    or last.get("error")
                    or last.get("message")
                    or f"{label} failed."
                )
                raise TurnitinAPIError(str(message))
            if time.monotonic() >= deadline:
                raise TurnitinAPIError(f"Timed out waiting for Turnitin {label}.")
            time.sleep(max(0.2, self.poll_interval))

    def wait_for_pdf(self, submission_id: str, pdf_id: str, *, timeout: float | None = None) -> bytes:
        return self._wait_for_pdf_bytes(
            f"submissions/{submission_id}/similarity/pdf/{pdf_id}",
            timeout=timeout,
            label="similarity PDF",
        )

    def _download_pdf_bytes(self, path: str) -> bytes | None:
        response = self._request(
            "GET",
            path,
            expected=(200, 202),
            accept="application/pdf",
        )
        ctype = (response.headers.get("Content-Type") or "").lower()
        if "pdf" in ctype or response.content[:5] == b"%PDF-":
            return response.content
        try:
            payload = response.json()
        except ValueError:
            return None
        if isinstance(payload, dict) and _is_error(payload.get("status")):
            raise TurnitinAPIError(
                str(payload.get("error") or payload.get("message") or "PDF generation failed.")
            )
        return None

    def _wait_for_pdf_bytes(
        self,
        path: str,
        *,
        timeout: float | None = None,
        label: str = "PDF",
    ) -> bytes:
        limit = timeout if timeout is not None else self.similarity_timeout
        deadline = time.monotonic() + limit
        while True:
            pdf = self._download_pdf_bytes(path)
            if pdf:
                return pdf
            if time.monotonic() >= deadline:
                raise TurnitinAPIError(f"Timed out waiting for Turnitin {label}.")
            time.sleep(max(0.2, self.poll_interval))

    def download_similarity_pdf(self, submission_id: str, pdf_id: str) -> bytes | None:
        return self._download_pdf_bytes(
            f"submissions/{submission_id}/similarity/pdf/{pdf_id}"
        )

    def create_viewer_url(self, submission_id: str, viewer_user_id: str) -> str | None:
        payload = self._try_json(
            "POST",
            f"submissions/{submission_id}/viewer-url",
            expected=(200, 201),
            extra_headers={"Content-Type": "application/json"},
            json_body={
                "viewer_user_id": viewer_user_id,
                "locale": "en-US",
                "viewer_default_permission_set": "INSTRUCTOR",
                "similarity": {"view_settings": {"save_changes": False}},
            },
        )
        if not payload:
            return None
        url = str(payload.get("viewer_url") or payload.get("url") or "").strip()
        return url or None

    def get_ai_writing(self, submission_id: str) -> dict[str, Any] | None:
        for resource in _AI_RESOURCE_PATHS:
            payload = self._try_json("GET", f"submissions/{submission_id}/{resource}")
            if payload is not None:
                payload["_resource"] = resource
                return payload
        return None

    def request_ai_writing(self, submission_id: str) -> str | None:
        for resource in _AI_RESOURCE_PATHS:
            payload = self._try_json(
                "PUT",
                f"submissions/{submission_id}/{resource}",
                expected=(200, 201, 202, 204),
                extra_headers={"Content-Type": "application/json"},
                json_body={},
            )
            if payload is not None:
                return resource
        return None

    def wait_for_ai_writing(self, submission_id: str) -> dict[str, Any] | None:
        current = self.get_ai_writing(submission_id)
        if current is None:
            self.request_ai_writing(submission_id)
            current = self.get_ai_writing(submission_id)
        if current is None:
            return None
        if _is_complete(current.get("status")) or _is_error(current.get("status")):
            return current
        percent, _ = _extract_ai_percent(current, from_ai_resource=True)
        if current.get("status") is None and percent is not None:
            return current

        def _fetch() -> dict[str, Any]:
            data = self.get_ai_writing(submission_id) or current
            if data.get("status") is None and _extract_ai_percent(data, from_ai_resource=True)[0] is not None:
                data = dict(data)
                data["status"] = "COMPLETE"
            return data

        try:
            return self.wait_until(
                _fetch,
                timeout=self.similarity_timeout,
                label="AI writing report",
            )
        except TurnitinAPIError as exc:
            log.warning("Turnitin AI writing wait skipped: %s", exc)
            return self.get_ai_writing(submission_id)

    def _request_pdf_id(self, submission_id: str, resource: str) -> str | None:
        payload = self._try_json(
            "POST",
            f"submissions/{submission_id}/{resource}/pdf",
            expected=(200, 201, 202),
            extra_headers={"Content-Type": "application/json"},
            json_body={},
        )
        if not payload:
            return None
        pdf_id = str(payload.get("id") or payload.get("pdf_id") or "").strip()
        return pdf_id or None

    def download_ai_writing_pdf(self, submission_id: str, report_dir: Path | None) -> str | None:
        resources = list(_AI_RESOURCE_PATHS)
        known = self.get_ai_writing(submission_id) or {}
        preferred = str(known.get("_resource") or "").strip()
        if preferred:
            resources = [preferred] + [r for r in resources if r != preferred]
        for resource in resources:
            pdf_id = self._request_pdf_id(submission_id, resource)
            if not pdf_id:
                continue
            try:
                pdf_bytes = self._wait_for_pdf_bytes(
                    f"submissions/{submission_id}/{resource}/pdf/{pdf_id}",
                    label="AI writing PDF",
                )
            except TurnitinAPIError as exc:
                log.warning("Turnitin AI PDF via %s failed: %s", resource, exc)
                continue
            if report_dir is None:
                return None
            dest_dir = Path(report_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / "ai_highlights_report.pdf"
            dest.write_bytes(pdf_bytes)
            return str(dest.resolve())
        return None

    def fetch_ai_highlights(
        self,
        *,
        tca_submission_id: str,
        owner_id: str,
        report_dir: str | Path | None = None,
        include_viewer: bool = True,
    ) -> dict[str, Any]:
        """Pull AI writing % + highlighted PDF (or a Cloud Viewer URL)."""
        dest = Path(report_dir) if report_dir is not None else None
        ai_payload = self.wait_for_ai_writing(tca_submission_id)
        percent, asterisk = _extract_ai_percent(ai_payload, from_ai_resource=True)
        unavailable = None
        if ai_payload and _is_error(ai_payload.get("status")):
            unavailable = str(
                ai_payload.get("error")
                or ai_payload.get("message")
                or "AI writing report is not available for this file."
            )
        pdf_path = None
        if not unavailable and (ai_payload or include_viewer):
            try:
                pdf_path = self.download_ai_writing_pdf(tca_submission_id, dest)
            except TurnitinAPIError as exc:
                log.warning("Turnitin AI highlights PDF skipped: %s", exc)
        viewer_url = None
        if include_viewer and not pdf_path:
            try:
                viewer_url = self.create_viewer_url(tca_submission_id, owner_id)
            except TurnitinAPIError as exc:
                log.warning("Turnitin viewer URL skipped: %s", exc)
        display = None if unavailable else format_ai_display(percent, asterisk=asterisk)
        return {
            "ai_score": None if unavailable else percent,
            "ai_score_display": display,
            "ai_highlights": None if unavailable else percent,
            "ai_highlights_display": display,
            "ai_highlights_report_path": pdf_path,
            "ai_report_path": pdf_path,
            "ai_unavailable": unavailable,
            "viewer_url": viewer_url,
            "provider": "turnitin",
        }

    def check_file(
        self,
        *,
        file_path: str | Path,
        filename: str | None = None,
        owner_id: str,
        exclude_bibliography: bool = False,
        exclude_quotes: bool = False,
        report_dir: str | Path | None = None,
        on_created: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        path = Path(file_path)
        if not path.is_file():
            raise TurnitinAPIError(f"Upload file not found: {path}")
        data = path.read_bytes()
        title = filename or path.name
        eula_version = self.accept_eula(person_id=owner_id)
        submission_id = self.create_submission(
            owner_id=owner_id,
            title=title,
            eula_version=eula_version,
        )
        if on_created is not None:
            on_created(submission_id)
        self.upload_original(submission_id, title, data)
        self.wait_until(
            lambda: self.get_submission(submission_id),
            timeout=self.upload_timeout,
            label="upload processing",
        )
        self.request_similarity(
            submission_id,
            exclude_bibliography=exclude_bibliography,
            exclude_quotes=exclude_quotes,
        )
        similarity = self.wait_until(
            lambda: self.get_similarity(submission_id),
            timeout=self.similarity_timeout,
            label="similarity report",
        )
        percent = _as_percent(
            _nested_get(
                similarity,
                "overall_match_percentage",
                "overallMatchPercentage",
                "similarity.overall_match_percentage",
            )
        )
        sim_ai_percent, sim_ai_asterisk = _extract_ai_percent(similarity)
        pdf_path: str | None = None
        try:
            pdf_id = self.request_similarity_pdf(submission_id)
            pdf_bytes = self.wait_for_pdf(submission_id, pdf_id)
            if report_dir is not None:
                dest_dir = Path(report_dir)
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / "similarity_report.pdf"
                dest.write_bytes(pdf_bytes)
                pdf_path = str(dest.resolve())
        except TurnitinAPIError as exc:
            log.warning("Turnitin similarity PDF skipped: %s", exc)

        ai: dict[str, Any] = {}
        try:
            ai = self.fetch_ai_highlights(
                tca_submission_id=submission_id,
                owner_id=owner_id,
                report_dir=report_dir,
                include_viewer=False,
            )
        except TurnitinAPIError as exc:
            log.warning("Turnitin AI writing skipped: %s", exc)

        ai_percent = ai.get("ai_score")
        if ai_percent is None:
            ai_percent = sim_ai_percent
        ai_display = ai.get("ai_score_display")
        if not ai_display:
            ai_display = format_ai_display(ai_percent, asterisk=sim_ai_asterisk)
        ai_pdf = ai.get("ai_highlights_report_path") or ai.get("ai_report_path")

        result: dict[str, Any] = {
            "external_id": submission_id,
            "similarity": percent,
            "similarity_display": None if percent is None else f"{percent:g}%",
            "ai_score": ai_percent,
            "ai_score_display": ai_display,
            "ai_highlights": ai.get("ai_highlights") if ai.get("ai_highlights") is not None else ai_percent,
            "ai_highlights_display": ai.get("ai_highlights_display") or ai_display,
            "ai_unavailable": ai.get("ai_unavailable"),
            "similarity_report_path": pdf_path,
            "ai_report_path": ai_pdf,
            "ai_highlights_report_path": ai_pdf,
            "viewer_url": ai.get("viewer_url"),
            "provider": "turnitin",
        }
        return result
