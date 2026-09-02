"""PlagDetect REST client.

Auth headers (from plagdetect.org/user/api-docs):

    X-API-Key / X-API-Secret

Flow: POST /submit → poll GET /status/{id} → GET /download/{id}/{ai|plagiarism}.
Highlights are a separate POST /highlights/{id} (1 Turnitin slot).
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import requests

from services.turnitin_api.client import format_ai_display

from .config import api_base, api_key, api_secret

log = logging.getLogger(__name__)

_COMPLETE = frozenset({"complete", "completed", "success"})
_FAILED = frozenset({"failed", "failure", "error"})
_HIGHLIGHT_PERCENT_KEYS = (
    "highlight_percentage",
    "highlights_percentage",
    "ai_highlights_percentage",
    "highlighted_percentage",
    "ai_highlight_percentage",
    "highlight_score",
    "ai_highlights",
)
_PDF_PERCENT_RE = re.compile(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*%")


class PlagDetectAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def parse_percent(value: Any, *, mask_low: bool = True) -> tuple[float | None, bool]:
    """Return (percent, asterisk). ``*%`` and 1–19% are asterisk when ``mask_low``."""
    if value is None or isinstance(value, bool):
        return None, False
    if isinstance(value, str):
        text = value.strip().lower().replace(" ", "")
        if text in {"*", "*%", "asterisk"}:
            return None, True
        if text.endswith("%"):
            text = text[:-1]
        value = text
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, False
    if number < 0:
        return None, False
    if not mask_low:
        return number, False
    return number, 0 < number < 20


def format_plain_percent(percent: float | None) -> str | None:
    """Highlights scores are shown as a number, never Turnitin's ``*%`` mask."""
    if percent is None:
        return None
    if percent == int(percent):
        return f"{int(percent)}%"
    return f"{percent:g}%"


def highlights_percent_from_payloads(payloads: Iterable[dict[str, Any] | None]) -> float | None:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in _HIGHLIGHT_PERCENT_KEYS:
            if key not in payload:
                continue
            number, _ = parse_percent(payload.get(key), mask_low=False)
            if number is not None:
                return number
    return None


def highlights_percent_from_pdf(path: str | Path | None) -> float | None:
    """Best-effort number from an AI Highlights PDF. Many reports are image-only."""
    if not path:
        return None
    pdf_path = Path(path)
    if not pdf_path.is_file():
        return None
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:6])
    except Exception:  # noqa: BLE001
        return None
    if not text.strip():
        return None
    for pattern in (
        r"highlighted[^%\n]{0,48}?(\d{1,2}(?:\.\d+)?)\s*%",
        r"ai[\s-]*writing[^%\n]{0,48}?(\d{1,2}(?:\.\d+)?)\s*%",
        r"overall[^%\n]{0,48}?(\d{1,2}(?:\.\d+)?)\s*%",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    numbers = [float(item) for item in _PDF_PERCENT_RE.findall(text)]
    numbers = [item for item in numbers if 0 <= item < 100]
    return numbers[0] if numbers else None


def resolve_highlights_percent(
    hl_status: dict[str, Any] | None,
    status: dict[str, Any] | None,
    child_status: dict[str, Any] | None = None,
    *,
    pdf_path: str | Path | None = None,
    copy_unmasked_parent_ai: bool = True,
) -> float | None:
    """Pick the Highlights % without applying Turnitin's 1–19% ``*%`` mask."""
    hl_score = highlights_percent_from_payloads((hl_status, status, child_status))
    if hl_score is None and child_status:
        child_ai, _ = parse_percent(child_status.get("ai_percentage"), mask_low=False)
        if child_ai is not None:
            hl_score = child_ai
    if hl_score is None:
        hl_score = highlights_percent_from_pdf(pdf_path)
    if hl_score is None and copy_unmasked_parent_ai and status:
        ai_score, ai_star = parse_percent(status.get("ai_percentage"))
        if ai_score is not None and not ai_star:
            hl_score = ai_score
    return hl_score


class PlagDetectAPIClient:
    def __init__(
        self,
        *,
        api_key_value: str | None = None,
        api_secret_value: str | None = None,
        base_url: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 60.0,
        poll_interval: float | None = None,
        check_timeout: float | None = None,
        download_timeout: float | None = None,
    ) -> None:
        self.api_key = (api_key_value if api_key_value is not None else api_key()).strip()
        self.api_secret = (
            api_secret_value if api_secret_value is not None else api_secret()
        ).strip()
        if not self.api_key or not self.api_secret:
            raise PlagDetectAPIError(
                "PlagDetect API Key/Secret is not set. "
                "Use PLAGDETECT_API_KEY and PLAGDETECT_API_SECRET "
                "(or TURNITIN_API_KEY / TURNITIN_API_SECRET)."
            )
        self.base_url = (base_url or api_base()).rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.poll_interval = (
            poll_interval
            if poll_interval is not None
            else float(os.environ.get("PLAGDETECT_API_POLL_INTERVAL", "10") or 10)
        )
        self.check_timeout = (
            check_timeout
            if check_timeout is not None
            else float(os.environ.get("PLAGDETECT_CHECK_TIMEOUT", "540") or 540)
        )
        self.download_timeout = (
            download_timeout
            if download_timeout is not None
            else float(os.environ.get("PLAGDETECT_API_DOWNLOAD_TIMEOUT", "90") or 90)
        )

    @classmethod
    def from_env(cls, **kwargs: Any) -> PlagDetectAPIClient:
        return cls(**kwargs)

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "X-API-Secret": self.api_secret,
        }

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def _raise_http(self, method: str, path: str, response: requests.Response) -> None:
        detail = (response.text or "").strip().replace("\n", " ")[:400]
        message = f"PlagDetect API {method} {path} returned {response.status_code}"
        if detail:
            message = f"{message}: {detail}"
        if response.status_code == 401:
            message = (
                "PlagDetect rejected the API credentials (HTTP 401). "
                "Open plagdetect.org → API → API Keys and confirm the Key and "
                "Secret are active."
            )
        raise PlagDetectAPIError(message, status_code=response.status_code)

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected: tuple[int, ...] = (200, 201, 202),
        json_body: Any = None,
        data: dict[str, str] | None = None,
        files: Any = None,
        timeout: float | None = None,
        stream: bool = False,
    ) -> requests.Response:
        url = self._url(path)
        try:
            response = self.session.request(
                method,
                url,
                headers=self._headers(),
                json=json_body,
                data=data,
                files=files,
                timeout=timeout or self.timeout,
                stream=stream,
            )
        except requests.RequestException as exc:
            raise PlagDetectAPIError(f"PlagDetect API request failed: {exc}") from exc
        if response.status_code not in expected:
            self._raise_http(method, path, response)
        return response

    def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._request(method, path, **kwargs)
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise PlagDetectAPIError(f"PlagDetect API returned non-JSON from {path}") from exc
        return payload if isinstance(payload, dict) else {}

    def get_account(self) -> dict[str, Any]:
        return self._json("GET", "account")

    def submit(
        self,
        file_path: str | Path,
        filename: str,
        *,
        exclude_bibliography: bool = True,
        exclude_quotes: bool = True,
    ) -> dict[str, Any]:
        path = Path(file_path)
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with path.open("rb") as fh:
            payload = self._json(
                "POST",
                "submit",
                expected=(200, 201, 202),
                files={"file": (filename, fh, mime)},
                data={
                    "exclude_bibliography": "true" if exclude_bibliography else "false",
                    "exclude_quotes": "true" if exclude_quotes else "false",
                },
            )
        if payload.get("success") is False:
            raise PlagDetectAPIError(
                str(payload.get("message") or payload.get("error") or "Submit failed."),
                status_code=400,
            )
        return payload

    def get_status(self, submission_id: str) -> dict[str, Any]:
        return self._json("GET", f"status/{submission_id}")

    def wait_until_complete(self, submission_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.check_timeout
        last: dict[str, Any] = {}
        while True:
            last = self.get_status(submission_id)
            status = str(last.get("status") or "").strip().lower()
            if status in _COMPLETE:
                return last
            if status in _FAILED:
                raise PlagDetectAPIError(
                    str(last.get("message") or last.get("error") or "PlagDetect check failed.")
                )
            if time.monotonic() >= deadline:
                raise PlagDetectAPIError(
                    f"Timed out waiting for PlagDetect submission {submission_id}."
                )
            time.sleep(max(0.2, self.poll_interval))

    def download_report(self, submission_id: str, report_type: str, dest: Path) -> Path:
        response = self._request(
            "GET",
            f"download/{submission_id}/{report_type}",
            expected=(200,),
            timeout=self.download_timeout,
        )
        body = response.content or b""
        ctype = (response.headers.get("Content-Type") or "").lower()
        if body[:4] != b"%PDF" and "pdf" not in ctype:
            snippet = body[:200].decode("utf-8", errors="replace").replace("\n", " ")
            raise PlagDetectAPIError(
                f"PlagDetect download/{report_type} did not return a PDF"
                + (f": {snippet}" if snippet else ".")
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return dest

    def request_highlights(self, submission_id: str) -> dict[str, Any]:
        return self._json("POST", f"highlights/{submission_id}", expected=(200, 201, 202))

    def get_highlights_status(self, submission_id: str) -> dict[str, Any]:
        return self._json("GET", f"highlights/{submission_id}/status")

    def retry_highlights(self, submission_id: str) -> dict[str, Any]:
        return self._json(
            "POST",
            f"highlights/{submission_id}/retry",
            expected=(200, 201, 202),
        )

    def wait_for_highlights(self, submission_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.check_timeout
        last: dict[str, Any] = {}
        while True:
            last = self.get_highlights_status(submission_id)
            status = str(
                last.get("highlight_status") or last.get("status") or ""
            ).strip().lower()
            if status in _COMPLETE or last.get("file_available") is True:
                return last
            if status in _FAILED:
                raise PlagDetectAPIError(
                    str(last.get("message") or last.get("error") or "Highlight generation failed.")
                )
            if time.monotonic() >= deadline:
                raise PlagDetectAPIError(
                    f"Timed out waiting for PlagDetect highlights {submission_id}."
                )
            time.sleep(max(0.2, self.poll_interval))

    def check_file(
        self,
        *,
        file_path: str | Path,
        filename: str,
        exclude_bibliography: bool = True,
        exclude_quotes: bool = True,
        report_dir: str | Path,
        on_created: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        created = self.submit(
            file_path,
            filename,
            exclude_bibliography=exclude_bibliography,
            exclude_quotes=exclude_quotes,
        )
        external_id = str(
            created.get("submission_id") or created.get("id") or ""
        ).strip()
        if not external_id:
            raise PlagDetectAPIError("PlagDetect submit returned no submission_id.")
        if on_created:
            on_created(external_id)
        status = self.wait_until_complete(external_id)
        return self._persist_completed(
            external_id,
            status,
            report_dir=Path(report_dir),
            download_reports=True,
        )

    def fetch_reports(
        self,
        *,
        submission_id: str,
        report_dir: str | Path,
        fetch_similarity: bool = True,
        fetch_ai: bool = True,
        fetch_highlights: bool = False,
    ) -> dict[str, Any]:
        dest_dir = Path(report_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        out: dict[str, Any] = {"external_id": str(submission_id)}
        if fetch_similarity:
            path = self.download_report(
                submission_id, "plagiarism", dest_dir / "similarity_report.pdf"
            )
            out["similarity_report_path"] = str(path)
        if fetch_ai:
            try:
                path = self.download_report(
                    submission_id, "ai", dest_dir / "ai_report.pdf"
                )
                out["ai_report_path"] = str(path)
            except PlagDetectAPIError as exc:
                log.warning("PlagDetect AI PDF skipped: %s", exc)
                out["ai_unavailable"] = str(exc)
        if fetch_highlights:
            path = self.download_report(
                submission_id, "highlights", dest_dir / "ai_highlights_report.pdf"
            )
            out["ai_highlights_report_path"] = str(path)
        return out

    def fetch_highlights(
        self,
        *,
        submission_id: str,
        report_dir: str | Path,
        retry: bool = False,
    ) -> dict[str, Any]:
        if retry:
            self.retry_highlights(submission_id)
        else:
            queued = self.request_highlights(submission_id)
            if queued.get("success") is False:
                raise PlagDetectAPIError(
                    str(queued.get("message") or queued.get("error") or "Highlights request failed.")
                )
        hl_status = self.wait_for_highlights(submission_id)
        dest = Path(report_dir) / "ai_highlights_report.pdf"
        self.download_report(submission_id, "highlights", dest)
        status = self.get_status(submission_id)
        child_status = self._highlight_child_status(hl_status, status, submission_id)
        ai_score, ai_star = parse_percent(status.get("ai_percentage"))
        hl_score = resolve_highlights_percent(
            hl_status,
            status,
            child_status,
            pdf_path=dest,
        )
        return {
            "external_id": str(submission_id),
            "ai_score": ai_score,
            "ai_score_display": format_ai_display(ai_score, asterisk=ai_star),
            "ai_highlights": hl_score,
            "ai_highlights_display": format_plain_percent(hl_score),
            "ai_highlights_report_path": str(dest),
            "ai_report_path": str(dest),
            "provider": "plagdetect",
        }

    def lookup_highlights_percent(
        self,
        submission_id: str,
        *,
        pdf_path: str | Path | None = None,
    ) -> float | None:
        """Read Highlights % from existing API status. Does not request a new report."""
        hl_status = self.get_highlights_status(submission_id)
        status = self.get_status(submission_id)
        child_status = self._highlight_child_status(hl_status, status, submission_id)
        return resolve_highlights_percent(
            hl_status,
            status,
            child_status,
            pdf_path=pdf_path,
            copy_unmasked_parent_ai=False,
        )

    def _highlight_child_status(
        self,
        hl_status: dict[str, Any],
        status: dict[str, Any],
        submission_id: str,
    ) -> dict[str, Any] | None:
        child_id = str(
            hl_status.get("highlight_submission_id")
            or status.get("highlight_submission_id")
            or ""
        ).strip()
        if not child_id or child_id == str(submission_id):
            return None
        try:
            return self.get_status(child_id)
        except PlagDetectAPIError as exc:
            log.info("PlagDetect highlight child status skipped: %s", exc)
            return None

    def _persist_completed(
        self,
        external_id: str,
        status: dict[str, Any],
        *,
        report_dir: Path,
        download_reports: bool,
    ) -> dict[str, Any]:
        similarity, _ = parse_percent(
            status.get("plagiarism_percentage") or status.get("similarity")
        )
        ai_score, ai_star = parse_percent(status.get("ai_percentage"))
        ai_display = format_ai_display(ai_score, asterisk=ai_star)
        word_count = status.get("word_count")
        result: dict[str, Any] = {
            "external_id": external_id,
            "similarity": similarity,
            "similarity_display": None if similarity is None else f"{similarity:g}%",
            "ai_score": ai_score,
            "ai_score_display": ai_display,
            "ai_highlights": None,
            "ai_highlights_display": None,
            "ai_unavailable": None,
            "similarity_report_path": None,
            "ai_report_path": None,
            "word_count": word_count,
            "sandbox": bool(status.get("sandbox")),
            "provider": "plagdetect",
        }
        if download_reports:
            try:
                path = self.download_report(
                    external_id, "plagiarism", report_dir / "similarity_report.pdf"
                )
                result["similarity_report_path"] = str(path)
            except PlagDetectAPIError as exc:
                log.warning("PlagDetect similarity PDF skipped: %s", exc)
            ai_ok = ai_score is not None or ai_star
            if ai_ok:
                try:
                    path = self.download_report(
                        external_id, "ai", report_dir / "ai_report.pdf"
                    )
                    result["ai_report_path"] = str(path)
                except PlagDetectAPIError as exc:
                    log.warning("PlagDetect AI PDF skipped: %s", exc)
                    result["ai_unavailable"] = str(exc)
            elif word_count is not None:
                try:
                    count = int(word_count)
                except (TypeError, ValueError):
                    count = None
                if count is not None and not (300 <= count <= 30_000):
                    result["ai_unavailable"] = (
                        "AI reports work on documents between 300 and 30,000 words."
                    )
        return result
