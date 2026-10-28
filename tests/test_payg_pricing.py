import pytest

from services.economy.plans import PlanError, checkout_item, payg_usd


@pytest.mark.parametrize(
    ("credits", "usd"),
    [(500, 7), (1000, 12), (1500, 17), (2000, 22), (2500, 27), (9500, 97), (10000, 102)],
)
def test_payg_price_is_two_dollars_plus_five_per_pack(credits, usd):
    assert payg_usd(credits) == usd
    item = checkout_item(credits=credits)
    assert item["usd"] == float(usd)
    assert item["coins"] == credits
    assert item["quantity"] == credits // 500


def test_payg_quantity_must_match_credits():
    assert checkout_item(credits=2000, quantity=4)["quantity"] == 4
    assert checkout_item(credits=10000, quantity="20")["quantity"] == 20
    with pytest.raises(PlanError):
        checkout_item(credits=2000, quantity=5)


@pytest.mark.parametrize("credits", [0, 400, 750, 10500])
def test_payg_rejects_amounts_off_the_slider(credits):
    with pytest.raises(PlanError):
        checkout_item(credits=credits)
