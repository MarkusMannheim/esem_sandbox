"""Bid-curve clearing, the extension to the anchor market.

The core path clears at an anchor and is what the argument rests on. This is the
alternative, and what it is for is measuring the difference: uniform price against
pay-as-bid, elastic curves against rigid ones, on the same two sides.
"""

import numpy as np
import pytest

from esem_sandbox.core.crossing import BAND, Crossed, Order, cross, ladder


def _curves(anchor=80.0, volume=300.0, steps=5, spread=0.25):
    return (ladder("producer", anchor, volume, steps, spread, ascending=True),
            ladder("retailer", anchor, volume, steps, spread, ascending=False))


# --------------------------------------------------------------------------
# The crossing itself


def test_symmetric_curves_clear_at_the_anchor():
    """Two sides that disagree by the same amount in each direction meet in the
    middle, and the middle is where they both started."""
    writers, holders = _curves()
    result = cross(writers, holders, 80.0)
    assert result.price_per_mwh == pytest.approx(80.0)
    assert result.cleared


def test_only_the_slices_that_agree_trade():
    """A producer's dearest slices and a retailer's cheapest ones do not cross, and
    a market that cleared them anyway would be inventing a trade neither side
    offered."""
    writers, holders = _curves(volume=300.0, steps=5)
    result = cross(writers, holders, 80.0)
    assert result.volume_mw == pytest.approx(180.0)
    assert result.volume_mw < 300.0


def test_an_eager_buyer_clears_higher():
    writers, _ = _curves()
    keen = ladder("retailer", 100.0, 300.0, 5, 0.25, ascending=False)
    assert cross(writers, keen, 80.0).price_per_mwh > 80.0


def test_an_eager_seller_clears_lower():
    _, holders = _curves()
    keen = ladder("producer", 60.0, 300.0, 5, 0.25, ascending=True)
    assert cross(keen, holders, 80.0).price_per_mwh < 80.0


def test_a_steeper_curve_trades_less_when_the_two_sides_disagree():
    """Elasticity does what elasticity should: against a keener buyer, a producer
    whose curve rises steeply sells less of it."""
    volumes = []
    for spread in (0.05, 0.15, 0.25):
        writers = ladder("producer", 80.0, 300.0, 5, spread, ascending=True)
        holders = ladder("retailer", 100.0, 300.0, 5, spread, ascending=False)
        volumes.append(cross(writers, holders, 90.0).volume_mw)
    assert volumes[0] > volumes[1] > volumes[2], volumes


def test_when_the_two_sides_agree_the_spread_does_not_move_the_volume():
    """A property of mirror-image curves, stated so nobody reads the spread as a
    volume lever where it is not one. If both sides value the block identically and
    step away from it symmetrically, every slice below the midpoint crosses and
    every slice above it does not, whatever the steps are worth. Volume is then set
    by how finely the curves are cut, and tends to half of them."""
    for spread in (0.05, 0.25, 0.40):
        writers, holders = _curves(spread=spread)
        assert cross(writers, holders, 80.0).volume_mw == pytest.approx(180.0)

    shares = []
    for steps in (3, 9, 21):
        writers, holders = _curves(steps=steps)
        shares.append(cross(writers, holders, 80.0).volume_mw / 300.0)
    assert shares[0] > shares[1] > shares[2] > 0.5


def test_nothing_clears_when_the_best_bid_is_under_the_best_offer():
    writers = [Order("p", 100.0, 120.0)]
    holders = [Order("r", 100.0, 90.0)]
    result = cross(writers, holders, 100.0)
    assert not result.cleared
    assert result.volume_mw == 0.0 and result.writers == () and result.holders == ()


def test_an_empty_side_clears_nothing():
    writers, _ = _curves()
    assert not cross(writers, [], 80.0).cleared
    assert not cross([], writers, 80.0).cleared


def test_the_price_sits_between_the_last_pair_that_agreed():
    """The marginal writer would have accepted less and the marginal holder would
    have paid more. Splitting the difference is the convention that does not hand
    the whole of the last trade's surplus to one side by construction."""
    writers = [Order("p", 50.0, 70.0), Order("p", 50.0, 90.0)]
    holders = [Order("r", 50.0, 110.0), Order("r", 50.0, 95.0)]
    result = cross(writers, holders, 90.0)
    assert 90.0 <= result.price_per_mwh <= 95.0


# --------------------------------------------------------------------------
# Uniform price, which is the point of the extension


def test_everybody_settles_at_one_price():
    """Uniform price, not pay-as-bid. A writer who offered cheap is paid what the
    last accepted writer asked, which is the whole difference from the scheme's
    auction and the reason both are in this model."""
    writers, holders = _curves()
    result = cross(writers, holders, 80.0)
    cheapest_offer = min(o.price_per_mwh for o in writers)
    assert result.price_per_mwh > cheapest_offer, (
        "under pay-as-bid the cheapest writer would receive its own offer"
    )


def test_the_uniform_price_beats_pay_as_bid_for_the_cheap_writer():
    """The measurable contrast a workshop can run both ways."""
    writers, holders = _curves()
    result = cross(writers, holders, 80.0)
    traded = dict()
    for party, mw in result.writers:
        traded[party] = traded.get(party, 0.0) + mw
    uniform_revenue = result.volume_mw * result.price_per_mwh
    as_bid = 0.0
    left = result.volume_mw
    for order in sorted(writers, key=lambda o: o.price_per_mwh):
        take = min(order.volume_mw, left)
        as_bid += take * order.price_per_mwh
        left -= take
        if left <= 0:
            break
    assert uniform_revenue > as_bid, (
        f"uniform {uniform_revenue:,.0f} against pay-as-bid {as_bid:,.0f}"
    )


# --------------------------------------------------------------------------
# Conservation and allocation


def test_what_is_sold_is_what_is_bought():
    writers, holders = _curves()
    result = cross(writers, holders, 80.0)
    assert sum(v for _p, v in result.writers) == pytest.approx(result.volume_mw)
    assert sum(v for _p, v in result.holders) == pytest.approx(result.volume_mw)


def test_the_cheapest_writer_is_filled_first():
    writers = [Order("dear", 40.0, 95.0), Order("cheap", 40.0, 70.0)]
    holders = [Order("r", 60.0, 120.0)]
    result = cross(writers, holders, 90.0)
    assert result.writers[0][0] == "cheap"
    assert result.writers[0][1] == pytest.approx(40.0)


def test_the_dearest_holder_is_filled_first():
    writers = [Order("p", 100.0, 70.0)]
    holders = [Order("mean", 40.0, 80.0), Order("keen", 40.0, 130.0)]
    result = cross(writers, holders, 90.0)
    assert result.holders[0][0] == "keen"


def test_the_marginal_order_is_filled_in_part():
    writers = [Order("p", 100.0, 70.0)]
    holders = [Order("r", 60.0, 120.0)]
    result = cross(writers, holders, 90.0)
    assert result.volume_mw == pytest.approx(60.0)
    assert result.writers == (("p", pytest.approx(60.0)),)


# --------------------------------------------------------------------------
# The band


def test_the_band_drops_nonsense_and_says_how_much():
    """A curve with a thousand-dollar offer at one end has a crossing point that
    reflects the outlier rather than the market."""
    writers = [Order("p", 50.0, 80.0), Order("p", 50.0, 4_000.0)]
    holders = [Order("r", 50.0, 85.0), Order("r", 50.0, 1.0)]
    result = cross(writers, holders, 80.0)
    assert result.dropped == 2
    assert result.volume_mw == pytest.approx(50.0)


def test_the_band_does_not_bind_on_the_curves_this_model_makes():
    """A band that bound often would be a price control rather than a screen."""
    for spread in (0.05, 0.25, 0.45):
        writers, holders = _curves(spread=spread)
        assert cross(writers, holders, 80.0).dropped == 0


def test_the_band_is_half_to_four_times_the_anchor():
    assert BAND == (0.5, 4.0)
    writers = [Order("p", 10.0, 40.1)]
    holders = [Order("r", 10.0, 319.0)]
    assert cross(writers, holders, 80.0).cleared
    assert cross([Order("p", 10.0, 39.0)], holders, 80.0).dropped == 1


# --------------------------------------------------------------------------
# Inputs


def test_an_order_with_no_volume_is_not_an_order():
    with pytest.raises(ValueError, match="volume"):
        Order("p", 0.0, 80.0)


def test_a_crossing_needs_an_anchor_to_band_against():
    with pytest.raises(ValueError, match="anchor"):
        cross(*_curves(), anchor=0.0)


def test_a_single_step_curve_is_a_flat_offer():
    assert [o.price_per_mwh for o in ladder("p", 80.0, 100.0, 1, 0.3, True)] == [80.0]


def test_the_crossing_is_deterministic():
    writers, holders = _curves()
    first, second = cross(writers, holders, 80.0), cross(writers, holders, 80.0)
    assert first == second


def test_the_band_works_on_a_negative_anchor():
    """The solar block clears below zero on most days of this model's year, so a
    negative anchor is the ordinary case rather than an edge one. Half of minus two
    dollars is minus one and four times it is minus eight, so the multipliers arrive
    the wrong way round; taken in the order they were written the band inverts and
    admits nothing."""
    writers = [Order("p", 50.0, -6.0)]
    holders = [Order("r", 50.0, -3.0)]
    result = cross(writers, holders, -4.0)
    assert result.dropped == 0
    assert result.cleared
    assert result.price_per_mwh == pytest.approx(-4.5)
    assert cross([Order("p", 10.0, -20.0)], holders, -4.0).dropped == 1


def test_a_zero_anchor_has_no_band_and_says_so():
    with pytest.raises(ValueError, match="zero"):
        cross([Order("p", 10.0, 1.0)], [Order("r", 10.0, 2.0)], 0.0)


def test_the_share_that_trades_turns_on_the_parity_of_the_step_count():
    """Written down because it is an artefact and it looks like a result.

    With mirror-image curves and an odd number of slices, one slice sits exactly on
    the anchor and crosses with its mirror, so a little over half the volume trades.
    With an even number none does and exactly half trades. A magnitude that turns on
    the parity of a parameter is not a magnitude to quote at a room.
    """
    for steps in (3, 5, 7, 9):
        writers, holders = _curves(steps=steps)
        share = cross(writers, holders, 80.0).volume_mw / 300.0
        assert share == pytest.approx((steps + 1) / (2 * steps)), steps
    for steps in (4, 10, 20):
        writers, holders = _curves(steps=steps)
        assert cross(writers, holders, 80.0).volume_mw / 300.0 == pytest.approx(0.5)
