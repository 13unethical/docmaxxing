"""Telegram getUpdates poller for support replies (webhook alternative).

Hostinger / some VPS firewalls accept browser traffic but drop or time out
inbound connections from Telegram datacenters, so webhooks never arrive.
Long-polling ``getUpdates`` from the VPS outbound path is reliable.

Only one process should run the poller (fcntl lock). Enable with
``TELEGRAM_POLLING=1`` (and delete the bot webhook).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import requests

from services.secret_redaction import describe_exception, redact

logger = logging.getLogger(__name__)

_LOCK_PATH = "/tmp/docmaxxing-telegram-poller.lock"
_STARTED = False
_STARTED_LOCK = threading.Lock()


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _telegram_token() -> str:
    return (os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def _delete_webhook(token: str) -> None:
    try:
        res = requests.get(
            f"https://api.telegram.org/bot{token}/deleteWebhook",
            params={"drop_pending_updates": "false"},
            timeout=20,
        )
        data = res.json() if res.content else {}
        logger.info("telegram poller: deleteWebhook -> %s", redact(data))
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram poller: deleteWebhook failed: %s", describe_exception(exc))


def _process_update(update: dict[str, Any]) -> None:
    from services.economy.support_chat import process_admin_update

    process_admin_update(update, source="poller")


def _poll_loop(token: str) -> None:
    offset = 0
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    logger.info("telegram poller: started getUpdates loop")
    while True:
        try:
            res = requests.get(
                url,
                params={
                    "timeout": 50,
                    "offset": offset,
                    "allowed_updates": '["message"]',
                },
                timeout=60,
            )
            data = res.json() if res.content else {}
            if not data.get("ok"):
                desc = redact(str(data.get("description") or res.text[:200]))
                # Webhook still set → conflict; keep retrying after deleteWebhook.
                logger.warning("telegram poller: getUpdates not ok: %s", desc)
                if "webhook" in desc.lower():
                    _delete_webhook(token)
                time.sleep(3)
                continue
            for update in data.get("result") or []:
                if not isinstance(update, dict):
                    continue
                try:
                    _process_update(update)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "telegram poller: failed update_id=%s: %s",
                        update.get("update_id"),
                        describe_exception(exc),
                    )
                uid = update.get("update_id")
                if isinstance(uid, int) and not isinstance(uid, bool):
                    offset = max(offset, uid + 1)
        except requests.Timeout:
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram poller: loop error: %s", describe_exception(exc))
            time.sleep(5)


def try_start_telegram_poller() -> bool:
    """Start background getUpdates poller once per host if enabled."""
    global _STARTED
    if not _env_truthy("TELEGRAM_POLLING"):
        return False
    token = _telegram_token()
    if not token:
        logger.warning("telegram poller: TELEGRAM_POLLING set but token missing")
        return False

    with _STARTED_LOCK:
        if _STARTED:
            return False
        _STARTED = True

    # Only one gunicorn worker should poll.
    try:
        import fcntl
    except ImportError:
        fcntl = None  # type: ignore[assignment]

    lock_fh = open(_LOCK_PATH, "a+", encoding="utf-8")
    if fcntl is not None:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.info("telegram poller: another process holds the lock — skip")
            lock_fh.close()
            return False

    # Keep lock_fh open for process lifetime.
    lock_fh.write(str(os.getpid()))
    lock_fh.flush()

    _delete_webhook(token)
    thread = threading.Thread(
        target=_poll_loop,
        args=(token,),
        name="telegram-support-poller",
        daemon=True,
    )
    thread.start()
    logger.info("telegram poller: thread launched pid=%s", os.getpid())
    return True
