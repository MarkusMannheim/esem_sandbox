"""The procurement scheme: what it buys, what it pays, and who ends up carrying it.

The conservation tests here are the ones that make a cost figure believable. A
scheme that quietly created or destroyed money would report a net benefit made of
arithmetic rather than of capacity.
"""

import numpy as np
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.contracts import SWAP, age, settle_book
from esem_sandbox.core.esem import (
    ADMINISTRATOR, Administrator, AwardLine, Bid, award_contract,
    award_strike_per_mwh, blended_wacc, clear_pay_as_bid, eligible_technologies,
    firm_contribution_mw, lane_volume_mw, levy_per_mwh,
    long_run_cost_per_mw_year, recycle, reserve_margin_gap_mw, screen,
    unserved_after_firm,
)
from esem_sandbox.core.forward import Anchor, Cell, CellOutcome


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def _anchor(shortfalls, weights=None, demand_mwh=50_000_000.0):
    """An anchor whose cells carry the hourly shortfalls a test needs."""
    n = len(shortfalls)
    weights = weights if weights is not None else [1.0 / n] * n
    outcomes = tuple(
        CellOutcome(
            cell=Cell(shape_year=i, growth_path="central", peak_band=1, weight=w,
                      annual_growth=0.019, peak_multiplier=1.0),
            rent_per_mw_year={"ocgt": 100_000.0, "ccgt": 100_000.0,
                              "battery_8h": 100_000.0},
            unit_rent_per_mw_year={}, block_prices={"overnight": 50.0},
            mean_price=50.0, unserved_mwh=float(np.sum(s)),
            unserved_fraction=float(np.sum(s)) / demand_mwh,
            peak_shortfall_mw=float(np.max(s)) if len(s) else 0.0,
            shortfall_mw=np.asarray(s, dtype=float),
            operational_demand_mwh=demand_mwh,
        )
        for i, (s, w) in enumerate(zip(shortfalls, weights))
    )
    return Anchor(offset=4, year=2030, outcomes=outcomes)


# --------------------------------------------------------------------------
# How much to buy


def test_the_lane_is_sized_on_the_shape_of_the_shortfall_not_its_total(settings):
    """One deep hour and fifty shallow ones can carry the same energy and need very
    different amounts of plant to close. A lane sized off a total cannot tell them
    apart."""
    deep = np.zeros(8760); deep[0] = 5_000.0
    shallow = np.zeros(8760); shallow[:50] = 100.0
    assert deep.sum() == shallow.sum()
    a = lane_volume_mw(_anchor([deep]), settings)
    b = lane_volume_mw(_anchor([shallow]), settings)
    assert a > b, f"the deep gap needs more capacity: {a:,.0f} against {b:,.0f} MW"


def test_a_reliable_system_buys_nothing(settings):
    """A scheme that buys capacity a reliable system does not need is one whose cost
    has no benefit to set against it. The model has to be able to show that."""
    assert lane_volume_mw(_anchor([np.zeros(8760)]), settings) == 0.0


def test_the_lane_closes_the_gap_it_was_sized_to_close(settings):
    short = np.zeros(8760); short[100:140] = np.linspace(200.0, 3_000.0, 40)
    anchor = _anchor([short])
    standard = settings.reliability["standard_use_fraction"]
    volume = lane_volume_mw(anchor, settings)
    assert volume > 0
    assert unserved_after_firm(anchor, volume) <= standard
    assert unserved_after_firm(anchor, volume - 50.0) > standard, (
        "and it must not buy more than it needed"
    )


def test_the_lane_weights_cells_and_does_not_count_them(settings):
    """A one-in-ten cell must enter the volume at one in ten."""
    bad = np.zeros(8760); bad[:20] = 4_000.0
    good = np.zeros(8760)
    rare = lane_volume_mw(_anchor([bad, good], weights=[0.1, 0.9]), settings)
    even = lane_volume_mw(_anchor([bad, good], weights=[0.5, 0.5]), settings)
    assert rare < even, (
        f"a rarer bad cell must need less capacity: {rare:,.0f} against {even:,.0f}"
    )


def test_the_reserve_margin_is_reported_and_is_not_the_volume(settings):
    """A margin is a rule of thumb about how much capacity a peak needs. The lane is
    sized on the shortfall itself, and showing both is how an audience sees the
    difference between them."""
    short = np.zeros(8760); short[0:5] = 900.0
    anchor = _anchor([short])
    lane = lane_volume_mw(anchor, settings)
    margin = reserve_margin_gap_mw(anchor, firm_capacity_mw=9_000.0,
                                   peak_mw=12_500.0, margin=0.15)
    assert margin == pytest.approx(12_500.0 * 1.15 - 9_000.0)
    assert margin != pytest.approx(lane)


# --------------------------------------------------------------------------
# What a megawatt is worth to the lane


def test_storage_firm_credit_is_measured_against_the_gap_it_must_cover(settings):
    """A four-hour battery covers a four-hour gap completely and a twelve-hour one a
    third of the way, and no factor in a table can tell those apart because the
    difference is a property of the weather."""
    short = np.zeros(8760)
    short[10:14] = 500.0                       # a four-hour evening gap
    narrow = _anchor([short])
    wide = np.zeros(8760)
    wide[10:22] = 500.0                        # a twelve-hour gap
    broad = _anchor([wide])
    tech = settings.tech("battery_8h")
    tight = firm_contribution_mw(tech, 100.0, narrow)
    loose = firm_contribution_mw(tech, 100.0, broad)
    assert tight > loose, (
        f"the same battery cannot be worth as much against a longer gap: "
        f"{tight:.1f} against {loose:.1f} MW"
    )
    assert tight == pytest.approx(100.0 * tech.availability), "8h covers a 4h gap whole"


def test_dispatchable_firm_credit_is_availability_times_planner_credit(settings):
    short = np.zeros(8760); short[0:3] = 100.0
    tech = settings.tech("ocgt")
    assert firm_contribution_mw(tech, 200.0, _anchor([short])) == pytest.approx(
        200.0 * tech.availability * tech.firm_factor)


def test_only_plant_that_can_be_relied_on_may_bid(settings):
    names = {t.technology for t in eligible_technologies(settings)}
    assert "wind" not in names and "solar" not in names
    assert "ocgt" in names


# --------------------------------------------------------------------------
# The auction


def _bid(name, price, firm=100.0, mw=200.0, tech="ocgt"):
    return Bid(bidder=name, technology=tech, capacity_mw=mw, firm_mw=firm,
               price_per_mw_year=price, lead_years=2)


def test_the_screen_scales_with_the_market_but_has_a_floor(settings):
    dear = _bid("a", 700.0 * 8760)
    assert screen([dear], spot_per_mwh=10.0, settings=settings) == [], (
        "in a cheap year the floor of $500/MWh binds and a $700 bid is nonsense"
    )
    assert screen([dear], spot_per_mwh=200.0, settings=settings) == [dear], (
        "at a $200 spot the ceiling is $1,000 and the same bid is merely expensive"
    )
    tiny = _bid("b", 100.0 * 8760)
    assert screen([tiny], spot_per_mwh=1.0, settings=settings) == [tiny], (
        "the floor must keep a sane bid alive in a cheap year"
    )


def test_pay_as_bid_pays_each_what_it_asked(settings):
    lines = clear_pay_as_bid([_bid("a", 50_000.0), _bid("b", 90_000.0)], 200.0)
    assert [l.price_per_mw_year for l in lines] == [50_000.0, 90_000.0], (
        "under a uniform price both would be paid 90,000"
    )


def test_the_last_bid_is_taken_in_part(settings):
    """A lane that rounded up would buy capacity it had not decided it needed, and
    one that rounded down would stop short of the standard it exists to meet."""
    lines = clear_pay_as_bid([_bid("a", 10.0), _bid("b", 20.0)], 150.0)
    assert sum(l.firm_mw for l in lines) == pytest.approx(150.0)
    assert lines[-1].capacity_mw == pytest.approx(200.0 * 0.5)


def test_clearing_stops_at_the_gap(settings):
    lines = clear_pay_as_bid([_bid(n, 10.0 * i) for i, n in enumerate("abcdef", 1)],
                             250.0)
    assert sum(l.firm_mw for l in lines) == pytest.approx(250.0)


def test_a_zero_gap_buys_nothing(settings):
    assert clear_pay_as_bid([_bid("a", 1.0)], 0.0) == []


def test_a_contracted_plant_is_financed_more_cheaply(settings):
    tech = settings.tech("ocgt")
    naked = blended_wacc(tech, settings, 0.0)
    full = blended_wacc(tech, settings, 1.0)
    assert naked == tech.wacc
    assert full == settings.esem["contracted_wacc"] < naked
    assert long_run_cost_per_mw_year(tech, full, 0.0) < \
        long_run_cost_per_mw_year(tech, naked, 0.0)


def test_the_lane_does_not_pay_twice_for_energy_the_pool_already_pays_for(settings):
    tech = settings.tech("ocgt")
    gross = long_run_cost_per_mw_year(tech, tech.wacc, 0.0)
    net = long_run_cost_per_mw_year(tech, tech.wacc, 40_000.0)
    assert net == pytest.approx(gross - 40_000.0)
    assert long_run_cost_per_mw_year(tech, tech.wacc, 10 * gross) == 0.0


# --------------------------------------------------------------------------
# The award


def test_an_award_starts_when_the_plant_does_and_not_when_it_is_signed(settings):
    """The instrument's whole point. A contract that started at award would pay for
    delivery before there was anything to deliver."""
    line = AwardLine(bid=_bid("m", 50_000.0), firm_mw=100.0, capacity_mw=200.0,
                     price_per_mw_year=50_000.0)
    c = award_contract(line, 60.0, generator="m", commissioning_year=2030,
                       tenor_years=12)
    assert c.start_year == 2030
    assert not c.in_force(2029) and c.in_force(2030) and c.in_force(2041)
    assert not c.in_force(2042)


def test_an_award_settles_exactly_its_tenor_and_then_leaves_the_book(settings):
    line = AwardLine(bid=_bid("m", 50_000.0), firm_mw=100.0, capacity_mw=200.0,
                     price_per_mw_year=50_000.0)
    c = award_contract(line, 60.0, generator="m", commissioning_year=2030,
                       tenor_years=12)
    book = [c]
    settled = 0
    for year in range(2026, 2060):
        if book and book[0].in_force(year):
            settled += 1
        book = age(book, year)
    assert settled == 12
    assert book == [], "a book that is empty must be empty, not marked expired"


def test_the_strike_pays_the_awardee_what_it_bid(settings):
    """A swap settles the difference between strike and spot, so a generator holding
    one receives the strike whatever the pool does. Setting it at the expected price
    plus the bid makes the contract worth the bid and nothing else."""
    line = AwardLine(bid=_bid("m", 87_600.0), firm_mw=100.0, capacity_mw=200.0,
                     price_per_mw_year=87_600.0)
    strike = award_strike_per_mwh(50.0, line)
    uplift = (strike - 50.0) * line.capacity_mw * 8760.0
    assert uplift == pytest.approx(line.cost)


def test_the_generator_writes_and_the_administrator_holds(settings):
    """The direction that fixes the generator's price: it sells into the pool at
    whatever the pool pays and the contract makes up the difference."""
    line = AwardLine(bid=_bid("m", 50_000.0), firm_mw=100.0, capacity_mw=200.0,
                     price_per_mw_year=50_000.0)
    c = award_contract(line, 100.0, generator="m", commissioning_year=2030,
                       tenor_years=12)
    assert c.writer == "m" and c.holder == ADMINISTRATOR
    cheap = settle_book(settings, [c], np.full(8760, 20.0), 2030)
    assert cheap["m"] > 0, "a low pool price must pay the generator, not charge it"
    dear = settle_book(settings, [c], np.full(8760, 400.0), 2030)
    assert dear["m"] < 0, "and a high one must claw back"


# --------------------------------------------------------------------------
# Conservation


def test_every_contract_the_scheme_writes_nets_to_zero(settings):
    line = AwardLine(bid=_bid("m", 50_000.0), firm_mw=100.0, capacity_mw=200.0,
                     price_per_mw_year=50_000.0)
    award = award_contract(line, 90.0, generator="m", commissioning_year=2030,
                           tenor_years=12)
    admin = Administrator(awards=[award])
    strips = recycle(admin, settings, year=2030, anchor_per_mwh=80.0,
                     buyers=[("retailer_a", 120.0), ("retailer_b", 80.0)])
    price = np.linspace(10.0, 300.0, 8760)
    flows = settle_book(settings, [award] + strips, price, 2030)
    assert sum(flows.values()) == pytest.approx(0.0, abs=1e-6), (
        "a contract moves money; it does not make any"
    )


def test_the_levy_is_exactly_the_administrator_s_net_plus_its_overheads(settings):
    consumed = 50_000_000.0
    for net in (-1.2e8, 0.0, 3.4e7):
        rate = levy_per_mwh(net, settings, consumed)
        assert rate * consumed == pytest.approx(
            -net + settings.esem["overhead_per_year"])


def test_the_levy_is_charged_from_the_first_year_even_with_no_awards(settings):
    """An administrator costs money to run before it has bought anything. A levy
    that ignored that would understate the scheme by the cost of the body
    collecting it."""
    assert levy_per_mwh(0.0, settings, 50_000_000.0) > 0


def test_unsold_volume_is_warehoused_rather_than_vanishing(settings):
    line = AwardLine(bid=_bid("m", 50_000.0), firm_mw=100.0, capacity_mw=1_000.0,
                     price_per_mw_year=50_000.0)
    award = award_contract(line, 90.0, generator="m", commissioning_year=2030,
                           tenor_years=12)
    admin = Administrator(awards=[award])
    recycle(admin, settings, year=2030, anchor_per_mwh=80.0,
            buyers=[("retailer_a", 300.0)])
    assert admin.warehoused_mw[2030] == pytest.approx(700.0)
    assert admin.sold_mw(2030) == pytest.approx(300.0)


def test_the_conduct_lever_changes_the_price_and_is_checked(settings):
    line = AwardLine(bid=_bid("m", 50_000.0), firm_mw=100.0, capacity_mw=200.0,
                     price_per_mw_year=50_000.0)
    award = award_contract(line, 90.0, generator="m", commissioning_year=2030,
                           tenor_years=12)
    fire = load_settings({"esem": {"recycling_conduct": "fire_sale"}})
    admin = Administrator(awards=[award])
    strips = recycle(admin, fire, year=2030, anchor_per_mwh=80.0,
                     buyers=[("retailer_a", 100.0)])
    assert strips[0].strike_per_mwh == pytest.approx(
        80.0 * fire.esem["fire_sale_fraction"])
    with pytest.raises(ValueError, match="conduct"):
        recycle(Administrator(awards=[award]),
                load_settings({"esem": {"recycling_conduct": "hoard"}}),
                year=2030, anchor_per_mwh=80.0, buyers=[("retailer_a", 100.0)])


def test_a_recycled_strip_lasts_one_year(settings):
    line = AwardLine(bid=_bid("m", 50_000.0), firm_mw=100.0, capacity_mw=200.0,
                     price_per_mw_year=50_000.0)
    admin = Administrator(awards=[award_contract(
        line, 90.0, generator="m", commissioning_year=2030, tenor_years=12)])
    strips = recycle(admin, settings, year=2030, anchor_per_mwh=80.0,
                     buyers=[("retailer_a", 100.0)])
    assert all(c.tenor_years == 1 for c in strips)
    window = int(settings.esem["recycling_window_years"])
    assert {c.start_year for c in strips} == set(range(2030, 2030 + window + 1))
