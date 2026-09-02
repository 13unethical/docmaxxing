"""Official Turnitin Core API (TCA) client.

Opt-in via ``TURNITIN_USE_TCA=1``. Key/Secret without that flag are treated
as PlagDetect HTTP API credentials.
"""

from .client import TurnitinAPIError, TurnitinCoreClient
from .config import is_configured, prefer_official_api

__all__ = [
    "TurnitinAPIError",
    "TurnitinCoreClient",
    "is_configured",
    "prefer_official_api",
]
