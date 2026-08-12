"""Assignment formatting stage uses Formatter V2, not FormatJob."""

from __future__ import annotations

from pathlib import Path

from services.assignment_formatting import (
    AssignmentFormatEngine,
    _overrides_from_requirement,
)


def _draft() -> dict:
    return {
        "id": "d1",
        "title": "Essay",
        "content": "## Introduction\n\nBody paragraph about coastal risk and policy.\n",
        "total_words": 8,
    }


def test_assignment_format_uses_v2_pipeline(tmp_path, monkeypatch) -> None:
    src = Path("services/assignment_formatting/__init__.py").read_text(encoding="utf-8")
    assert "FormatJob" not in src
    assert "format_document_full" not in src
    assert "UserOverrides" in src
    assert "resolve_format_spec" in src
    assert "format_document_v2" in src

    monkeypatch.setenv("PROJECT_STORAGE_DIR", str(tmp_path))
    formatted = AssignmentFormatEngine().format_draft(
        draft=_draft(),
        requirement_json={"citation_style": "harvard"},
        project_id="proj-v2",
    )
    assert formatted["engine_version"].startswith("format-engine-2")
    assert "v2_pipeline" in formatted["applied_rules"]
    assert "notices" in formatted
    assert isinstance(formatted["notices"], list)
    assert Path(formatted["path"]).read_bytes()[:2] == b"PK"


def test_assignment_supports_all_five_styles_including_chicago_and_ieee(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_STORAGE_DIR", str(tmp_path))
    engine = AssignmentFormatEngine()
    expected = {
        "harvard": "harvard",
        "APA": "apa7",
        "mla9": "mla9",
        "Chicago 17": "chicago17",
        "IEEE": "ieee",
    }
    for raw, style_id in expected.items():
        formatted = engine.format_draft(
            draft=_draft(),
            requirement_json={"citation_style": raw},
            project_id=f"proj-{style_id}",
        )
        assert formatted["style_id"] == style_id, raw
        _, resolved = _overrides_from_requirement({"citation_style": raw})
        assert resolved.value == style_id


def test_assignment_has_no_hardcoded_spacing_default(tmp_path, monkeypatch) -> None:
    src = Path("services/assignment_formatting/__init__.py").read_text(encoding="utf-8")
    assert "default=2.0" not in src
    assert "bottom_center" not in src

    overrides, style = _overrides_from_requirement({"citation_style": "harvard"})
    assert style.value == "harvard"
    assert overrides.line_spacing is None
    assert overrides.page_numbering is None

    monkeypatch.setenv("PROJECT_STORAGE_DIR", str(tmp_path))
    harvard = AssignmentFormatEngine().format_draft(
        draft=_draft(),
        requirement_json={"citation_style": "harvard"},
        project_id="proj-harvard-defaults",
    )
    ieee = AssignmentFormatEngine().format_draft(
        draft=_draft(),
        requirement_json={"citation_style": "ieee"},
        project_id="proj-ieee-defaults",
    )
    assert harvard["profile_summary"]["line_spacing"] == 1.5
    assert ieee["profile_summary"]["line_spacing"] == 1.0
    assert harvard["profile_summary"]["page_number_position"] == "bottom_center"
    assert ieee["profile_summary"]["page_number_position"] == "bottom_center"
    apa = AssignmentFormatEngine().format_draft(
        draft=_draft(),
        requirement_json={"citation_style": "apa7"},
        project_id="proj-apa-defaults",
    )
    assert apa["profile_summary"]["page_number_position"] == "top_right"


def test_assignment_notices_reach_project_result(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_STORAGE_DIR", str(tmp_path))
    formatted = AssignmentFormatEngine().format_draft(
        draft=_draft(),
        requirement_json={
            "citation_style": "apa7",
            "formatting": {"alignment": "justify"},
        },
        project_id="proj-notices",
    )
    notices = formatted["notices"]
    assert notices
    assert any(n.get("field") == "alignment" for n in notices)
    assert any(n.get("severity") == "deviation" for n in notices)
