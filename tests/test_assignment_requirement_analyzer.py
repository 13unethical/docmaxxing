"""Requirement analyzer normalization helpers."""

from __future__ import annotations

from services.assignment_project.requirement_analyzer import (
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
