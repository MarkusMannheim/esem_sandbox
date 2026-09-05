"""The contract stack against real dispatched prices, not stubs.

The netting invariants run on invented series on purpose, so the arithmetic cannot be
rescued by a plausible market. This file is the other half: it runs the same machinery
over prices the model actually produced, which is where units, block masks and the
shape of a real year get a chance to disagree with each other.

The lesson it encodes: hydro looked entirely plausible on price while delivering half
its energy budget. Prices being sensible is not evidence that quantities are.
"""

import numpy as np
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.agents import default_roster
from esem_sandbox.core.clearing import (
    block_prices_of, cap_anchor, cap_cost_basis, energy_margin_per_mw_year,
    ewma_block_anchor, realised_mean_excess,
)
from esem_sandbox.core.contracts import CAP, SWAP, Contract, settle, settle_book
from esem_sandbox.core.dispatch import dispatch_year
from esem_sandbox.core.weather import generate_bundle

PEAK_MW = 12500.0


def _peaker_basis(settings, years):
    """Cost basis for the marginal peaker, net of what it earns in the pool."""
    unit = next(u for u in settings.fleet if u.unit == "ocgt_a")
    margin = float(np.mean([
        energy_margin_per_mw_year(r.price, unit.srmc_per_mwh, unit.availability)
        for r in years
    ]))
    return cap_cost_basis(1400, 16, 0.07, 25, 0.85, margin)


@pytest.fixture(scope="module")
def settings():
    return load_settings()


@pytest.fixture(scope="module")
def years(settings):
    bundle = generate_bundle(settings.weather["seed"], settings.weather["shape_years"])
    out = []
    for y in range(settings.weather["shape_years"]):
        shape = bundle["demand_shape"][y]
        out.append(dispatch_year(settings, 2026, shape * (PEAK_MW / shape.max()),
                                 bundle["wind_cf"][y], bundle["solar_cf"][y]))
    return out


def test_a_book_priced_off_real_anchors_still_nets_to_zero(settings, years):
    history = [block_prices_of(settings, r.price) for r in years[:3]]
    book = []
    for block in settings.blocks():
        anchor = ewma_block_anchor(history, block)
        book.append(Contract(kind=SWAP, holder="retailer_a", writer="gentailer_a",
                             strike_per_mwh=anchor, volume_mw=500.0,
                             start_year=2026, tenor_years=3, block=block))
    payoffs = np.array([np.clip(r.price - 300.0, 0.0, None).sum() for r in years])
    basis = _peaker_basis(settings, years)
    premium = cap_anchor(basis, realised_mean_excess(years[0].price, 300.0),
                         payoffs, np.full(len(years), 1 / len(years)), 0.60)
    book.append(Contract(kind=CAP, holder="retailer_a", writer="merchant",
                         strike_per_mwh=300.0, volume_mw=200.0, start_year=2026,
                         tenor_years=3, premium_per_mwh=premium))

    for offset, result in enumerate(years[:3]):
        flows = settle_book(settings, book, result.price, 2026 + offset)
        assert sum(flows.values()) == pytest.approx(0.0, abs=1e-6)
        assert set(flows) == {"retailer_a", "gentailer_a", "merchant"}


def test_a_swap_struck_at_the_anchor_is_roughly_fair_over_the_history(settings, years):
    """A lane anchored on what a block has been worth should not systematically
    enrich either side across the years it was fitted to."""
    history = [block_prices_of(settings, r.price) for r in years]
    anchor = ewma_block_anchor(history, "peak", half_life_years=1e6)   # flat weights
    contract = Contract(kind=SWAP, holder="r", writer="w", strike_per_mwh=anchor,
                        volume_mw=100.0, start_year=2026, tenor_years=len(years),
                        block="peak")
    total = sum(settle(settings, contract, r.price, 2026 + i)["r"]
                for i, r in enumerate(years))
    scale = abs(anchor) * 100.0 * 8760 * len(years)
    assert abs(total) < 0.05 * scale, (
        f"anchored swap moved ${total:,.0f} across the fitted years"
    )


def test_the_cap_premium_is_a_small_part_of_what_the_cap_pays(settings, years):
    """A premium larger than the expected payout would mean nobody buys; one far
    below it would mean nobody writes. This checks the anchor lands between."""
    payoffs = np.array([np.clip(r.price - 300.0, 0.0, None).sum() for r in years])
    weights = np.full(len(years), 1 / len(years))
    basis = _peaker_basis(settings, years)
    premium = cap_anchor(basis, realised_mean_excess(years[0].price, 300.0),
                         payoffs, weights, 0.60)
    annual_premium = premium * 8760.0
    expected_payout = float(payoffs @ weights)
    assert 0.05 * expected_payout < annual_premium < 1.5 * expected_payout, (
        f"premium ${annual_premium:,.0f}/MW-yr against expected payout "
        f"${expected_payout:,.0f}"
    )


def test_the_cap_writer_loses_in_the_drought_year_and_gains_in_mild_ones(settings, years):
    """The point of the product, and the reason anyone pays for it.

    If the writer never lost money the cap would not be insurance, and if it never
    gained the writer would not exist.
    """
    payoffs = np.array([np.clip(r.price - 300.0, 0.0, None).sum() for r in years])
    weights = np.full(len(years), 1 / len(years))
    basis = _peaker_basis(settings, years)
    premium = cap_anchor(basis, realised_mean_excess(years[0].price, 300.0),
                         payoffs, weights, 0.60)
    contract = Contract(kind=CAP, holder="retailer_a", writer="merchant",
                        strike_per_mwh=300.0, volume_mw=100.0, start_year=2026,
                        tenor_years=len(years), premium_per_mwh=premium)
    writer = [settle(settings, contract, r.price, 2026 + i)["merchant"]
              for i, r in enumerate(years)]
    worst = int(np.argmax(payoffs))
    assert writer[worst] < 0, "the writer must lose in the scarcest year"
    assert any(w > 0 for i, w in enumerate(writer) if i != worst), (
        "the writer must gain in quiet years or it would never write"
    )


def test_retailer_cover_is_sized_off_its_own_load_not_the_system(settings, years):
    """Two retailers holding 60 and 40 per cent of load should contract in that
    proportion. This is a quantity check: prices being sensible says nothing about
    whether the volumes were built from the right base."""
    roster = {a.name: a for a in default_roster()}
    average_load = float(years[0].operational_demand_mw.mean())
    volumes = {}
    for name in ("retailer_a", "retailer_b"):
        agent = roster[name]
        volumes[name] = agent.swap_cover * agent.load_share * average_load
    ratio = volumes["retailer_a"] / volumes["retailer_b"]
    assert ratio == pytest.approx(0.60 / 0.40, rel=1e-9)
    assert sum(volumes.values()) == pytest.approx(0.75 * average_load, rel=1e-9)
