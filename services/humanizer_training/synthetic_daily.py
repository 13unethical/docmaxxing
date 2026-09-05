"""Synthetic daily backfill planner/runner (isolated teacher collection).

Uses the shared site-wide Humanizer daily budget. Dry-run safe.
Scheduled via systemd timer (``deploy/docmaxxing-humanizer-training-daily.*``).
Live runs require ``--execute`` (or systemd ExecStart). Idempotent per Tashkent day.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.humanizer_training.daily_budget import (
    DailyHumanizerBudget,
    get_humanizer_daily_budget,
    humanizer_period_date_iso,
    release_humanizer_slots,
    reserve_humanizer_slots,
    within_reset_window,
)
from services.humanizer_training.teacher.documents.schema import DocumentCollectorConfig

DEFAULT_SYNTHETIC_ROOT = Path("data/humanizer_training/synthetic_daily")
DEFAULT_MINUTES_BEFORE_RESET = 10.0
DAILY_RUN_MARKER_NAME = "daily_run_marker.json"


def daily_run_marker_path(output_dir: Path) -> Path:
    return Path(output_dir) / DAILY_RUN_MARKER_NAME


def has_daily_run_marker(output_dir: Path) -> bool:
    return daily_run_marker_path(output_dir).is_file()


def read_daily_run_marker(output_dir: Path) -> dict[str, Any] | None:
    path = daily_run_marker_path(output_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unreadable", "path": str(path)}
    return data if isinstance(data, dict) else {"status": "invalid", "raw": data}


def claim_daily_run_marker(
    output_dir: Path,
    *,
    day: str,
    status: str = "claimed",
) -> bool:
    """Atomically claim today's synthetic run. Returns False if already claimed."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = daily_run_marker_path(out)
    payload = {
        "date": day,
        "timezone": "Asia/Tashkent",
        "status": status,
        "claimed_at": datetime.now(timezone.utc).isoformat(),
        "dataset_kind": "synthetic_daily",
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return True


def update_daily_run_marker(output_dir: Path, **fields: Any) -> None:
    path = daily_run_marker_path(output_dir)
    existing = read_daily_run_marker(output_dir) or {}
    existing.update(fields)
    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@dataclass(slots=True)
class DailyBackfillPlan:
    dry_run: bool
    within_window: bool
    minutes_before_reset: float
    budget: DailyHumanizerBudget
    documents_to_attempt: int
    max_documents: int | None
    output_dir: Path
    reason: str
    seed: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "within_window": self.within_window,
            "minutes_before_reset": self.minutes_before_reset,
            "budget": self.budget.as_dict(),
            "documents_to_attempt": self.documents_to_attempt,
            "max_documents": self.max_documents,
            "output_dir": str(self.output_dir),
            "reason": self.reason,
            "seed": self.seed,
            "dataset_kind": "synthetic_daily",
            "separated_from_real_user_raw": True,
            "teacher": {
                "model": "Legacy 5.1",
                "ui_model_label": "Ghost 5.1 Legacy",
                "level": 8,
            },
        }


@dataclass(slots=True)
class DailyBackfillResult:
    plan: DailyBackfillPlan
    reserved: int = 0
    released: int = 0
    successful: int = 0
    failed: int = 0
    executed: bool = False
    collector_manifest: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.as_dict(),
            "reserved": self.reserved,
            "released": self.released,
            "successful": self.successful,
            "failed": self.failed,
            "executed": self.executed,
            "collector_manifest": self.collector_manifest,
        }


def plan_daily_backfill(
    *,
    dry_run: bool = True,
    minutes_before_reset: float = DEFAULT_MINUTES_BEFORE_RESET,
    date: str | None = None,
    force_window: bool = False,
    output_root: Path = DEFAULT_SYNTHETIC_ROOT,
    seed: int | None = None,
    max_documents: int | None = None,
) -> DailyBackfillPlan:
    day = date or humanizer_period_date_iso()
    budget = get_humanizer_daily_budget(day=day)
    in_window = force_window or within_reset_window(
        minutes_before_reset=minutes_before_reset, budget=budget
    )
    remaining = int(budget.remaining)
    if max_documents is not None:
        remaining = min(remaining, max(0, int(max_documents)))

    out = Path(output_root) / day
    if has_daily_run_marker(out):
        reason = "already_ran_today"
        attempt = 0
    elif budget.daily_limit <= 0:
        reason = "daily_limit_is_zero"
        attempt = 0
    elif remaining <= 0:
        reason = "no_remaining_allowance"
        attempt = 0
    elif not in_window:
        reason = (
            f"outside_reset_window "
            f"(need <= {minutes_before_reset} min; have {budget.minutes_until_reset})"
        )
        attempt = 0
    else:
        reason = "ready"
        attempt = remaining

    # Deterministic seed from date string for reproducible synthetic docs.
    derived_seed = seed if seed is not None else (500_000 + int(day.replace("-", "")) % 100_000)
    return DailyBackfillPlan(
        dry_run=bool(dry_run),
        within_window=bool(in_window),
        minutes_before_reset=float(minutes_before_reset),
        budget=budget,
        documents_to_attempt=int(attempt),
        max_documents=max_documents,
        output_dir=out,
        reason=reason,
        seed=int(derived_seed),
    )


def run_daily_backfill(
    *,
    dry_run: bool = True,
    minutes_before_reset: float = DEFAULT_MINUTES_BEFORE_RESET,
    max_documents: int | None = None,
    date: str | None = None,
    force_window: bool = False,
    output_root: Path = DEFAULT_SYNTHETIC_ROOT,
    seed: int | None = None,
    execute_collector: bool = True,
) -> DailyBackfillResult:
    """Plan and optionally execute synthetic daily collection.

    Live execution reserves budget slots first, then runs the isolated document
    collector (Legacy 5.1 / level 8). Failures release unused reservations.
    """
    plan = plan_daily_backfill(
        dry_run=dry_run,
        minutes_before_reset=minutes_before_reset,
        max_documents=max_documents,
        date=date,
        force_window=force_window,
        output_root=output_root,
        seed=seed,
    )
    plan.output_dir.mkdir(parents=True, exist_ok=True)
    (plan.output_dir / "plan.json").write_text(
        json.dumps(plan.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = DailyBackfillResult(plan=plan)
    if dry_run or plan.documents_to_attempt <= 0:
        return result

    # Idempotency: only one live synthetic run per Tashkent calendar day.
    if not claim_daily_run_marker(plan.output_dir, day=plan.budget.date):
        plan.reason = "already_ran_today"
        plan.documents_to_attempt = 0
        return result

    reservation = reserve_humanizer_slots(plan.documents_to_attempt, day=plan.budget.date)
    result.reserved = reservation.reserved
    if reservation.reserved <= 0:
        plan.reason = "reservation_failed_zero_slots"
        update_daily_run_marker(
            plan.output_dir,
            status="skipped_zero_reservation",
            reserved=0,
        )
        return result

    update_daily_run_marker(
        plan.output_dir,
        status="reserved",
        reserved=reservation.reserved,
    )

    if not execute_collector:
        # Test hook: reservation + marker only (no Chrome / teacher).
        update_daily_run_marker(
            plan.output_dir,
            status="completed_reservation_only",
            reserved=reservation.reserved,
        )
        return result

    from services.humanizer_training.teacher.documents.collector import (
        TeacherDocumentCollector,
    )

    cfg = DocumentCollectorConfig(
        count=reservation.reserved,
        seed=plan.seed,
        output_dir=str(plan.output_dir / "teacher_raw"),
        dry_run=False,
        resume=True,
        max_provider_words=5000,
        provider_name="stealthwriter",
        model="Legacy 5.1",
        level=8,
        timeout_s=150.0,
        max_attempts_per_document=2,
        max_retries=2,
    )
    try:
        collection = TeacherDocumentCollector(cfg).run()
        result.executed = True
        result.collector_manifest = dict(collection.manifest or {})
        result.successful = int(
            collection.summary.get("successful")
            or collection.manifest.get("successful_documents_added")
            or 0
        )
        # Failures / skips free reserved slots so we never permanently burn quota.
        unused = max(0, reservation.reserved - result.successful)
        if unused:
            release_humanizer_slots(unused, day=plan.budget.date)
            result.released = unused
        result.failed = max(0, reservation.reserved - result.successful)
    except Exception as exc:  # noqa: BLE001
        release_humanizer_slots(reservation.reserved, day=plan.budget.date)
        result.released = reservation.reserved
        result.collector_manifest = {"error": str(exc)}
        update_daily_run_marker(
            plan.output_dir,
            status="failed",
            error=str(exc),
            reserved=reservation.reserved,
            released=result.released,
        )
        raise

    update_daily_run_marker(
        plan.output_dir,
        status="completed",
        reserved=reservation.reserved,
        successful=result.successful,
        released=result.released,
        failed=result.failed,
    )
    (plan.output_dir / "result.json").write_text(
        json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result
