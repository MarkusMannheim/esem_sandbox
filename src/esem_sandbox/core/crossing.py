"""Bid-curve clearing: what happens when the two sides do not agree on a price.

The core contract market clears at an anchor. Both sides accept it, the volume is
whatever the retailer wanted, and the price is what the block has lately been worth.
That is enough for the argument the model exists to make, it can be explained in a
sentence, and it can be checked by hand.

This is the extension, and it answers a different question: what if the two sides
have to find each other? Writers offer ascending, because a producer that has
already sold most of its output wants more for the next megawatt. Holders bid
descending, because a retailer that has already covered most of its load will pay
less for the next. Where the curves cross is the price, and everybody who traded
pays it, whatever they asked.

**Uniform price, not pay-as-bid.** The auction in the scheme is pay-as-bid because
that is what the scheme being modelled does; a bilateral market is not, and the
difference between the two is one of the things a workshop can measure here by
running both. Under a uniform price the marginal trade sets everybody's price, so a
writer who offered cheap is paid what the last accepted writer asked.

**What the elasticity lever does, and where it does nothing.** A steeper curve
trades less against a counterparty that values the block differently, which is what
elasticity should mean. Where both sides value it identically and step away from it
symmetrically, the spread cancels: every slice below the midpoint crosses and every
slice above it does not, whatever the steps are priced at. Volume is then decided by
how finely the curves are cut, and by whether that number is odd: with an odd count
one slice sits on the anchor and crosses with its mirror, so ``(steps + 1) /
(2 x steps)`` of the volume trades; with an even count none does and exactly half
trades. That is a property of a setting rather than of a market. That is a property of
mirror-image curves rather than a defect, and it is written down because the spread
looks like a volume lever there and is not one.

**The band exists to stop nonsense, not to set the price.** Offers outside half to
four times the anchor are dropped before the crossing, on the magnitude of the
anchor rather than on its sign: the solar block clears below zero on most days of
this model's year, and a band that took the multipliers in the order they were
written would invert there and admit nothing, because a curve with a
thousand-dollar offer at one end has a crossing point that reflects the outlier
rather than the market. A band that bound often would be a price control; a test
pins that it does not bind on the curves this model generates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BAND = (0.5, 4.0)


@dataclass(frozen=True)
class Order:
    """One party's willingness to trade a volume at a price."""

    party: str
    volume_mw: float
    price_per_mwh: float

    def __post_init__(self) -> None:
        if self.volume_mw <= 0:
            raise ValueError("an order with no volume is not an order")


@dataclass(frozen=True)
class Crossed:
    """The outcome: one price, one volume, and who traded."""

    price_per_mwh: float
    volume_mw: float
    writers: tuple[tuple[str, float], ...]
    holders: tuple[tuple[str, float], ...]
    dropped: int = 0

    @property
    def cleared(self) -> bool:
        return self.volume_mw > 0


def _in_band(orders: list[Order], anchor: float,
             band: tuple[float, float]) -> tuple[list[Order], int]:
    # Sorted, because the anchor can be negative and the band then inverts: half of
    # minus two dollars is minus one and four times it is minus eight, so the
    # multipliers arrive the wrong way round. The solar block clears below zero in
    # this model most days of the year, so this is the ordinary case rather than an
    # edge one, and unsorted it dropped every order in that block.
    low, high = sorted((anchor * band[0], anchor * band[1]))
    keep = [o for o in orders if low <= o.price_per_mwh <= high]
    return keep, len(orders) - len(keep)


def _fill(orders: list[Order], volume: float) -> tuple[tuple[str, float], ...]:
    """Allocate a cleared volume down an ordered curve, the last one in part."""
    out: list[tuple[str, float]] = []
    left = volume
    for order in orders:
        if left <= 1e-12:
            break
        take = min(order.volume_mw, left)
        out.append((order.party, take))
        left -= take
    return tuple(out)


def cross(writers: list[Order], holders: list[Order], anchor: float,
          band: tuple[float, float] = BAND) -> Crossed:
    """Clear an ascending writer curve against a descending holder curve.

    The crossing is the volume at which the holders' willingness to pay stops
    covering the writers' willingness to sell. Everybody who trades settles at one
    price, taken as the midpoint of the last pair that agreed: the marginal writer
    would have accepted less and the marginal holder would have paid more, and
    splitting the difference is the convention that does not hand the whole of the
    last trade's surplus to one side by construction.
    """
    if anchor == 0:
        raise ValueError(
            "a crossing cannot band against an anchor of zero: every multiple of it "
            "is zero, so the band admits nothing"
        )
    sell, dropped_s = _in_band(writers, anchor, band)
    buy, dropped_b = _in_band(holders, anchor, band)
    sell = sorted(sell, key=lambda o: o.price_per_mwh)
    buy = sorted(buy, key=lambda o: -o.price_per_mwh)

    volume = 0.0
    last_sell = last_buy = None
    i = j = 0
    sold = bought = 0.0
    while i < len(sell) and j < len(buy):
        if buy[j].price_per_mwh < sell[i].price_per_mwh:
            break
        step = min(sell[i].volume_mw - sold, buy[j].volume_mw - bought)
        volume += step
        sold += step
        bought += step
        last_sell, last_buy = sell[i].price_per_mwh, buy[j].price_per_mwh
        if sold >= sell[i].volume_mw - 1e-12:
            i += 1
            sold = 0.0
        if bought >= buy[j].volume_mw - 1e-12:
            j += 1
            bought = 0.0

    dropped = dropped_s + dropped_b
    if volume <= 0 or last_sell is None:
        return Crossed(price_per_mwh=0.0, volume_mw=0.0, writers=(), holders=(),
                       dropped=dropped)
    price = 0.5 * (last_sell + last_buy)
    return Crossed(price_per_mwh=price, volume_mw=volume,
                   writers=_fill(sell, volume), holders=_fill(buy, volume),
                   dropped=dropped)


def ladder(party: str, anchor: float, volume_mw: float, steps: int,
           spread: float, ascending: bool) -> list[Order]:
    """One party's curve: ``steps`` equal slices, priced away from the anchor.

    A producer's first slice is offered below the anchor and its last above, because
    the megawatts it has not yet sold are worth more to it than the ones it has. A
    retailer's curve is the mirror. ``spread`` is how far the curve reaches from the
    anchor as a fraction of it, and it is the only thing that decides how elastic
    either side is.
    """
    if steps < 1 or volume_mw <= 0:
        return []
    slice_mw = volume_mw / steps
    offsets = np.linspace(-spread, spread, steps) if steps > 1 else np.array([0.0])
    if not ascending:
        offsets = offsets[::-1]
    return [Order(party=party, volume_mw=slice_mw,
                  price_per_mwh=anchor * (1.0 + float(off)))
            for off in offsets]
