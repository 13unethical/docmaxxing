"""Temporary structured trace logging for assignment upload/pricing diagnostics."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from services.assignment_project.paths import assignment_storage_root, assignment_trace_log_path

_LOGGER: logging.Logger | None = None


def _logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    logger = logging.getLogger("assignment.trace")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    log_path = assignment_trace_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    _LOGGER = logger
    return logger


def trace(event: str, **fields: Any) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "storage_root": str(assignment_storage_root()),
        "event": event,
        **fields,
    }
    _logger().info(json.dumps(payload, ensure_ascii=False, default=str))
