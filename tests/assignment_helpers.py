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


def current_quote_id(projects: ProjectService, project_id: str) -> str:
    """The quote the student is shown now; every confirmation names the quote it accepts."""
    return str(projects.store.require_project(project_id).artifacts["pricing"]["quote_id"])


def mark_project_paid(projects: ProjectService, project_id: str) -> None:
    """Quote and confirm through the service, so the payment covers the current inputs."""
    requirement = projects.store.require_requirement(project_id)
    if not requirement.analyzed_at and not requirement.assignment_type:
        seed_analyzed_requirement(projects, project_id)
    projects.calculate_pricing(project_id)
    projects.confirm_payment(project_id, quote_id=current_quote_id(projects, project_id))


def record_checked_delivery(projects: ProjectService, project_id: str, package_id: str) -> None:
    """Store what ``run_delivery`` records once a package passed the paid-scope check.

    For tests that place a package on disk directly: downloads serve only checked packages.
    """
    from services.assignment_project.service import DELIVERY_SCOPE_KEY, PAYMENT_CYCLE_KEY
    from services.writer_engine.models import count_words

    project = projects.store.require_project(project_id)
    art = project.artifacts
    source = art.get("humanized_draft") or art.get("draft") or {}
    art[DELIVERY_SCOPE_KEY] = {
        "package_id": package_id,
        "cycle_id": str(art.get(PAYMENT_CYCLE_KEY) or ""),
        "words": count_words(str(source.get("content") or "")),
        "source_sha256": projects._delivery_source_hash(project),
    }
    projects.store.save_project(project)


def plant_stale_project_json(root, project_id: str, project_data: dict) -> None:
    """Put an old project copy into bundle.json behind the store's back.

    The store refuses or merges stale saves; this stands in for a copy that reached the disk
    anyway (an old worker build, a restored backup), so SQLite must still be the authority.
    """
    import json
    from pathlib import Path

    path = Path(root) / project_id / "bundle.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["project"] = project_data
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def prepare_project_for_research(projects: ProjectService, project_id: str) -> None:
    seed_analyzed_requirement(projects, project_id)
    mark_project_paid(projects, project_id)
