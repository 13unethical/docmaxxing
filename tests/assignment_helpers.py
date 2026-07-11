"""Shared helpers for assignment integration tests."""

from __future__ import annotations

from services.assignment_pipeline.models import utc_now
from services.assignment_project.service import ProjectService


def seed_analyzed_requirement(projects: ProjectService, project_id: str) -> None:
    bundle = projects.store.require_bundle(project_id)
    requirement = bundle.requirement
    requirement.assignment_type = "Essay"
    requirement.word_count = 2500
    requirement.title = "Digital Transformation in Higher Education"
    requirement.analyzed_at = utc_now()
    projects.store.save_requirement(requirement)


def mark_project_paid(projects: ProjectService, project_id: str, *, price: float = 49.0) -> None:
    bundle = projects.store.require_bundle(project_id)
    bundle.project.price = price
    bundle.project.artifacts["payment_confirmed"] = True
    projects.store.save_project(bundle.project)


def prepare_project_for_research(projects: ProjectService, project_id: str) -> None:
    seed_analyzed_requirement(projects, project_id)
    mark_project_paid(projects, project_id)
