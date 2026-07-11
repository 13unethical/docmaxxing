"""In-memory review report storage."""

from __future__ import annotations

from threading import RLock

from services.reviewer_engine.models import ReviewReport


class ReviewReportStore:
    def __init__(self) -> None:
        self._reports: dict[str, ReviewReport] = {}
        self._by_project: dict[str, str] = {}
        self._lock = RLock()

    def save(self, report: ReviewReport) -> ReviewReport:
        with self._lock:
            self._reports[report.id] = report
            if report.project_id:
                self._by_project[report.project_id] = report.id
            return report

    def get(self, report_id: str) -> ReviewReport | None:
        with self._lock:
            return self._reports.get(report_id)

    def get_by_project(self, project_id: str) -> ReviewReport | None:
        with self._lock:
            report_id = self._by_project.get(project_id)
            if not report_id:
                return None
            return self._reports.get(report_id)

    def require(self, report_id: str) -> ReviewReport:
        report = self.get(report_id)
        if report is None:
            raise KeyError(f"Review report not found: {report_id}")
        return report

    def require_by_project(self, project_id: str) -> ReviewReport:
        report = self.get_by_project(project_id)
        if report is None:
            raise KeyError(f"Review report not found for project: {project_id}")
        return report
