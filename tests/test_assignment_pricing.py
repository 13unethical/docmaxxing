"""Tests for assignment pricing (volume x difficulty[1-10], no urgency)."""

from __future__ import annotations

import pytest

from services.assignment_project.pricing import (
    calculate_project_price,
    estimate_preparation_minutes,
)


def test_volume_is_linear_at_8_usd_per_1000_words():
    # difficulty 1 -> x1.0
    assert calculate_project_price({"word_count": 1000, "difficulty": 1})["amount_usd"] == 8.0
    assert calculate_project_price({"word_count": 500, "difficulty": 1})["amount_usd"] == 4.0
    assert calculate_project_price({"word_count": 100, "difficulty": 1})["amount_usd"] == 0.8


def test_no_minimum_price():
    result = calculate_project_price({"word_count": 50, "difficulty": 1})
    assert result["amount_usd"] == pytest.approx(0.4)


def test_difficulty_multipliers_1_to_10():
    expected = {
        1: 1.00, 2: 1.05, 3: 1.10, 4: 1.15, 5: 1.20,
        6: 1.25, 7: 1.30, 8: 1.35, 9: 1.45, 10: 1.50,
    }
    for grade, mult in expected.items():
        result = calculate_project_price({"word_count": 1000, "difficulty": grade})
        assert result["difficulty_stars"] == grade
        assert result["difficulty_multiplier"] == mult
        assert result["amount_usd"] == pytest.approx(8.0 * mult)


def test_difficulty_is_clamped_to_10():
    assert calculate_project_price({"word_count": 1000, "difficulty": 99})["difficulty_stars"] == 10


def test_no_urgency_or_priority_in_breakdown():
    result = calculate_project_price({"word_count": 2000, "difficulty": 6})
    assert "priority" not in result
    assert "priority_multiplier" not in result
    assert "hours_until_deadline" not in result


def test_legacy_priority_kwarg_is_ignored():
    a = calculate_project_price({"word_count": 2000, "difficulty": 6})
    b = calculate_project_price({"word_count": 2000, "difficulty": 6}, priority="urgent")
    assert a["amount_usd"] == b["amount_usd"]


def test_sources_do_not_change_price():
    without = calculate_project_price({"word_count": 2000, "difficulty": 6, "minimum_sources": 0})
    with_many = calculate_project_price({"word_count": 2000, "difficulty": 6, "minimum_sources": 25})
    assert without["amount_usd"] == with_many["amount_usd"]


def test_estimated_time_grows_with_length_and_difficulty():
    result = calculate_project_price({"word_count": 2000, "difficulty": 6})
    assert result["estimated_minutes"] >= 3
    small = estimate_preparation_minutes(1000, 1)
    big_words = estimate_preparation_minutes(5000, 1)
    harder = estimate_preparation_minutes(1000, 10)
    assert big_words > small
    assert harder > small


def test_difficulty_estimated_when_missing():
    result = calculate_project_price({"word_count": 3000})
    assert result["difficulty_estimated"] is True
    assert 1 <= result["difficulty_stars"] <= 10


def test_difficulty_from_number_rating_and_text():
    assert calculate_project_price({"word_count": 1000, "difficulty": 8})["difficulty_stars"] == 8
    assert calculate_project_price({"word_count": 1000, "difficulty": "7/10"})["difficulty_stars"] == 7
    assert calculate_project_price({"word_count": 1000, "difficulty": "3/5"})["difficulty_stars"] == 6
    assert calculate_project_price({"word_count": 1000, "difficulty": "★★★★☆"})["difficulty_stars"] == 8
    assert calculate_project_price({"word_count": 1000, "difficulty": "high"})["difficulty_stars"] == 7
