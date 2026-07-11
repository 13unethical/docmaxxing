"""ZeroGPT Business API transport client."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


def _is_jwt_like(token: str) -> bool:
    """True when the token looks like a JWT (header.payload.signature)."""
    parts = (token or "").split(".")
    return len(parts) == 3 and all(parts)


def _is_developer_api(base_url: str) -> bool:
    return "zerogpt.org" in (base_url or "").lower()


def _is_developer_api_key(api_key: str) -> bool:
    """Developer keys from api.zerogpt.org start with zgpt_sk_."""
    return (api_key or "").startswith("zgpt_sk_")


def _developer_key_help() -> str:
    return (
        "Developer API (api.zerogpt.org) requires ZEROGPT_API_KEY like zgpt_sk_live_.... "
        "Your UUID key is for the business API — use ZEROGPT_BASE_URL=https://api.zerogpt.com "
        "with ZEROGPT_EMAIL and ZEROGPT_PASSWORD instead."
    )


class ZeroGPTError(RuntimeError):
    """Raised when ZeroGPT request cannot be completed."""


@dataclass(slots=True)
class ZeroGPTConfig:
    base_url: str
    api_key: str
    email: str
    password: str
    detect_path: str
    humanize_path: str
    paraphrase_path: str
    advanced_paraphrase_path: str
    text_field: str
    timeout_s: float = 60.0
    transform_timeout_s: float = 300.0

    @classmethod
    def from_env(cls) -> "ZeroGPTConfig":
        base_url = (os.environ.get("ZEROGPT_BASE_URL") or "https://api.zerogpt.com").strip().rstrip("/")
        api_key = (os.environ.get("ZEROGPT_API_KEY") or "").strip()
        email = (os.environ.get("ZEROGPT_EMAIL") or "").strip()
        password = (os.environ.get("ZEROGPT_PASSWORD") or "").strip()
        timeout_s = float(os.environ.get("ZEROGPT_TIMEOUT_S") or 60)
        transform_timeout_s = float(os.environ.get("ZEROGPT_TRANSFORM_TIMEOUT_S") or 300)
        developer_api = _is_developer_api(base_url)
        default_detect = (
            "/api/v1/developer/ai-detection" if developer_api else "/api/detect/detectText"
        )
        default_humanize = (
            "/api/v1/developer/humanize" if developer_api else "/api/transform/humanize"
        )
        default_paraphrase = (
            "/api/v1/developer/paraphrase"
            if developer_api
            else "/api/transform/rephrase"
        )
        default_advanced_paraphrase = (
            "/api/v1/developer/advanced-paraphrase"
            if developer_api
            else "/api/transform/paraphrase"
        )
        default_text_field = "text" if developer_api else "input_text"
        detect_path = (os.environ.get("ZEROGPT_DETECT_PATH") or default_detect).strip()
        humanize_path = (os.environ.get("ZEROGPT_HUMANIZE_PATH") or default_humanize).strip()
        paraphrase_path = (
            os.environ.get("ZEROGPT_PARAPHRASE_PATH") or default_paraphrase
        ).strip()
        advanced_paraphrase_path = (
            os.environ.get("ZEROGPT_ADVANCED_PARAPHRASE_PATH") or default_advanced_paraphrase
        ).strip()
        text_field = (os.environ.get("ZEROGPT_TEXT_FIELD") or default_text_field).strip() or "input_text"
        return cls(
            base_url=base_url,
            api_key=api_key,
            email=email,
            password=password,
            detect_path=detect_path,
            humanize_path=humanize_path,
            paraphrase_path=paraphrase_path,
            advanced_paraphrase_path=advanced_paraphrase_path,
            text_field=text_field,
            timeout_s=timeout_s,
            transform_timeout_s=transform_timeout_s,
        )


class ZeroGPTClient:
    """HTTP-only client for ZeroGPT Business API."""

    def __init__(self, config: ZeroGPTConfig | None = None) -> None:
        self.config = config or ZeroGPTConfig.from_env()
        self._jwt_token: str | None = None
        self._session = requests.Session()

    def _uses_api_key_bearer(self) -> bool:
        """Developer API accepts zgpt_sk_* keys. Business API needs login JWT."""
        return (
            _is_developer_api(self.config.base_url)
            and _is_developer_api_key(self.config.api_key)
        )

    def _validate_config(self) -> None:
        if not _is_developer_api(self.config.base_url):
            return
        if not self.config.api_key:
            raise ZeroGPTError(
                "ZEROGPT_API_KEY is required for api.zerogpt.org. "
                "Create one at https://api.zerogpt.org (format: zgpt_sk_...)."
            )
        if not _is_developer_api_key(self.config.api_key):
            raise ZeroGPTError(_developer_key_help())

    def _ensure_auth(self) -> None:
        self._validate_config()
        if self._uses_api_key_bearer():
            return
        if self._jwt_token:
            return
        if self.config.api_key and _is_jwt_like(self.config.api_key):
            self._jwt_token = self.config.api_key
            return
        self.login()

    def login(self) -> str:
        if self._uses_api_key_bearer():
            return self.config.api_key
        if self._jwt_token:
            return self._jwt_token
        if not self.config.email or not self.config.password:
            raise ZeroGPTError(
                "For api.zerogpt.com set ZEROGPT_EMAIL and ZEROGPT_PASSWORD. "
                + _developer_key_help()
            )

        url = f"{self.config.base_url}/api/auth/login"
        payload = {"email": self.config.email, "password": self.config.password}
        try:
            response = self._session.post(url, json=payload, timeout=self.config.timeout_s)
        except requests.RequestException as exc:
            raise ZeroGPTError(f"Login request failed: {exc}") from exc

        body = _parse_json(response)
        if not response.ok:
            raise ZeroGPTError(f"Login failed ({response.status_code}): {body}")

        token = str(((body.get("data") or {}).get("token") or "")).strip()
        if not token:
            raise ZeroGPTError(f"Login response does not contain data.token: {body}")

        self._jwt_token = token
        return token

    def refresh_token(self) -> str:
        self._jwt_token = None
        return self.login()

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        if not path.startswith("/"):
            path = f"/{path}"
        self._ensure_auth()
        effective_timeout = timeout_s if timeout_s is not None else self.config.timeout_s

        response = self._request_once(
            method,
            path,
            json_body=json_body,
            timeout_s=effective_timeout,
        )
        if response.status_code in {401, 403} and not self._uses_api_key_bearer():
            self.refresh_token()
            response = self._request_once(
                method,
                path,
                json_body=json_body,
                timeout_s=effective_timeout,
            )

        body = _parse_json(response)
        if response.ok:
            body = _ensure_api_success(body, path=path)
        else:
            raw_text = str(body.get("raw_text") or "")
            if "Not enough segments" in raw_text or "JWTError" in raw_text:
                raise ZeroGPTError(
                    "ZeroGPT rejected the auth token. Use ZEROGPT_BASE_URL=https://api.zerogpt.com "
                    "with ZEROGPT_EMAIL/ZEROGPT_PASSWORD."
                )
            err = body.get("error") if isinstance(body.get("error"), dict) else {}
            if err.get("code") == "invalid_api_key_format":
                raise ZeroGPTError(_developer_key_help())
            raise ZeroGPTError(
                f"ZeroGPT request failed ({response.status_code}) for {path}: {body}"
            )
        return body

    def detect(self, text: str) -> dict[str, Any]:
        return self.request(
            "POST",
            self.config.detect_path,
            json_body={self.config.text_field: text},
        )

    def humanize(self, text: str, *, tone: str | None = None) -> dict[str, Any]:
        if _is_developer_api(self.config.base_url):
            return self._transform_request(
                "POST",
                self.config.humanize_path,
                json_body={self.config.text_field: text},
            )
        body: dict[str, Any] = {"string": text, "skipRealtime": 1}
        if tone:
            body["tone"] = tone
        return self._transform_request("POST", self.config.humanize_path, json_body=body)

    def paraphrase(self, text: str, *, tone: str = "Academic") -> dict[str, Any]:
        if _is_developer_api(self.config.base_url):
            return self._transform_request(
                "POST",
                self.config.paraphrase_path,
                json_body={self.config.text_field: text, "tone": tone},
            )
        return self._transform_request(
            "POST",
            self.config.paraphrase_path,
            json_body={"string": text, "tone": tone, "skipRealtime": 1},
        )

    def advanced_paraphrase(self, text: str, *, tone: str = "Academic") -> dict[str, Any]:
        if _is_developer_api(self.config.base_url):
            return self._transform_request(
                "POST",
                self.config.advanced_paraphrase_path,
                json_body={self.config.text_field: text, "tone": tone},
            )
        return self._transform_request(
            "POST",
            self.config.advanced_paraphrase_path,
            json_body={"string": text, "tone": tone, "skipRealtime": 1},
        )

    def _transform_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        timeout_s = self.config.transform_timeout_s
        last_error: ZeroGPTError | None = None
        for attempt in range(2):
            try:
                return self.request(
                    method,
                    path,
                    json_body=json_body,
                    timeout_s=timeout_s,
                )
            except ZeroGPTError as exc:
                if "timed out" not in str(exc).lower() or attempt == 1:
                    raise
                last_error = exc
        if last_error:
            raise last_error
        raise ZeroGPTError(f"ZeroGPT transform request failed for {path}")

    def _business_api_key_header(self) -> dict[str, str]:
        """Business dashboard UUID keys are sent as ApiKey, not Bearer."""
        if _is_developer_api(self.config.base_url):
            return {}
        if self.config.api_key and not _is_jwt_like(self.config.api_key):
            return {"ApiKey": self.config.api_key}
        return {}

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        headers.update(self._business_api_key_header())
        if self._uses_api_key_bearer():
            headers["Authorization"] = f"Bearer {self.config.api_key}"
            return headers
        self._ensure_auth()
        token = self._jwt_token or ""
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request_once(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> requests.Response:
        url = f"{self.config.base_url}{path}"
        headers = self._auth_headers()
        effective_timeout = timeout_s if timeout_s is not None else self.config.timeout_s
        try:
            return self._session.request(
                method=method,
                url=url,
                headers=headers,
                json=json_body,
                timeout=effective_timeout,
            )
        except requests.Timeout as exc:
            raise ZeroGPTError(
                f"ZeroGPT request timed out after {effective_timeout:.0f}s for {path}. "
                "Try again, use a shorter text chunk, or increase ZEROGPT_TRANSFORM_TIMEOUT_S."
            ) from exc
        except requests.RequestException as exc:
            raise ZeroGPTError(f"Request failed for {path}: {exc}") from exc


def _ensure_api_success(body: dict[str, Any], *, path: str) -> dict[str, Any]:
    """Business API may return HTTP 200 with success=false in JSON."""
    if body.get("success") is False:
        message = str(body.get("message") or body.get("error") or "ZeroGPT request failed")
        code = body.get("code")
        if message == "Illegal Request":
            raise ZeroGPTError(
                "ZeroGPT rejected the request. Verify API credits, package includes Text Transformers, "
                "and your server IP is whitelisted in the ZeroGPT dashboard."
            )
        if "must contain at least 50 characters" in message.lower():
            raise ZeroGPTError(
                f"ZeroGPT request failed for {path}: {message}. "
                "Ensure the request uses the 'string' field (not input_text) for transform endpoints."
            )
        if code:
            raise ZeroGPTError(f"ZeroGPT request failed for {path} ({code}): {message}")
        raise ZeroGPTError(f"ZeroGPT request failed for {path}: {message}")
    return body


def _parse_json(response: requests.Response) -> dict[str, Any]:
    try:
        parsed = response.json()
    except ValueError:
        return {"raw_text": response.text}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}
