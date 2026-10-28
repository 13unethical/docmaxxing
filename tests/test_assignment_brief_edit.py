"""Editing the parsed Assignment brief before payment."""

from __future__ import annotations

import pytest

from services.assignment_pipeline.service import AssignmentPipelineService
from services.assignment_project import ProjectService
from services.assignment_project.store import ProjectStore
from tests.test_assignment_project import _StubRequirementAnalyzer


@pytest.fixture
def service(tmp_path):
    return ProjectService(
        store=ProjectStore(root=tmp_path / "projects"),
        pipeline=AssignmentPipelineService(),
        analyzer=_StubRequirementAnalyzer(),
    )


def _priced_project(service, note="essay on climate policy"):
    bundle = service.create_project(
        note=note,
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    service.analyze_requirements(bundle.project.id)
    return service.calculate_pricing(bundle.project.id)


def test_word_count_change_reprices(service):
    priced = _priced_project(service)
    before = priced.project.artifacts["pricing"]["amount_coins"]

    updated = service.update_brief(priced.project.id, word_count=1500)

    assert updated.requirement.word_count == 1500
    assert updated.project.estimated_word_count == 1500
    after = updated.project.artifacts["pricing"]["amount_coins"]
    assert after < before
    assert updated.project.credits == after


def test_fields_and_instructions_reach_the_writer_note(service):
    priced = _priced_project(service)
    pid = priced.project.id

    service.update_brief(
        pid,
        assignment_type="Report",
        citation_style="Harvard",
        deadline="Friday",
        instructions="Focus on the UK",
    )
    updated = service.update_brief(pid, instructions="Focus on Germany")

    req = updated.requirement
    assert (req.assignment_type, req.citation_style, req.deadline) == ("Report", "Harvard", "Friday")
    assert updated.project.note == "essay on climate policy\n\nAdditional instructions from the student:\nFocus on Germany"

    cleared = service.update_brief(pid, instructions="")
    assert cleared.project.note == "essay on climate policy"


def test_out_of_range_length_rejected(service):
    priced = _priced_project(service)
    with pytest.raises(ValueError):
        service.update_brief(priced.project.id, word_count=50)


def test_brief_locked_after_payment(service):
    priced = _priced_project(service)
    service.confirm_payment(priced.project.id)
    with pytest.raises(ValueError):
        service.update_brief(priced.project.id, word_count=1500)
