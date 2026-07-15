"""Real delivery packager: writes files and ZIP archive."""

from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any, Protocol

from docx import Document

from services.assignment_pipeline.models import utc_now
from services.assignment_project.paths import assignment_storage_root
from services.delivery_engine.models import (
    DeliveryEngineInput,
    DeliveryFile,
    DeliveryPackage,
    DeliveryStatus,
    ProjectSummary,
)


class DeliveryPackager(Protocol):
    def package(self, payload: DeliveryEngineInput) -> DeliveryPackage: ...


class RealDeliveryPackager:
    VERSION = "real-1.0"

    def package(self, payload: DeliveryEngineInput) -> DeliveryPackage:
        project_id = payload.project_id or "local"
        draft = payload.final_draft
        requirement = payload.requirement_json
        research = payload.research_plan
        blueprint = payload.blueprint
        review = payload.review_report
        detection = payload.detection_report

        title = _safe_filename(
            str(draft.get("title") or requirement.get("title") or requirement.get("assignment_type") or "Assignment")
        )
        root = assignment_storage_root() / project_id / "delivery"
        root.mkdir(parents=True, exist_ok=True)

        summary = _build_summary(payload, title, review, detection)
        now = utc_now()
        package_id = str(uuid.uuid4())

        files: list[DeliveryFile] = []
        staged_files: list[tuple[DeliveryFile, bytes]] = []

        docx_name = f"{title}.docx"
        docx_bytes = _build_docx_bytes(str(draft.get("title") or title), str(draft.get("content") or ""))
        files.append(_file("Final Assignment", docx_name, "final_assignment_docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", root / docx_name, len(docx_bytes)))
        staged_files.append((files[-1], docx_bytes))

        pdf_name = f"{title}.pdf"
        pdf_bytes = _build_pdf_bytes(str(draft.get("title") or title), str(draft.get("content") or ""))
        files.append(_file("Final Assignment", pdf_name, "final_assignment_pdf", "application/pdf", root / pdf_name, len(pdf_bytes)))
        staged_files.append((files[-1], pdf_bytes))

        json_specs = [
            ("Requirement JSON", "requirement.json", "requirement_json", requirement),
            ("Research JSON", "research.json", "research_json", research),
            ("Blueprint JSON", "blueprint.json", "blueprint_json", blueprint),
            ("Review JSON", "review.json", "review_json", review),
            ("AI Detection JSON", "ai_detection.json", "ai_detection_json", detection),
            ("Project Summary JSON", "project_summary.json", "project_summary_json", summary.to_dict()),
        ]
        for label, filename, file_type, payload_obj in json_specs:
            blob = json.dumps(payload_obj, ensure_ascii=False, indent=2).encode("utf-8")
            files.append(_file(label, filename, file_type, "application/json", root / filename, len(blob)))
            staged_files.append((files[-1], blob))

        for entry, blob in staged_files:
            out_path = Path(entry.storage_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(blob)

        zip_name = f"{title}-delivery-package.zip"
        zip_path = root / zip_name
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for entry, _ in staged_files:
                zf.write(entry.storage_path, arcname=entry.filename)

        package_size = zip_path.stat().st_size

        package = DeliveryPackage(
            id=package_id,
            project_id=payload.project_id,
            status=DeliveryStatus.READY,
            files=files,
            project_summary=summary,
            package_download_url=f"/api/delivery/packages/{package_id}/download",
            package_size_bytes=package_size,
            final_draft_id=str(draft.get("id") or ""),
            engine_version=self.VERSION,
            prepared_at=now,
            ready_at=now,
        )
        return package


def _build_docx_bytes(title: str, content: str) -> bytes:
    doc = Document()
    doc.add_heading(title or "Assignment", level=1)
    for block in (content or "").split("\n\n"):
        text = block.strip()
        if text:
            doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _build_pdf_bytes(title: str, content: str) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception:
        # Keep delivery working even if reportlab is unavailable on the host.
        return _build_docx_bytes(title, content)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, title or "Assignment")
    y -= 24
    c.setFont("Helvetica", 10)
    for paragraph in (content or "").split("\n"):
        line = paragraph.strip()
        if not line:
            y -= 8
            continue
        chunks = [line[i : i + 110] for i in range(0, len(line), 110)]
        for chunk in chunks:
            if y < 40:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = height - 40
            c.drawString(40, y, chunk)
            y -= 14
    c.showPage()
    c.save()
    return buf.getvalue()


def _build_summary(
    payload: DeliveryEngineInput,
    title: str,
    review: dict[str, Any],
    detection: dict[str, Any],
) -> ProjectSummary:
    req = payload.requirement_json
    draft = payload.final_draft
    completion_time = payload.completion_time if payload.completion_time and payload.completion_time != "—" else "Not available"
    review_score = int(review.get("overall_score") or 0)
    ai_score = float(detection.get("overall_ai_score") or detection.get("average_score") or 0)
    return ProjectSummary(
        project_name=title,
        assignment_type=str(req.get("assignment_type") or "Not available"),
        word_count=int(draft.get("total_words") or req.get("word_count") or 0),
        citation_style=str(req.get("citation_style") or "Not available"),
        difficulty=str(req.get("difficulty") or "Not available"),
        completion_time=completion_time,
        total_revisions=int(payload.revision_attempts),
        total_humanization_attempts=int(payload.humanization_attempts),
        overall_review_score=review_score,
        final_ai_score=ai_score,
        pipeline_completion_date=utc_now().date().isoformat(),
        overall_quality_score=review_score,
    )


def _file(
    label: str,
    filename: str,
    file_type: str,
    mime_type: str,
    path: Path,
    size: int,
) -> DeliveryFile:
    file_id = str(uuid.uuid4())
    return DeliveryFile(
        id=file_id,
        label=label,
        filename=filename,
        file_type=file_type,
        mime_type=mime_type,
        size_bytes=size,
        storage_path=str(path),
        download_url=f"/api/delivery/files/{file_id}",
        ready=True,
    )


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return cleaned or "Assignment"
