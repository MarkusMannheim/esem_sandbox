"""Bilateral clearing: what a contract costs before anyone has signed one.

Four swap lanes, one per time-of-day block, and one cap lane. Each lane has an anchor,
which is the price the lane clears at in the core model. The bid-curve crossing that
the larger model uses is an extension; the anchor is what the talk is written from,
because it can be explained in a sentence and checked by hand.

A swap lane's anchor is what the block has been worth lately, on an exponentially
weighted average of realised block prices. Nobody in this market forecasts; they
extrapolate, which is what makes the boom-and-bust exercise work.

A cap lane's anchor is different in kind. A cap is insurance, so its price is the cost
of standing ready plus the price of bearing the risk:

    anchor = max(cost basis, realised mean excess) + loading

The cost basis is what a peaker needs per firm MW-hour to exist at all. The loading is
the risk. It is computed as the writer's certainty-equivalent gap, E[payout] minus
CE(payout), across the cells of whatever distribution is available, rather than as a
multiple of the standard deviation. The reason is consistency, not elegance: the
investment rule already uses an exact CARA certainty equivalent, so pricing the same
risk by mean-variance here would let the same firm value the same tail two different
ways in the same tick, and arbitrage the difference between building a peaker and
writing a cap against one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import Settings
from .report import block_mask

# Archetype risk aversion is a fraction on a 0 to 1 scale; this turns it into a CARA
# coefficient over dollars per MW-year. Chosen so a representative writer's loading on
# the packaged distribution is a few per cent of the premium, not a rounding error and
# not the whole price.
CARA_SCALE = 2.0e-5


def cara_certainty_equivalent(payoffs: np.ndarray, weights: np.ndarray,
                              a: float) -> float:
    """The certain amount worth as much as the gamble, to a CARA agent.

    Computed in a shifted frame so that exp() cannot overflow on payoffs of the size a
    scarcity year produces.
    """
    if a <= 0:
        return float(payoffs @ weights)
    shift = float(payoffs.max())
    ce = shift - (1.0 / a) * np.log(float(np.sum(weights * np.exp(-a * (payoffs - shift)))))
    return float(ce)


def risk_loading(payoffs: np.ndarray, weights: np.ndarray, risk_aversion: float,
                 scale: float = CARA_SCALE) -> float:
    """What a writer charges for bearing this payout distribution."""
    a = risk_aversion * scale
    return float(payoffs @ weights) - cara_certainty_equivalent(payoffs, weights, a)


def ewma_block_anchor(history: list[dict[str, float]], block: str,
                      half_life_years: float = 2.0) -> float:
    """The lane anchor: what this block has been worth, recent years counting more."""
    if not history:
        raise ValueError("no price history to anchor on")
    decay = 0.5 ** (1.0 / half_life_years)
    num = den = 0.0
    for age, year in enumerate(reversed(history)):
        w = decay ** age
        num += w * year[block]
        den += w
    return num / den


@dataclass(frozen=True)
class Lane:
    """One product's clearing outcome for a tick."""

    name: str
    anchor_per_mwh: float
    volume_mw: float
    band_low: float
    band_high: float

    def clears_at(self) -> float:
        return float(np.clip(self.anchor_per_mwh, self.band_low, self.band_high))


def cap_cost_basis(capex_per_kw: float, fom_per_kw_year: float, wacc: float,
                   life_years: float, firm_factor: float,
                   energy_margin_per_mw_year: float = 0.0) -> float:
    """What a peaker needs per firm MW-hour, net of what it earns selling energy.

    Netting the energy margin matters: a peaker that already covers part of its fixed
    cost in the pool does not need to recover it twice, and a cap premium that ignores
    this prices the plant as though the energy market did not exist.
    """
    crf = wacc / (1.0 - (1.0 + wacc) ** -life_years) if wacc > 0 else 1.0 / life_years
    fixed = capex_per_kw * 1000.0 * crf + fom_per_kw_year * 1000.0
    net = max(fixed - energy_margin_per_mw_year, 0.0)
    return net / (firm_factor * 8760.0)


def cap_anchor(cost_basis_per_mwh: float, realised_mean_excess_per_mwh: float,
               payoffs_per_mw: np.ndarray, weights: np.ndarray,
               writer_risk_aversion: float) -> float:
    """The cap lane's anchor.

    The floor is the greater of what the plant needs and what the cap has lately been
    worth; the loading is the writer's risk on top. Note what is NOT here: the
    within-year dispersion of hourly excess. That is the volatility of the spot price,
    not the risk the writer carries, and using it lifted the larger model's cap anchor
    to about $2,000/MWh on the strength of a single scarce interval.
    """
    floor = max(cost_basis_per_mwh, realised_mean_excess_per_mwh)
    hours = 8760.0
    loading_per_mwh = risk_loading(payoffs_per_mw, weights, writer_risk_aversion) / hours
    return floor + loading_per_mwh


def realised_mean_excess(price: np.ndarray, strike: float) -> float:
    """Mean excess over the strike, over every hour of the year.

    The full series, never a sampled duration curve.
    """
    return float(np.mean(np.clip(price - strike, 0.0, None)))


def block_prices_of(settings: Settings, price: np.ndarray) -> dict[str, float]:
    return {b: float(price[block_mask(settings, b, len(price))].mean())
            for b in settings.blocks()}
