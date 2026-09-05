"""The tick loop, as a whole.

These run on a reduced lattice and a short horizon. The lattice size does not
change any of the properties tested here - they are conservation laws, orderings
and coincidences, not levels - and a full 45 cell 20-year run costs
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


@pytest.mark.parametrize("seed", [20260904, 20260101, 19990101, 111])
def test_longer_cover_never_leaves_the_system_less_reliable(settings, small, seed):
    """A 10-year underwrite lowers every hurdle, and the reliability outcome may not
    get worse for it.

    Reliability rather than firm megawatts, because a lower hurdle changes what gets
    built as well as how much. On these four draws cover reduces firm capacity three
    times, by up to 795 MW, while unserved energy falls or holds every time: the
    cheaper hurdle buys storage and solar in place of gas, and the fleet delivers
    more from less firm plant. Pinning firm capacity would pin the mix.
    """
    underwritten = load_settings({"investment": {"merchant_underwrite_years": 10}})
    plain = run(settings, ticks=TICKS, seed=seed, cells=small)
    with_cover = run(underwritten, ticks=TICKS, seed=seed, cells=small)
    assert with_cover.total_unserved_gwh <= plain.total_unserved_gwh + 1e-6, (
        f"seed {seed}: {with_cover.total_unserved_gwh:.3f} GWh unserved with cover "
        f"against {plain.total_unserved_gwh:.3f} without"
    )


def test_the_build_ceiling_is_not_captured_by_whoever_is_asked_first(settings, small):
    """The ceiling is shared, so whoever is asked first gets it. With a fixed order
    that is the same firm every year: over 20 years the merchant and the
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
    """The levy is whatever balances the administrator's books, and it can go either
    way. It buys hedges struck on a projection four years out and sells them at the
    market price for each delivery, so consumers pay when prices come in below that
    projection and are paid when they come in above it. What it may not do is fail to
    reach the consumer view.
    """
    from esem_sandbox.core.simulate import ESEM
    scheme = run(settings, ticks=4, seed=SEED, cells=small, leg=ESEM)
    assert scheme.total_levy == pytest.approx(
        sum(t.levy_per_mwh * t.consumed_mwh for t in scheme.ticks))
    for tick in scheme.ticks:
        assert tick.levy_per_mwh * tick.consumed_mwh == pytest.approx(
            -tick.administrator_net + tick.administrator_overhead), (
            f"{tick.year}: the levy is not the administrator's net plus its overhead"
        )
    first = scheme.ticks[0]
    assert first.levy_per_mwh > 0, (
        "an administrator costs money to run before it has bought anything"
    )


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

    The reliability lane buys DELIVERED FIRM megawatts, sized on the shortfall. A
    capacity target buys NAMEPLATE megawatts against a number in a policy, and on
    this fleet 3,950 MW of awarded wind and solar leave firm capacity exactly where
    it was. None of the nameplate arrives as firm capacity, which is what a firm
    factor of a tenth means.

    Unserved energy still moves, and not because the awards delivered any of it. The
    target displaces merchant gas and wind through the shared build ceiling, and the
    market spends the freed room on storage. What the target changes is the mix it
    crowds out, and that is a second-order effect of the same firm factor.
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
    firm = lambda r: r.ticks[-1].firm_capacity_mw
    assert firm(with_scheme) == pytest.approx(firm(without)), (
        f"{awarded:,.0f} MW of nameplate wind and solar changed firm capacity from "
        f"{firm(without):,.0f} to {firm(with_scheme):,.0f} MW, which on a firm "
        "factor of a tenth it should not"
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


# --------------------------------------------------------------------------
# Four decisions against one forecast, or four in sequence


def test_an_unknown_investment_rule_fails_loudly(settings, small):
    """A scenario that names the rule wrongly must not quietly get the default."""
    with pytest.raises(ValueError, match="unknown investment rule"):
        run(settings, ticks=1, seed=SEED, cells=small, investment="sequentiall")


def test_the_default_rule_is_the_one_the_published_outputs_were_made_with(
        settings, small, baseline):
    """Naming the default explicitly must change nothing. The coincidence test every
    switch here has to pass: a leg that differs from the baseline while its own
    mechanism is doing nothing is a leg whose comparison means nothing."""
    explicit = run(settings, ticks=TICKS, seed=SEED, cells=small,
                   investment="simultaneous")
    assert _fingerprint(explicit) == _fingerprint(baseline)


def _share_at_the_ceiling(result, settings) -> float:
    total = at_cap = 0.0
    for tick in result.ticks:
        by_tech: dict[str, float] = {}
        for b in tick.builds:
            by_tech[b.technology] = by_tech.get(b.technology, 0.0) + b.capacity_mw
        for technology, mw in by_tech.items():
            total += mw
            if mw >= build_ceiling_mw(12_500.0, settings.tech(technology),
                                      settings) - 1e-6:
                at_cap += mw
    return at_cap / total if total else 0.0


def test_repricing_between_producers_stops_every_build_landing_on_the_ceiling(
        settings, small):
    """The property the sequential rule exists for, and the defect it answers.

    Under the default, every producer prices its candidate as a marginal addition to
    a market containing none of the others. The price feedback that should discipline
    that is real but far too weak to bind in one year: each 600 MW of wind takes about
    $50,000 per MW-year off the next block and adds about $6,000 to its hurdle,
    against an opening gap of $367,000, so closing it would take around 4,000 MW while
    the ceiling stops at 1,200. Each producer wants exactly one block, so four of them
    picking the same winner fill a ceiling that allows two, and the measured result is
    that ALL of the build lands on the ceiling - which makes the annual build volume a
    parameter rather than a result.

    Rebuilding the forward between producers breaks that. It is not a free
    improvement and this test does not claim it is one: perfect mutual observation is
    as much an idealisation as none at all, and it under-builds badly. What is pinned
    here is only the mechanism - that the repair reaches the thing it was aimed at.
    """
    default = run(settings, ticks=TICKS, seed=SEED, cells=small)
    sequential = run(settings, ticks=TICKS, seed=SEED, cells=small,
                     investment="sequential")
    assert _share_at_the_ceiling(default, settings) >= 0.9, (
        "if the default ever stops piling build onto the ceiling, the limitation "
        "this option answers has gone and the option needs re-justifying"
    )
    assert _share_at_the_ceiling(sequential, settings) < 0.75
    assert _fingerprint(sequential) != _fingerprint(default)


def test_a_short_run_is_a_prefix_of_a_long_one(settings):
    """One seed, two horizons: the shorter run's weather must be the longer run's
    opening years.

    The peak band used to be drawn from the same generator as the shape year, after
    it, so how many bands came out depended on how many shapes had been drawn first.
    A four-year run and a 20-year run on one seed therefore saw different peak
    bands in the same calendar years. The shape years were a prefix and the bands were
    not, which is the tell: it was the order of two calls and not a decision. The
    exercises run at reduced horizons, so this is where it mattered.
    """
    for seed in (SEED, 111, 7):
        short, long = draw_sequence(settings, seed, 4), draw_sequence(settings, seed, 20)
        k = len(short.shape_years)
        assert short.growth_path == long.growth_path, f"seed {seed}: path moved"
        assert short.shape_years == long.shape_years[:k], f"seed {seed}: shapes"
        assert short.peak_bands == long.peak_bands[:k], (
            f"seed {seed}: the peak bands depend on the horizon, so a short run is "
            "not a preview of a long one"
        )


def test_an_award_does_not_hedge_a_producers_unrelated_merchant_plant(settings, small):
    """Winning an auction hedges the plant that won it, and nothing else.

    The award flag used to be set to 1.0 on any win and never cleared or scoped to
    the awarded unit, so from a producer's first award to the end of the run every
    merchant project it priced carried a 12-year hedge it did not have. It biased
    only the ESEM leg, which is one half of the comparison the model exists to make.
    """
    from esem_sandbox.core.simulate import ESEM

    result = run(settings, ticks=6, seed=SEED, cells=small, leg=ESEM)
    winners = {a.bidder for t in result.ticks for a in t.awards}
    assert winners, "this run is meant to award something"
    theirs = [b for t in result.ticks for b in t.builds if b.owner in winners]
    assert theirs, "and the winners are meant to build merchant plant as well"

    # A merchant build may of course be partly covered by the producer's own swap
    # book. What it may NOT carry is the award channel, which is far longer: the
    # bilateral book covers three years of a life, an award 12. So the ceiling
    # a legitimately hedged merchant build can reach is the bilateral one.
    cap = float(settings.investment["hedge_fraction_cap"])
    bilateral = int(settings.investment["bilateral_contract_years"])
    award = int(settings.esem["contract_tenor_years"])
    for build in theirs:
        life = settings.tech(build.technology).life_years
        ceiling = cap * min(bilateral, life) / life
        assert build.contracted_share <= ceiling + 1e-9, (
            f"{build.owner}'s merchant {build.technology} is priced as "
            f"{build.contracted_share:.3f} contracted, above the {ceiling:.3f} its "
            f"bilateral book can reach: it is carrying the {award}-year award "
            "channel, which belongs to the plant that won the auction"
        )


def test_a_tenor_of_zero_is_an_auction_with_no_contract(settings, small):
    """A documented setting: the notebook invites a reader to try 6, then 0.

    Zero used to raise "tenor must be at least one year" partway through the run, so
    the exercise could not be run at all. Zero means no contract, which is what the
    scenario file always said it meant: the lane still buys, and the cost of capital
    it would otherwise have bought down is left alone.
    """
    from esem_sandbox.core.simulate import ESEM

    none = load_settings({"esem": {"contract_tenor_years": 0}})
    result = run(none, ticks=4, seed=SEED, cells=small, leg=ESEM)
    assert result.total_awarded_mw > 0, "the lane should still award"
    assert not [c for c in result.book if c.holder == "administrator"], (
        "a tenor of zero must write no award contract at all"
    )


def test_a_ladder_rung_does_not_depend_on_the_tenor_it_is_written_for(settings):
    """A strip is one rung of a ladder, so its size is the target over the ladder
    LENGTH and not over the contract's remaining life.

    The bootstrap clears three times, at tenors three, two and one, so that tick zero
    opens on a laddered book rather than on a market that has never traded. Sizing
    each strip by the tenor passed wrote them at a third, a half and the whole of the
    target, and all three are in force at tick zero: a run opened at 1.833 times the
    cover a retailer actually wanted, which lowered every producer's exposure and so
    every early hurdle.

    Hold everything else fixed and vary only the tenor. The volumes must not move.
    """
    import numpy as np
    from esem_sandbox.core.agents import default_roster
    from esem_sandbox.core.clearing import clear_bilateral

    roster = default_roster()
    history = [{"overnight": 40.0, "morning": 55.0, "solar": 20.0, "peak": 90.0}]
    common = dict(
        year=2026, start_year=2026, average_load_mw=6000.0, peak_load_mw=12500.0,
        cap_payoffs_per_mw=np.array([50_000.0]), cap_weights=np.array([1.0]),
        cap_cost_basis_per_mwh=12.0,
    )
    from esem_sandbox.core.contracts import CAP

    volumes = {SWAP: {}, CAP: {}}
    for tenor in (3, 2, 1):
        book = clear_bilateral(settings, roster, settings.fleet, history,
                               tenor_years=tenor, **common)
        for kind in (SWAP, CAP):
            rungs = sorted(round(c.volume_mw, 9) for c in book if c.kind == kind)
            assert rungs, f"tenor {tenor} wrote no {kind}s"
            volumes[kind][tenor] = rungs

    # BOTH lanes. The cap lane ladders on the same schedule and had the same divisor,
    # and fixing only the swap lane left half the book still over-hedged at tick zero.
    for kind in (SWAP, CAP):
        v = volumes[kind]
        assert v[3] == v[2] == v[1], (
            f"the {kind} rung changed size with the contract's tenor, so the "
            f"bootstrap's three clears write different fractions of one target: "
            f"{v[3][:2]} at tenor three against {v[1][:2]} at tenor one"
        )


def test_sequential_repricing_changes_only_the_plant_just_decided(settings, small):
    """The repriced view must differ from the previous producer's by the plant that
    was decided and by nothing else.

    Step 5 builds the forward view on one belief about how much everybody else
    builds, and then advances that belief by a step. The repricing closure used to
    read the advanced one, so the second producer in a tick faced a market containing
    the first producer's plant AND a whole extra step of assumed entry. That is not
    the mechanism the sequential rule exists to isolate, and the rule is one end of
    the bracket this model reports on how much a market builds.

    Checked by running the rule and confirming it still differs from the default:
    the guard is the assertion below plus the comment at simulate.py step 5, because
    the belief is captured in a closure and cannot be reached from outside.
    """
    from esem_sandbox.core.simulate import MERCHANT

    paced = run(settings, ticks=6, seed=SEED, cells=small, leg=MERCHANT,
                investment="sequential")
    blind = run(settings, ticks=6, seed=SEED, cells=small, leg=MERCHANT)
    built = lambda r: sum(b.capacity_mw for t in r.ticks for b in t.builds)
    assert built(paced) != built(blind), (
        "the two investment rules built exactly the same fleet, so the bracket this "
        "model reports has collapsed and one end of it is not doing anything"
    )
    assert built(paced) < built(blind), (
        "repricing after each producer should build LESS, not more: each one is "
        "offered a market that already contains what the last one decided"
    )
