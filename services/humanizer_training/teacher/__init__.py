"""Isolated offline teacher-data collection package.

Canonical synthetic path: ``teacher.documents`` (document-level Legacy 5.1 / level 8).
"""

from services.humanizer_training.teacher.config import TeacherProviderConfig, TeacherResult

__all__ = [
    "TeacherProviderConfig",
    "TeacherResult",
]
