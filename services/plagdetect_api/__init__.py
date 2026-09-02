"""PlagDetect HTTP API client (submit / status / download / highlights)."""

from .client import PlagDetectAPIError, PlagDetectAPIClient
from .config import is_configured, prefer_plagdetect_api

__all__ = [
    "PlagDetectAPIClient",
    "PlagDetectAPIError",
    "is_configured",
    "prefer_plagdetect_api",
]
