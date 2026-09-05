"""Contracts, and the settlement that moves money between the parties to them.

Two products, which is enough to carry the whole argument:

A **swap** fixes a price for a block of hours. The holder receives the difference
between the spot price and the strike, so a retailer holding swaps is insulated from
high prices and gives up the gains from low ones. It is a contract for difference on
MW, not an obligation to deliver energy.

A **cap** pays the holder whatever the spot price exceeds the strike, and nothing
when it does not, in exchange for a premium paid on every hour of the leg. It is
insurance against scarcity, and it is what a peaker sells when it cannot sell energy.

Settlement is deliberately blunt about one thing: a cap's payout is integrated over
every settled interval of the period. Sampling the price series and integrating over
the samples is how a single scarce interval comes to be paid as though it lasted for
tens of hours, which is the defect this model's larger sibling was carrying when this
one was written.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import Settings
from .report import block_mask, quarter_of_hour

SWAP = "swap"
CAP = "cap"


@dataclass(frozen=True)
class Contract:
    """One contract between two parties.

    ``volume_mw`` is the contracted quantity. ``block`` names the time-of-day block a
    swap applies to; a cap applies to every hour. ``premium_per_mwh`` is paid by the
    holder on every hour of the leg and is zero for a swap, whose price is its strike.
    """

    kind: str
    holder: str
    writer: str
    strike_per_mwh: float
    volume_mw: float
    start_year: int
    tenor_years: int
    block: str | None = None
    premium_per_mwh: float = 0.0
    quarter: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in (SWAP, CAP):
            raise ValueError(f"unknown contract kind: {self.kind}")
        if self.kind == SWAP and self.block is None:
            raise ValueError("a swap must name the block it applies to")
        if self.kind == CAP and self.premium_per_mwh <= 0:
            raise ValueError("a cap without a premium is a gift, not a contract")
        if self.tenor_years < 1:
            raise ValueError("tenor must be at least one year")
        if self.volume_mw < 0:
            raise ValueError("volume cannot be negative")

    def in_force(self, year: int) -> bool:
        """Contracts struck at t first settle at t+1, so delivery starts at start_year."""
        return self.start_year <= year < self.start_year + self.tenor_years

    def delivery_years(self) -> range:
        return range(self.start_year, self.start_year + self.tenor_years)


def hours_of(settings: Settings, contract: Contract, n_hours: int) -> np.ndarray:
    """The hours this contract settles over, as a boolean mask."""
    mask = np.ones(n_hours, dtype=bool)
    if contract.block is not None:
        mask &= block_mask(settings, contract.block, n_hours)
    if contract.quarter is not None:
        mask &= quarter_of_hour(n_hours) == contract.quarter
    return mask


def settle(settings: Settings, contract: Contract, price: np.ndarray,
           year: int) -> dict[str, float]:
    """One year of one contract, as a cashflow per party.

    Returns a mapping of party to dollars, positive being money received. The two
    entries sum to zero by construction: a contract moves money, it does not make
    any. Settlement over the full hourly series, never a sampled curve.
    """
    if not contract.in_force(year):
        return {contract.holder: 0.0, contract.writer: 0.0}

    mask = hours_of(settings, contract, len(price))
    hours = price[mask]
    if contract.kind == SWAP:
        to_holder = float(np.sum(hours - contract.strike_per_mwh) * contract.volume_mw)
    else:
        payout = float(np.sum(np.clip(hours - contract.strike_per_mwh, 0.0, None))
                       * contract.volume_mw)
        premium = contract.premium_per_mwh * contract.volume_mw * float(mask.sum())
        to_holder = payout - premium
    return {contract.holder: to_holder, contract.writer: -to_holder}


def settle_book(settings: Settings, book: list[Contract], price: np.ndarray,
                year: int) -> dict[str, float]:
    """Every contract in force this year, netted by party."""
    out: dict[str, float] = {}
    for contract in book:
        for party, amount in settle(settings, contract, price, year).items():
            out[party] = out.get(party, 0.0) + amount
    return out


def age(book: list[Contract], year: int) -> list[Contract]:
    """The contracts still in force after ``year`` has settled.

    One owner per object: contracts are dropped from the book when they expire rather
    than being marked expired and kept, so a book that is empty is empty.
    """
    return [c for c in book if c.in_force(year + 1)]
