"""Tests for credit pricing."""

from __future__ import annotations

import pytest

from services.economy.pricing import (
    FEATURE_COSTS,
    TOPUP_PACKAGES,
    USD_TO_COINS,
    assignment_cost_coins,
    detect_cost_credits,
    feature_cost,
    package,
    package_credits_per_usd,
    pro_savings_pct_vs_starter,
)
from services.assignment_project.pricing import calculate_project_price


def test_flat_feature_costs_match_table():
    for feature, cost in FEATURE_COSTS.items():
        if feature == "detect":
            # Detect is dynamic; FEATURE_COSTS holds the min/default only.
            assert feature_cost("detect", word_count=0) == detect_cost_credits(0)
            continue
        if feature == "humanize":
            # Site discount may reduce the live humanize price below FEATURE_COSTS.
            assert feature_cost(feature) <= cost
            continue
        assert feature_cost(feature) == cost


def test_detect_cost_scales_with_words():
    assert detect_cost_credits(0) == 1
    assert detect_cost_credits(1) == 1
    assert detect_cost_credits(100) == 1
    assert detect_cost_credits(101) == 2
    assert detect_cost_credits(1000) == 10
    assert feature_cost("detect", word_count=250) == 3
    assert feature_cost("detect", word_count=99) == 1


def test_humanize_list_price_is_twenty_five():
    assert FEATURE_COSTS["humanize"] == 25


def test_cite_cost_is_two_credits():
    assert feature_cost("cite") == 2


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
    assert package("credits_1000")["usd"] == 10.0
    assert package("credits_1000")["name"] == "Starter"
    assert package("credits_2500")["coins"] == 2200
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
        "credits_1000": (1000, 10.0, "Starter"),
        "credits_2500": (2200, 20.0, "Pro"),
    }
    for pkg_id, (coins, usd, name) in expected.items():
        info = package(pkg_id)
        assert info is not None
        assert info["coins"] == coins
        assert info["usd"] == usd
        assert info["name"] == name
        assert "price_id" in info


def test_package_credits_per_usd():
    assert package_credits_per_usd(1000, 10.0) == 100.0
    assert package_credits_per_usd(2200, 20.0) == 110.0


def test_pro_savings_pct_vs_starter():
    assert pro_savings_pct_vs_starter() == 10


def test_pricing_page_packages_derive_usage():
    from services.economy.pricing import pricing_page_packages

    rows = pricing_page_packages(user_id=42)
    assert len(rows) == 2
    starter, pro = rows
    humanize_cost = feature_cost("humanize")
    turnitin_cost = feature_cost("turnitin")
    assert starter["humanize_passes"] == 1000 // humanize_cost
    assert starter["turnitin_checks"] == 1000 // turnitin_cost
    assert starter["credits_per_usd_display"] == "100"
    assert pro["credits_per_usd_display"] == "110"
    assert pro["savings_pct"] == 10
    assert starter["savings_pct"] is None
    assert "checkout[custom][user_id]=42" in (starter["lemon_checkout_url"] or "")


def test_pricing_cost_rows_use_feature_costs():
    from services.economy.pricing import pricing_cost_rows

    rows = {r["label"]: r["value"] for r in pricing_cost_rows()}
    humanize = feature_cost("humanize")
    assert str(humanize) in rows["Humanize marked selections"]
    assert str(FEATURE_COSTS["turnitin"]) in rows["Turnitin similarity check"]
    assert str(detect_cost_credits(100)) in rows["AI detect in editor"]
