"""Provider abstraction for offline teacher rewriting."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests

from services.humanizer_training.teacher.config import TeacherProviderConfig, TeacherResult


class TeacherProviderError(RuntimeError):
    """Structured training provider failure with diagnostic meta."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        meta: dict[str, Any] | None = None,
        retryable: bool = True,
    ) -> None:
        self.code = code
        self.message = message or code
        self.meta = dict(meta or {})
        self.retryable = bool(retryable)
        super().__init__(f"StealthWriter teacher error: {self.code} — {self.message}")


class TeacherProvider(Protocol):
    def rewrite(self, source_text: str, **kwargs: Any) -> TeacherResult:
        ...


class MockTeacherProvider:
    """Deterministic local provider for explicit tests/fixtures only.

    Never used as the runtime default for real or synthetic collection.
    """

    def __init__(self, config: TeacherProviderConfig) -> None:
        self._config = config

    def rewrite(self, source_text: str, **kwargs: Any) -> TeacherResult:
        text = (source_text or "").strip()
        meta = {"provider_name": self._config.provider_name, "model": self._config.model, "level": self._config.level}
        if not text:
            return TeacherResult(text="", provider=self._config.provider_name, version=self._config.model, meta=meta)
        out = text.replace("should", "ought to").replace("can", "may")
        if out and out[-1] not in ".!?":
            out += "."
        return TeacherResult(
            text=out,
            provider=self._config.provider_name,
            version=self._config.model,
            meta=meta,
        )


class HttpJsonTeacherProvider:
    """External adapter (isolated from production browser worker/routes)."""

    def __init__(self, config: TeacherProviderConfig) -> None:
        if not config.endpoint:
            raise ValueError("HTTP provider requires endpoint")
        self._config = config

    def rewrite(self, source_text: str, **kwargs: Any) -> TeacherResult:
        payload = {
            "text": source_text,
            "model": self._config.model,
            "level": self._config.level,
        }
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        started = time.monotonic()
        response = requests.post(
            self._config.endpoint,
            json=payload,
            headers=headers,
            timeout=float(self._config.timeout_s),
        )
        if not response.ok:
            raise RuntimeError(f"teacher provider HTTP {response.status_code}")
        data = response.json() if response.content else {}
        out = str(data.get("output") or data.get("teacher_output") or data.get("text") or "").strip()
        if not out:
            raise RuntimeError("teacher provider returned empty output")
        _ = started  # reserved for later metrics
        meta = {
            "provider_name": self._config.provider_name,
            "model": self._config.model,
            "level": self._config.level,
            "endpoint": self._config.endpoint,
        }
        return TeacherResult(
            text=out,
            provider=self._config.provider_name,
            version=self._config.model,
            meta=meta,
        )


def _parse_level(raw: int | str | None, fallback: int = 8) -> int:
    """Coerce a level value to int, falling back for non-numeric strings."""
    if raw is None or raw == "":
        return fallback
    if isinstance(raw, int):
        return raw
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def _resolve_stealthwriter_model(config: TeacherProviderConfig) -> str:
    """Use training-safe default unless the user explicitly overrode model."""
    from services.humanizer_training.teacher.config import DEFAULT_MODEL

    explicit = bool((config.extra or {}).get("explicit_model"))
    raw = (config.model or "").strip() if isinstance(config.model, str) else ""
    if explicit and raw:
        return raw
    # Reject accidental legacy mock defaults if they still appear in old configs.
    if raw and raw.lower() not in {"mock-v1", "mock", "default"}:
        return raw
    return DEFAULT_MODEL


def _resolve_stealthwriter_timeout(config: TeacherProviderConfig) -> float:
    """Use a longer browser timeout unless explicitly overridden."""
    from services.humanizer_training.teacher.config import DEFAULT_TIMEOUT_S

    explicit = bool((config.extra or {}).get("explicit_timeout"))
    if explicit and config.timeout_s is not None:
        return float(config.timeout_s)
    if config.timeout_s is None:
        return DEFAULT_TIMEOUT_S
    current = float(config.timeout_s)
    # Legacy short CLI default from the retired paragraph collector.
    if current == 45.0:
        return DEFAULT_TIMEOUT_S
    return current


class StealthWriterBridgeProvider:
    """Bridges TeacherProvider protocol to StealthWriterTeacherProvider.

    Isolated from production: uses its own Chrome, profile, and session.
    Import is deferred so the module can be imported without playwright installed.
    """

    def __init__(self, config: TeacherProviderConfig) -> None:
        self._config = config
        # Deferred import — avoids pulling in browser deps when not needed.
        from services.humanizer_training.teacher.stealthwriter_provider import (
            StealthWriterTeacherProvider,
            TrainingBrowserConfig,
        )
        training_cfg = TrainingBrowserConfig(
            model=_resolve_stealthwriter_model(config),
            level=_parse_level(config.level),
            timeout_s=_resolve_stealthwriter_timeout(config),
            max_retries=int(config.max_retries) if config.max_retries else 3,
        )
        self._sw = StealthWriterTeacherProvider(training_cfg)
        self._started = False

    def _ensure_started(self) -> None:
        if not self._started:
            self._sw.start()
            self._started = True

    def rewrite(self, source_text: str, **kwargs: Any) -> TeacherResult:
        self._ensure_started()
        document_id = kwargs.get("document_id")
        result = self._sw.rewrite(source_text, document_id=document_id if isinstance(document_id, str) else None)
        if result.success:
            # Use actual runtime config from TrainingBrowserConfig, not CLI defaults
            actual_cfg = self._sw._cfg
            meta = {
                "provider_name": "stealthwriter_training",
                "model": actual_cfg.model,
                "level": actual_cfg.level,
                "timeout_s": actual_cfg.timeout_s,
                "max_retries": actual_cfg.max_retries,
            }
            # Propagate DOM-verified selection fields when present.
            if result.meta:
                meta.update(result.meta)
            return TeacherResult(
                text=result.humanized_text or "",
                provider=result.provider,
                version=result.model,
                meta=meta,
            )
        from services.humanizer_training.teacher.stealthwriter_provider import NON_RETRYABLE_ERRORS

        meta = dict(result.meta or {})
        meta.setdefault("error_code", result.error)
        meta.setdefault("error_message", result.error_detail or result.error)
        meta.setdefault("retryable", (result.error or "") not in NON_RETRYABLE_ERRORS)
        raise TeacherProviderError(
            result.error or "UNKNOWN",
            result.error_detail,
            meta=meta,
            retryable=bool(meta.get("retryable", True)),
        )

    def stop(self) -> None:
        if self._started:
            self._sw.stop()
            self._started = False


@dataclass(slots=True)
class ProviderFactory:
    config: TeacherProviderConfig

    def build(self) -> TeacherProvider:
        name = (self.config.provider_name or "").strip().lower()
        if not name:
            raise ValueError(
                "teacher provider_name is required "
                "(use 'stealthwriter' for real collection, or 'mock_teacher' in tests only)"
            )
        if name == "mock_teacher":
            # Explicit mock only — never an accidental default.
            return MockTeacherProvider(self.config)
        if name == "http_json":
            return HttpJsonTeacherProvider(self.config)
        if name in {"stealthwriter", "stealthwriter_training"}:
            return StealthWriterBridgeProvider(self.config)
        raise ValueError(f"Unsupported teacher provider: {self.config.provider_name}")

