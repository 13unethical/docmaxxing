"""Assignment formatting stage uses Formatter V2, not FormatJob."""

from __future__ import annotations

from pathlib import Path

from services.assignment_formatting import (
    AssignmentFormatEngine,
    _overrides_from_requirement,
)
from services.assignment_spec.word_count_statement import (
    requirement_asks_to_state_word_count,
    text_asks_to_state_word_count,
)


def test_length_limit_is_not_an_instruction_to_print_word_count() -> None:
    assert text_asks_to_state_word_count("Write an essay of 2000 words using APA.") is False
    assert requirement_asks_to_state_word_count({"word_count": 2000}) is False


def test_cover_instruction_is_detected() -> None:
    assert text_asks_to_state_word_count("Please state the word count on the cover.") is True
    assert requirement_asks_to_state_word_count({"state_word_count": True}) is True


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
    assert "Word count:" not in (harvard.get("plain_text") or "")
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


def test_word_count_line_only_when_brief_asks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_STORAGE_DIR", str(tmp_path))
    engine = AssignmentFormatEngine()
    silent = engine.format_draft(
        draft=_draft(),
        requirement_json={"citation_style": "harvard", "word_count": 2000},
        project_id="proj-wc-silent",
    )
    assert not (silent.get("plain_text") or "").lstrip().startswith("Word count:")

    asked = engine.format_draft(
        draft=_draft(),
        requirement_json={
            "citation_style": "harvard",
            "word_count": 2000,
            "state_word_count": True,
        },
        project_id="proj-wc-asked",
    )
    assert (asked.get("plain_text") or "").lstrip().startswith("Word count:")

    rubric_asked = engine.format_draft(
        draft=_draft(),
        requirement_json={
            "citation_style": "harvard",
            "rubric": [
                {
                    "criterion": "Presentation",
                    "description": "State the word count on the cover page.",
                }
            ],
        },
        project_id="proj-wc-rubric",
    )
    assert (rubric_asked.get("plain_text") or "").lstrip().startswith("Word count:")

    leftover = dict(_draft())
    leftover["content"] = "Word count: 8\n\n## Introduction\n\nBody paragraph about coastal risk and policy.\n"
    stripped = engine.format_draft(
        draft=leftover,
        requirement_json={"citation_style": "harvard"},
        project_id="proj-wc-strip",
    )
    assert not (stripped.get("plain_text") or "").lstrip().startswith("Word count:")


def test_docx_from_markdown_splits_glued_references() -> None:
    from services.assignment_formatting import _docx_from_markdown

    blob = (
        "Donnelly, J. (2007). *Universal Human Rights in Theory and Practice*. Cornell University Press. "
        "Marks, S. P. (2006). *Human Rights: A Brief Introduction*. "
        "(This is a placeholder for a relevant work by Stephen P. Marks). "
        "United Nations. (1948). *Universal Declaration of Human Rights*."
    )
    doc = _docx_from_markdown(
        "Human Rights Journal",
        "## References\n" + blob,
    )
    texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    assert "References" in texts
    assert any(t.startswith("Donnelly, J. (2007).") for t in texts)
    assert any(t.startswith("Marks, S. P. (2006).") for t in texts)
    assert any(t.startswith("United Nations. (1948).") for t in texts)
    assert not any("*" in t for t in texts if t != "Human Rights Journal")
    assert not any("placeholder" in t.lower() for t in texts)
    glued = next((t for t in texts if "Donnelly" in t and "Marks" in t), None)
    assert glued is None
