"""Dispatch, the scarcity ladder and the administered cap."""

import numpy as np
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.dispatch import (
    _apply_ladder, _curtailment_price, _offer_stack, _price_from_stack,
    _unit_generation, dispatch_year,
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


def test_must_run_coal_offers_at_its_own_price_not_a_wind_farms(settings):
    """A coal band avoiding a shutdown and a wind farm forgoing certificates are
    different economics, so they are different numbers. They were the same constant."""
    prices, caps, _ = _offer_stack(list(settings.fleet), settings,
                                   {"water_value": 40.0})
    must_run = settings.dispatch["must_run_offer_per_mwh"]
    assert prices[0] == must_run
    assert caps[0] > 0
    wind_offer = next(u.srmc_per_mwh for u in settings.fleet if u.technology == "wind")
    assert must_run != wind_offer, "these must not collapse back to one constant"


def test_surplus_is_priced_by_the_plant_on_the_margin_of_curtailment(settings, bundle):
    """The surplus price used to be one constant, so a fifth of the year sat at a
    single identical negative value. It should now vary with how deep the surplus is."""
    res = _year(settings, bundle, 0)
    negative = res.price[res.price < 0]
    assert len(negative) > 100, "this system should have plenty of surplus hours"
    levels = np.unique(negative)
    assert len(levels) >= 2, (
        f"only {len(levels)} distinct negative price(s): the curtailment merit order "
        "has collapsed back to a single constant"
    )
    wind = next(u.srmc_per_mwh for u in settings.fleet if u.technology == "wind")
    solar = next(u.srmc_per_mwh for u in settings.fleet if u.technology == "solar")
    assert solar in levels and wind in levels, (
        "both curtailable technologies should set the price in some hour"
    )
    assert levels.min() >= settings.market["minimum_price_per_mwh"]


def test_deeper_surplus_gives_a_lower_price(settings):
    """The ordering is the whole point: the plant willing to accept least is
    curtailed first, so the price falls as the surplus deepens."""
    solar = np.array([100.0, 100.0, 100.0])
    wind = np.array([100.0, 100.0, 100.0])
    price = _curtailment_price(np.array([50.0, 150.0, 500.0]),
                               [(-25.0, solar), (-45.0, wind)],
                               market_floor=-1000.0)
    np.testing.assert_array_equal(price, [-25.0, -45.0, -1000.0])


def test_eight_capped_hours_trigger_the_administered_cap(settings):
    """The published threshold is a sum of five-minute trading interval prices.
    At $20,300 the market may run 7.5 hours at the cap before it is suspended, so
    the eighth hour of an hourly model breaches it and the seventh does not."""
    n = 200
    residual = np.zeros(n)
    residual[:12] = 1e6          # far beyond anything physical or on the ladder
    stack_price = np.full(n, 50.0)
    price, unserved, _, administered = _apply_ladder(
        residual, stack_price, firm_capacity=0.0, settings=settings)
    mpc = settings.market["market_price_cap_per_mwh"]
    apc = settings.market["administered_price_cap_per_mwh"]
    trigger = int(np.argmax(administered))
    assert administered.any(), "the cap must fire"
    assert trigger == 7, f"expected the 8th capped hour to breach, got hour {trigger + 1}"
    assert (price[:7] == mpc).all(), "the cap must not fire early"
    assert price[7] == apc
    assert unserved[:12].sum() > 0


def test_seven_capped_hours_do_not_trigger_it(settings):
    n = 200
    residual = np.zeros(n)
    residual[:7] = 1e6
    _, _, _, administered = _apply_ladder(
        residual, np.full(n, 50.0), 0.0, settings)
    mpc = settings.market["market_price_cap_per_mwh"]
    assert 7 * mpc < settings.hourly_price_threshold
    assert not administered.any()


def test_the_threshold_matches_the_regulators_own_gloss(settings):
    """A guard against the units error this test file used to enshrine.

    The threshold was previously divided by two, on the assumption that it was a
    sum of half-hourly prices. It is a sum of five-minute prices, so the model ran
    about 45 hours at the cap instead of 7.5 before suspension.
    """
    hours = settings.hourly_price_threshold / settings.market["market_price_cap_per_mwh"]
    assert 7.0 < hours < 8.0, (
        f"{hours:.2f} hours at the cap; the AEMC schedule glosses this pair as 7.5"
    )


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
    whole point of locating droughts rather than declaring them, and it is the
    contrast the workshop is built on, so it is pinned rather than left to chance.

    The system's tightness is set by the import link's coincidence derate in
    fleet.csv. If the reliability standard changes, that derate is what must be
    re-calibrated to keep this contrast, not this assertion.
    """
    fractions = sorted(_year(settings, bundle, y).unserved_fraction
                       for y in range(settings.weather["shape_years"]))
    standard = settings.reliability["standard_use_fraction"]
    worst, next_worst = fractions[-1], fractions[-2]
    assert worst > standard, (
        f"the drought year should breach: {worst:.5%} against {standard:.5%}"
    )
    assert next_worst < standard, (
        f"only the drought year should breach: {next_worst:.5%} against {standard:.5%}"
    )
    assert worst > 2 * next_worst, (
        "the contrast should be clear, not marginal, so a small data change cannot "
        "quietly invert which year is the short one"
    )


def test_the_storage_re_stack_actually_converges(settings, bundle):
    """Storage schedules against a price and then moves it, which is a cobweb.

    Undamped it oscillated in a two-cycle and never settled at any ceiling, while
    the loop reported nothing: it simply stopped when it ran out of passes. The
    tolerance was also compared against the annual mean rather than the peak block
    it is named for, and could only fire on the final iteration, so it changed
    nothing at any value.
    """
    res = _year(settings, bundle, 0)
    assert res.storage_converged, (
        f"did not converge in {res.storage_passes} passes; a silent non-convergence "
        "is how a wrong answer gets reported as a right one"
    )
    assert res.storage_passes < settings.dispatch["max_storage_passes"], (
        "converging only on the last allowed pass means the ceiling is binding"
    )


def test_a_store_never_charges_and_discharges_in_the_same_hour(settings, bundle):
    """Two independent sorts do not partition a day when prices tie, and a
    curtailment merit order makes ties common. A twelve-hour store was scheduled to
    do both in the same hour on 308 days of 365."""
    res = _year(settings, bundle, 0)
    day_price = res.price[:365 * 24].reshape(365, 24)
    for unit in (u for u in settings.fleet if u.technology in ("battery", "phes")):
        slots = max(1, min(12, int(round(float(unit.duration_h)))))
        for d in range(0, 365, 7):
            order = np.argsort(day_price[d], kind="stable")
            charge, discharge = set(order[:slots].tolist()), set(order[-slots:].tolist())
            assert not (charge & discharge), (
                f"{unit.unit} charges and discharges in the same hour on day {d}"
            )


def test_hydro_actually_spends_its_energy_budget(settings, bundle):
    """The budget is a declared quantity, so it has to be delivered.

    It used to be a price offer and nothing more: an offer only moves hydro among
    nine discrete thermal steps, so between two of them the delivered energy did
    not change. It under-spent by 40 to 50 per cent, and quadrupling the budget
    changed neither the offer nor the delivery.
    """
    unit = next(u for u in settings.fleet if u.technology == "hydro")
    for y in range(settings.weather["shape_years"]):
        res = _year(settings, bundle, y)
        delivered = res.generation_mwh[unit.unit].sum() / 1000.0
        assert delivered == pytest.approx(unit.energy_budget_gwh, rel=0.005), (
            f"year {y} delivered {delivered:.0f} GWh of a {unit.energy_budget_gwh:.0f} "
            "GWh budget"
        )


def test_the_hydro_budget_changes_what_hydro_delivers(settings, bundle):
    """A budget that does not move delivery is not a budget."""
    import dataclasses
    shape = bundle["demand_shape"][0]
    demand = shape * (12500.0 / shape.max())
    delivered = []
    for budget in (2100.0, 4200.0):
        fleet = tuple(dataclasses.replace(u, energy_budget_gwh=budget)
                      if u.technology == "hydro" else u for u in settings.fleet)
        s = dataclasses.replace(settings, fleet=fleet)
        res = dispatch_year(s, 2026, demand, bundle["wind_cf"][0], bundle["solar_cf"][0])
        delivered.append(res.generation_mwh["hydro_a"].sum() / 1000.0)
    assert delivered[1] == pytest.approx(2 * delivered[0], rel=0.01)


def test_hydro_cannot_deliver_more_than_the_year_can_absorb(settings, bundle):
    """A budget larger than the residual can take is capped by physics, not spent."""
    import dataclasses
    unit = next(u for u in settings.fleet if u.technology == "hydro")
    fleet = tuple(dataclasses.replace(u, energy_budget_gwh=99_000.0)
                  if u.technology == "hydro" else u for u in settings.fleet)
    s = dataclasses.replace(settings, fleet=fleet)
    shape = bundle["demand_shape"][0]
    res = dispatch_year(s, 2026, shape * (12500.0 / shape.max()),
                        bundle["wind_cf"][0], bundle["solar_cf"][0])
    delivered = res.generation_mwh["hydro_a"].sum()
    assert delivered < 99_000_000.0
    assert delivered <= unit.available_mw * 8760 * 1.0001


def test_energy_conserves_every_hour(settings, bundle):
    """The check the whole model should be judged against.

    Generation net of curtailment, plus what the demand-response ladder supplied,
    plus what went unserved, must equal the demand the grid was asked to serve, in
    every hour. Rooftop is excluded because it never reaches the grid. The wind and
    solar fleet used to be missing from reported generation entirely, so this could
    not even be evaluated.
    """
    for y in range(settings.weather["shape_years"]):
        res = _year(settings, bundle, y)
        served = sum(v for k, v in res.generation_mwh.items() if k != "rooftop")
        balance = served + res.ladder_mw + res.unserved_mwh - res.operational_demand_mw
        assert np.abs(balance).max() < 1e-6, (
            f"year {y}: worst hourly imbalance {np.abs(balance).max():.6f} MW"
        )


def test_the_threshold_fast_path_agrees_with_the_sequential_loop(settings):
    """A fast path that changes the answer is not a fast path.

    The early return tested only whole 168-hour windows, so a breach inside the
    year's first 167 hours would have been skipped.
    """
    n = 400
    price = np.full(n, 50.0)
    price[:20] = 12_000.0            # a breach entirely inside the first window
    _, _, _, administered = _apply_ladder(
        np.zeros(n), price, firm_capacity=1e9, settings=settings)
    assert administered.any(), (
        "a threshold breach in the first 167 hours must not be skipped"
    )
