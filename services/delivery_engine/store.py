"""In-memory delivery package storage."""

from __future__ import annotations

from threading import RLock

from services.delivery_engine.models import DeliveryPackage


class DeliveryPackageStore:
    def __init__(self) -> None:
        self._packages: dict[str, DeliveryPackage] = {}
        self._by_project: dict[str, str] = {}
        self._lock = RLock()

    def save(self, package: DeliveryPackage) -> DeliveryPackage:
        with self._lock:
            self._packages[package.id] = package
            if package.project_id:
                self._by_project[package.project_id] = package.id
            return package

    def get(self, package_id: str) -> DeliveryPackage | None:
        with self._lock:
            return self._packages.get(package_id)

    def get_by_project(self, project_id: str) -> DeliveryPackage | None:
        with self._lock:
            package_id = self._by_project.get(project_id)
            if not package_id:
                return None
            return self._packages.get(package_id)

    def require(self, package_id: str) -> DeliveryPackage:
        package = self.get(package_id)
        if package is None:
            raise KeyError(f"Delivery package not found: {package_id}")
        return package

    def require_by_project(self, project_id: str) -> DeliveryPackage:
        package = self.get_by_project(project_id)
        if package is None:
            raise KeyError(f"Delivery package not found for project: {project_id}")
        return package

    def get_file(self, file_id: str):
        from services.delivery_engine.models import DeliveryFile

        with self._lock:
            for package in self._packages.values():
                for file_record in package.files:
                    if file_record.id == file_id:
                        return file_record
        return None

    def require_file(self, file_id: str):
        file_record = self.get_file(file_id)
        if file_record is None:
            raise KeyError(f"Delivery file not found: {file_id}")
        return file_record

    def update_status(self, package_id: str, status) -> DeliveryPackage:
        with self._lock:
            package = self.require(package_id)
            package.status = status
            return package
