"""The procurement scheme: a lane, an auction, a book and a levy.

This is the mechanism the whole model exists to put a number on. An administrator
buys firm capacity that the market on its own would not build, pays for it with
long-dated contracts, sells the resulting cover back to retailers, and charges
consumers the difference. Everything about whether that is worth doing turns on four
quantities, and each one is computed here rather than assumed:

**How much to buy.** Not a reserve margin, and not a share of peak. The lane volume
is the delivered firm capacity that brings expected unserved energy at the near
anchor down to the reliability standard, computed on each cell's hourly shortfall.
A reserve margin is a rule of thumb about a quantity; this is the quantity itself.
The margin is still worked out and reported, because an audience will ask, but it is
telemetry and never volume.

**What it is worth.** Bids are long-run cost at a blended cost of capital, screened
against a ceiling, and cleared pay-as-bid in merit order until the gap is closed.
Pay-as-bid rather than uniform price because that is what the scheme being modelled
does, and the difference between the two is one of the things a workshop can measure
here by changing a line.

**When it is committed.** At award, not at commissioning. That is the whole point of
the instrument: a contract signed today is what lets a plant reach a final investment
decision today, and the plant arrives after its lead time. The contract is dated to
start when the plant starts.

**Who pays.** The administrator's net settlement position, plus its overheads,
divided by the energy consumers actually took, in the same year. No smoothing, no
fund, no borrowing: a levy that arrives in the year the money moved is a levy an
audience can add up.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config import Settings, TechCost
from .contracts import Contract, SWAP
from .forward import Anchor

ADMINISTRATOR = "administrator"


# --------------------------------------------------------------------------
# How much to buy


def unserved_after_firm(anchor: Anchor, firm_mw: float) -> float:
    """Expected unserved energy at this anchor if ``firm_mw`` of firm capacity ran.

    Firm capacity meets the shortest part of the shortfall first, hour by hour: a
    megawatt of capacity can serve a megawatt in every hour it is called, so what it
    removes is the part of each hour's gap that falls under it. Weighted across
    cells at their own probabilities, never counted.
    """
    total = 0.0
    for outcome in anchor.outcomes:
        if outcome.operational_demand_mwh <= 0:
            continue
        left = float(np.clip(outcome.shortfall_mw - firm_mw, 0.0, None).sum())
        total += outcome.cell.weight * left / outcome.operational_demand_mwh
    return total


def lane_volume_mw(anchor: Anchor, settings: Settings,
                   tolerance_mw: float = 1.0) -> float:
    """The delivered firm capacity that brings expected unserved energy to the standard.

    Monotone in capacity, so a bisection finds it exactly. Returns zero when the
    anchor already sits inside the standard, which is the answer that matters most:
    a scheme that buys capacity a reliable system does not need is a scheme whose
    cost has no benefit to set against it, and this model should be able to show
    that rather than assume it away.
    """
    standard = float(settings.reliability["standard_use_fraction"])
    if unserved_after_firm(anchor, 0.0) <= standard:
        return 0.0
    lo = 0.0
    hi = max((float(o.shortfall_mw.max()) for o in anchor.outcomes), default=0.0)
    if hi <= 0.0 or unserved_after_firm(anchor, hi) > standard:
        return hi                       # even covering the deepest hour is not enough
    while hi - lo > tolerance_mw:
        mid = 0.5 * (lo + hi)
        if unserved_after_firm(anchor, mid) > standard:
            lo = mid
        else:
            hi = mid
    return hi


def reserve_margin_gap_mw(anchor: Anchor, firm_capacity_mw: float,
                          peak_mw: float, margin: float = 0.15) -> float:
    """The deterministic reserve-margin gap, for reporting only.

    This is the number a planner would quote and an audience will ask about, so it
    is computed and shown. It is never the lane volume. A margin is a rule of thumb
    about how much capacity a peak needs; the lane is sized on the shortfall itself,
    and the two differ by however wrong the rule of thumb is on this fleet.
    """
    return max(0.0, peak_mw * (1.0 + margin) - firm_capacity_mw)


# --------------------------------------------------------------------------
# What it is worth


@dataclass(frozen=True)
class Bid:
    """One entrant's offer into the lane, in delivered firm megawatts."""

    bidder: str
    technology: str
    capacity_mw: float
    firm_mw: float
    price_per_mw_year: float
    lead_years: int

    def __post_init__(self) -> None:
        if self.capacity_mw <= 0 or self.firm_mw <= 0:
            raise ValueError("a bid with no capacity is not a bid")


def blended_wacc(tech: TechCost, settings: Settings, contracted_share: float) -> float:
    """The cost of capital a part-contracted project is financed at.

    A contracted megawatt is financed as debt would be and an uncontracted one as
    equity is, so a project that is mostly contracted borrows more cheaply. This is
    the channel through which a long-dated contract lowers the cost of the plant
    rather than only the risk of the investor, and it is why the scheme can be worth
    more than the risk premium it removes.
    """
    floor = float(settings.esem["contracted_wacc"])
    share = float(np.clip(contracted_share, 0.0, 1.0))
    return tech.wacc + share * (floor - tech.wacc)


def long_run_cost_per_mw_year(tech: TechCost, wacc: float,
                              energy_margin_per_mw_year: float) -> float:
    """What a plant needs from the lane, net of what it earns in the pool.

    The energy margin is netted for the same reason the cap's cost basis nets it: a
    plant that earns in the market does not need to be paid for that twice, and a
    lane that ignored it would price capacity at roughly double what it costs.
    """
    r, n = wacc, tech.life_years
    crf = r / (1.0 - (1.0 + r) ** -n) if r > 0 else 1.0 / n
    fixed = tech.capex_per_kw * 1000.0 * crf + tech.fom_per_kw_year * 1000.0
    return max(0.0, fixed - energy_margin_per_mw_year)


def screen(bids: list[Bid], spot_per_mwh: float, settings: Settings) -> list[Bid]:
    """Reject bids above the sanity ceiling.

    The ceiling is the larger of a multiple of the spot price and a floor, so it
    scales with a market that is genuinely expensive without collapsing to nothing in
    a cheap year. It is a screen against nonsense, not a price cap: a scheme that
    quietly capped its own clearing price would report a cost it did not pay.
    """
    multiple = float(settings.esem["screen_multiple_of_spot"])
    floor = float(settings.esem["screen_floor_per_mwh"])
    ceiling_per_mwh = max(multiple * spot_per_mwh, floor)
    ceiling = ceiling_per_mwh * 8760.0
    return [b for b in bids if b.price_per_mw_year <= ceiling]


@dataclass(frozen=True)
class AwardLine:
    bid: Bid
    firm_mw: float
    capacity_mw: float
    price_per_mw_year: float

    @property
    def cost(self) -> float:
        return self.firm_mw * self.price_per_mw_year


def clear_pay_as_bid(bids: list[Bid], gap_mw: float) -> list[AwardLine]:
    """Cheapest first until the gap is closed, each paid what it asked.

    Pay-as-bid, so the last megawatt in does not lift the price of every megawatt
    before it. The final bid is taken in part rather than whole where the gap runs
    out inside it: a lane that rounded up would buy capacity it had not decided it
    needed, and one that rounded down would stop short of the standard it exists to
    meet.
    """
    if gap_mw <= 0:
        return []
    out: list[AwardLine] = []
    left = gap_mw
    # Stable sort on price alone. Breaking ties by name would hand every award to
    # whichever firm sorts first, which is the auction's version of the build
    # ceiling being captured by whoever is asked first; the caller offers the bids
    # in an order that rotates instead.
    for bid in sorted(bids, key=lambda b: b.price_per_mw_year):
        if left <= 0:
            break
        take = min(bid.firm_mw, left)
        share = take / bid.firm_mw
        out.append(AwardLine(bid=bid, firm_mw=take,
                             capacity_mw=bid.capacity_mw * share,
                             price_per_mw_year=bid.price_per_mw_year))
        left -= take
    return out


# --------------------------------------------------------------------------
# When it is committed


def award_strike_per_mwh(expected_price_per_mwh: float, line: AwardLine) -> float:
    """The strike that pays an awardee exactly what it bid.

    A swap settles the difference between the strike and the spot price on the
    contracted volume, so a plant selling into the pool and holding one receives the
    strike whatever the pool does. Setting the strike at the expected price plus the
    bid, spread over the hours of the year, makes the contract worth the bid and
    nothing else: the scheme pays for the capacity it asked for, not for a view about
    where prices are going.
    """
    if line.capacity_mw <= 0:
        return expected_price_per_mwh
    return expected_price_per_mwh + line.cost / (line.capacity_mw * 8760.0)


def award_contract(line: AwardLine, strike_per_mwh: float, *, generator: str,
                   commissioning_year: int, tenor_years: int) -> Contract:
    """The contract an award writes, dated to start when the plant starts.

    The generator WRITES and the administrator HOLDS, which is the direction that
    fixes the generator's price: it sells into the pool at whatever the pool pays and
    the contract makes up the difference to the strike. The administrator therefore
    carries the market position, which is exactly what it then recycles to retailers.

    Dated at commissioning, not at award. That is the instrument's whole point: the
    contract is what lets the plant reach a final investment decision now, and the
    plant arrives after its lead time. A contract that started at award would pay for
    delivery before there was anything to deliver.
    """
    return Contract(
        kind=SWAP, holder=ADMINISTRATOR, writer=generator,
        strike_per_mwh=strike_per_mwh, volume_mw=line.capacity_mw,
        start_year=commissioning_year, tenor_years=tenor_years, block="overnight",
    )


# --------------------------------------------------------------------------
# Who pays


@dataclass
class Administrator:
    """The scheme's books, and the levy that balances them.

    It holds the long side of every award and sells one-year strips of that position
    back to retailers. Whatever it does not sell it carries. Whatever it is left out
    of pocket, plus what it costs to run, consumers pay in the same year.
    """

    awards: list[Contract] = field(default_factory=list)
    recycled: list[Contract] = field(default_factory=list)
    warehoused_mw: dict[int, float] = field(default_factory=dict)
    levy_paid: list[float] = field(default_factory=list)

    def held_mw(self, year: int) -> float:
        """The position the administrator carries into a delivery year."""
        return sum(c.volume_mw for c in self.awards if c.in_force(year))

    def sold_mw(self, year: int) -> float:
        return sum(c.volume_mw for c in self.recycled if c.in_force(year))


def recycle(admin: Administrator, settings: Settings, *, year: int,
            anchor_per_mwh: float, buyers: list[tuple[str, float]]) -> list[Contract]:
    """Offer each delivery year's position back as a one-year strip.

    Per tranche, from this year out to the recycling window, so a retailer can buy
    cover for a year it can actually see. Volume nobody takes is warehoused rather
    than dumped, unless the conduct lever says otherwise: what an administrator does
    with unsold volume is a policy question with a real price attached, and making it
    a lever is how a workshop can put a number on it.
    """
    window = int(settings.esem["recycling_window_years"])
    conduct = str(settings.esem["recycling_conduct"])
    if conduct not in ("warehouse", "fire_sale"):
        raise ValueError(
            f"unknown recycling conduct {conduct!r}: expected 'warehouse' or "
            "'fire_sale'"
        )
    written: list[Contract] = []
    for delivery in range(year, year + window + 1):
        available = admin.held_mw(delivery) - admin.sold_mw(delivery)
        if available <= 0:
            continue
        price = anchor_per_mwh
        if conduct == "fire_sale":
            price = anchor_per_mwh * float(settings.esem["fire_sale_fraction"])
        wanted = sum(mw for _name, mw in buyers)
        taken = min(available, wanted)
        for name, mw in buyers:
            share = (mw / wanted) if wanted > 0 else 0.0
            volume = taken * share
            if volume <= 0:
                continue
            written.append(Contract(
                kind=SWAP, holder=name, writer=ADMINISTRATOR,
                strike_per_mwh=price, volume_mw=volume, start_year=delivery,
                tenor_years=1, block="overnight",
            ))
        admin.warehoused_mw[delivery] = available - taken
    admin.recycled.extend(written)
    return written


def levy_per_mwh(net_settlement: float, settings: Settings,
                 consumed_mwh: float) -> float:
    """What consumers pay this year, per megawatt hour they took.

    Minus the administrator's net position plus what it costs to run, in the year the
    money moved. No fund, no smoothing and no borrowing: a levy that arrives in the
    year of the cashflow is one an audience can add up, and one that does not let a
    scheme look cheap by moving its cost into a year nobody is looking at.
    """
    if consumed_mwh <= 0:
        return 0.0
    return (-net_settlement + float(settings.esem["overhead_per_year"])) / consumed_mwh


# --------------------------------------------------------------------------
# What a megawatt of each thing is worth to the lane


def shortfall_hours_per_day(anchor: Anchor) -> float:
    """The longest run of shortfall a single day carries, expected across cells.

    This is what decides whether duration matters. A store with four hours of energy
    covers a four-hour evening gap completely and a twelve-hour one only a third of
    the way, and no credit factor written into a table can tell those apart, because
    the difference is a property of the weather rather than of the battery.
    """
    total = 0.0
    for outcome in anchor.outcomes:
        short = outcome.shortfall_mw
        if short.size == 0:
            continue
        days = short.size // 24
        by_day = (short[:days * 24].reshape(days, 24) > 0).sum(axis=1)
        total += outcome.cell.weight * float(by_day.max() if days else 0)
    return total


def firm_contribution_mw(tech: TechCost, capacity_mw: float,
                         anchor: Anchor) -> float:
    """The firm capacity one plant delivers to the lane.

    Dispatchable plant is credited at its availability times its planner credit: it
    can run whenever it is called, less the time it is out.

    Storage is MEASURED, not credited. A store can only cover a shortfall for as long
    as its energy lasts, so a four-hour battery against a six-hour gap delivers two
    thirds of its power and no more. Reading a firm factor out of a table instead
    would let a scheme buy energy-limited capacity as though it were firm, and then
    discover in the year it mattered that it had bought two thirds of what it paid
    for.
    """
    rated = capacity_mw * tech.availability
    if not tech.duration_h:
        return rated * tech.firm_factor
    gap_hours = shortfall_hours_per_day(anchor)
    if gap_hours <= 0:
        return rated * tech.firm_factor
    return rated * min(1.0, float(tech.duration_h) / gap_hours)


def eligible_technologies(settings: Settings) -> list[TechCost]:
    """What may bid: plant that can be relied on when the system is tight.

    The same column that decides what may write a cap decides what may bid into the
    lane, and for the same reason. A wind farm is not a worse investment than a
    peaker; it is a different product, and a lane that buys reliability should not be
    able to buy something that is only sometimes there.
    """
    return [t for t in settings.tech_costs if t.cap_eligible]
