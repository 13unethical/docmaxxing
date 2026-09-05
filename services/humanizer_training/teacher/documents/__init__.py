"""Document-level offline teacher collection package."""

from services.humanizer_training.teacher.documents.collector import TeacherDocumentCollector
from services.humanizer_training.teacher.documents.generator import generate_documents, summarize_document_plan
from services.humanizer_training.teacher.documents.schema import (
    DocumentCollectorConfig,
    HumanizerTeacherDocument,
    SyntheticDocument,
    TeacherChunkRecord,
)

__all__ = [
    "TeacherDocumentCollector",
    "generate_documents",
    "summarize_document_plan",
    "DocumentCollectorConfig",
    "HumanizerTeacherDocument",
    "SyntheticDocument",
    "TeacherChunkRecord",
]
