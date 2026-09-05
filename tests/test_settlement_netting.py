"""The netting invariants, on stub prices, before any other contract code.

A contract moves money between two parties. It cannot create or destroy any. These
tests run on invented price series rather than dispatched ones, so they check the
settlement arithmetic itself and cannot be rescued by a plausible-looking market.
"""

import numpy as np
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.contracts import CAP, SWAP, Contract, age, settle, settle_book


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def _swap(**kw):
    base = dict(kind=SWAP, holder="retailer", writer="gentailer",
                strike_per_mwh=70.0, volume_mw=100.0, start_year=2026,
                tenor_years=3, block="peak")
    return Contract(**{**base, **kw})


def _cap(**kw):
    base = dict(kind=CAP, holder="retailer", writer="peaker",
                strike_per_mwh=300.0, volume_mw=50.0, start_year=2026,
                tenor_years=2, premium_per_mwh=12.0)
    return Contract(**{**base, **kw})


def test_a_contract_moves_money_it_does_not_make_any(settings):
    price = np.random.default_rng(1).uniform(-100.0, 4000.0, 8760)
    for contract in (_swap(), _cap()):
        flows = settle(settings, contract, price, 2026)
        assert sum(flows.values()) == pytest.approx(0.0, abs=1e-6), contract.kind


def test_the_whole_book_nets_to_zero_every_year(settings):
    rng = np.random.default_rng(2)
    book = [_swap(), _swap(block="solar", holder="retailer_b", strike_per_mwh=40.0),
            _cap(), _cap(holder="retailer_b", writer="merchant", volume_mw=25.0)]
    for year in range(2026, 2031):
        price = rng.uniform(-200.0, 15000.0, 8760)
        flows = settle_book(settings, book, price, year)
        assert sum(flows.values()) == pytest.approx(0.0, abs=1e-6), year


def test_each_contract_settles_exactly_its_tenor(settings):
    price = np.full(8760, 100.0)
    contract = _swap(tenor_years=3, start_year=2026)
    settled = [y for y in range(2020, 2040)
               if settle(settings, contract, price, y)[contract.holder] != 0.0]
    assert settled == [2026, 2027, 2028]


def test_a_book_empties(settings):
    book = [_swap(tenor_years=2), _cap(tenor_years=1)]
    for year in range(2026, 2029):
        book = age(book, year)
    assert book == [], "contracts must leave the book when they expire"


def test_a_swap_pays_the_difference_and_only_on_its_block(settings):
    """A swap is a contract for difference on MW, over its block's hours alone."""
    price = np.full(8760, 90.0)
    contract = _swap(strike_per_mwh=70.0, volume_mw=100.0, block="peak")
    hours = int(np.sum(np.arange(8760) % 24 >= 16) - np.sum(np.arange(8760) % 24 >= 22))
    got = settle(settings, contract, price, 2026)[contract.holder]
    assert got == pytest.approx((90.0 - 70.0) * 100.0 * hours)


def test_a_swap_pays_the_writer_when_the_price_is_low(settings):
    price = np.full(8760, 50.0)
    flows = settle(settings, _swap(strike_per_mwh=70.0), price, 2026)
    assert flows["retailer"] < 0 and flows["gentailer"] > 0


def test_a_cap_is_settled_over_every_interval_not_a_sampled_curve(settings):
    """One scarce hour is one hour.

    Integrating over a 101-point sample of the sorted series makes that hour the top
    point at one per cent weight, and pays it as though it lasted for tens of hours.
    That defect cost the larger model a whole tick's cap book at fifteen to twenty
    times cost basis.
    """
    price = np.full(8760, 50.0)
    price[0] = 20300.0
    contract = _cap(strike_per_mwh=300.0, volume_mw=1.0, premium_per_mwh=0.0001)
    payout = settle(settings, contract, price, 2026)[contract.holder]
    premium = 0.0001 * 1.0 * 8760
    assert payout + premium == pytest.approx(20300.0 - 300.0)

    sampled = np.sort(price)[::-1][np.linspace(0, 8759, 101).astype(int)]
    sampled_payout = float(np.clip(sampled - 300.0, 0.0, None).mean() * 8760)
    assert sampled_payout > 40 * (20300.0 - 300.0), (
        "the sampled basis should overstate by more than fortyfold, which is why "
        "settlement reads the full series"
    )


def test_a_cap_holder_pays_the_premium_even_when_it_never_pays_out(settings):
    price = np.full(8760, 50.0)
    contract = _cap(strike_per_mwh=300.0, volume_mw=50.0, premium_per_mwh=12.0)
    flows = settle(settings, contract, price, 2026)
    assert flows[contract.holder] == pytest.approx(-12.0 * 50.0 * 8760)
    assert flows[contract.writer] == pytest.approx(+12.0 * 50.0 * 8760)


def test_a_contract_out_of_force_settles_nothing(settings):
    price = np.random.default_rng(3).uniform(0.0, 5000.0, 8760)
    flows = settle(settings, _swap(start_year=2030), price, 2026)
    assert all(v == 0.0 for v in flows.values())


def test_nonsense_contracts_are_refused(settings):
    with pytest.raises(ValueError, match="unknown contract kind"):
        Contract(kind="future", holder="a", writer="b", strike_per_mwh=1.0,
                 volume_mw=1.0, start_year=2026, tenor_years=1, block="peak")
    with pytest.raises(ValueError, match="must name the block"):
        _swap(block=None)
    with pytest.raises(ValueError, match="gift"):
        _cap(premium_per_mwh=0.0)
    with pytest.raises(ValueError, match="tenor"):
        _swap(tenor_years=0)
