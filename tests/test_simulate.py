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
