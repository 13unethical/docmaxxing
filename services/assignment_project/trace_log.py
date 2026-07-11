"""Temporary structured trace logging for assignment upload/pricing diagnostics."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from services.assignment_project.paths import assignment_storage_root, assignment_trace_log_path

_LOGGER: logging.Logger | None = None
_FALLBACK_LOGGER: logging.Logger | None = None


def _fallback_logger() -> logging.Logger:
    global _FALLBACK_LOGGER
    if _FALLBACK_LOGGER is not None:
        return _FALLBACK_LOGGER
    logger = logging.getLogger("assignment.trace.fallback")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    _FALLBACK_LOGGER = logger
    return logger


def _logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    logger = logging.getLogger("assignment.trace")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    log_path = assignment_trace_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    except OSError as exc:
        fallback = _fallback_logger()
        fallback.info(
            json.dumps(
                {
                    "event": "trace.file_handler.failed",
                    "log_path": str(log_path),
                    "error": str(exc),
                }
            )
        )
        logger.addHandler(logging.StreamHandler(sys.stderr))
    _LOGGER = logger
    return logger


def trace(event: str, **fields: Any) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "storage_root": str(assignment_storage_root()),
        "trace_log": str(assignment_trace_log_path()),
        "event": event,
        **fields,
    }
    line = json.dumps(payload, ensure_ascii=False, default=str)
    try:
        _logger().info(line)
    except Exception:
        _fallback_logger().info(line)


def trace_startup() -> None:
    trace(
        "trace.startup",
        trace_log_exists=assignment_trace_log_path().is_file(),
    )
