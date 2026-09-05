"""Lane anchors, the cap premium, and the roster that stands behind them."""

import numpy as np
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.agents import (
    PRODUCER, RETAILER, Agent, check_roster, default_roster,
)
from esem_sandbox.core.clearing import (
    cap_anchor, cap_cost_basis, cara_certainty_equivalent, ewma_block_anchor,
    realised_mean_excess, risk_loading,
)


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def test_every_unit_is_owned_exactly_once(settings):
    """A unit owned by nobody earns revenue that reaches no balance sheet; one owned
    twice earns it twice. Neither shows up in a price."""
    names = {u.unit for u in settings.fleet
             if u.technology not in ("rooftop", "import")}
    check_roster(default_roster(), names)


def test_an_unowned_unit_is_refused(settings):
    names = {u.unit for u in settings.fleet
             if u.technology not in ("rooftop", "import")} | {"ghost_unit"}
    with pytest.raises(ValueError, match="unowned units: ghost_unit"):
        check_roster(default_roster(), names)


def test_a_doubly_owned_unit_is_refused():
    roster = (Agent("a", PRODUCER, 0.5, units=("x",)),
              Agent("b", PRODUCER, 0.5, units=("x",)),
              Agent("r", RETAILER, 0.5, load_share=1.0))
    with pytest.raises(ValueError, match="owned by a and b"):
        check_roster(roster, {"x"})


def test_retailer_load_must_sum_to_the_whole_system():
    roster = (Agent("r", RETAILER, 0.5, load_share=0.6),)
    with pytest.raises(ValueError, match="sum to 0.6"):
        check_roster(roster, set())


def test_a_certainty_equivalent_is_below_the_mean_and_falls_with_risk_aversion():
    payoffs = np.array([10_000.0, 50_000.0, 200_000.0])
    weights = np.full(3, 1 / 3)
    mean = float(payoffs @ weights)
    previous = mean
    for a in (1e-6, 5e-6, 2e-5):
        ce = cara_certainty_equivalent(payoffs, weights, a)
        assert ce < mean
        assert ce < previous, "more risk aversion must mean a lower certain equivalent"
        previous = ce


def test_a_certain_payoff_carries_no_loading():
    payoffs = np.full(5, 40_000.0)
    weights = np.full(5, 0.2)
    assert risk_loading(payoffs, weights, 0.6) == pytest.approx(0.0, abs=1e-6)


def test_the_loading_survives_a_scarcity_year_without_overflowing():
    """A cap payout in a bad year is large. exp() of it is not representable, so the
    certainty equivalent is computed in a shifted frame."""
    payoffs = np.array([3e4, 5e4, 8e4, 9e4, 2.1e6])
    weights = np.full(5, 0.2)
    loading = risk_loading(payoffs, weights, 0.6)
    assert np.isfinite(loading) and loading > 0


def test_the_cap_anchor_floors_on_the_cost_of_standing_ready():
    """A writer will not sell below what the plant needs, however quiet the market."""
    quiet = np.full(5, 100.0)
    weights = np.full(5, 0.2)
    basis = cap_cost_basis(1400, 16, 0.07, 25, 0.85, 69_000.0)
    anchor = cap_anchor(basis, 0.0, quiet, weights, 0.6)
    assert anchor >= basis


def test_the_cap_anchor_does_not_lift_on_one_scarce_interval():
    """The defect this construction exists to avoid.

    Using the within-year dispersion of hourly excess lifted the larger model's cap
    anchor to about $2,000/MWh on the strength of a single interval at the price cap.
    The loading here reads across years, not within one, so a single interval moves it
    by cents.
    """
    weights = np.full(5, 0.2)
    basis = cap_cost_basis(1400, 16, 0.07, 25, 0.85, 69_000.0)
    calm = np.full(5, 5_000.0)
    base = cap_anchor(basis, 0.0, calm, weights, 0.6)

    price = np.full(8760, 50.0)
    price[0] = 20_300.0
    excess = realised_mean_excess(price, 300.0)
    spiked = calm.copy()
    spiked[0] += (20_300.0 - 300.0)          # one interval, in one year
    lifted = cap_anchor(basis, excess, spiked, weights, 0.6)

    assert lifted - base < 5.0, (
        f"one scarce interval moved the anchor by ${lifted - base:,.2f}/MWh"
    )


def test_more_risk_aversion_costs_the_holder_more():
    payoffs = np.array([3e4, 5e4, 8e4, 9e4, 2.1e5])
    weights = np.full(5, 0.2)
    basis = cap_cost_basis(1400, 16, 0.07, 25, 0.85, 69_000.0)
    timid = cap_anchor(basis, 0.0, payoffs, weights, 0.60)
    bold = cap_anchor(basis, 0.0, payoffs, weights, 0.45)
    assert timid > bold


def test_netting_the_energy_margin_lowers_what_a_cap_must_charge():
    """A peaker already covering part of its fixed cost in the pool does not recover
    it twice."""
    bare = cap_cost_basis(1400, 16, 0.07, 25, 0.85, 0.0)
    earning = cap_cost_basis(1400, 16, 0.07, 25, 0.85, 69_000.0)
    assert earning < bare
    assert bare / earning > 1.8, (
        "the packaged peaker earns about $69,000 per MW-year in the pool against a "
        "fixed cost near $136,000, so forgetting the margin roughly doubles what a "
        "cap must charge and prices it above what it can ever expect to pay"
    )


def test_the_block_anchor_weights_recent_years_more():
    history = [{"peak": 50.0}, {"peak": 50.0}, {"peak": 150.0}]
    anchor = ewma_block_anchor(history, "peak", half_life_years=1.0)
    assert 100.0 < anchor < 150.0, (
        "the latest year should dominate without erasing the earlier ones"
    )


def test_the_block_anchor_is_flat_on_a_flat_history():
    history = [{"peak": 80.0} for _ in range(6)]
    assert ewma_block_anchor(history, "peak") == pytest.approx(80.0)


def test_no_history_is_an_error_not_a_guess():
    with pytest.raises(ValueError, match="no price history"):
        ewma_block_anchor([], "peak")


def test_mean_excess_reads_every_hour_not_a_sampled_curve():
    price = np.full(8760, 50.0)
    price[0] = 20_300.0
    assert realised_mean_excess(price, 300.0) == pytest.approx(20_000.0 / 8760)
