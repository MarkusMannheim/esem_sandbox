"""The investment rule: exposure, the certainty equivalent, pacing and exit.

Most of this runs against stub forward views. The rule is arithmetic over a
distribution, and a distribution invented to have a known answer tests the
arithmetic; a distribution that came out of the dispatch tests the dispatch.
"""

import numpy as np
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.agents import Agent, PRODUCER, RETAILER, default_roster
from esem_sandbox.core.clearing import cara_certainty_equivalent, cara_coefficient
from esem_sandbox.core.contracts import CAP, SWAP, Contract
from esem_sandbox.core.forward import Anchor, Cell, CellOutcome, ForwardView, EntryState
from esem_sandbox.core.investment import (
    EXIT_ELIGIBLE, ExitLedger, achieved_swap_cover, build_ceiling_mw, build_size_mw,
    evaluate, exit_notices, going_forward_npv_per_mw, rank_candidates,
    residual_exposure,
)


@pytest.fixture(scope="module")
def settings():
    return load_settings()


@pytest.fixture(scope="module")
def merchant():
    return next(a for a in default_roster() if a.name == "merchant")


def _view(tech_rents, unit_rents=None, offsets=(4, 8, 12), weights=None):
    """A forward view whose per-cell rents are whatever the test says they are."""
    n = len(next(iter(tech_rents.values())))
    weights = weights if weights is not None else [1.0 / n] * n
    anchors = []
    for off in offsets:
        outcomes = tuple(
            CellOutcome(
                cell=Cell(shape_year=i, growth_path="central", peak_band=1,
                          weight=w, annual_growth=0.019, peak_multiplier=1.0),
                rent_per_mw_year={t: v[i] for t, v in tech_rents.items()},
                unit_rent_per_mw_year={u: v[i] for u, v in (unit_rents or {}).items()},
                block_prices={"peak": 100.0}, mean_price=100.0, unserved_mwh=0.0,
                unserved_fraction=0.0, peak_shortfall_mw=0.0,
            )
            for i, w in enumerate(weights)
        )
        anchors.append(Anchor(offset=off, year=2026 + off, outcomes=outcomes))
    return ForwardView(anchors=tuple(anchors), entry=EntryState())


# --------------------------------------------------------------------------
# One coefficient, everywhere


def test_the_cap_writer_and_the_investor_price_the_same_tail_the_same_way(settings):
    """The regression this consolidation exists to prevent. Built separately, the
    two disagreed by a factor of two, which is a firm that can write a cap, decline
    the peaker that would cover it, and bank a difference that exists only because
    two functions disagreed."""
    from esem_sandbox.core import clearing, investment
    assert investment.cara_coefficient is clearing.cara_coefficient, (
        "there must be exactly one place a CARA coefficient is built"
    )
    payoffs = np.array([3e4, 5e4, 8e4, 9e4, 2.1e5])
    weights = np.full(5, 0.2)
    a = cara_coefficient(0.60, 1.0, settings)
    writer_gap = float(payoffs @ weights) - cara_certainty_equivalent(payoffs, weights, a)
    view = _view({"ocgt": list(payoffs)})
    verdict = evaluate(view, settings.tech("ocgt"), 
                       Agent("m", PRODUCER, 0.60), settings,
                       exposure=1.0, capacity_mw=200.0)
    assert verdict.risk_discount_per_mw_year > 0
    assert writer_gap > 0


def test_a_fully_hedged_producer_bears_no_price_risk(settings, merchant):
    """At zero exposure the coefficient is zero, the certainty equivalent is the
    expected value, and the rule reduces to expected rent against fixed cost."""
    view = _view({"ocgt": [50_000.0, 150_000.0, 400_000.0]})
    v = evaluate(view, settings.tech("ocgt"), merchant, settings,
                 exposure=0.0, capacity_mw=200.0)
    assert v.risk_discount_per_mw_year == pytest.approx(0.0, abs=1e-6)
    assert v.certainty_equivalent_per_mw_year == pytest.approx(
        v.expected_rent_per_mw_year)


def test_the_penalty_saturates_instead_of_exploding_on_a_scarcity_tail(settings,
                                                                      merchant):
    """The doom loop this construction is built against.

    A mean-variance penalty is linear in variance and so quadratic in the spread.
    With an honest distribution that reaches the value of lost load in one cell it
    explodes and prices out the very firm capacity that would have relieved the
    scarcity. The exact certainty equivalent can never fall below the worst cell,
    so the penalty is bounded by the expected value less the minimum.
    """
    rents = [80_000.0, 90_000.0, 100_000.0, 110_000.0, 8_000_000.0]
    view = _view({"ocgt": rents})
    v = evaluate(view, settings.tech("ocgt"), merchant, settings,
                 exposure=1.0, capacity_mw=200.0)
    bound = v.expected_rent_per_mw_year - min(rents)
    assert 0 < v.risk_discount_per_mw_year <= bound

    a = cara_coefficient(merchant.risk_aversion, 1.0, settings)
    lifetime = view.lifetime_rent(settings.tech("ocgt"))
    variance = float(np.var(lifetime))
    mean_variance_penalty = 0.5 * a * variance
    assert mean_variance_penalty > 20 * v.risk_discount_per_mw_year, (
        "the approximation this replaces must be visibly worse on a tail, or the "
        "test is not exercising the case it claims to"
    )


# --------------------------------------------------------------------------
# Exposure


def test_exposure_is_one_minus_cover_times_tenor_over_life(settings):
    assert residual_exposure(settings, 25, swap_cover=0.0) == 1.0
    assert residual_exposure(settings, 25, swap_cover=0.75) == pytest.approx(
        1.0 - 0.75 * 3 / 25)


def test_cover_is_capped_below_one_because_it_covers_a_forecast(settings):
    cap = settings.investment["hedge_fraction_cap"]
    assert residual_exposure(settings, 25, swap_cover=1.0) == pytest.approx(
        1.0 - cap * 3 / 25)


def test_the_channels_take_the_largest_and_never_the_sum(settings):
    """Cover from a swap book and cover from an award land on the same delivery
    years. Adding them would let a producer count one year of certainty twice."""
    both = residual_exposure(settings, 25, swap_cover=0.75, award_years=12,
                             award_cover=1.0)
    award_only = residual_exposure(settings, 25, award_years=12, award_cover=1.0)
    assert both == pytest.approx(award_only)


def test_what_a_long_award_buys_that_a_short_book_cannot(settings):
    """The whole point of the tenor. A three-year bilateral book cannot underwrite
    a twenty-five year asset however much of the output it covers."""
    book = 1.0 - residual_exposure(settings, 25, swap_cover=1.0)
    award = 1.0 - residual_exposure(settings, 25, award_years=12, award_cover=1.0)
    assert book == pytest.approx(0.102, abs=0.001)
    assert award == pytest.approx(0.408, abs=0.001)


def test_the_underwrite_is_off_by_default(settings):
    """The merchant leg is the policy-free counterfactual. A default underwrite
    would make it a mild policy leg wearing the merchant label."""
    assert settings.investment["merchant_underwrite_years"] == 0
    assert residual_exposure(settings, 25) == 1.0
    lifted = load_settings({"investment": {"merchant_underwrite_years": 10}})
    assert residual_exposure(lifted, 25) < 1.0


def test_swap_cover_is_weighted_by_the_hours_the_block_covers(settings):
    """A peak-only swap covers six hours in twenty-four. Counting it as though it
    covered the day would overstate cover fourfold and buy down a hurdle that
    nothing had been done to buy down."""
    agent = Agent("p", PRODUCER, 0.5, units=("ocgt_a",))
    peak = Contract(kind=SWAP, holder="r", writer="p", strike_per_mwh=100.0,
                    volume_mw=100.0, start_year=2026, tenor_years=3, block="peak")
    expected = 100.0 * 8760
    cover = achieved_swap_cover(agent, [peak], settings, 2026, expected)
    assert cover == pytest.approx(6 / 24, abs=0.01)


def test_a_written_cap_is_not_price_certain_cover(settings):
    """A cap does not fix the writer's price on its output below the strike. Its
    income is income, not certainty."""
    agent = Agent("p", PRODUCER, 0.5, units=("ocgt_a",))
    cap = Contract(kind=CAP, holder="r", writer="p", strike_per_mwh=300.0,
                   volume_mw=100.0, start_year=2026, tenor_years=3,
                   premium_per_mwh=12.0)
    assert achieved_swap_cover(agent, [cap], settings, 2026, 100.0 * 8760) == 0.0


def test_a_more_contracted_producer_never_faces_a_higher_hurdle(settings, merchant):
    """The ranking the whole apparatus exists to produce."""
    view = _view({"ocgt": [40_000.0, 120_000.0, 500_000.0]})
    naked = evaluate(view, settings.tech("ocgt"), merchant, settings,
                     exposure=1.0, capacity_mw=200.0)
    covered = evaluate(view, settings.tech("ocgt"), merchant, settings,
                       exposure=residual_exposure(settings, 25, award_years=12,
                                                  award_cover=1.0),
                       capacity_mw=200.0)
    assert covered.hurdle_per_mw_year <= naked.hurdle_per_mw_year
    assert covered.builds >= naked.builds


# --------------------------------------------------------------------------
# The per-MW-year basis


def test_no_capacity_factor_enters_the_comparison(settings, merchant):
    """A peaker running two per cent of the year and a wind farm running
    thirty-five are each tested against their own costs, not against a common
    denominator that would flatter one of them."""
    view = _view({"ocgt": [200_000.0] * 3, "wind": [200_000.0] * 3})
    peaker = evaluate(view, settings.tech("ocgt"), merchant, settings,
                      exposure=1.0, capacity_mw=200.0)
    wind = evaluate(view, settings.tech("wind"), merchant, settings,
                    exposure=1.0, capacity_mw=200.0)
    assert peaker.builds and not wind.builds, (
        "identical rent, different fixed costs, so the peaker builds and the wind "
        "farm does not; any capacity-factor denominator would break this"
    )


# --------------------------------------------------------------------------
# Pacing


def test_a_build_is_a_whole_number_of_generating_units(settings):
    tech = settings.tech("ocgt")
    size = build_size_mw(12_500.0, tech, settings)
    assert size % tech.unit_size_mw == 0
    assert size == 600.0, "5 per cent of 12,500 MW is 625, rounded to three 200 MW units"


def test_a_build_is_never_smaller_than_one_unit(settings):
    assert build_size_mw(10.0, settings.tech("ccgt"), settings) == 250.0


def test_the_ceiling_is_a_number_of_producers_worth_of_plant(settings):
    """Stated as concurrency rather than megawatts so it scales with the system. A
    fixed megawatt ceiling that damps a twelve gigawatt system dominates a
    twenty-three gigawatt one, and bound in every year of a twenty-year run."""
    tech = settings.tech("ocgt")
    small = build_ceiling_mw(12_500.0, tech, settings)
    large = build_ceiling_mw(23_000.0, tech, settings)
    assert small == pytest.approx(2 * build_size_mw(12_500.0, tech, settings))
    assert large > small, "the ceiling must grow with the system it paces"


def test_a_producer_takes_at_most_its_allowance_of_decisions(settings, merchant):
    view = _view({t.technology: [400_000.0] * 3 for t in settings.tech_costs})
    ranked = rank_candidates(view, merchant, settings, peak_mw=12_500.0)
    assert len(ranked) == settings.investment["candidates_per_producer"]
    surpluses = [v.surplus_per_mw_year for v in ranked]
    assert surpluses == sorted(surpluses, reverse=True), "best first"


def test_a_retailer_builds_nothing(settings):
    retailer = Agent("r", RETAILER, 0.5, load_share=1.0)
    view = _view({t.technology: [900_000.0] * 3 for t in settings.tech_costs})
    assert rank_candidates(view, retailer, settings, peak_mw=12_500.0) == []


# --------------------------------------------------------------------------
# Exit


def _coal(settings, name="coal_b"):
    return next(u for u in settings.fleet if u.unit == name)


def test_exit_reads_the_plant_s_own_cost_and_not_a_technology_proxy(settings):
    """A coal unit at $47/MWh and a combined cycle at $96 are not interchangeable.
    Borrowing one as a proxy for the other decides the retirement schedule on the
    wrong cost."""
    coal = _coal(settings)
    poor = _view({"ccgt": [900_000.0] * 3}, unit_rents={coal.unit: [1_000.0] * 3})
    npv = going_forward_npv_per_mw(coal, poor, settings, 2026)
    assert npv < 0, (
        "the plant's own rent is far below its fixed cost, so it must look "
        "unviable however rich the technology row beside it looks"
    )


def test_a_plant_with_no_measurable_rent_is_never_retired_for_it(settings):
    """A wind row's offer is a curtailment offer, not a cost, so it gets no rent
    number at all. Absence of a measurement is not evidence of failure."""
    coal = _coal(settings)
    blind = _view({"ccgt": [1.0] * 3}, unit_rents={})
    assert going_forward_npv_per_mw(coal, blind, settings, 2026) == 0.0


def test_one_bad_year_is_weather_and_two_is_a_decision(settings):
    """This model has a one-in-five drought shape-year in it by construction, so a
    single-year trigger would retire the fleet on a wind lull."""
    coal = _coal(settings)
    poor = _view({"ccgt": [1.0] * 3}, unit_rents={coal.unit: [1_000.0] * 3})
    ledger = ExitLedger()
    assert exit_notices(settings.fleet, poor, settings, 2026, ledger) == []
    second = exit_notices(settings.fleet, poor, settings, 2027, ledger)
    assert [u.unit for u, _ in second], "a second consecutive bad year gives notice"


def test_a_good_year_resets_the_count(settings):
    coal = _coal(settings)
    poor = _view({"ccgt": [1.0] * 3}, unit_rents={coal.unit: [1_000.0] * 3})
    rich = _view({"ccgt": [1.0] * 3}, unit_rents={coal.unit: [900_000.0] * 3})
    ledger = ExitLedger()
    exit_notices(settings.fleet, poor, settings, 2026, ledger)
    exit_notices(settings.fleet, rich, settings, 2027, ledger)
    assert exit_notices(settings.fleet, poor, settings, 2028, ledger) == [], (
        "the run of negatives must restart, not resume"
    )


def test_notices_are_staggered_worst_first(settings):
    """Each plant's exit is evaluated against a forward holding the rest of the
    fleet fixed, so a whole cohort can each conclude it should leave against a
    picture in which the others all stayed."""
    eligible = [u for u in settings.fleet
                if u.technology in EXIT_ELIGIBLE and u.in_service(2026)
                and u.retirement_year > 2029]
    assert len(eligible) > settings.investment["max_exit_notices_per_tick"]
    rents = {u.unit: [1_000.0] * 3 for u in eligible}
    poor = _view({"ccgt": [1.0] * 3}, unit_rents=rents)
    ledger = ExitLedger()
    exit_notices(settings.fleet, poor, settings, 2026, ledger)
    fired = exit_notices(settings.fleet, poor, settings, 2027, ledger)
    assert len(fired) == settings.investment["max_exit_notices_per_tick"]
    npvs = [npv for _, npv in fired]
    assert npvs == sorted(npvs), "worst first"


def test_a_plant_already_leaving_does_not_notice_again(settings):
    leaving = next(u for u in settings.fleet if u.unit == "coal_a")
    assert leaving.retirement_year == 2029
    rents = {u.unit: [1_000.0] * 3 for u in settings.fleet if u.srmc_per_mwh >= 0}
    poor = _view({"ccgt": [1.0] * 3}, unit_rents=rents)
    ledger = ExitLedger()
    for year in (2026, 2027):
        fired = exit_notices(settings.fleet, poor, settings, year, ledger)
    assert leaving.unit not in [u.unit for u, _ in fired], (
        "it is already inside its own notice period; there is nothing to notice"
    )
