"""Tests for coin pricing."""

from __future__ import annotations

import pytest

from services.economy.pricing import (
    FEATURE_COSTS,
    TOPUP_PACKAGES,
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
    assert package("credits_1000")["coins"] == 1000
    assert package("credits_1000")["usd"] == 9.0
    assert package("credits_1000")["name"] == "Starter"
    assert package("credits_2500")["coins"] == 2500
    assert package("credits_2500")["usd"] == 20.0
    assert package("credits_2500")["name"] == "Pro"
    assert package("credits_2500")["featured"] is True
    assert package("credits_100") is None
    assert package("credits_500") is None
    assert package("credits_2000") is None
    assert package("credits_5000") is None
    assert package("credits_10000") is None
    assert package("unknown") is None


def test_catalog_is_starter_and_pro_only():
    """Pricing UI and checkout share this catalog — only Starter + Pro."""
    assert set(TOPUP_PACKAGES) == {"credits_1000", "credits_2500"}
    expected = {
        "credits_1000": (1000, 9.0, "Starter"),
        "credits_2500": (2500, 20.0, "Pro"),
    }
    for pkg_id, (coins, usd, name) in expected.items():
        info = package(pkg_id)
        assert info is not None
        assert info["coins"] == coins
        assert info["usd"] == usd
        assert info["name"] == name
        assert "price_id" in info
