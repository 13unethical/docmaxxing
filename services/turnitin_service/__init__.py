"""Turnitin / PlagDetect submission persistence and processing."""

from .store import TurnitinStore, init_db
from .service import TurnitinService

__all__ = ["TurnitinStore", "TurnitinService", "init_db"]
