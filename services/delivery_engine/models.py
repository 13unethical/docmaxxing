"""Delivery Engine data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class DeliveryStatus(StrEnum):
    PREPARING_FILES = "preparing_files"
    GENERATING_REPORTS = "generating_reports"
    PACKAGING = "packaging"
    READY = "ready"


@dataclass
class DeliveryFile:
    id: str
    label: str
    filename: str
    file_type: str
    mime_type: str
    size_bytes: int
    storage_path: str
    download_url: str | None = None
    ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "filename": self.filename,
            "file_type": self.file_type,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "storage_path": self.storage_path,
            "download_url": self.download_url,
            "ready": self.ready,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeliveryFile:
        return cls(
            id=str(data.get("id") or ""),
            label=str(data.get("label") or ""),
            filename=str(data.get("filename") or ""),
            file_type=str(data.get("file_type") or ""),
            mime_type=str(data.get("mime_type") or "application/octet-stream"),
            size_bytes=int(data.get("size_bytes") or 0),
            storage_path=str(data.get("storage_path") or ""),
            download_url=data.get("download_url"),
            ready=bool(data.get("ready")),
        )


@dataclass
class ProjectSummary:
    project_name: str
    assignment_type: str
    word_count: int
    citation_style: str
    difficulty: str
    completion_time: str
    total_revisions: int
    total_humanization_attempts: int
    overall_review_score: int
    final_ai_score: float
    pipeline_completion_date: str
    overall_quality_score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "assignment_type": self.assignment_type,
            "word_count": self.word_count,
            "citation_style": self.citation_style,
            "difficulty": self.difficulty,
            "completion_time": self.completion_time,
            "total_revisions": self.total_revisions,
            "total_humanization_attempts": self.total_humanization_attempts,
            "overall_review_score": self.overall_review_score,
            "final_ai_score": self.final_ai_score,
            "pipeline_completion_date": self.pipeline_completion_date,
            "overall_quality_score": self.overall_quality_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectSummary:
        return cls(
            project_name=str(data.get("project_name") or ""),
            assignment_type=str(data.get("assignment_type") or ""),
            word_count=int(data.get("word_count") or 0),
            citation_style=str(data.get("citation_style") or ""),
            difficulty=str(data.get("difficulty") or ""),
            completion_time=str(data.get("completion_time") or ""),
            total_revisions=int(data.get("total_revisions") or 0),
            total_humanization_attempts=int(data.get("total_humanization_attempts") or 0),
            overall_review_score=int(data.get("overall_review_score") or 0),
            final_ai_score=float(data.get("final_ai_score") or 0),
            pipeline_completion_date=str(data.get("pipeline_completion_date") or ""),
            overall_quality_score=int(data.get("overall_quality_score") or 0),
        )


@dataclass
class DeliveryPackage:
    id: str
    project_id: str | None
    status: DeliveryStatus
    files: list[DeliveryFile]
    project_summary: ProjectSummary
    package_download_url: str | None
    package_size_bytes: int
    final_draft_id: str | None
    engine_version: str = "mock-1.0"
    prepared_at: datetime | None = None
    ready_at: datetime | None = None
    client_format: str = "docx"
    client_filename: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "status": self.status.value,
            "files": [item.to_dict() for item in self.files],
            "project_summary": self.project_summary.to_dict(),
            "package_download_url": self.package_download_url,
            "package_size_bytes": self.package_size_bytes,
            "final_draft_id": self.final_draft_id,
            "engine_version": self.engine_version,
            "prepared_at": self.prepared_at.isoformat() if self.prepared_at else None,
            "ready_at": self.ready_at.isoformat() if self.ready_at else None,
            "client_format": self.client_format,
            "client_filename": self.client_filename,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeliveryPackage:
        prepared_at = None
        ready_at = None
        if data.get("prepared_at"):
            prepared_at = datetime.fromisoformat(str(data["prepared_at"]).replace("Z", "+00:00"))
        if data.get("ready_at"):
            ready_at = datetime.fromisoformat(str(data["ready_at"]).replace("Z", "+00:00"))
        try:
            status = DeliveryStatus(str(data.get("status") or DeliveryStatus.READY.value))
        except ValueError:
            status = DeliveryStatus.READY
        return cls(
            id=str(data["id"]),
            project_id=data.get("project_id"),
            status=status,
            files=[DeliveryFile.from_dict(item) for item in (data.get("files") or [])],
            project_summary=ProjectSummary.from_dict(data.get("project_summary") or {}),
            package_download_url=data.get("package_download_url"),
            package_size_bytes=int(data.get("package_size_bytes") or 0),
            final_draft_id=data.get("final_draft_id"),
            engine_version=str(data.get("engine_version") or "mock-1.0"),
            prepared_at=prepared_at,
            ready_at=ready_at,
            client_format=str(data.get("client_format") or "docx"),
            client_filename=data.get("client_filename"),
        )


@dataclass
class DeliveryEngineInput:
    final_draft: dict[str, Any]
    requirement_json: dict[str, Any]
    research_plan: dict[str, Any]
    blueprint: dict[str, Any]
    review_report: dict[str, Any]
    detection_report: dict[str, Any]
    project_id: str | None = None
    revision_attempts: int = 0
    humanization_attempts: int = 0
    completion_time: str = "—"
    # Absolute path to Format Engine DOCX. When set, delivery must ship this file
    # instead of rebuilding an unformatted document from markdown.
    formatted_document_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "final_draft": dict(self.final_draft),
            "requirement_json": dict(self.requirement_json),
            "research_plan": dict(self.research_plan),
            "blueprint": dict(self.blueprint),
            "review_report": dict(self.review_report),
            "detection_report": dict(self.detection_report),
            "revision_attempts": self.revision_attempts,
            "humanization_attempts": self.humanization_attempts,
            "completion_time": self.completion_time,
            "formatted_document_path": self.formatted_document_path,
        }
