"""Requirement analyzer normalization helpers."""

from __future__ import annotations

from services.assignment_project.requirement_analyzer import (
    _apply_user_scope_from_note,
    _extract_section_word_budgets_from_sources,
    _extract_word_count_from_sources,
    _normalize_required_sections,
    _normalize_requirement_json,
)


def test_extract_word_count_range_short_summary():
    sections = {
        "assignment_brief": (
            "Your summary should include Introduction, Body paragraph 1, Body paragraph 2, "
            "Concluding Paragraph and Reference List. Write 500-550 words."
        ),
        "rubric": "Not provided",
        "lecture_notes": "Not provided",
        "uploaded_files": "",
    }
    assert _extract_word_count_from_sources(sections) == 550


def test_extract_word_count_range_long_essay():
    sections = {
        "assignment_brief": "Write an essay of 1800–2200 words using APA 7.",
        "rubric": "Not provided",
        "lecture_notes": "Not provided",
        "uploaded_files": "",
    }
    assert _extract_word_count_from_sources(sections) == 2200


def test_extract_word_count_exact_limit():
    sections = {
        "assignment_brief": "Approximate length: 3000 words. Include a literature review.",
        "rubric": "Not provided",
        "lecture_notes": "Not provided",
        "uploaded_files": "",
    }
    assert _extract_word_count_from_sources(sections) == 3000


def test_normalize_accepts_range_string_from_gemini():
    raw = {
        "assignment_type": "Summary",
        "title": "Reading summary",
        "word_count": "500-550",
        "citation_style": "APA 7",
        "required_sections": ["Introduction", "Body", "Conclusion"],
        "rubric": [],
        "learning_outcomes": [],
        "minimum_sources": 2,
        "formatting": {
            "font_family": None,
            "font_size": None,
            "line_spacing": None,
            "margins": None,
            "alignment": None,
        },
        "deadline": None,
        "difficulty": None,
        "missing_information": [],
    }
    assert _normalize_requirement_json(raw)["word_count"] == 550


def test_extract_section_word_budgets_from_learning_journal_brief():
    sections = {
        "assignment_brief": (
            "Students are required to write a Learning Journal (1200 words). "
            "Your paper should consist of the following: "
            "Cover page "
            "Introduction (briefly state the purpose of the learning journal) – 100 words "
            "Journal Entry 1 (select a historical concept) – 200 words "
            "Journal Entry 2 (select a historical stage) – 200 words "
            "Journal Entry 3 (select any stage) – 200 words "
            "Journal Entry 4 (select two historical concepts) – 200 words "
            "Reflection (reflect on journal entry materials) – 300 words "
            "References"
        ),
        "rubric": "Not provided",
        "lecture_notes": "Not provided",
        "uploaded_files": "",
    }
    budgets = _extract_section_word_budgets_from_sources(sections)
    assert budgets["Introduction"] == 100
    assert budgets["Journal Entry 1"] == 200
    assert budgets["Journal Entry 4"] == 200
    assert budgets["Reflection"] == 300
    assert sum(budgets.values()) == 1200


def test_normalize_keeps_section_word_budgets():
    raw = {
        "assignment_type": "Learning Journal",
        "title": "Learning Journal",
        "word_count": 1200,
        "citation_style": None,
        "required_sections": ["Introduction", "Journal Entry 1", "Reflection", "References"],
        "section_word_budgets": {"Introduction": 100, "Journal Entry 1": 200, "Reflection": 300},
        "rubric": [],
        "learning_outcomes": [],
        "minimum_sources": None,
        "formatting": {
            "font_family": None,
            "font_size": None,
            "line_spacing": None,
            "margins": None,
            "alignment": None,
        },
        "deadline": None,
        "difficulty": None,
        "missing_information": [],
    }
    normalized = _normalize_requirement_json(raw)
    assert normalized["section_word_budgets"]["Introduction"] == 100
    assert normalized["section_word_budgets"]["Reflection"] == 300
    assert normalized["state_word_count"] is False


def test_null_or_string_list_fields_are_accepted():
    raw = {
        "assignment_type": "Essay",
        "word_count": 300,
        "required_sections": None,
        "rubric": None,
        "learning_outcomes": "Reflect on personal experience",
        "formatting": None,
        "missing_information": None,
    }
    normalized = _normalize_requirement_json(raw)
    assert normalized["required_sections"] == []
    assert normalized["rubric"] == []
    assert normalized["learning_outcomes"] == ["Reflect on personal experience"]
    assert normalized["missing_information"] == []


def test_required_sections_dict_strings_become_clean_titles():
    raw = [
        "{'section_name': 'Introduction', 'content': 'title, author and overview'}",
        "{'section_name': 'Body paragraph 1', 'content': 'article main idea'}",
        "Reference List",
    ]
    assert _normalize_required_sections(raw) == [
        "Introduction: title, author and overview",
        "Body paragraph 1: article main idea",
        "Reference List",
    ]


def test_user_scope_note_keeps_only_shelter_and_transportation():
    full = [
        "Cover Page",
        "Introduction",
        "Shelter",
        "Transportation",
        "Food",
        "Energy",
        "Water",
        "Conclusion",
        "References",
    ]
    note = (
        "Only write Shelter and Transportation for Findhorn Ecovillage, "
        "about 2 pages each. Include the attached photos. "
        "Do not write Food, Energy, Water, Cover, or Conclusion — teammates' parts."
    )
    scoped, budgets, word_count = _apply_user_scope_from_note(
        note,
        full,
        section_word_budgets={},
        word_count=5000,
    )
    titles = [s.split(":", 1)[0].strip() for s in scoped]
    assert "Shelter" in titles
    assert "Transportation" in titles
    assert "Food" not in titles
    assert "Energy" not in titles
    assert "Water" not in titles
    assert "Cover Page" not in titles
    assert "Conclusion" not in titles
    assert any("Reference" in t for t in titles)
    # 2 pages × ~550 words × 2 body sections
    assert word_count == 2200
    assert budgets.get("Shelter") == 1100
    assert budgets.get("Transportation") == 1100


def test_user_scope_ignored_without_narrowing_signal():
    sections = ["Introduction", "Body", "Conclusion", "References"]
    scoped, budgets, word_count = _apply_user_scope_from_note(
        "Please use a formal academic tone and APA citations.",
        sections,
        {"Introduction": 200},
        1000,
    )
    assert scoped == sections
    assert budgets == {"Introduction": 200}
    assert word_count == 1000
