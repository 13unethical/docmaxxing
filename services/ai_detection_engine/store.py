"""In-memory AI detection session and report storage."""

from __future__ import annotations

from threading import RLock

from services.ai_detection_engine.models import DetectionReport, DetectionSession


class DetectionSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, DetectionSession] = {}
        self._by_project: dict[str, str] = {}
        self._lock = RLock()

    def save(self, session: DetectionSession) -> DetectionSession:
        with self._lock:
            self._sessions[session.id] = session
            if session.project_id:
                self._by_project[session.project_id] = session.id
            return session

    def get(self, session_id: str) -> DetectionSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def get_by_project(self, project_id: str) -> DetectionSession | None:
        with self._lock:
            session_id = self._by_project.get(project_id)
            if not session_id:
                return None
            return self._sessions.get(session_id)

    def require(self, session_id: str) -> DetectionSession:
        session = self.get(session_id)
        if session is None:
            raise KeyError(f"Detection session not found: {session_id}")
        return session

    def require_by_project(self, project_id: str) -> DetectionSession:
        session = self.get_by_project(project_id)
        if session is None:
            raise KeyError(f"Detection session not found for project: {project_id}")
        return session


class DetectionReportStore:
    def __init__(self) -> None:
        self._reports: dict[str, DetectionReport] = {}
        self._by_project: dict[str, str] = {}
        self._lock = RLock()

    def save(self, report: DetectionReport) -> DetectionReport:
        with self._lock:
            self._reports[report.id] = report
            if report.project_id:
                self._by_project[report.project_id] = report.id
            return report

    def get(self, report_id: str) -> DetectionReport | None:
        with self._lock:
            return self._reports.get(report_id)

    def get_by_project(self, project_id: str) -> DetectionReport | None:
        with self._lock:
            report_id = self._by_project.get(project_id)
            if not report_id:
                return None
            return self._reports.get(report_id)

    def require(self, report_id: str) -> DetectionReport:
        report = self.get(report_id)
        if report is None:
            raise KeyError(f"Detection report not found: {report_id}")
        return report

    def require_by_project(self, project_id: str) -> DetectionReport:
        report = self.get_by_project(project_id)
        if report is None:
            raise KeyError(f"Detection report not found for project: {project_id}")
        return report
