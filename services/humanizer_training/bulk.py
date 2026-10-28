"""Bulk teacher collection on a paid StealthWriter plan.

The StealthWriter account is shared with the production humanizer, so training only
spends ``daily_limit - production_reserve`` humanizations per StealthWriter day and
stops at once when StealthWriter shows its limit message. Every provider call is
counted, including failed ones, so the estimate errs on the side of production.

Disabled unless ``HUMANIZER_TRAINING_BULK_DAILY_LIMIT`` is set above zero.
Pause without stopping the service: create ``<root>/PAUSE``.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from services.humanizer_training.teacher.config import TeacherResult
from services.humanizer_training.teacher.documents.source_pool import DEFAULT_POOL_ROOT, SourcePool
from services.humanizer_training.teacher.provider import TeacherProvider, TeacherProviderError

DEFAULT_BULK_ROOT = Path("data/humanizer_training/bulk")
DEFAULT_LEVEL_WEIGHTS = "4:1,6:2,8:3,10:3"
PRODUCTION_SESSION_FILE = Path("browser_profiles/sessions/stealthwriter.json")
TRAINING_SESSION_FILE = Path("browser_profiles/training_sessions/stealthwriter.json")
# After a limit message, look again this much later in case it was not the daily cap.
LIMIT_RECHECK = timedelta(hours=1)
LOGIN_RECHECK = timedelta(minutes=30)
IDLE_WAIT = timedelta(minutes=10)
MIN_PARAGRAPH_PRESERVATION = 0.6


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def parse_level_weights(raw: str) -> dict[int, float]:
    """``"4:1,8:3"`` -> ``{4: 1.0, 8: 3.0}``; levels outside 1–10 are rejected."""
    out: dict[int, float] = {}
    for part in (raw or "").split(","):
        if not part.strip():
            continue
        level, _, weight = part.partition(":")
        lvl = int(level)
        if not 1 <= lvl <= 10:
            raise ValueError(f"StealthWriter level must be 1-10, got {lvl}")
        out[lvl] = float(weight or 1)
    if not out:
        raise ValueError("no levels configured")
    return out


@dataclass(slots=True)
class BulkConfig:
    daily_limit: int = 0
    production_reserve: int = 60
    batch_size: int = 10
    level_weights: dict[int, float] = field(default_factory=lambda: parse_level_weights(DEFAULT_LEVEL_WEIGHTS))
    reset_utc_hour: int = 0
    # In the last N minutes before the reset, training may spend the unused production
    # reserve too; StealthWriter's own limit message stops it if users spent it.
    reserve_release_minutes: int = 60
    reuse_production_session: bool = True
    timeout_s: float = 300.0
    root: Path = DEFAULT_BULK_ROOT
    pool_root: Path = DEFAULT_POOL_ROOT

    @classmethod
    def from_env(cls) -> "BulkConfig":
        return cls(
            daily_limit=max(0, _env_int("HUMANIZER_TRAINING_BULK_DAILY_LIMIT", 0)),
            production_reserve=max(0, _env_int("HUMANIZER_TRAINING_BULK_PRODUCTION_RESERVE", 60)),
            batch_size=max(1, _env_int("HUMANIZER_TRAINING_BULK_BATCH", 10)),
            level_weights=parse_level_weights(
                os.environ.get("HUMANIZER_TRAINING_BULK_LEVELS") or DEFAULT_LEVEL_WEIGHTS
            ),
            reset_utc_hour=_env_int("HUMANIZER_TRAINING_BULK_RESET_UTC_HOUR", 0) % 24,
            reserve_release_minutes=max(0, _env_int("HUMANIZER_TRAINING_BULK_RESERVE_RELEASE_MIN", 60)),
            reuse_production_session=(os.environ.get("HUMANIZER_TRAINING_BULK_REUSE_SESSION", "1").strip() != "0"),
        )

    @property
    def training_limit(self) -> int:
        return max(0, self.daily_limit - self.production_reserve)

    @property
    def enabled(self) -> bool:
        return self.training_limit > 0

    def release_starts(self, now: datetime) -> datetime:
        return next_reset(now, self.reset_utc_hour) - timedelta(minutes=self.reserve_release_minutes)

    def limit_at(self, now: datetime) -> int:
        """Training share now: the whole daily limit inside the release window."""
        if self.reserve_release_minutes > 0 and now >= self.release_starts(now):
            return self.daily_limit
        return self.training_limit

    def safe_dict(self) -> dict[str, Any]:
        return {
            "daily_limit": self.daily_limit,
            "production_reserve": self.production_reserve,
            "training_limit": self.training_limit,
            "reserve_release_minutes": self.reserve_release_minutes,
            "batch_size": self.batch_size,
            "level_weights": {str(k): v for k, v in self.level_weights.items()},
            "reset_utc_hour": self.reset_utc_hour,
        }


def sw_day(now: datetime, reset_utc_hour: int = 0) -> str:
    """StealthWriter quota day label: the UTC date of the last reset."""
    utc = now.astimezone(timezone.utc)
    return (utc - timedelta(hours=reset_utc_hour)).date().isoformat()


def next_reset(now: datetime, reset_utc_hour: int = 0) -> datetime:
    utc = now.astimezone(timezone.utc)
    candidate = utc.replace(hour=reset_utc_hour, minute=0, second=0, microsecond=0)
    return candidate if candidate > utc else candidate + timedelta(days=1)


class QuotaLedger:
    """Training humanizations spent on one StealthWriter day (single runner process)."""

    def __init__(self, root: Path, day: str) -> None:
        self.path = Path(root) / "ledger" / f"{day}.json"
        self.day = day

    def read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"day": self.day, "used": 0, "limit_hit_at": None, "limit_message": None}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def used(self) -> int:
        return int(self.read().get("used") or 0)

    def take(self, limit: int) -> bool:
        data = self.read()
        if int(data.get("used") or 0) >= limit:
            return False
        data["used"] = int(data.get("used") or 0) + 1
        self._write(data)
        return True

    def mark_limit_hit(self, message: str, now: datetime) -> None:
        data = self.read()
        data["limit_hit_at"] = now.astimezone(timezone.utc).isoformat()
        data["limit_message"] = (message or "")[:240]
        self._write(data)

    def limit_hit_at(self) -> datetime | None:
        raw = self.read().get("limit_hit_at")
        return datetime.fromisoformat(raw) if raw else None


class QuotaProvider:
    """Counts every teacher call against the ledger and refuses once the share is spent."""

    def __init__(
        self,
        inner: TeacherProvider,
        ledger: QuotaLedger,
        limit: int,
        clock: Callable[[], datetime],
    ) -> None:
        self.inner = inner
        self.ledger = ledger
        self.limit = limit
        self.clock = clock

    def rewrite(self, source_text: str, **kwargs: Any) -> TeacherResult:
        if not self.ledger.take(self.limit):
            raise TeacherProviderError(
                "DAILY_LIMIT",
                "training share of the StealthWriter daily limit is used",
                retryable=False,
            )
        try:
            return self.inner.rewrite(source_text, **kwargs)
        except TeacherProviderError as exc:
            if exc.code == "DAILY_LIMIT":
                self.ledger.mark_limit_hit(exc.message, self.clock())
            raise


def reuse_production_session(
    production: Path = PRODUCTION_SESSION_FILE,
    training: Path = TRAINING_SESSION_FILE,
) -> bool:
    """Same StealthWriter account: copy the production login when it is newer."""
    if not production.is_file():
        return False
    if training.is_file() and training.stat().st_mtime >= production.stat().st_mtime:
        return False
    training.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(production, training)
    return True


@dataclass(slots=True)
class CycleResult:
    action: str
    wait_s: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)


def status(cfg: BulkConfig, now: datetime) -> dict[str, Any]:
    day = sw_day(now, cfg.reset_utc_hour)
    ledger = QuotaLedger(cfg.root, day)
    pool = SourcePool(cfg.pool_root)
    used = ledger.used()
    return {
        **cfg.safe_dict(),
        "enabled": cfg.enabled,
        "paused": (cfg.root / "PAUSE").exists(),
        "sw_day": day,
        "used_today": used,
        "limit_now": cfg.limit_at(now),
        "remaining_today": max(0, cfg.limit_at(now) - used),
        "reserve_release_at": cfg.release_starts(now).isoformat(),
        "limit_hit_at": ledger.read().get("limit_hit_at"),
        "next_reset": next_reset(now, cfg.reset_utc_hour).isoformat(),
        "pool_pending": pool.pending_count(),
        "pool_used": pool.used_count(),
    }


def run_cycle(
    cfg: BulkConfig,
    *,
    provider: TeacherProvider,
    now: datetime,
    clock: Callable[[], datetime],
    collector_cls: Any = None,
) -> CycleResult:
    """One scheduling decision: wait, or collect one batch."""
    if not cfg.enabled:
        return CycleResult("disabled", IDLE_WAIT.total_seconds())
    if (cfg.root / "PAUSE").exists():
        return CycleResult("paused", IDLE_WAIT.total_seconds())

    day = sw_day(now, cfg.reset_utc_hour)
    ledger = QuotaLedger(cfg.root, day)
    reset_at = next_reset(now, cfg.reset_utc_hour)
    until_reset = (reset_at - now).total_seconds() + 120

    hit_at = ledger.limit_hit_at()
    if hit_at is not None and now - hit_at < LIMIT_RECHECK:
        wait = min(until_reset, (hit_at + LIMIT_RECHECK - now).total_seconds())
        return CycleResult("limit_wait", wait, {"limit_message": ledger.read().get("limit_message")})

    limit = cfg.limit_at(now)
    remaining = limit - ledger.used()
    if remaining <= 0:
        wait = until_reset
        if limit < cfg.daily_limit and cfg.reserve_release_minutes > 0:
            wait = min(wait, (cfg.release_starts(now) - now).total_seconds() + 5)
        return CycleResult("quota_done", wait, {"used": ledger.used()})

    pool = SourcePool(cfg.pool_root)
    pending = pool.pending_count()
    if pending == 0:
        return CycleResult("pool_empty", IDLE_WAIT.total_seconds())

    from services.humanizer_training.teacher.documents.schema import DocumentCollectorConfig

    if collector_cls is None:
        from services.humanizer_training.teacher.documents.collector import TeacherDocumentCollector

        collector_cls = TeacherDocumentCollector

    count = min(cfg.batch_size, remaining, pending)
    stamp = now.astimezone(timezone.utc).strftime("%H%M%S")
    collector = collector_cls(
        DocumentCollectorConfig(
            count=count,
            seed=int(day.replace("-", "")),
            output_dir=str(cfg.root / day / f"batch-{stamp}"),
            source_pool_dir=str(cfg.pool_root),
            provider_name="stealthwriter",
            model="Legacy 5.1",
            level=8,
            level_weights=dict(cfg.level_weights),
            timeout_s=cfg.timeout_s,
            max_attempts_per_document=2,
        ),
        provider=QuotaProvider(provider, ledger, limit, clock),
    )
    summary = dict(collector.run().summary or {})
    stopped = summary.get("stopped_reason")
    detail = {
        "requested": count,
        "successful": summary.get("successful"),
        "failed": summary.get("failed"),
        "by_level": summary.get("successful_by_level"),
        "provider_calls": summary.get("provider_calls"),
        "used_today": ledger.used(),
        "stopped_reason": stopped,
        "paragraph_preservation": summary.get("paragraph_preservation_rate"),
    }
    paragraphs = detail["paragraph_preservation"]
    if paragraphs is not None and paragraphs < MIN_PARAGRAPH_PRESERVATION and (summary.get("successful") or 0) >= 3:
        # Merged paragraphs make pairs unusable for training; stop spending quota.
        (cfg.root / "PAUSE").write_text(
            f"paragraph_preservation={paragraphs} in batch-{stamp}; check teacher extraction\n",
            encoding="utf-8",
        )
        return CycleResult("paused_quality", 0.0, detail)
    if stopped == "LOGIN_REQUIRED":
        return CycleResult("login_required", 0.0, detail)
    if stopped == "DAILY_LIMIT":
        if ledger.limit_hit_at() is None:
            return CycleResult("quota_done", until_reset, detail)
        return CycleResult("limit_hit", 0.0, {**detail, "limit_message": ledger.read().get("limit_message")})
    return CycleResult("batch_done", 0.0, detail)
