"""Gunicorn settings for DocMaxxing production (LLM stages need long timeouts)."""

from __future__ import annotations

import multiprocessing

bind = "127.0.0.1:5001"
workers = max(2, min(4, multiprocessing.cpu_count()))
worker_class = "sync"
timeout = 300
graceful_timeout = 60
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
