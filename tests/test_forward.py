"""The forward view: the lattice, the rent basis and the free-entry fixed point.

The convergence tests run against a stub rent curve rather than the dispatch. That
is deliberate and it is the same discipline the contract stack was built under: a
state machine tested only through a plausible-looking market can be rescued by the
market, and the thing under test here is whether the rule converges at all.
"""

import numpy as np
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.forward import (
    Anchor, Cell, CellOutcome, EntryState, cell_plan, dispatch_anchor,
    interpolated_rent, lifetime_rent_by_cell, lifetime_rent_per_mw_year,
    peak_banded, rent_per_mw_year, update_projected_entry,
)
from esem_sandbox.core.weather import generate_bundle


@pytest.fixture(scope="module")
def settings():
    return load_settings()


# --------------------------------------------------------------------------
# The lattice


def test_the_lattice_is_forty_five_cells_at_product_weights(settings):
    cells = cell_plan(settings)
    assert len(cells) == 45, "five shape-years by three growth paths by three bands"
    assert sum(c.weight for c in cells) == pytest.approx(1.0)


def test_the_lattice_does_not_depend_on_any_seed(settings):
    """Enumerated, not sampled. Two callers must see the same futures at the same
    probabilities, or a paired comparison is comparing two different questions."""
    a = cell_plan(settings)
    b = cell_plan(load_settings())
    assert [(c.shape_year, c.growth_path, c.peak_band, c.weight) for c in a] == \
           [(c.shape_year, c.growth_path, c.peak_band, c.weight) for c in b]


def test_a_one_in_ten_peak_band_enters_at_one_in_ten(settings):
    """The defect this whole apparatus is arranged against: weights computed,
    passed everywhere, and then reduced with a plain arithmetic mean, so a
    one-in-ten-year peak entered the answer at one in three."""
    cells = cell_plan(settings)
    hot = sum(c.weight for c in cells if c.peak_multiplier == 1.08)
    assert hot == pytest.approx(0.1), (
        f"the hot band carries {hot:.3f} of the probability, not 0.1; a plain mean "
        "over the 15 hot cells of 45 would give 0.333"
    )


def test_the_peak_band_moves_the_peak_and_not_the_energy():
    demand = np.array([100.0, 200.0, 300.0, 400.0, 500.0, 250.0])
    for multiplier in (1.08, 1.00, 0.95):
        banded = peak_banded(demand, multiplier)
        assert banded.max() == pytest.approx(demand.max() * multiplier)
        assert banded.mean() == pytest.approx(demand.mean()), (
            "annual energy must be preserved exactly, not approximately: the peak "
            "band carries peak uncertainty and the shape-years carry energy, and a "
            "scalar multiple would make the demand axis carry both"
        )


# --------------------------------------------------------------------------
# The rent basis


def test_a_wind_candidate_is_not_paid_its_curtailment_offer(settings):
    """fleet.csv offers wind at minus forty-five dollars. That is what a plant will
    pay to keep running rather than forfeit a certificate this model does not
    represent; it is not a cost, and using it as the rent basis credits a candidate
    wind farm with revenue that does not exist."""
    price = np.full(8760, 40.0)
    cf = np.full(8760, 0.35)
    tech = settings.tech("wind")
    assert tech.srmc_per_mwh == 0.0, "the candidate table states cost, not offer"
    rent = rent_per_mw_year(price, tech, settings, cf)
    assert rent == pytest.approx(40.0 * 0.35 * 8760)
    offer_basis = float(np.sum(np.clip(price - (-45.0), 0.0, None) * cf))
    assert offer_basis - rent == pytest.approx(45.0 * 0.35 * 8760, rel=1e-9)
    assert offer_basis - rent > 130_000, (
        "using the offer would add about $138,000 per MW-year of invented revenue"
    )


def test_a_price_taker_earns_nothing_in_an_hour_below_its_cost(settings):
    """Curtailment is priced, not scheduled. In a surplus hour the price is under
    the candidate's cost, and a plant that takes the price simply stops."""
    price = np.concatenate([np.full(4380, 100.0), np.full(4380, -80.0)])
    cf = np.full(8760, 0.4)
    rent = rent_per_mw_year(price, settings.tech("solar"), settings, cf)
    assert rent == pytest.approx(100.0 * 0.4 * 4380)


def test_thermal_rent_is_the_positive_margin_times_availability(settings):
    price = np.concatenate([np.full(100, 500.0), np.full(8660, 20.0)])
    tech = settings.tech("ocgt")
    expected = (500.0 - tech.srmc_per_mwh) * 100 * tech.availability
    assert rent_per_mw_year(price, tech, settings) == pytest.approx(expected)


def test_storage_rent_uses_the_scheduler_that_will_govern_it(settings):
    """A candidate valued by a cleaner rule than the one that will dispatch it once
    built is valued at a spread it can never realise."""
    rng = np.random.default_rng(7)
    price = 80.0 + 60.0 * np.sin(np.arange(8760) * 2 * np.pi / 24) + rng.normal(0, 5, 8760)
    four = rent_per_mw_year(price, settings.tech("battery_4h"), settings)
    two = rent_per_mw_year(price, settings.tech("battery_2h"), settings)
    assert four > two > 0, "more duration earns more spread on a diurnal price"


# --------------------------------------------------------------------------
# Lifetime rent, interpolation and the terminal


def test_the_terminal_is_the_technology_s_own_cost_not_a_flat_constant(settings):
    """A flat dollar-per-MWh terminal sits below a peaker's break-even and makes
    peaking plant unbuildable for reasons that have nothing to do with the market."""
    for name in ("ocgt", "wind", "battery_8h"):
        tech = settings.tech(name)
        past_the_end = interpolated_rent({4: 1.0, 8: 1.0, 12: 1.0}, 13,
                                         tech.fixed_cost_per_mw_year)
        assert past_the_end == pytest.approx(tech.fixed_cost_per_mw_year), (
            f"{name} must earn exactly its own long-run cost past the last anchor"
        )


def test_interpolation_clamps_below_the_first_anchor_and_steps_after_the_last():
    anchors = {4: 100.0, 8: 200.0, 12: 300.0}
    assert interpolated_rent(anchors, 2, 999.0) == 100.0
    assert interpolated_rent(anchors, 6, 999.0) == pytest.approx(150.0)
    assert interpolated_rent(anchors, 12, 999.0) == pytest.approx(300.0)
    assert interpolated_rent(anchors, 12.5, 999.0) == 999.0


def test_lifetime_rent_sits_between_the_anchors_and_the_terminal(settings):
    tech = settings.tech("ocgt")
    flat = tech.fixed_cost_per_mw_year
    assert lifetime_rent_per_mw_year({4: flat, 8: flat, 12: flat}, tech) == \
        pytest.approx(flat), "rent everywhere at cost must average to cost"
    rich = lifetime_rent_per_mw_year({4: 3 * flat, 8: 3 * flat, 12: 3 * flat}, tech)
    assert flat < rich < 3 * flat, (
        "a rich forward is diluted by the zero-profit tail, never erased by it"
    )


def _stub_anchor(offset, rents_by_cell, shortfall=0.0, weights=None):
    n = len(rents_by_cell)
    weights = weights if weights is not None else [1.0 / n] * n
    outcomes = tuple(
        CellOutcome(
            cell=Cell(shape_year=i, growth_path="central", peak_band=1, weight=w,
                      annual_growth=0.019, peak_multiplier=1.0),
            rent_per_mw_year={"ocgt": r}, unit_rent_per_mw_year={"ocgt_a": r},
            block_prices={"peak": 100.0},
            mean_price=100.0, unserved_mwh=0.0, unserved_fraction=0.0,
            peak_shortfall_mw=shortfall,
        )
        for i, (r, w) in enumerate(zip(rents_by_cell, weights))
    )
    return Anchor(offset=offset, year=2030 + offset, outcomes=outcomes)


def test_lifetime_rent_keeps_each_cell_whole(settings):
    """A cell is one coherent future. Averaging over cells before interpolating
    would collapse the distribution before the risk measure ever saw it, and the
    risk measure is the entire point of the investment rule."""
    tech = settings.tech("ocgt")
    anchors = [_stub_anchor(4, [50_000.0, 400_000.0]),
               _stub_anchor(8, [50_000.0, 400_000.0]),
               _stub_anchor(12, [50_000.0, 400_000.0])]
    per_cell = lifetime_rent_by_cell(anchors, tech)
    assert len(per_cell) == 2
    assert per_cell[1] > per_cell[0] * 2, (
        "the spread across futures must survive into the lifetime numbers; "
        f"got {per_cell}"
    )


# --------------------------------------------------------------------------
# The free-entry fixed point


class _StepRent:
    """A rent curve of the shape the dispatch actually produces: decreasing in
    assumed entry, and discrete, because the price is set by a merit order and a
    ladder of tranches rather than by a smooth function."""

    def __init__(self, threshold, step_dollars=30_000.0, step_mw=430.0):
        self.threshold = threshold
        self.step_dollars = step_dollars
        self.step_mw = step_mw

    def __call__(self, mw):
        raw = 1_600_000.0 - 220.0 * mw
        return max(0.0, round(raw / self.step_dollars) * self.step_dollars)


def _converge(settings, rent_curve, iterations=40, offsets=(8,)):
    state = EntryState()
    seen = []
    for _ in range(iterations):
        anchors = [_stub_anchor(o, [rent_curve(state.at(o))], shortfall=4000.0)
                   for o in offsets]
        seen.append(state.at(offsets[0]))
        state = update_projected_entry(state, anchors, settings)
    return state, seen


def test_the_fixed_point_settles_and_stays_settled(settings):
    tech = settings.tech("ocgt")
    curve = _StepRent(tech.fixed_cost_per_mw_year)
    state, seen = _converge(settings, curve)
    tail = seen[-8:]
    assert len(set(tail)) == 1, f"the state must stop moving; it ran {tail}"
    assert state.settled(8, tech.unit_size_mw)


def test_it_settles_where_the_last_entrant_still_covers_its_cost(settings):
    tech = settings.tech("ocgt")
    curve = _StepRent(tech.fixed_cost_per_mw_year)
    state, _ = _converge(settings, curve)
    settled = state.at(8)
    assert curve(settled) >= tech.fixed_cost_per_mw_year, (
        "free entry proceeds while it pays, so the fixed point is the largest "
        "assumed entry at which the last entrant still earns its cost"
    )
    assert curve(settled + tech.unit_size_mw) < tech.fixed_cost_per_mw_year, (
        "and one more unit must not pay, or the state stopped short"
    )


def test_a_rent_tolerance_could_never_have_stopped_this(settings):
    """The regression this rule exists to prevent. Rent is a step function of
    assumed entry, so there may be no quantity of entry at which rent lands inside
    a tolerance band around break-even. A rule that stops only when it lands there
    does not stop."""
    tech = settings.tech("ocgt")
    threshold = tech.fixed_cost_per_mw_year
    tolerance = threshold * 0.02          # the band the superseded rule used
    curve = _StepRent(threshold)
    reachable = {curve(mw) for mw in np.arange(0.0, 12_000.0, 1.0)}
    inside = [r for r in reachable if abs(r - threshold) <= tolerance]
    assert not inside, (
        "this stub must have no rent level inside the tolerance band, or it is not "
        "reproducing the discreteness that broke the tolerance rule"
    )


def test_no_new_entry_is_assumed_inside_the_build_lead(settings):
    """A decision that would deliver capacity two years out lies in the past, and a
    projection does not get to change the past."""
    tech = settings.tech("ocgt")
    state = EntryState()
    anchors = [_stub_anchor(o, [10 * tech.fixed_cost_per_mw_year], shortfall=4000.0)
               for o in (1, 4)]
    state = update_projected_entry(state, anchors, settings)
    assert state.at(1) == 0.0, f"lead is {tech.lead_years} years; offset 1 is inside it"
    assert state.at(4) > 0.0


def test_entry_that_cannot_pay_stays_at_zero_and_leaves_the_shortfall_visible(settings):
    """The failure mode this guards is a model reporting a market as adequate
    because it assumed the capacity that would have made it so."""
    state = EntryState()
    for _ in range(6):
        anchors = [_stub_anchor(8, [1.0], shortfall=9000.0)]
        state = update_projected_entry(state, anchors, settings)
    assert state.at(8) == 0.0


def test_the_belief_is_on_the_run_and_not_in_a_module_global(settings):
    """Two legs of a paired run must not share one belief about entry, and a test
    must not leave its state behind for the next one."""
    tech = settings.tech("ocgt")
    a, _ = _converge(settings, _StepRent(tech.fixed_cost_per_mw_year), iterations=6)
    b = EntryState()
    assert b.at(8) == 0.0 and a.at(8) > 0.0
    c = a.copy()
    c.by_offset[8].mw = 99_999.0
    assert a.at(8) != 99_999.0, "copy() must not alias the beliefs it copies"


# --------------------------------------------------------------------------
# One pass through the real dispatch


@pytest.fixture(scope="module")
def one_anchor(settings):
    bundle = generate_bundle(settings.weather["seed"], settings.weather["shape_years"])
    cells = tuple(c for c in cell_plan(settings) if c.shape_year in (0, 4))
    return dispatch_anchor(settings, settings.fleet, bundle, offset=4, year=2030,
                           peak_mw=12500.0, cells=cells)


def test_a_dispatched_anchor_prices_every_cell_and_every_candidate(settings, one_anchor):
    assert len(one_anchor.outcomes) == 18
    for outcome in one_anchor.outcomes:
        assert set(outcome.rent_per_mw_year) == {t.technology for t in settings.tech_costs}
        assert set(outcome.block_prices) == set(settings.blocks())


def test_the_forward_reduces_by_weight_and_not_by_count(settings, one_anchor):
    rents = one_anchor.rents("ocgt")
    weighted = one_anchor.expected(rents)
    plain = float(rents.mean())
    assert weighted != pytest.approx(plain, rel=1e-6), (
        "with a 10/80/10 peak band the two reductions must differ; if they agree "
        "the weights are not reaching the reduction"
    )
