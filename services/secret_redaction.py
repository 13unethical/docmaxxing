"""Remove credentials from text that is about to be logged or returned as diagnostics.

Provider exceptions quote the request URL (``...?key=...``, ``/bot<token>/sendMessage``), and
error bodies or header reprs can carry API keys. ``redact`` strips known credential formats and
the literal values of configured secrets (environment variables whose names say KEY, TOKEN,
SECRET, PASSWORD, ...), so a new key format is still covered once it is configured.

``install_log_redaction`` applies the same filter to every log record of the process, including
formatted tracebacks; integrations still sanitize their own messages first.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

REDACTED = "<redacted>"

_SECRET_ENV_NAME = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PASS|CREDENTIAL|PRIVATE|AUTH|COOKIE|DSN|SIGNATURE)",
    re.IGNORECASE,
)
_MIN_SECRET_LEN = 8

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Telegram bot token in Bot API URLs and on its own.
    (re.compile(r"(/bot)[0-9]{3,}:[A-Za-z0-9_-]{10,}"), r"\1" + REDACTED),
    (re.compile(r"\b[0-9]{6,12}:[A-Za-z0-9_-]{30,}\b"), REDACTED),
    # Credentials in query strings / form bodies / key=value log text.
    (
        re.compile(
            r"(?i)(?<![A-Za-z0-9_-])((?:key|api[_-]?key|apikey|token|access[_-]?token|refresh[_-]?token|auth|"
            r"secret|client[_-]?secret|password|passwd|signature|sig|x-goog-api-key)=)[^&#\s'\"<>]+"
        ),
        r"\1" + REDACTED,
    ),
    # Header values in reprs and raw header text.
    (
        re.compile(
            r"(?i)((?:x-goog-api-key|x-api-key|api[_-]?key|authorization|proxy-authorization|cookie|"
            r"set-cookie|x-telegram-bot-api-secret-token)['\"]?\s*[:=]\s*['\"]?)"
            r"(?:(?:bearer|basic|token)\s+)?[^\s'\",;}]+"
        ),
        r"\1" + REDACTED,
    ),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + REDACTED),
    # Well-known key formats.
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), REDACTED),
    (re.compile(r"\bAQ\.[A-Za-z0-9_.-]{12,}"), REDACTED),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}"), REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), REDACTED),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), REDACTED),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), REDACTED),
]


def _configured_secrets() -> list[str]:
    values = set()
    for name, value in os.environ.items():
        if not value or not _SECRET_ENV_NAME.search(name):
            continue
        value = value.strip()
        if len(value) >= _MIN_SECRET_LEN:
            values.add(value)
    return sorted(values, key=len, reverse=True)


def redact(text: Any) -> str:
    """``text`` as a string with credentials replaced by ``<redacted>``."""
    if text is None:
        return ""
    value = text if isinstance(text, str) else str(text)
    if not value:
        return value
    for secret in _configured_secrets():
        if secret in value:
            value = value.replace(secret, REDACTED)
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def redact_data(data: Any) -> Any:
    """Copy of JSON-like ``data`` with every string redacted."""
    if isinstance(data, str):
        return redact(data)
    if isinstance(data, dict):
        return {key: redact_data(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [redact_data(value) for value in data]
    return data


def describe_exception(exc: BaseException | None, *, max_len: int = 500) -> str:
    """``Type: message`` for an exception and its causes, credentials removed.

    Safe for logs and admin diagnostics; never includes a traceback.
    """
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(parts) < 4:
        seen.add(id(current))
        message = redact(str(current)).strip()
        label = type(current).__name__
        parts.append(f"{label}: {message}" if message else label)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    text = " <- ".join(parts) if parts else "unknown error"
    return text[:max_len]


_TRACEBACK_FORMATTER = logging.Formatter()
_INSTALLED_FLAG = "_secret_redaction_installed"


def _scrub_record(record: logging.LogRecord) -> None:
    try:
        message = record.getMessage()
    except Exception:  # noqa: BLE001
        return
    clean = redact(message)
    if clean != message:
        record.msg = clean
        record.args = None
    if record.exc_info and not record.exc_text:
        try:
            record.exc_text = redact(_TRACEBACK_FORMATTER.formatException(record.exc_info))
        except Exception:  # noqa: BLE001
            pass
    if record.stack_info:
        record.stack_info = redact(record.stack_info)


def install_log_redaction() -> None:
    """Redact every log record created in this process (idempotent)."""
    current = logging.getLogRecordFactory()
    if getattr(current, _INSTALLED_FLAG, False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = current(*args, **kwargs)
        _scrub_record(record)
        return record

    setattr(factory, _INSTALLED_FLAG, True)
    logging.setLogRecordFactory(factory)
