"""The tick loop, as a whole.

These run on a reduced lattice and a short horizon. The lattice size does not
change any of the properties tested here - they are conservation laws, orderings
and coincidences, not levels - and a full forty-five cell twenty-year run costs
three and a half minutes, which is a thing to do deliberately rather than on every
commit.
"""

import numpy as np
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.agents import PRODUCER, RETAILER, ownable_units
from esem_sandbox.core.contracts import SWAP
from esem_sandbox.core.forward import cell_plan
from esem_sandbox.core.investment import build_ceiling_mw
from esem_sandbox.core.simulate import BOOTSTRAP_YEARS, draw_sequence, run

TICKS = 4
SEED = 20260904


@pytest.fixture(scope="module")
def settings():
    return load_settings()


@pytest.fixture(scope="module")
def small(settings):
    """Nine cells: one weather shape by three growth paths by three peak bands."""
    return tuple(c for c in cell_plan(settings) if c.shape_year == 0)


@pytest.fixture(scope="module")
def baseline(settings, small):
    return run(settings, ticks=TICKS, seed=SEED, cells=small)


# --------------------------------------------------------------------------
# Coincidence: two runs must differ by the thing under test and by nothing else


def _fingerprint(result):
    return [(t.year, round(t.mean_price, 9), round(t.unserved_gwh, 9),
             tuple(sorted((b.technology, b.capacity_mw, b.owner) for b in t.builds)),
             t.notices, t.live_contracts)
            for t in result.ticks]


def test_the_same_seed_gives_the_same_run(settings, small, baseline):
    again = run(settings, ticks=TICKS, seed=SEED, cells=small)
    assert _fingerprint(again) == _fingerprint(baseline)


def test_a_lever_at_its_no_op_value_changes_nothing(settings, small, baseline):
    """The coincidence test every switch in this model has to pass. A leg that
    differs from the baseline while its own mechanism is doing nothing is a leg
    whose comparison means nothing."""
    explicit = load_settings({"investment": {"merchant_underwrite_years": 0}})
    assert _fingerprint(run(explicit, ticks=TICKS, seed=SEED, cells=small)) == \
        _fingerprint(baseline)


def test_the_weather_sequence_is_drawn_from_the_seed_and_nothing_else(settings):
    """Two legs must see the same weather, or the model reports the difference
    between two climates as the effect of a policy."""
    other = load_settings({"investment": {"merchant_underwrite_years": 10,
                                          "build_fraction_of_peak": 0.2}})
    assert draw_sequence(settings, SEED, 20) == draw_sequence(other, SEED, 20)


def test_the_realised_draw_comes_from_the_lattice_s_own_distribution(settings):
    """The design's claim, and the reason a forward number can be compared with a
    realised one at all: many realised draws must reproduce the lattice's
    probabilities, because they come from the same marginals."""
    draw = draw_sequence(settings, 11, 20_000)
    bands = np.array(settings.weather["peak_band_weights"], dtype=float)
    bands = bands / bands.sum()
    seen = np.bincount(draw.peak_bands, minlength=len(bands)) / len(draw.peak_bands)
    assert np.allclose(seen, bands, atol=0.01), (
        f"realised peak bands {seen} against lattice weights {bands}"
    )
    shapes = np.bincount(draw.shape_years,
                         minlength=settings.weather["shape_years"])
    shapes = shapes / shapes.sum()
    assert np.allclose(shapes, 1 / settings.weather["shape_years"], atol=0.01)


# --------------------------------------------------------------------------
# Conservation


def test_every_tick_s_contracts_net_to_zero(baseline):
    """A contract moves money; it does not make any. If a tick's cashflows do not
    sum to zero, some party is being paid by nobody."""
    for tick in baseline.ticks:
        total = sum(tick.cashflows.values())
        scale = max(1.0, max(abs(v) for v in tick.cashflows.values() or [1.0]))
        assert abs(total) / scale < 1e-9, (
            f"{tick.year}: cashflows sum to {total:,.2f} on a scale of {scale:,.0f}"
        )


def test_the_book_ages_instead_of_growing_for_ever(baseline, settings):
    """Contracts are dropped when they expire rather than marked expired and kept,
    so a book that is empty is empty and a book that is full is carrying live
    obligations."""
    counts = [t.live_contracts for t in baseline.ticks]
    assert counts[0] > 0, "the bootstrap must leave a book behind it"
    assert max(counts) <= counts[0] * 2, (
        f"the book is growing without bound: {counts}"
    )


def test_a_producer_is_hedged_from_the_first_tick(settings, baseline):
    """What the bootstrap is for. Without three clears at tenors one, two and three
    before tick zero the model opens on a market that has never traded, every
    producer looks naked in the tick that sets the tone for the run, and the
    exposure term the investment rule turns on is one by construction rather than
    by measurement."""
    first = baseline.ticks[0].swap_cover
    assert first, "no producers recorded"
    assert all(c > 0 for c in first.values()), (
        f"producers open the run at cover {first}; the bootstrap did not happen and "
        "every hurdle in the run is an unhedged one"
    )


def test_the_hedge_book_is_a_ladder_and_not_a_cliff(baseline):
    """Retailers write a strip each year sized at a third of their target, so three
    overlapping strips carry it. A book written all at once and expiring all at once
    would swing a producer between fully covered and naked, and the exposure term
    would be measuring the calendar rather than the market."""
    starts = sorted({c.start_year for c in baseline.book})
    assert len(starts) >= 2, f"every contract in the book starts in {starts}"


# --------------------------------------------------------------------------
# Pacing and lead times


def test_no_technology_exceeds_its_annual_ceiling(baseline, settings):
    for tick in baseline.ticks:
        by_tech: dict[str, float] = {}
        for b in tick.builds:
            by_tech[b.technology] = by_tech.get(b.technology, 0.0) + b.capacity_mw
        for tech, mw in by_tech.items():
            ceiling = build_ceiling_mw(tick.peak_mw, settings.tech(tech), settings)
            assert mw <= ceiling + 1e-9, (
                f"{tick.year}: {mw:,.0f} MW of {tech} against a ceiling of "
                f"{ceiling:,.0f}"
            )


def test_a_build_arrives_after_its_lead_time_and_not_before(baseline, settings):
    for tick in baseline.ticks:
        for b in tick.builds:
            lead = settings.tech(b.technology).lead_years
            assert b.commissioned_year == b.decided_year + lead


def test_nothing_generates_before_it_is_built(baseline, settings):
    for unit in baseline.fleet:
        if unit.commissioned_year > 0:
            assert not unit.in_service(unit.commissioned_year - 1)
            assert unit.in_service(unit.commissioned_year)


def test_every_built_unit_has_exactly_one_owner(baseline):
    """A unit owned by nobody earns revenue that reaches no balance sheet, and a
    unit owned twice earns it twice. Neither shows up in a price."""
    from esem_sandbox.core.agents import check_roster
    check_roster(baseline.roster, ownable_units(baseline.fleet))


def test_a_build_is_recorded_with_the_arithmetic_that_justified_it(baseline):
    """The hurdle-versus-rent panel is the decision itself, not a retelling of it."""
    for tick in baseline.ticks:
        for b in tick.builds:
            assert b.expected_rent_per_mw_year > 0
            assert b.hurdle_per_mw_year > 0
            assert 0.0 <= b.contracted_share <= 1.0


# --------------------------------------------------------------------------
# Ranking


def test_a_market_given_longer_cover_never_builds_less_firm_capacity(settings, small,
                                                                    baseline):
    """The ordering the whole model exists to produce. A ten-year underwrite lowers
    the hurdle, and a lower hurdle cannot mean less plant."""
    underwritten = load_settings({"investment": {"merchant_underwrite_years": 10}})
    with_cover = run(underwritten, ticks=TICKS, seed=SEED, cells=small)
    firm = lambda r: sum(b.capacity_mw * settings.tech(b.technology).firm_factor
                         for t in r.ticks for b in t.builds)
    assert firm(with_cover) >= firm(baseline) - 1e-9, (
        f"{firm(with_cover):,.0f} MW firm with cover against "
        f"{firm(baseline):,.0f} MW without"
    )


def test_the_build_ceiling_is_not_captured_by_whoever_is_asked_first(settings, small):
    """The ceiling is shared, so whoever is asked first gets it. With a fixed order
    that is the same firm every year: over twenty years the merchant and the
    regional merchant, who are the archetypes the risk story is about, built almost
    nothing while the two gentailers built almost everything, for no reason but
    where they sat in a tuple."""
    result = run(settings, ticks=8, seed=SEED, cells=small)
    builders = {b.owner for t in result.ticks for b in t.builds}
    producers = {a.name for a in result.roster if a.kind == PRODUCER}
    assert len(builders) > settings.investment["concurrent_builds_per_year"], (
        f"only {sorted(builders)} ever built, of {sorted(producers)}"
    )


def test_the_two_legs_see_one_weather_sequence(settings, small):
    """A comparison between the legs has to be a comparison of the mechanism. A leg
    that drew its own weather would report the difference between two climates as
    the effect of a policy."""
    from esem_sandbox.core.simulate import ESEM
    merchant = run(settings, ticks=3, seed=SEED, cells=small)
    scheme = run(settings, ticks=3, seed=SEED, cells=small, leg=ESEM)
    assert merchant.draw == scheme.draw


def test_the_scheme_leg_is_the_merchant_leg_with_something_added(settings, small):
    """Nothing about the scheme may run on the leg that is meant to be without it."""
    merchant = run(settings, ticks=3, seed=SEED, cells=small)
    for tick in merchant.ticks:
        assert tick.awards == ()
        assert tick.lane_volume_mw == 0.0
        assert tick.levy_per_mwh == 0.0
        assert tick.administrator_net == 0.0


def test_an_unreliable_leg_is_not_reported_as_the_cheap_one(settings, small):
    """The line that stops a bill view being an argument for unreliability. Unserved
    energy is a cost even though nobody invoices for it."""
    result = run(settings, ticks=3, seed=SEED, cells=small)
    priced = result.unserved_valued_at_the_cap(settings)
    assert priced == pytest.approx(
        result.total_unserved_gwh * 1000.0
        * settings.market["market_price_cap_per_mwh"])
    assert result.consumer_cost(settings) > result.total_wholesale_cost or \
        result.total_unserved_gwh == 0.0


def test_the_levy_reaches_the_consumer_view_in_dollars(settings, small):
    from esem_sandbox.core.simulate import ESEM
    scheme = run(settings, ticks=4, seed=SEED, cells=small, leg=ESEM)
    assert scheme.total_levy == pytest.approx(
        sum(t.levy_per_mwh * t.consumed_mwh for t in scheme.ticks))
    assert scheme.total_levy > 0, "the administrator costs money to run from year one"


def test_an_award_commits_a_plant_the_merchant_rule_had_not_committed(settings, small):
    """What award-at-final-investment-decision means: the plant is committed in the
    year of the award and arrives after its lead time, and it exists on the scheme
    leg and not on the merchant one."""
    from esem_sandbox.core.simulate import ESEM
    scheme = run(settings, ticks=4, seed=SEED, cells=small, leg=ESEM)
    awarded = [u for u in scheme.fleet if u.unit.endswith("_awarded")]
    assert awarded, "the lane opened and awarded nothing"
    merchant = run(settings, ticks=4, seed=SEED, cells=small)
    assert not [u for u in merchant.fleet if u.unit.endswith("_awarded")]
    for tick in scheme.ticks:
        for award in tick.awards:
            assert award.commissioning_year > tick.year, (
                "a plant cannot arrive in the year it is decided"
            )
            lead = settings.tech(award.technology).lead_years
            assert award.commissioning_year == tick.year + lead


def test_the_legs_coincide_exactly_when_the_lane_never_opens(settings, small):
    """The coincidence the decomposition exercise rests on.

    The scheme's effect reaches the market through three channels: the exposure a
    long contract removes, the cost of capital it lowers, and the capacity it
    procures. Attributing the whole effect to any one of them is the tempting and
    false version of this story, and the way to separate them is to be able to switch
    each off and see the legs meet.

    This pins the third. With a reliability standard nothing can breach, the lane is
    empty in every year, and the scheme leg must then be the merchant leg to the last
    bit. Anything that differs is something about the scheme leaking into a leg where
    nothing was procured.
    """
    from esem_sandbox.core.simulate import ESEM
    loose = load_settings({"reliability": {"standard_use_fraction": 1.0}})
    merchant = run(loose, ticks=TICKS, seed=SEED, cells=small)
    scheme = run(loose, ticks=TICKS, seed=SEED, cells=small, leg=ESEM)
    assert all(t.lane_volume_mw == 0.0 for t in scheme.ticks), "the lane must be shut"
    assert _fingerprint(scheme) == _fingerprint(merchant)


def test_the_risk_channel_now_reaches_the_projection_as_well(settings, small):
    """This test used to assert the opposite, and the change is deliberate.

    While the projection assumed one technology, the risk premium only scaled one
    threshold and moved nothing: switching it off left the fleet identical over
    four ticks, and the decomposition exercise leaned on that. Now the projection
    chooses among technologies, and the premium is applied per technology, so it
    decides WHICH plant the forecast assumes gets built as well as how much. That
    reaches the prices every investor reads, and the fleet moves.

    The direction is not fixed, and the claim here is deliberately about movement
    rather than about sign. The premium pulls two ways: it raises every investor's
    own hurdle, which builds less, and it raises the threshold the projection uses
    for entry by others, which projects a tighter market and builds more. Over six
    weather draws the fleet moved in five, and the market built more without the
    premium in one of them and less in four. On one draw - a low growth one - it
    moved nothing at all, so this assertion is about this seed and this tick count
    and not about every run.

    What the decomposition exercise actually refutes survives and is the narrower
    claim: the effect of a long contract cannot be ATTRIBUTED to the exposure it
    removes. It cannot, because the channel does not even hold its sign across
    weather draws, while the capital it cheapens and the plant it procures do.
    """
    risk_free = load_settings({"investment": {"risk_premium": 0.0}})
    base = run(settings, ticks=TICKS, seed=SEED, cells=small)
    flat = run(risk_free, ticks=TICKS, seed=SEED, cells=small)
    assert _fingerprint(flat) != _fingerprint(base), (
        "the risk premium now selects between technologies in the projection, so "
        "switching it off has to move something"
    )
    base_caps = [c.premium_per_mwh for c in base.book if c.kind == "cap"]
    flat_caps = [c.premium_per_mwh for c in flat.book if c.kind == "cap"]
    assert base_caps and flat_caps
    assert max(base_caps) != pytest.approx(max(flat_caps)), (
        "and it must still price insurance on the same coefficient"
    )


def test_the_bill_and_the_resource_cost_are_not_the_same_number(settings, small):
    """The line that stops a bill view being an argument.

    Most of a bill is a payment from consumers to producers. A scheme that builds
    capacity pushes the pool price down and cuts the bill by far more than it costs,
    but that reduction is a transfer, not a saving.
    """
    result = run(settings, ticks=TICKS, seed=SEED, cells=small)
    assert result.resource_cost(settings) < result.consumer_cost(settings), (
        "a bill that was not mostly transfer would be a remarkable market"
    )
    assert sum(t.fuel_and_vom for t in result.ticks) > 0
    assert sum(t.fixed_cost_of_fleet for t in result.ticks) > 0


def test_sunk_capital_is_not_charged_to_the_run(settings, small):
    """Charging a run for money spent before it started would compare two legs on
    cashflows neither of them moved."""
    result = run(settings, ticks=2, seed=SEED, cells=small)
    first = result.ticks[0]
    assert first.annualised_capex_of_new_build == 0.0, (
        "nothing decided in the first year can have been commissioned in it"
    )


def test_switching_off_the_financing_channel_changes_the_scheme_and_not_the_market(
        settings, small):
    """The second channel. Setting the contracted cost of capital to the rate a
    merchant pays removes the financing advantage a contract confers, which changes
    what the lane costs without touching a market that has no lane."""
    from esem_sandbox.core.simulate import ESEM
    same_wacc = load_settings({"esem": {"contracted_wacc": 0.07}})
    assert same_wacc.tech("ocgt").wacc == 0.07, "the levelling value must match"
    base_merchant = run(settings, ticks=TICKS, seed=SEED, cells=small)
    levelled_merchant = run(same_wacc, ticks=TICKS, seed=SEED, cells=small)
    assert _fingerprint(levelled_merchant) == _fingerprint(base_merchant), (
        "a leg with no lane cannot notice what a contract would have been financed at"
    )
    base = run(settings, ticks=3, seed=SEED, cells=small, leg=ESEM)
    levelled = run(same_wacc, ticks=3, seed=SEED, cells=small, leg=ESEM)
    base_cost = sum(t.scheme_cost for t in base.ticks)
    levelled_cost = sum(t.scheme_cost for t in levelled.ticks)
    assert levelled_cost >= base_cost, (
        f"a plant financed at the merchant rate cannot ask for less: "
        f"{levelled_cost:,.0f} against {base_cost:,.0f}"
    )


def test_a_plant_can_be_closed_by_policy_rather_than_economics(settings, small):
    """Forced closure is separate from the economic exit rule and deliberately so.
    Exit is a decision a firm takes when its going-forward position turns negative
    twice; this is a closure the world imposes, and gating both on one switch would
    let a run with economic exit turned off quietly ignore a policy as well."""
    from esem_sandbox.core.simulate import forced_retirements

    base = run(settings, ticks=TICKS, seed=SEED, cells=small)
    early = run(settings, ticks=TICKS, seed=SEED, cells=small,
                retire={"coal_b": 2029})
    fleet = {u.unit: u for u in early.fleet}
    assert fleet["coal_b"].retirement_year == 2029
    assert _fingerprint(early) != _fingerprint(base), (
        "closing 2.6 GW of coal early has to change something"
    )


def test_retiring_plant_that_does_not_exist_fails_loudly(settings):
    from esem_sandbox.core.simulate import forced_retirements

    with pytest.raises(ValueError, match="does not exist"):
        forced_retirements(settings.fleet, {"coal_z": 2030}, 2026)


def test_plant_cannot_be_retired_before_the_run_starts(settings):
    """A plant that never operates should be taken out of the fleet, not retired in
    the past, or the run reports capacity it never had."""
    from esem_sandbox.core.simulate import forced_retirements

    with pytest.raises(ValueError, match="before the run starts"):
        forced_retirements(settings.fleet, {"coal_b": 2020}, 2026)


def test_no_forced_retirement_leaves_the_fleet_exactly_as_it_was(settings):
    from esem_sandbox.core.simulate import forced_retirements

    assert forced_retirements(settings.fleet, None, 2026) is settings.fleet
    assert forced_retirements(settings.fleet, {}, 2026) is settings.fleet


def test_a_market_that_has_to_find_a_price_trades_less_than_one_that_assumes_it(
        settings, small):
    """What the bid-curve extension is for.

    The core path clears at an anchor: both sides accept it and the whole volume
    trades. The extension makes them find each other, and only what both wanted
    trades. The difference between the two runs is the price of that assumption, and
    on this market it is about two fifths of the contracted volume, which then shows
    up in every producer's exposure and so in every hurdle.
    """
    anchored = run(settings, ticks=4, seed=SEED, cells=small)
    crossed = run(settings, ticks=4, seed=SEED, cells=small, clearing="crossing")
    volume = lambda r: sum(c.volume_mw for c in r.book if c.kind == SWAP)
    assert volume(crossed) < volume(anchored) * 0.8, (
        f"{volume(crossed):,.0f} against {volume(anchored):,.0f} MW"
    )
    assert min(crossed.ticks[-1].swap_cover.values()) < \
        min(anchored.ticks[-1].swap_cover.values()), (
        "less cover bought has to mean less cover held"
    )


def test_an_unknown_clearing_rule_fails_rather_than_falling_back(settings, small):
    with pytest.raises(ValueError, match="clearing"):
        run(settings, ticks=1, seed=SEED, cells=small, clearing="whatever")


def test_the_scheme_never_records_more_firm_capacity_than_it_built(settings, small):
    """Clearing hands back a part-filled bid and the award rounds it down to whole
    generating units. Carrying the pre-rounding firm figure across that made the
    scheme report contracting capacity it had not built, and pay for it: the strike
    spreads the bid over the contracted volume, and the bid was sized on firm
    megawatts that no longer existed."""
    from esem_sandbox.core.esem import firm_contribution_mw
    from esem_sandbox.core.simulate import ESEM

    result = run(settings, ticks=6, seed=SEED, cells=small, leg=ESEM)
    awards = [a for t in result.ticks for a in t.awards]
    assert awards, "the lane awarded nothing, so this test proves nothing"
    for award in awards:
        tech = settings.tech(award.technology)
        ceiling = award.capacity_mw * tech.availability
        assert award.firm_mw <= ceiling + 1e-9, (
            f"{award.technology} recorded {award.firm_mw:,.1f} firm MW from "
            f"{award.capacity_mw:,.0f} MW of plant, which cannot deliver more than "
            f"{ceiling:,.1f}"
        )
        assert award.capacity_mw % tech.unit_size_mw == 0


def test_the_scheme_builds_inside_the_same_ceiling_as_everybody_else(settings, small):
    """One supply chain builds a scheme's wind farm and a merchant's. Letting the
    scheme build on top of the annual ceiling rather than inside it made a policy
    look like it added capacity when what it added was permission the model had not
    granted anybody else."""
    from esem_sandbox.core.investment import build_ceiling_mw

    result = run(settings, ticks=8, seed=SEED, cells=small, scheme=True)
    for tick in result.ticks:
        totals: dict[str, float] = {}
        for b in tick.builds:
            totals[b.technology] = totals.get(b.technology, 0.0) + b.capacity_mw
        awarded = (tick.scheme_year.awarded_by_technology
                   if tick.scheme_year else None) or {}
        for tech, mw in awarded.items():
            totals[tech] = totals.get(tech, 0.0) + mw
        for tech, mw in totals.items():
            ceiling = build_ceiling_mw(tick.peak_mw, settings.tech(tech), settings)
            assert mw <= ceiling + 1e-9, (
                f"{tick.year}: {mw:,.0f} MW of {tech} against a ceiling of "
                f"{ceiling:,.0f}, counting the scheme's awards"
            )


def test_a_capacity_target_buys_capacity_and_not_reliability(settings, small):
    """The distinction the two instruments exist to show, measured rather than
    argued.

    The reliability lane buys DELIVERED FIRM megawatts, sized on the shortfall, and
    the reliability outcome moves. A capacity target buys NAMEPLATE megawatts against
    a number in a policy. On this fleet it adds 2,350 MW of wind and solar, displaces
    1,600 MW of merchant wind through the shared build ceiling, spends five million
    dollars, and changes unserved energy by nothing at all.

    That is not a criticism of capacity targets. It is what a firm factor of a tenth
    means, and a model that could not show it would be a model in which any megawatt
    was as good as any other.
    """
    without = run(settings, ticks=8, seed=SEED, cells=small)
    with_scheme = run(settings, ticks=8, seed=SEED, cells=small, scheme=True)

    awarded = 0.0
    for tick in with_scheme.ticks:
        if tick.scheme_year:
            awarded += sum((tick.scheme_year.awarded_by_technology or {}).values())
    assert awarded > 1_000.0, "the scheme awarded almost nothing, so this proves little"

    built = lambda r: sum(r.built_by_technology().values())
    assert built(with_scheme) + awarded > built(without), (
        "the scheme has to add capacity, or there is nothing to compare"
    )
    assert with_scheme.total_unserved_gwh == pytest.approx(
        without.total_unserved_gwh), (
        f"{awarded:,.0f} MW of nameplate wind and solar moved unserved energy from "
        f"{without.total_unserved_gwh:.3f} to {with_scheme.total_unserved_gwh:.3f} "
        "GWh, which on these firm factors it should not"
    )


def test_a_milestone_can_be_missed_because_nobody_could_build_it_that_fast(
        settings, small):
    """A real reason a target is missed, and one that was invisible until the scheme
    was made to share the annual build ceiling. Recording it as a supply failure
    would say nobody wanted to sell, which is the opposite of what happened."""
    from esem_sandbox.core.scheme import BUILD_CEILING

    result = run(settings, ticks=8, seed=SEED, cells=small, scheme=True)
    reasons = [t.scheme_year.binding for t in result.ticks
               if t.scheme_year and t.scheme_year.sought_mw > 0]
    assert reasons, "no milestone fell inside this horizon"
    assert BUILD_CEILING in reasons, reasons
    for tick in result.ticks:
        year = tick.scheme_year
        if year and year.binding == BUILD_CEILING:
            assert year.awarded_mw < year.sought_mw
            assert year.shortfall_mw > 0
