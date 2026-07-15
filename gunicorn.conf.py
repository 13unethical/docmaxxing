"""Gunicorn settings for DocMaxxing production (LLM stages need long timeouts)."""

from __future__ import annotations

import multiprocessing

# Production nginx proxies to 127.0.0.1:8000 (local dev Flask uses 5001).
bind = "127.0.0.1:8000"
workers = max(2, min(4, multiprocessing.cpu_count()))
worker_class = "sync"
timeout = 600
graceful_timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
