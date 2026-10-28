#!/usr/bin/env python3
"""Long-running bulk Humanizer teacher collection (systemd: docmaxxing-humanizer-bulk).

Spends the training share of the StealthWriter account's daily limit, batch by batch,
and sleeps until the next StealthWriter reset when it is used up.

    python scripts/run_humanizer_bulk_collection.py --status
    python scripts/run_humanizer_bulk_collection.py --once      # one batch, then exit
    python scripts/run_humanizer_bulk_collection.py             # run forever

Requires HUMANIZER_TRAINING_BULK_DAILY_LIMIT (e.g. 350). Pause: touch data/humanizer_training/bulk/PAUSE.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.alerts.telegram_alerts import send_telegram_alert  # noqa: E402
from services.humanizer_training.bulk import (  # noqa: E402
    LOGIN_RECHECK,
    BulkConfig,
    reuse_production_session,
    run_cycle,
    status,
)
from services.humanizer_training.teacher.config import TeacherProviderConfig  # noqa: E402
from services.humanizer_training.teacher.provider import StealthWriterBridgeProvider  # noqa: E402

MAX_SLEEP_S = 300.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log(event: str, **fields) -> None:
    print(json.dumps({"ts": _now().isoformat(), "event": event, **fields}, ensure_ascii=False, default=str), flush=True)


def _alert(text: str, key: str, cooldown_s: int) -> None:
    send_telegram_alert(f"Humanizer training: {text}", key=f"humanizer-bulk:{key}", cooldown_sec=cooldown_s)


class ProviderHolder:
    """Keeps one training Chrome alive between batches; rebuilt after login changes."""

    def __init__(self, cfg: BulkConfig) -> None:
        self.cfg = cfg
        self.provider: StealthWriterBridgeProvider | None = None

    def get(self) -> StealthWriterBridgeProvider:
        if self.provider is None:
            self.provider = StealthWriterBridgeProvider(
                TeacherProviderConfig(
                    provider_name="stealthwriter",
                    model="Legacy 5.1",
                    level=8,
                    timeout_s=self.cfg.timeout_s,
                    max_retries=1,
                    extra={"explicit_model": True, "explicit_level": True, "explicit_timeout": True},
                )
            )
        return self.provider

    def stop(self) -> None:
        if self.provider is not None:
            try:
                self.provider.stop()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            self.provider = None


def run(cfg: BulkConfig, *, once: bool) -> int:
    holder = ProviderHolder(cfg)
    login_retry_used = False
    try:
        while True:
            try:
                result = run_cycle(cfg, provider=holder.get(), now=_now(), clock=_now)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                _log("error", error=str(exc))
                _alert(f"collector error: {exc}", "error", 3600)
                holder.stop()
                result = None
                wait = MAX_SLEEP_S
            else:
                _log(result.action, wait_s=round(result.wait_s), **result.detail)
                wait = result.wait_s
                if result.action == "batch_done":
                    login_retry_used = False
                elif result.action == "login_required":
                    holder.stop()
                    if cfg.reuse_production_session and not login_retry_used and reuse_production_session():
                        login_retry_used = True
                        _log("session_reused_from_production")
                        continue
                    _alert(
                        "StealthWriter session expired; log in again "
                        "(scripts/login_stealthwriter_training.py --headed-login, then push the session).",
                        "login",
                        3 * 3600,
                    )
                    wait = LOGIN_RECHECK.total_seconds()
                elif result.action == "limit_hit":
                    _alert(f"StealthWriter limit message: {result.detail}", "limit", 6 * 3600)
                elif result.action == "quota_done":
                    holder.stop()
                    st = status(cfg, _now())
                    _alert(
                        f"daily share used ({st['used_today']}/{st['training_limit']}), "
                        f"pool pending {st['pool_pending']}, next reset {st['next_reset']}",
                        f"done:{st['sw_day']}",
                        20 * 3600,
                    )
                elif result.action == "paused_quality":
                    holder.stop()
                    _alert(
                        "paused: StealthWriter output lost paragraph breaks "
                        f"(preservation {result.detail.get('paragraph_preservation')}). "
                        f"Check the extraction, then delete {cfg.root / 'PAUSE'}.",
                        "paragraphs",
                        6 * 3600,
                    )
                elif result.action == "pool_empty":
                    _alert("source pool is empty; run scripts/fill_humanizer_source_pool.py", "pool", 6 * 3600)
                elif result.action in ("disabled", "paused"):
                    holder.stop()
            if once:
                return 0
            if wait > 0:
                time.sleep(min(wait, MAX_SLEEP_S))
    finally:
        holder.stop()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--status", action="store_true", help="Print quota/pool status and exit")
    p.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    args = p.parse_args()

    cfg = BulkConfig.from_env()
    if args.status:
        print(json.dumps(status(cfg, _now()), indent=2, ensure_ascii=False))
        return 0
    if not cfg.enabled:
        print("HUMANIZER_TRAINING_BULK_DAILY_LIMIT is not set above the production reserve; nothing to do.")
        return 0

    cfg.root.mkdir(parents=True, exist_ok=True)
    lock = (cfg.root / "runner.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Another bulk collection runner is already active.")
        return 1
    _log("start", **cfg.safe_dict())
    return run(cfg, once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
