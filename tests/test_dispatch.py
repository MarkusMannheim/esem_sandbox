"""Dispatch, the scarcity ladder and the administered cap."""

import numpy as np
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.dispatch import (
    _apply_ladder, _offer_stack, _price_from_stack, _unit_generation,
    dispatch_year,
)
from esem_sandbox.core.weather import HOURS_PER_YEAR, generate_bundle


@pytest.fixture(scope="module")
def settings():
    return load_settings()


@pytest.fixture(scope="module")
def bundle(settings):
    return generate_bundle(settings.weather["seed"], settings.weather["shape_years"])


def _year(settings, bundle, y, peak=12500.0):
    shape = bundle["demand_shape"][y]
    return dispatch_year(settings, 2026, shape * (peak / shape.max()),
                         bundle["wind_cf"][y], bundle["solar_cf"][y])


def test_price_is_the_marginal_offer(settings):
    prices = np.array([10.0, 50.0, 200.0])
    caps = np.array([100.0, 100.0, 100.0])
    got = _price_from_stack(np.array([50.0, 150.0, 250.0]), prices, caps, -10.0)
    np.testing.assert_array_equal(got, [10.0, 50.0, 200.0])


def test_surplus_clears_at_the_floor(settings):
    prices, caps = np.array([50.0]), np.array([100.0])
    got = _price_from_stack(np.array([-5.0, 0.0]), prices, caps, -10.0)
    np.testing.assert_array_equal(got, [-10.0, -10.0])


def test_must_run_coal_lets_the_solar_block_collapse(settings):
    prices, caps, _ = _offer_stack(list(settings.fleet), settings,
                                   {"water_value": 40.0})
    floor = settings.dispatch["vre_offer_per_mwh"]
    assert prices[0] == floor, "a must-run band should offer at the floor"
    assert caps[0] > 0


def test_thirty_seven_capped_hours_trigger_the_administered_cap(settings):
    """The threshold is $745,300 over 168 hourly intervals, so 37 hours at the
    $20,300 cap breach it: 37 x 20,300 = 751,100."""
    n = 200
    residual = np.zeros(n)
    residual[:37] = 1e6          # far beyond anything physical or on the ladder
    stack_price = np.full(n, 50.0)
    price, unserved, _, administered = _apply_ladder(
        residual, stack_price, firm_capacity=0.0, settings=settings)
    mpc = settings.market["market_price_cap_per_mwh"]
    apc = settings.market["administered_price_cap_per_mwh"]
    assert (price[:36] == mpc).all(), "the cap must not fire early"
    assert not administered[:36].any()
    assert administered[36], "the 37th capped hour breaches the threshold"
    assert price[36] == apc
    assert unserved[:37].sum() > 0


def test_thirty_six_capped_hours_do_not_trigger_it(settings):
    n = 200
    residual = np.zeros(n)
    residual[:36] = 1e6
    _, _, _, administered = _apply_ladder(
        residual, np.full(n, 50.0), 0.0, settings)
    assert not administered.any(), "36 x 20,300 = 730,800, below the threshold"


def test_ladder_tiers_are_called_in_order_and_run_out(settings):
    """Each tier has a call-hour budget for the year. Once spent it is gone, and
    the next scarce hour reaches further up the ladder."""
    tier = settings.dsr[0]
    n = tier.call_hours + 5
    residual = np.full(n, tier.capacity_mw * 0.5)
    price, _, ladder, _ = _apply_ladder(residual, np.full(n, 50.0), 0.0, settings)
    assert (price[:tier.call_hours] == tier.price_per_mwh).all()
    assert price[tier.call_hours] > tier.price_per_mwh
    assert ladder[:tier.call_hours].sum() > 0


def test_unserved_energy_is_what_the_ladder_cannot_cover(settings):
    ladder_total = sum(t.capacity_mw for t in settings.dsr)
    residual = np.array([ladder_total + 500.0])
    _, unserved, _, _ = _apply_ladder(residual, np.array([50.0]), 0.0, settings)
    assert unserved[0] == pytest.approx(500.0)


def test_a_partly_loaded_band_is_shared_pro_rata(settings):
    """Two units offering the same price split the marginal band by capacity,
    because per-plant revenue depends on the tie-break."""
    prices = np.array([20.0, 20.0])
    caps = np.array([300.0, 100.0])
    gen = _unit_generation(np.array([200.0]), prices, caps, ["big", "small"])
    assert gen["big"][0] == pytest.approx(150.0)
    assert gen["small"][0] == pytest.approx(50.0)


def test_energy_limited_hydro_sets_a_price_between_coal_and_the_ladder(
        settings, bundle):
    res = _year(settings, bundle, 0)
    coal = min(u.srmc_per_mwh for u in settings.fleet if u.technology == "coal")
    assert coal <= res.water_value_per_mwh <= 300.0, (
        "without an opportunity-cost offer the duration curve has two steps "
        "and cap contracts pay nothing in a normal year")


def test_prices_sit_between_the_floor_and_the_cap(settings, bundle):
    for y in range(settings.weather["shape_years"]):
        res = _year(settings, bundle, y)
        assert res.price.min() >= settings.market["minimum_price_per_mwh"]
        assert res.price.max() <= settings.market["market_price_cap_per_mwh"]
        assert len(res.price) == HOURS_PER_YEAR


def test_the_drought_year_is_the_one_that_breaches_the_standard(settings, bundle):
    """The lull-on-heat year is short and the mild years are not. This is the
    whole point of locating droughts rather than declaring them."""
    fractions = [_year(settings, bundle, y).unserved_fraction
                 for y in range(settings.weather["shape_years"])]
    standard = settings.reliability["standard_use_fraction"]
    assert max(fractions) > standard
    assert sorted(fractions)[len(fractions) // 2] < standard
