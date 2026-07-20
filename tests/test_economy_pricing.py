"""Tests for coin pricing."""

from __future__ import annotations

import pytest

from services.economy.pricing import (
    FEATURE_COSTS,
    USD_TO_COINS,
    assignment_cost_coins,
    feature_cost,
    package,
)
from services.assignment_project.pricing import calculate_project_price


def test_flat_feature_costs_match_table():
    for feature, cost in FEATURE_COSTS.items():
        assert feature_cost(feature) == cost


def test_unknown_feature_raises():
    with pytest.raises(KeyError):
        feature_cost("nonexistent")


def test_assignment_cost_converts_usd_to_coins():
    requirement = {"word_count": 2000, "required_sections": ["a", "b", "c"]}
    usd = calculate_project_price(requirement, priority="standard")["amount_usd"]
    coins = assignment_cost_coins(requirement, priority="standard")
    assert coins == int(round(usd * USD_TO_COINS))
    assert coins > 0


def test_assignment_via_feature_cost():
    requirement = {"word_count": 1500}
    direct = assignment_cost_coins(requirement)
    via = feature_cost("assignment", requirement=requirement, priority="standard")
    assert direct == via


def test_package_lookup():
    assert package("starter")["coins"] == 500
    assert package("student")["coins"] == 1500
    assert package("cram")["coins"] == 2900
    assert package("unknown") is None


def test_packages_convert_usd_at_fixed_rate():
    for pkg in ("starter", "student", "cram"):
        info = package(pkg)
        assert info["coins"] == info["usd"] * USD_TO_COINS
