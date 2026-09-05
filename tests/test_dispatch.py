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


def test_the_schedule_does_not_depend_on_the_price_it_produces(settings, bundle):
    """There is no cobweb left to converge, because there is no loop.

    Storage used to pick its hours by ranking a price its own schedule then moved.
    That needed an iteration, damping to stop a two-cycle, a pass ceiling and a
    convergence flag; on a fleet with four gigawatts of batteries added it cycled
    anyway and reported convergence as false. Shaving quantities off the residual
    removes the dependency rather than damping it: the thresholds, and so the
    schedule, are a function of the residual and the unit alone.

    This test states that as a property rather than trusting the reading. Dispatch
    the same year twice from residuals that are identical, and the storage schedule
    must be identical to the last bit, whatever the prices in between did.
    """
    a = _year(settings, bundle, 4)
    b = _year(settings, bundle, 4)
    for unit in (u for u in settings.fleet if u.technology in ("battery", "phes")):
        assert np.array_equal(a.generation_mwh[unit.unit], b.generation_mwh[unit.unit])
    assert not hasattr(a, "storage_passes"), (
        "a pass count is a claim that there is something to iterate"
    )


def test_a_store_still_leaves_the_peak_block_dearer_than_the_trough(settings, bundle):
    """What the round-trip test buys. A store charges only on days whose spread
    covers the round trip, so it never trades energy at a loss, and a lull with no
    cheap hours leaves it empty rather than cycling for the sake of it."""
    res = _year(settings, bundle, 4)
    for unit in (u for u in settings.fleet if u.technology in ("battery", "phes")):
        gen = res.generation_mwh[unit.unit]
        charged = np.clip(-gen, 0.0, None)
        drawn = np.clip(gen, 0.0, None)
        if charged.sum() <= 0 or drawn.sum() <= 0:
            continue
        paid = float((res.price * charged).sum() / charged.sum())
        got = float((res.price * drawn).sum() / drawn.sum())
        assert got > paid, (
            f"{unit.unit} sold at ${got:,.2f} what it bought at ${paid:,.2f}"
        )

def test_a_store_never_delivers_energy_it_did_not_store(settings, bundle):
    """Conservation for the store itself, not just the bus.

    Cumulative discharge may never exceed what was charged, times the round trip.
    This is the storage equivalent of the reverse interconnector flow that created
    energy in the larger model.

    This test used to allow the store a free half charge at the start of the year,
    because the scheduler gave it one. The allowance is gone, and with it the cover
    it was providing: under it a store could deliver up to half its capacity out of
    nothing, and the day-level state-of-charge accounting was doing exactly that on
    days whose trough fell after their peak.
    """
    for year in range(len(bundle["demand_shape"])):
        res = _year(settings, bundle, year)
        for unit in (u for u in settings.fleet
                     if u.technology in ("battery", "phes")):
            gen = res.generation_mwh[unit.unit]
            rte = float(unit.round_trip_efficiency or 0.85)
            stored = np.cumsum(np.clip(-gen, 0.0, None) * rte)
            drawn = np.cumsum(np.clip(gen, 0.0, None))
            assert (drawn <= stored + 1e-6).all(), (
                f"{unit.unit} in shape year {year} delivers "
                f"{(drawn - stored).max():,.1f} MWh more than it ever stored"
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


def test_reported_firm_capacity_matches_what_the_residual_excludes(settings, bundle):
    """One source of truth for the stack the residual is measured against.

    Hydro is scheduled against its budget and netted out of the residual, so any
    consumer that re-sums the fleet and includes hydro double counts it. That is
    exactly what the worst-window search and the worst-week chart were doing: a
    threshold 1,235 MW above the stack the ladder itself used.
    """
    res = _year(settings, bundle, 4)
    thermal = [u for u in settings.fleet
               if u.in_service(2026) and u.technology != "hydro"]
    _, caps, _ = _offer_stack(thermal, settings)
    assert res.firm_capacity_mw == pytest.approx(float(caps.sum()))
    hydro = sum(u.available_mw for u in settings.fleet
                if u.technology == "hydro" and u.in_service(2026))
    assert hydro > 0
    assert res.firm_capacity_mw < float(caps.sum()) + hydro


def test_no_unit_generates_below_its_own_offer(settings, bundle):
    """The invariant a merit order exists to enforce.

    Withdrawal runs from the least negative offer to the most: solar at -$25, then
    wind at -$45, then a coal band bidding -$60 to avoid a shutdown. Because that
    coal band bids BELOW wind and solar and sits inside the stack, pricing the
    negative region off the stack alone cleared 1,131 hours a year at -$60 with wind
    and solar still at full output, which is plant running below the price it said
    it would accept. Curtailment therefore begins at the must-run floor, not at zero
    residual.
    """
    for y in range(settings.weather["shape_years"]):
        res = _year(settings, bundle, y)
        for tech in ("wind", "solar"):
            unit = next((u for u in settings.fleet if u.technology == tech), None)
            if unit is None:
                continue
            running = res.generation_mwh[unit.unit] > 1e-9
            below = running & (res.price < unit.srmc_per_mwh - 1e-9)
            assert not below.any(), (
                f"year {y}: {unit.unit} generates in {int(below.sum())} hours priced "
                f"below its own ${unit.srmc_per_mwh:.0f}/MWh offer"
            )


def test_the_withdrawal_ladder_has_all_of_its_rungs(settings, bundle):
    """Each negative offer should be able to set the price."""
    res = _year(settings, bundle, 0)
    levels = set(np.round(np.unique(res.price[res.price < 0]), 1))
    for tech in ("solar", "wind"):
        offer = next(u.srmc_per_mwh for u in settings.fleet if u.technology == tech)
        assert offer in levels, f"{tech}'s offer ${offer:.0f} never sets the price"
    assert settings.dispatch["must_run_offer_per_mwh"] in levels


def test_a_hydro_row_without_a_budget_still_generates(settings, bundle):
    """Not every hydro row is energy limited, and one without a budget must not
    vanish. It was excluded from the stack because it is hydro, then skipped by the
    scheduler because it has no budget, so it neither offered nor generated."""
    import dataclasses
    fleet = tuple(dataclasses.replace(u, energy_budget_gwh=None)
                  if u.technology == "hydro" else u for u in settings.fleet)
    s = dataclasses.replace(settings, fleet=fleet)
    shape = bundle["demand_shape"][4]
    res = dispatch_year(s, 2026, shape * (12500.0 / shape.max()),
                        bundle["wind_cf"][4], bundle["solar_cf"][4])
    unit = next(u for u in s.fleet if u.technology == "hydro")
    assert unit.unit in res.generation_mwh, "the row disappeared from the result"
    assert res.generation_mwh[unit.unit].sum() > 0, "it never generated"


def test_storage_cannot_make_the_peak_worse(settings, bundle):
    """The property that makes the scheduler safe, and it is structural rather than
    tuned: charging fills the trough to a level at or below the level discharging
    shaves the peak down to, so the post-storage residual cannot exceed the
    pre-storage peak.

    Ranking prices had no such property. Every store saw the same price series,
    picked the same cheap hours and charged at full power in all of them, and ten
    gigawatts of four-hour batteries added to this fleet lifted peak net load from
    9,605 MW to 20,880 and took unserved energy from 0.005 per cent of demand to
    22.8. Storage was manufacturing the scarcity it exists to relieve.
    """
    from dataclasses import replace
    from esem_sandbox.config import Unit

    def battery(mw):
        return Unit(unit=f"probe_{mw}", technology="battery", capacity_mw=mw,
                    availability=0.98, srmc_per_mwh=0.0, retirement_year=9999,
                    commissioned_year=0, must_run_mw=0.0, energy_budget_gwh=None,
                    duration_h=4.0, round_trip_efficiency=0.85, firm_factor=0.65,
                    cap_eligible=False, fom_per_kw_year=19.0)

    base = _year(settings, bundle, 4)
    worse = None
    for mw in (1_000.0, 4_000.0, 10_000.0):
        fleet = settings.fleet + (battery(mw),)
        res = _year(replace(settings, fleet=fleet), bundle, 4)
        assert res.residual_mw.max() <= base.residual_mw.max() + 1e-6, (
            f"{mw:,.0f} MW of storage lifted peak net load from "
            f"{base.residual_mw.max():,.0f} to {res.residual_mw.max():,.0f} MW"
        )
        assert res.unserved_fraction <= base.unserved_fraction + 1e-12, (
            f"{mw:,.0f} MW of storage raised unserved energy from "
            f"{base.unserved_fraction:.5%} to {res.unserved_fraction:.5%}"
        )
        worse = res
    assert worse.unserved_fraction < base.unserved_fraction


def test_a_long_duration_store_is_not_idle_all_year(settings, bundle):
    """Targeting a full cycle every day is impossible for a twelve-hour store: it
    cannot charge for fifteen hours and discharge for twelve inside one day. Its
    charge level was pushed above its discharge level, every day was rejected as
    incoherent, and the unit sat idle for the whole year while the model reported it
    as part of the fleet."""
    res = _year(settings, bundle, 4)
    phes = next(u for u in settings.fleet if u.technology == "phes")
    gen = res.generation_mwh[phes.unit]
    delivered = float(np.clip(gen, 0.0, None).sum())
    capacity = phes.available_mw * float(phes.duration_h)
    assert delivered > 50 * capacity, (
        f"{phes.unit} delivered {delivered / capacity:.1f} times its own storage "
        "over a year, which is not a store that is running"
    )
