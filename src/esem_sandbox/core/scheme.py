"""A state scheme: one row, a milestone a year, and a counterparty that holds on.

The procurement scheme in ``esem.py`` buys reliability. This buys a service somebody
decided they wanted, which is a different thing and behaves differently in three
ways that matter.

**It has a quantity of its own.** The lane volume in the reliability scheme is
computed from projected unserved energy, so it moves with the system. A scheme's
milestone is a number in a policy, and it does not care what the market is doing.
That is the point of modelling it: a target that is easy in one year and impossible
in another is exactly what a milestone is.

**It can fail, and how it failed is the output.** A milestone is not always met, and
the interesting question is which constraint stopped it: nobody eligible bid, every
bid was above the price ceiling, or the money ran out. Recording "awarded 300 of
500 MW" and leaving it there hides the only thing a reader wanted to know. So the
binding channel is named every year, including in the years when nothing bound.

**Its counterparty holds to maturity.** The administrator sells its position back to
retailers and charges consumers the difference. A scheme counterparty does not: it
holds what it bought until the contract runs out. That means the cost lands
differently and it is not recycled into anybody's hedge book, which is a real
difference between the two instruments rather than a simplification of one.

There is no lateness channel. A plant that is awarded arrives after its lead time
and not later, because slippage is a distribution this model does not have and
inventing one would put a number on a risk it cannot measure.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from .contracts import Contract, SWAP
from .esem import AwardLine, Bid, clear_pay_as_bid

SCHEME_COUNTERPARTY = "scheme_counterparty"

# Why a milestone was not met. Ordered, because more than one can be true at once
# and a reader wants the one that bound first.
NOTHING_SOUGHT = "nothing sought"
MET = "met"
NO_ELIGIBLE_BIDS = "no eligible bids"
PRICE_CEILING = "the price ceiling"
BUDGET = "the budget"
SUPPLY = "nobody had any more to sell"


@dataclass(frozen=True)
class SchemeRow:
    """One scheme: what it buys, how much a year, from whom, and on what terms."""

    service: str
    milestones: dict[int, float]
    technologies: tuple[str, ...]
    ceiling_per_mw_year: float
    budget_per_year: float
    tenor_years: int

    def sought(self, year: int) -> float:
        return float(self.milestones.get(year, 0.0))


@dataclass(frozen=True)
class SchemeYear:
    """One year of one scheme, and the reason it went the way it did."""

    year: int
    service: str
    sought_mw: float
    awarded_mw: float
    spend: float
    binding: str

    @property
    def shortfall_mw(self) -> float:
        return max(0.0, self.sought_mw - self.awarded_mw)


def _eligible(bids: list[Bid], row: SchemeRow) -> list[Bid]:
    return [b for b in bids if b.technology in row.technologies]


def _under_ceiling(bids: list[Bid], row: SchemeRow) -> list[Bid]:
    return [b for b in bids if b.price_per_mw_year <= row.ceiling_per_mw_year]


def _affordable(lines: list[AwardLine], budget: float) -> tuple[list[AwardLine], bool]:
    """Take award lines in merit order until the money runs out.

    The last line is taken in part rather than dropped whole: a scheme with a budget
    for two thirds of a project buys two thirds of it, and one that rounded down
    would report a budget as binding harder than it does.
    """
    kept: list[AwardLine] = []
    left = budget
    bound = False
    for line in lines:
        if left <= 0:
            bound = True
            break
        if line.cost <= left:
            kept.append(line)
            left -= line.cost
            continue
        bound = True
        share = left / line.cost if line.cost > 0 else 0.0
        if share > 0:
            kept.append(AwardLine(bid=line.bid, firm_mw=line.firm_mw * share,
                                  capacity_mw=line.capacity_mw * share,
                                  price_per_mw_year=line.price_per_mw_year))
        left = 0.0
    return kept, bound


def clear_scheme(row: SchemeRow, bids: list[Bid], year: int
                 ) -> tuple[SchemeYear, list[AwardLine]]:
    """One year of one scheme, through the same clearing the auction uses.

    The order of the checks is the order a reader would ask them in: was anything
    sought, did anybody eligible bid, was anything under the ceiling, did the money
    last, and did supply run out. The first one that bound is the one reported,
    because a year in which three things bound at once is still a year in which one
    of them bound first.
    """
    sought = row.sought(year)
    if sought <= 0:
        return SchemeYear(year, row.service, 0.0, 0.0, 0.0, NOTHING_SOUGHT), []

    eligible = _eligible(bids, row)
    if not eligible:
        return SchemeYear(year, row.service, sought, 0.0, 0.0, NO_ELIGIBLE_BIDS), []

    affordable = _under_ceiling(eligible, row)
    if not affordable:
        return SchemeYear(year, row.service, sought, 0.0, 0.0, PRICE_CEILING), []

    lines = clear_pay_as_bid(affordable, sought)
    lines, budget_bound = _affordable(lines, row.budget_per_year)
    awarded = sum(line.firm_mw for line in lines)
    spend = sum(line.cost for line in lines)

    if awarded >= sought - 1e-9:
        binding = MET
    elif budget_bound:
        binding = BUDGET
    elif len(affordable) < len(eligible):
        binding = PRICE_CEILING
    else:
        binding = SUPPLY
    return SchemeYear(year, row.service, sought, awarded, spend, binding), lines


def scheme_contracts(lines: list[AwardLine], row: SchemeRow, *,
                     strikes: dict[str, float], commissioning: dict[str, int]
                     ) -> list[Contract]:
    """What the scheme signs, held to maturity by its counterparty.

    Written the same way round as an award in the reliability scheme: the generator
    writes and the counterparty holds, so the generator receives the strike whatever
    the pool does. The difference is what happens next, which is nothing. The
    counterparty does not recycle, warehouse or fire-sell; it holds.
    """
    out: list[Contract] = []
    for line in lines:
        party = line.bid.bidder
        out.append(Contract(
            kind=SWAP, holder=SCHEME_COUNTERPARTY, writer=party,
            strike_per_mwh=strikes[line.bid.technology],
            volume_mw=line.capacity_mw,
            start_year=commissioning[line.bid.technology],
            tenor_years=row.tenor_years, block="overnight",
        ))
    return out


def load_scheme(settings: Settings) -> SchemeRow | None:
    """The packaged scheme row, or nothing when the model is not running one.

    Returns ``None`` rather than an empty scheme, so a caller has to decide what to
    do about a scheme that is not there instead of quietly clearing one with no
    milestones in it.
    """
    from ..config import read_csv

    rows = read_csv("scheme.csv")
    if not rows:
        return None
    milestones = {int(r["year"]): float(r["milestone_mw"]) for r in rows}
    service = rows[0]["service"]
    if any(r["service"] != service for r in rows):
        raise ValueError(
            "scheme.csv holds more than one service; this model runs one scheme row"
        )
    return SchemeRow(
        service=service,
        milestones=milestones,
        technologies=tuple(settings.scheme["technologies"]),
        ceiling_per_mw_year=float(settings.scheme["ceiling_per_mw_year"]),
        budget_per_year=float(settings.scheme["budget_per_year"]),
        tenor_years=int(settings.scheme["tenor_years"]),
    )
