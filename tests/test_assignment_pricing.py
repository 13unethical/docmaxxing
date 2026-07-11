"""Tests for assignment pricing."""

from __future__ import annotations

from services.assignment_project.pricing import calculate_project_price


def test_calculate_project_price_standard():
    result = calculate_project_price(
        {
            "word_count": 2000,
            "difficulty": "★★★☆☆",
            "required_sections": ["Introduction", "Analysis", "Conclusion"],
        },
        priority="standard",
    )
    assert result["amount_usd"] >= 29.0
    assert result["priority"] == "standard"


def test_calculate_project_price_urgent_multiplier():
    standard = calculate_project_price({"word_count": 3000}, priority="standard")
    urgent = calculate_project_price({"word_count": 3000}, priority="urgent")
    assert urgent["amount_usd"] > standard["amount_usd"]
