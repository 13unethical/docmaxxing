"""Tests for academic_title_case."""

from __future__ import annotations

import pytest

from formatter_v2.render.text_case import academic_title_case


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("climate adaptation in coastal cities", "Climate Adaptation in Coastal Cities"),
        ("a study of the climate", "A Study of the Climate"),
        ("what the data are for", "What the Data Are For"),
        ("adaptation: a review of methods", "Adaptation: A Review of Methods"),
        ("well-being and mental health", "Well-Being and Mental Health"),
        ("the role of IPCC assessments", "The Role of IPCC Assessments"),
        ("scenarios under RCP4.5 forcing", "Scenarios Under RCP4.5 Forcing"),
        ("surveys at McDonald locations", "Surveys at McDonald Locations"),
        ("reasons why students don't revise", "Reasons Why Students Don't Revise"),
        ("on the use of via and per", "On the Use of via and Per"),
        ("into the storm and over the reef", "Into the Storm and over the Reef"),
        ("from theory onto practice", "From Theory onto Practice"),
        ("climate change: the hard problem", "Climate Change: The Hard Problem"),
        ("an overview of an approach", "An Overview of an Approach"),
        ("but not for nothing", "But Not for Nothing"),
        ("UPPERcase Already Mixed stays", "UPPERcase Already Mixed Stays"),
        ("mixed well-known results", "Mixed Well-Known Results"),
    ],
)
def test_academic_title_case_cases(raw: str, expected: str) -> None:
    assert academic_title_case(raw) == expected


def test_academic_title_case_does_not_use_str_title_apostrophe() -> None:
    assert "Don'T" not in academic_title_case("students don't quit")
    assert academic_title_case("don't start here") == "Don't Start Here"


def test_academic_title_case_empty() -> None:
    assert academic_title_case("") == ""


def test_numbered_heading_capitalises_first_real_word() -> None:
    assert academic_title_case("2.1 The Aral Sea Basin") == "2.1 The Aral Sea Basin"
    assert academic_title_case("2.1 the Aral Sea Basin") == "2.1 The Aral Sea Basin"
    assert academic_title_case("2. the role of water") == "2. The Role of Water"


def test_roman_numbered_heading_capitalises_first_real_word() -> None:
    assert academic_title_case("IV. the Aral Sea Basin") == "IV. The Aral Sea Basin"
    assert academic_title_case("VII The Role of Water") == "VII The Role of Water"


def test_last_word_rule_unaffected_by_leading_number() -> None:
    assert academic_title_case("2.1 climate of the") == "2.1 Climate of The"
    assert academic_title_case("IV. a study of the") == "IV. A Study of The"


def test_numbered_heading_capitalises_first_real_word() -> None:
    assert academic_title_case("2.1 The Aral Sea Basin") == "2.1 The Aral Sea Basin"
    assert academic_title_case("2.1 the Aral Sea Basin") == "2.1 The Aral Sea Basin"
    assert academic_title_case("2. the role of water") == "2. The Role of Water"


def test_roman_numbered_heading_capitalises_first_real_word() -> None:
    assert academic_title_case("IV. The Aral Sea Basin") == "IV. The Aral Sea Basin"
    assert academic_title_case("VII the role of water") == "VII The Role of Water"


def test_last_word_rule_unaffected_by_leading_number() -> None:
    assert academic_title_case("2.1 climate of the") == "2.1 Climate of The"
    assert academic_title_case("IV. a study of the") == "IV. A Study of The"
