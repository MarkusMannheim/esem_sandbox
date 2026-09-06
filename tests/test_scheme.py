"""The state scheme: a milestone, a ceiling, a budget, and why it was missed.

The reliability lane's volume is computed from the system. A scheme's milestone is a
number in a policy and does not care what the market is doing, so it can be missed,
and which constraint missed it is the output rather than a footnote.
"""

import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.esem import Bid
from esem_sandbox.core.scheme import (
    BUDGET, MET, NOTHING_SOUGHT, NO_ELIGIBLE_BIDS, PRICE_CEILING,
    SCHEME_COUNTERPARTY, SUPPLY, SchemeRow, clear_scheme, load_scheme,
    scheme_contracts,
)


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def _row(**kwargs):
    base = dict(service="renewable capacity", milestones={2030: 1000.0},
                technologies=("wind", "solar"), ceiling_per_mw_year=120_000.0,
                budget_per_year=250_000_000.0, tenor_years=15)
    base.update(kwargs)
    return SchemeRow(**base)


def _bid(tech="wind", mw=400.0, price=100_000.0, name="p"):
    # A capacity target is written in nameplate, so the quantity it clears against
    # is nameplate. See the note in the settings file.
    return Bid(bidder=name, technology=tech, capacity_mw=mw, firm_mw=mw,
               price_per_mw_year=price, lead_years=3)


def test_a_milestone_that_is_met_says_so():
    year, lines = clear_scheme(_row(), [_bid(mw=600.0), _bid(mw=600.0, name="q")], 2030)
    assert year.binding == MET
    assert year.awarded_mw == pytest.approx(1000.0)
    assert year.shortfall_mw == 0.0
    assert sum(l.firm_mw for l in lines) == pytest.approx(1000.0)


def test_a_year_with_no_milestone_is_not_a_year_that_failed():
    year, lines = clear_scheme(_row(), [_bid()], 2031)
    assert year.binding == NOTHING_SOUGHT
    assert year.sought_mw == 0.0 and lines == []


def test_the_technology_filter_binds_and_is_named():
    year, _ = clear_scheme(_row(), [_bid(tech="ocgt", mw=2000.0)], 2030)
    assert year.binding == NO_ELIGIBLE_BIDS
    assert year.awarded_mw == 0.0


def test_the_price_ceiling_binds_and_is_named():
    year, _ = clear_scheme(_row(), [_bid(price=500_000.0, mw=2000.0)], 2030)
    assert year.binding == PRICE_CEILING
    assert year.spend == 0.0


def test_the_budget_binds_and_is_named():
    """A scheme with money for two thirds of a project buys two thirds of it. One
    that dropped the marginal award whole would report a budget as binding harder
    than it does."""
    row = _row(budget_per_year=50_000_000.0)
    year, lines = clear_scheme(row, [_bid(mw=2000.0, price=100_000.0)], 2030)
    assert year.binding == BUDGET
    assert year.spend <= row.budget_per_year + 1e-6
    assert 0 < year.awarded_mw < 1000.0


def test_running_out_of_sellers_is_not_the_same_as_running_out_of_money():
    """Three ways to miss a milestone, and a reader wants to know which one."""
    year, _ = clear_scheme(_row(), [_bid(mw=300.0)], 2030)
    assert year.binding == SUPPLY
    assert year.awarded_mw == pytest.approx(300.0)
    assert year.shortfall_mw == pytest.approx(700.0)


def test_the_cheapest_eligible_bid_is_taken_first():
    dear = _bid(mw=600.0, price=110_000.0, name="dear")
    cheap = _bid(mw=600.0, price=60_000.0, name="cheap")
    _year, lines = clear_scheme(_row(), [dear, cheap], 2030)
    assert lines[0].bid.bidder == "cheap"


def test_the_counterparty_holds_what_it_buys():
    """The administrator sells its position back to retailers and charges consumers
    the difference. A scheme counterparty does not: it holds until the contract runs
    out. That is a real difference between the two instruments."""
    row = _row()
    _year, lines = clear_scheme(row, [_bid(mw=1200.0)], 2030)
    contracts = scheme_contracts(lines, row, strikes={"wind": 70.0},
                                 commissioning={"wind": 2033})
    assert contracts
    for c in contracts:
        assert c.holder == SCHEME_COUNTERPARTY
        assert c.writer == "p"
        assert c.start_year == 2033
        assert c.tenor_years == row.tenor_years


def test_the_packaged_scheme_loads_and_is_one_service(settings):
    row = load_scheme(settings)
    assert row is not None
    assert row.milestones and min(row.milestones.values()) > 0
    assert row.technologies == tuple(settings.scheme["technologies"])
    years = sorted(row.milestones)
    assert [row.milestones[y] for y in years] == sorted(row.milestones.values()), (
        "a milestone trajectory that fell would be a different kind of policy"
    )


def test_a_milestone_is_nameplate_and_not_firm(settings):
    """Nine gigawatts of nameplate wind at a firm factor of a tenth is nine hundred
    megawatts of firm capacity. A scheme that reported the first as though it were
    the second would be out by a factor of ten."""
    row = load_scheme(settings)
    wind = settings.tech("wind")
    biggest = max(row.milestones.values())
    assert biggest * wind.firm_factor < biggest / 5, (
        "the technologies this scheme buys are not firm, which is the whole reason "
        "its milestone has to be read as nameplate"
    )
