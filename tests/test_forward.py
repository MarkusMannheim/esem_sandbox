"""The forward view: the lattice, the rent basis and the free-entry fixed point.

The convergence tests run against a stub rent curve rather than the dispatch. That
is deliberate and it is the same discipline the contract stack was built under: a
state machine tested only through a plausible-looking market can be rescued by the
market, and the thing under test here is whether the rule converges at all.
"""

from dataclasses import replace

import numpy as np
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.forward import (
    Anchor, Cell, CellOutcome, EntryBelief, EntryState, cell_plan, dispatch_anchor,
    incumbent_rents, interpolated_rent, lifetime_rent_by_cell,
    lifetime_rent_per_mw_year, peak_banded, rent_per_mw_year,
    update_projected_entry,
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
    """fleet.csv offers wind at minus 45 dollars. That is what a plant will
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


def test_an_incumbent_s_rent_is_booked_on_what_it_generated(settings):
    """A coal unit keeps its must-run band on through hours priced below its
    running cost. Those hours are losses it carries, and the tick's ledger charges
    them; the rent the exit test reads has to carry them too, or a plant is kept
    open on money it never earned. A unit with no must-run band books exactly the
    positive margin on the hours it ran, and a unit the dispatch never ran is not
    measurable rather than zero."""
    from esem_sandbox.core.dispatch import dispatch_year
    from esem_sandbox.core.weather import generate_bundle

    bundle = generate_bundle(1, 1)
    shape = bundle["demand_shape"][0]
    res = dispatch_year(settings, 2026, shape * (12_500.0 / shape.max()),
                        bundle["wind_cf"][0], bundle["solar_cf"][0])
    live = tuple(u for u in settings.fleet if u.in_service(2026))
    rents = incumbent_rents(res.price, res.generation_mwh, live)

    coal = next(u for u in live if u.technology == "coal" and u.must_run_mw > 0)
    gen = res.generation_mwh[coal.unit]
    below_cost = (gen > 0) & (res.price < coal.srmc_per_mwh)
    assert below_cost.sum() > 0, "the must-run band ran through hours below cost"
    clip = float(np.clip(res.price - coal.srmc_per_mwh, 0.0, None).sum()
                 * coal.availability)
    assert rents[coal.unit] < clip, "the below-cost hours have to cost the plant"
    assert rents[coal.unit] == pytest.approx(
        float(np.sum(gen * (res.price - coal.srmc_per_mwh))) / coal.capacity_mw)

    gas = next(u for u in live if u.technology in ("ocgt", "ccgt")
               and u.must_run_mw == 0)
    ran = res.generation_mwh[gas.unit] > 0
    assert np.all(res.price[ran] >= gas.srmc_per_mwh - 1e-9), (
        "a price taker with no must-run band runs only at or above its cost"
    )
    assert rents[gas.unit] >= 0.0

    assert gas.unit not in incumbent_rents(res.price, {}, live), (
        "a unit the dispatch never booked is not measurable"
    )
    assert not any(u.srmc_per_mwh < 0 for u in live if u.unit in rents), (
        "a curtailment offer is not a running cost and gets no rent"
    )


def test_storage_rent_uses_the_scheduler_that_will_govern_it(settings):
    """A candidate valued by a cleaner rule than the one that will dispatch it once
    built is valued at a spread it can never realise."""
    rng = np.random.default_rng(7)
    hours = np.arange(8760)
    residual = 6000.0 + 2500.0 * np.sin(hours * 2 * np.pi / 24 - 1.6) \
        + rng.normal(0, 80, 8760)
    price = 40.0 + 0.02 * (residual - residual.mean())
    four = rent_per_mw_year(price, settings.tech("battery_4h"), settings, None, residual)
    two = rent_per_mw_year(price, settings.tech("battery_2h"), settings, None, residual)
    assert four > two > 0, "more duration earns more spread on a diurnal load shape"


def test_a_storage_candidate_cannot_be_valued_without_a_load_shape(settings):
    """Storage is scheduled against quantities, so a price series alone does not say
    what a battery is worth: it says what the shape it shaves was worth."""
    with pytest.raises(ValueError, match="residual"):
        rent_per_mw_year(np.full(8760, 50.0), settings.tech("battery_4h"), settings)


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
    assert state.settled(8, {tech.technology: tech.unit_size_mw})


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


# --------------------------------------------------------------------------
# What caution is priced over


def _lattice_view(settings, cells=None):
    from esem_sandbox.core.forward import forward_view
    bundle = generate_bundle(settings.weather["seed"], settings.weather["shape_years"])
    return forward_view(settings, settings.fleet, bundle, year=2026, peak_mw=12_500.0,
                        entry=EntryState(), cells=cells)


@pytest.fixture(scope="module")
def tick_zero_view(settings):
    return _lattice_view(settings)


def test_the_expectation_is_the_same_whatever_caution_is_priced_over(settings, tick_zero_view):
    """Collapsing cells to worlds moves the dispersion the hurdle is charged for and
    nothing else: each world's rent is the weighted mean of its cells, so the
    expectation is the full-lattice mean under every grouping."""
    from esem_sandbox.core.forward import RISK_WORLDS, risk_worlds
    view = tick_zero_view
    cells = tuple(o.cell for o in view.nearest.outcomes)
    for tech in settings.tech_costs:
        rents = view.lifetime_rent(tech)
        mean = float(rents @ view.weights)
        for grouping in RISK_WORLDS:
            r, w = risk_worlds(rents, cells, view.weights, grouping)
            assert w.sum() == pytest.approx(1.0)
            assert float(r @ w) == pytest.approx(mean, rel=1e-9), (tech.technology, grouping)
    with pytest.raises(ValueError, match="risk_premium_worlds"):
        risk_worlds(rents, cells, view.weights, "weather")


def test_caution_priced_on_the_growth_path_charges_less_than_on_every_cell(settings, tick_zero_view):
    """The weather shape and the peak band are drawn afresh every year, so over a
    life they average out and only the growth path is one future. A hurdle that
    priced every cell as a lifetime charged for dispersion the run cannot produce:
    on the packaged fleet three quarters of a peaker's premium and almost all of
    a battery's. The certainty equivalent on growth worlds is never below the one
    on every cell, and the premium falls."""
    from esem_sandbox.core.clearing import cara_certainty_equivalent, cara_coefficient
    from esem_sandbox.core.forward import risk_worlds
    view = tick_zero_view
    cells = tuple(o.cell for o in view.nearest.outcomes)
    a = cara_coefficient(0.6, 1.0, settings)
    premium = {}
    for name in ("ocgt", "battery_4h"):
        rents = view.lifetime_rent(settings.tech(name))
        by_cell = cara_certainty_equivalent(*risk_worlds(rents, cells, view.weights, "all"), a)
        by_band = cara_certainty_equivalent(*risk_worlds(rents, cells, view.weights, "growth_band"), a)
        by_path = cara_certainty_equivalent(*risk_worlds(rents, cells, view.weights, "growth"), a)
        assert by_cell <= by_band <= by_path, name
        mean = float(rents @ view.weights)
        premium[name] = (mean - by_path, mean - by_cell)
        assert premium[name][0] < premium[name][1], name
    # A peaker's rent moves with demand, so most of its premium is the growth
    # path's and survives; a battery's moves with the peak band, which does not.
    assert premium["ocgt"][0] > 0.5 * premium["ocgt"][1]
    assert premium["battery_4h"][0] < 0.1 * premium["battery_4h"][1]
    r, w = risk_worlds(view.lifetime_rent(settings.tech("ocgt")), cells, view.weights, "growth")
    assert len(r) == len({c.growth_path for c in cells})


def test_the_tail_pays_what_the_projection_stops_assuming_entry_at(settings, tick_zero_view):
    """The entry step assumes plant until the marginal entrant's expected rent has
    fallen to its fixed cost plus the loading the market's most cautious investor
    demands. The years past the last projection year pay that same price, so the
    build test and the projection agree on what the long run pays; a tail at the
    cost of entry alone left every candidate short by the tail's share of the
    loading. The loading is one number across cells, so it moves every cell's
    level and none of the dispersion caution is priced on."""
    from dataclasses import replace
    from esem_sandbox.core.agents import default_roster
    from esem_sandbox.core.clearing import cara_certainty_equivalent, cara_coefficient
    from esem_sandbox.core.simulate import _merchant_entry_loading, with_tail
    plain = tick_zero_view
    loaded = with_tail(settings, plain, default_roster())
    a = cara_coefficient(0.6, 1.0, settings)
    for name in ("ocgt", "solar", "battery_8h"):
        tech = settings.tech(name)
        loading = loaded.tail_loading[name]
        assert loading > 0
        assert loaded.tail_per_mw_year(tech) == pytest.approx(
            tech.fixed_cost_per_mw_year + loading)
        before, after = plain.lifetime_rent(tech), loaded.lifetime_rent(tech)
        lift = after - before
        assert lift.min() > 0 and lift.max() == pytest.approx(lift.min(), rel=1e-9), (
            f"{name}: the tail lifts every cell by the same amount"
        )
        r0, w = plain.risk_distribution(tech, settings)
        r1, _ = loaded.risk_distribution(tech, settings)
        premium0 = float(r0 @ w) - cara_certainty_equivalent(r0, w, a)
        premium1 = float(r1 @ w) - cara_certainty_equivalent(r1, w, a)
        assert premium1 == pytest.approx(premium0, rel=1e-9), (
            f"{name}: caution is unchanged by a constant in the tail"
        )
    # The loading measured on the loaded view is the loading: no circularity.
    again = _merchant_entry_loading(settings, loaded, default_roster())
    for name, v in loaded.tail_loading.items():
        assert again[name] == pytest.approx(v, rel=1e-9)


def test_a_market_that_knows_its_growth_path_carries_no_premium(settings):
    """With all the prior weight on one growth path there is one world under the
    ruling, the certainty equivalent equals the expectation, and every hurdle is
    the plain cost. That is what pricing caution on the growth axis alone means,
    and it is why the knowing-the-path experiment has to name the worlds it
    prices over."""
    from esem_sandbox.core.agents import PRODUCER, default_roster
    from esem_sandbox.core.investment import evaluate
    one_path = replace(settings, growth=tuple(
        replace(g, weight=1.0 if g.path == "central" else 0.0) for g in settings.growth))
    view = _lattice_view(one_path, cells=tuple(
        c for c in cell_plan(one_path) if c.shape_year in (0, 4)))
    merchant = [a for a in default_roster() if a.kind == PRODUCER][0]
    v = evaluate(view, one_path.tech("ocgt"), merchant, one_path, exposure=1.0,
                 capacity_mw=200.0)
    assert v.risk_discount_per_mw_year == pytest.approx(0.0, abs=1e-6)
    every_cell = replace(one_path, forward={**one_path.forward,
                                            "risk_premium_worlds": "all"})
    v_all = evaluate(view, every_cell.tech("ocgt"), merchant, every_cell,
                     exposure=1.0, capacity_mw=200.0)
    assert v_all.risk_discount_per_mw_year > 0.0


def test_the_belief_is_on_the_run_and_not_in_a_module_global(settings):
    """Two legs of a paired run must not share one belief about entry, and a test
    must not leave its state behind for the next one."""
    tech = settings.tech("ocgt")
    a, _ = _converge(settings, _StepRent(tech.fixed_cost_per_mw_year), iterations=6)
    b = EntryState()
    assert b.at(8) == 0.0 and a.at(8) > 0.0
    c = a.copy()
    c.by_offset[8]["ocgt"].mw = 99_999.0
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


def test_a_cell_subset_is_restored_to_a_distribution(settings):
    """A subset of a normalised lattice is not normalised. Nine of the 45
    cells sum to a fifth, and every reduction downstream assumes one."""
    from esem_sandbox.core.forward import renormalised
    subset = tuple(c for c in cell_plan(settings) if c.shape_year == 0)
    assert sum(c.weight for c in subset) == pytest.approx(0.2)
    assert sum(c.weight for c in renormalised(subset)) == pytest.approx(1.0)
    ratios = [b.weight / a.weight for a, b in zip(subset, renormalised(subset))]
    assert max(ratios) == pytest.approx(min(ratios)), "relative weights must be kept"


# --------------------------------------------------------------------------
# Entry open to technology


def test_the_projection_is_not_told_which_technology_to_assume(settings):
    """Naming one forces the projection to price replacement capacity at that
    technology's running cost while the investment step goes and builds something
    else, so the two halves of the same model disagree about what a market does
    when it is short.

    And a peaker is not even the obvious guess: on this cost table the cheapest
    megawatt-year belongs to a two-hour battery, before a dollar of fuel is bought.
    """
    from esem_sandbox.core.forward import entry_candidates

    names = {t.technology for t in entry_candidates(settings)}
    assert names == {t.technology for t in settings.tech_costs}
    assert len(names) > 1
    cheapest = min(settings.tech_costs, key=lambda t: t.fixed_cost_per_mw_year)
    assert cheapest.technology != "ocgt", (
        "if the peaker ever becomes the cheapest megawatt-year here, the sentence "
        "above stops being the reason and the reason needs rewriting"
    )


def test_only_one_technology_moves_a_tick(settings):
    """Every candidate is measured against the SAME anchor, so letting all of them
    move in one pass has each answer 'would I be worth building?' about a market
    none of the others has entered yet. On this fleet that gave 15 gigawatts
    of assumed entry on a 12 gigawatt system, wandering and never settling."""
    tech = settings.tech("ocgt")
    rich = {t.technology: 10 * settings.tech(t.technology).fixed_cost_per_mw_year
            for t in settings.tech_costs}
    anchor = _stub_anchor(8, [1.0], shortfall=4000.0)
    anchor = Anchor(offset=8, year=2038, outcomes=tuple(
        replace(o, rent_per_mw_year=rich) for o in anchor.outcomes))
    state = update_projected_entry(EntryState(), [anchor], settings)
    moved = [t for t, mw in state.mix(8).items() if mw > 0]
    assert len(moved) == 1, f"{len(moved)} technologies moved in one tick: {moved}"


def _anchor_with(settings, offset, rents, shortfall=2000.0):
    base = _stub_anchor(offset, [1.0], shortfall=shortfall)
    return Anchor(offset=offset, year=2026 + offset, outcomes=tuple(
        replace(o, rent_per_mw_year=rents) for o in base.outcomes))


def test_a_settled_best_candidate_does_not_freeze_the_second(settings):
    """A candidate whose bracket has closed to one unit moves nothing. Chosen
    again while its surplus ranks first, it left every other candidate at the
    anchor frozen whatever their surplus: on the packaged fleet a combined cycle
    held the +8 anchor for sixteen passes with a peaker and a four-hour battery
    both paying and able to grow. The mover is the best candidate that can still
    move, and the anchor rests only when no paying candidate can."""
    ocgt, ccgt = settings.tech("ocgt"), settings.tech("ccgt")
    zero = {t.technology: 0.0 for t in settings.tech_costs}
    rents = dict(zero, ccgt=2 * ccgt.fixed_cost_per_mw_year,
                 ocgt=1.5 * ocgt.fixed_cost_per_mw_year)
    state = EntryState()
    state.by_offset[8] = {"ccgt": EntryBelief(mw=2_500.0, lo_mw=2_500.0,
                                              hi_mw=2_500.0 + ccgt.unit_size_mw)}
    after = update_projected_entry(state, [_anchor_with(settings, 8, rents)],
                                   settings)
    assert after.at(8, "ccgt") == 2_500.0, "the settled candidate stays put"
    assert after.at(8, "ocgt") > 0.0, "the paying candidate behind it moves"
    assert after.largest_surplus[8] == pytest.approx(ccgt.fixed_cost_per_mw_year)
    # When every paying candidate is settled the anchor rests, and the surplus
    # left at it is still recorded.
    state.by_offset[8]["ocgt"] = EntryBelief(mw=600.0, lo_mw=600.0,
                                             hi_mw=600.0 + ocgt.unit_size_mw)
    only = dict(zero, ccgt=2 * ccgt.fixed_cost_per_mw_year,
                ocgt=1.5 * ocgt.fixed_cost_per_mw_year)
    rest = update_projected_entry(state, [_anchor_with(settings, 8, only)],
                                  settings)
    assert rest.mix(8) == state.mix(8)
    assert rest.largest_surplus[8] > 0.0


def test_a_gated_best_candidate_does_not_skip_the_anchor(settings):
    """No anchor closer than a technology's lead can gain assumed entry of it.
    When the best-paying candidate is inside its lead the anchor is not skipped
    for the tick, which would starve a shorter-lead candidate that pays."""
    zero = {t.technology: 0.0 for t in settings.tech_costs}
    long_lead = max(settings.tech_costs, key=lambda t: t.lead_years)
    short_lead = min((t for t in settings.tech_costs if t.lead_years < long_lead.lead_years),
                     key=lambda t: t.lead_years)
    offset = long_lead.lead_years - 1
    assert offset >= short_lead.lead_years
    rents = dict(zero, **{long_lead.technology: 3 * long_lead.fixed_cost_per_mw_year,
                          short_lead.technology: 2 * short_lead.fixed_cost_per_mw_year})
    after = update_projected_entry(EntryState(),
                                   [_anchor_with(settings, offset, rents)], settings)
    assert after.at(offset, long_lead.technology) == 0.0
    assert after.at(offset, short_lead.technology) > 0.0


def test_a_technology_keeps_its_bracket_when_another_becomes_marginal(settings):
    """Assume enough batteries and a combined cycle looks best; assume enough of
    those and batteries do. Discarding what was learned on a switch made the state
    climb for ever."""
    cheap = {t.technology: 0.0 for t in settings.tech_costs}
    rich = dict(cheap, ocgt=10 * settings.tech("ocgt").fixed_cost_per_mw_year)
    def anchor_with(rents):
        base = _stub_anchor(8, [1.0], shortfall=2000.0)
        return Anchor(offset=8, year=2038, outcomes=tuple(
            replace(o, rent_per_mw_year=rents) for o in base.outcomes))

    state = update_projected_entry(EntryState(), [anchor_with(rich)], settings)
    assert state.at(8, "ocgt") > 0
    # Now nothing pays: the peaker must unwind, and its bracket must survive.
    after = update_projected_entry(state, [anchor_with(cheap)], settings)
    assert after.belief(8, "ocgt").hi_mw is not None, (
        "the observation that this much was too much has to be kept"
    )


def test_an_assumed_battery_is_dispatched_as_a_battery(settings):
    """A projection that adds undifferentiated capacity prices it at whatever the
    last thing in the stack costs."""
    from esem_sandbox.core.forward import anchor_fleet

    fleet = anchor_fleet(settings.fleet, 2035, {"battery_8h": 500.0}, settings)
    added = [u for u in fleet if u.unit.startswith("projected_entry")]
    assert len(added) == 1
    assert added[0].technology == "battery"
    assert added[0].duration_h == 8.0
    assert added[0].round_trip_efficiency is not None


def test_plant_assumed_at_four_years_is_still_there_at_eight_and_twelve(settings):
    """Every life on the cost table outlasts the span from the first anchor to the
    last, so a plant the projection assumes built by four years out is in service
    at eight and at twelve. Far anchors dispatched without it would let the lifetime
    rent the build test chains from the three anchors value an 8h battery at three
    times its fixed cost on a view whose own +4 anchor says the same plant does not
    pay. A belief at eight years does not reach back to four."""
    state = EntryState()
    state.by_offset[4] = {"battery_8h": EntryBelief(mw=1_000.0)}
    state.by_offset[8] = {"ocgt": EntryBelief(mw=300.0)}
    assert state.mix(4) == {"battery_8h": 1_000.0}
    assert state.mix(8) == {"battery_8h": 1_000.0, "ocgt": 300.0}
    assert state.mix(12) == {"battery_8h": 1_000.0, "ocgt": 300.0}
    assert state.at(8) == 300.0, "the anchor's own belief stays the increment"
    assert state.at(12) == 0.0


def test_the_assumed_mix_can_hold_more_than_one_technology(settings):
    from esem_sandbox.core.forward import anchor_fleet

    fleet = anchor_fleet(settings.fleet, 2035,
                         {"ocgt": 300.0, "battery_4h": 200.0}, settings)
    added = sorted(u.unit for u in fleet if u.unit.startswith("projected_entry"))
    assert added == ["projected_entry_battery_4h", "projected_entry_ocgt"]
