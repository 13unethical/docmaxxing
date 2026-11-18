"""Best-effort Telegram alerts with cooldown-based deduplication."""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from services.secret_redaction import describe_exception, redact

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
                redact((res.text or "")[:200]),
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram alert request failed: %s", describe_exception(exc))
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


def notify_stealthwriter_session_expiring(*, expires_at: datetime, hours_left: float) -> bool:
    cooldown = _env_int("TELEGRAM_SESSION_EXPIRY_COOLDOWN_SEC", 6 * 3600)
    local = expires_at.astimezone(ZoneInfo("Asia/Tashkent"))
    lines = [
        f"StealthWriter login expires in {max(1, round(hours_left))} h",
        f"Expires: {local:%Y-%m-%d %H:%M} Tashkent",
        f"Host: {_host_label()}",
        "Action: log in again (scripts/bootstrap_stealthwriter_login.py on the Mac), push the session, restart the service.",
    ]
    return send_telegram_alert(
        "\n".join(lines),
        key=f"stealthwriter_session_expiring:{expires_at.isoformat()}",
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


def notify_turnitin_slots_low(*, left: int) -> bool:
    """Alert when the shared Turnitin check pool drops below 3."""
    cooldown = _env_int("TELEGRAM_TURNITIN_SLOTS_ALERT_COOLDOWN_SEC", 1800)
    n = max(0, int(left))
    lines = [
        f"Turnitin pool low: {n} check{'s' if n != 1 else ''} left",
        f"Host: {_host_label()}",
        "Action: Admin → Settings → Turnitin pool → add checks and Save.",
    ]
    return send_telegram_alert(
        "\n".join(lines),
        key=f"turnitin_slots_low:{n}",
        cooldown_sec=cooldown,
    )


def notify_site_error(
    *,
    path: str | None = None,
    method: str | None = None,
    status_code: int | None = None,
    error: str | None = None,
    user_id: int | None = None,
) -> bool:
    """Alert when a user-facing request fails with a server error."""
    cooldown = _env_int("TELEGRAM_SITE_ERROR_ALERT_COOLDOWN_SEC", 300)
    safe_error = (error or "").strip().replace("\n", " ")
    if len(safe_error) > 240:
        safe_error = safe_error[:240] + "..."
    status = int(status_code or 500)
    lines = [
        f"Site error {status}",
        f"Host: {_host_label()}",
        f"Request: {(method or '?').upper()} {path or '/'}",
    ]
    if user_id is not None:
        lines.append(f"User id: {int(user_id)}")
    if safe_error:
        lines.append(f"Error: {safe_error}")
    key = f"site_error:{status}:{(path or '/')[:80]}"
    return send_telegram_alert("\n".join(lines), key=key, cooldown_sec=cooldown)

_HUMANIZE_FIX = {
    "FREE_ENGINE_UNAVAILABLE": (
        "Student model returned None (cold, UNCHANGED, or Modal down). "
        "Warm via /api/browser/humanizer/warm, check Modal GPU, retry once."
    ),
    "UNAVAILABLE": (
        "Paid humanize path got no student result. Same as cold/Modal — warm + check Modal logs."
    ),
    "HUMANIZE_FAILED": (
        "Unhandled exception in humanize. Check gunicorn / journalctl for the traceback."
    ),
    "TIMEOUT": "Request timed out waiting for the model. Check Modal latency and keep-warm.",
    "LOGIN_REQUIRED": "Legacy StealthWriter session — usually unused now; ignore unless browser jobs run.",
}


def notify_humanize_failure(
    *,
    code: str,
    message: str | None = None,
    user_id: int | None = None,
    guest: bool = False,
    free_run: bool = False,
    words: int | None = None,
    path: str | None = None,
    source: str | None = None,
) -> bool:
    """Alert when a user-facing humanize request fails (not rate limits / auth)."""
    cooldown = _env_int("TELEGRAM_HUMANIZE_ALERT_COOLDOWN_SEC", 180)
    err = (code or "UNKNOWN").strip().upper() or "UNKNOWN"
    safe_message = (message or "").strip().replace("\n", " ")
    if len(safe_message) > 240:
        safe_message = safe_message[:240] + "…"
    who = f"user:{int(user_id)}" if user_id is not None else ("guest" if guest else "unknown")
    lines = [
        f"Humanizer failed: {err}",
        f"Host: {_host_label()}",
        f"Who: {who}",
        f"Free run: {'yes' if free_run else 'no'}",
        f"Path: {path or '/'}",
    ]
    if source:
        lines.append(f"Source: {source}")
    if words is not None:
        lines.append(f"Words: {int(words)}")
    if safe_message:
        lines.append(f"Message: {safe_message}")
    fix = _HUMANIZE_FIX.get(err)
    if fix:
        lines.append(f"Fix: {fix}")
    key = f"humanize_failure:{err}:{who}"
    return send_telegram_alert("\n".join(lines), key=key, cooldown_sec=cooldown)

