"""Best-effort Telegram alerts with cooldown-based deduplication."""

from __future__ import annotations

import logging
import os
import socket
import threading
import time

import requests

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_LAST_SENT: dict[str, float] = {}

# Telegram rejects messages longer than this.
_TEXT_MAX_LEN = 4096


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except (TypeError, ValueError):
        return default


def _telegram_token() -> str:
    """Same bot as support chat / feedback (TELEGRAM_TOKEN or TELEGRAM_BOT_TOKEN)."""
    return _env("TELEGRAM_TOKEN") or _env("TELEGRAM_BOT_TOKEN")


def _telegram_chat_id() -> str:
    """Support chat by default; TELEGRAM_ALERT_CHAT_ID redirects alerts elsewhere."""
    return _env("TELEGRAM_ALERT_CHAT_ID") or _env("CHAT_ID") or _env("TELEGRAM_CHAT_ID")


def _alerts_enabled() -> bool:
    raw = _env("TELEGRAM_ALERTS_ENABLED").lower()
    if not raw:
        return True
    return raw in {"1", "true", "yes", "on"}


def _allow_send(key: str, cooldown_sec: int) -> bool:
    now = time.time()
    with _LOCK:
        last = _LAST_SENT.get(key, 0.0)
        if cooldown_sec > 0 and (now - last) < cooldown_sec:
            return False
        _LAST_SENT[key] = now
        return True


def send_telegram_alert(text: str, *, key: str, cooldown_sec: int) -> bool:
    """Send a deduplicated Telegram alert. Returns True when sent."""
    if not _alerts_enabled():
        return False
    token = _telegram_token()
    chat_id = _telegram_chat_id()
    if not token or not chat_id:
        logger.warning("telegram alerts not configured: %s", text.replace("\n", " | ")[:300])
        return False
    if not _allow_send(key, cooldown_sec):
        return False
    body = text if len(text) <= _TEXT_MAX_LEN else text[: _TEXT_MAX_LEN - 1] + "…"
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": body},
            timeout=8,
        )
        if not res.ok:
            logger.warning(
                "telegram alert failed status=%s body=%s",
                res.status_code,
                (res.text or "")[:200],
            )
            return False
        return True
    except Exception:  # noqa: BLE001
        logger.exception("telegram alert request failed")
        return False


def _host_label() -> str:
    env = _env("APP_ENV") or _env("FLASK_ENV") or "unknown-env"
    return f"{socket.gethostname()} ({env})"


def notify_stealthwriter_session_down(*, current_url: str | None, active_jobs: int) -> bool:
    cooldown = _env_int("TELEGRAM_SESSION_ALERT_COOLDOWN_SEC", 1800)
    lines = [
        "StealthWriter session is DOWN",
        f"Host: {_host_label()}",
        f"Active browser jobs: {int(active_jobs)}",
        f"Current URL: {current_url or 'unknown'}",
        "Action: bootstrap login on Mac, export, push session, restart service.",
    ]
    return send_telegram_alert(
        "\n".join(lines),
        key="stealthwriter_session_down",
        cooldown_sec=cooldown,
    )


def notify_stealthwriter_session_restored(*, current_url: str | None) -> bool:
    cooldown = _env_int("TELEGRAM_SESSION_RESTORED_COOLDOWN_SEC", 300)
    lines = [
        "StealthWriter session RESTORED",
        f"Host: {_host_label()}",
        f"Current URL: {current_url or 'unknown'}",
    ]
    return send_telegram_alert(
        "\n".join(lines),
        key="stealthwriter_session_restored",
        cooldown_sec=cooldown,
    )


def notify_browser_job_failure(
    *,
    provider: str,
    operation: str,
    code: str,
    error: str,
    job_id: str,
    attempts: int,
    max_attempts: int,
) -> bool:
    """Alert on critical browser-job failures with per-code cooldown."""
    cooldown = _env_int("TELEGRAM_BROWSER_ERROR_ALERT_COOLDOWN_SEC", 900)
    safe_error = (error or "").strip().replace("\n", " ")
    if len(safe_error) > 240:
        safe_error = safe_error[:240] + "..."
    lines = [
        "Browser pipeline critical failure",
        f"Host: {_host_label()}",
        f"Provider: {provider}",
        f"Operation: {operation}",
        f"Code: {code}",
        f"Job: {job_id}",
        f"Attempts: {attempts}/{max_attempts}",
        f"Error: {safe_error or '-'}",
    ]
    key = f"browser_failure:{provider}:{operation}:{code}"
    return send_telegram_alert("\n".join(lines), key=key, cooldown_sec=cooldown)

