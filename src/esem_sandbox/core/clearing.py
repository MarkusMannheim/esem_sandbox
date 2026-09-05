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

def cara_coefficient(risk_aversion: float, exposure: float,
                     settings: Settings) -> float:
    """One agent's absolute risk aversion over dollars per MW-year.

    THE ONLY PLACE a CARA coefficient is built, and both the cap lane and the
    investment rule go through it. That is not tidiness. A firm deciding whether to
    write a cap and a firm deciding whether to build the peaker that would cover it
    are pricing the same tail, and if they priced it at different coefficients the
    model would generate trades out of its own inconsistency: write the cap, decline
    the plant, and bank a difference that exists only because two functions
    disagreed. The two were briefly built separately here and did disagree, by a
    factor of two.

    Archetype risk aversion is a fraction on a nought-to-one scale. Exposure scales
    the coefficient because hedging removes risk borne rather than risk existing: a
    producer with no residual exposure has a coefficient of zero, at which point the
    certainty equivalent is the expected value and the rule it feeds reduces to
    expected rent against fixed cost. A cap writer passes an exposure of one,
    because writing naked insurance is what being unhedged means.
    """
    lam = risk_aversion * float(settings.investment["risk_premium"])
    return 2.0 * lam * max(0.0, exposure) * float(settings.investment["cara_scale"])


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
                 settings: Settings, exposure: float = 1.0) -> float:
    """What a writer charges for bearing this payout distribution.

    A writer is unhedged against what it has written, so the default exposure is
    one. The argument exists so that the coefficient comes from the same place the
    investment rule's does, not so that a caller can quietly pick a different one.
    """
    a = cara_coefficient(risk_aversion, exposure, settings)
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


def energy_margin_per_mw_year(price: np.ndarray, srmc_per_mwh: float,
                              availability: float) -> float:
    """What a unit earns in the pool above its own running cost, per MW of capacity.

    It runs only when the price covers its cost, so the margin is the positive part,
    and it is available only some of the time.
    """
    return float(np.clip(price - srmc_per_mwh, 0.0, None).sum() * availability)


def cap_cost_basis(capex_per_kw: float, fom_per_kw_year: float, wacc: float,
                   life_years: float, firm_factor: float,
                   energy_margin_per_mw_year: float) -> float:
    """What a peaker needs per firm MW-hour, net of what it earns selling energy.

    The energy margin is required rather than defaulted, because forgetting it is not
    a small error. On the packaged fleet a peaker's fixed cost is about $136,000 per
    MW-year and it earns about $69,000 of that in the pool, so ignoring the margin
    doubles the basis and prices the cap above what it can ever be expected to pay.
    A caller with genuinely no energy margin should pass zero and mean it.
    """
    crf = wacc / (1.0 - (1.0 + wacc) ** -life_years) if wacc > 0 else 1.0 / life_years
    fixed = capex_per_kw * 1000.0 * crf + fom_per_kw_year * 1000.0
    net = max(fixed - energy_margin_per_mw_year, 0.0)
    return net / (firm_factor * 8760.0)


def cap_anchor(cost_basis_per_mwh: float, realised_mean_excess_per_mwh: float,
               payoffs_per_mw: np.ndarray, weights: np.ndarray,
               writer_risk_aversion: float, settings: Settings) -> float:
    """The cap lane's anchor.

    The floor is the greater of what the plant needs and what the cap has lately been
    worth; the loading is the writer's risk on top. Note what is NOT here: the
    within-year dispersion of hourly excess. That is the volatility of the spot price,
    not the risk the writer carries, and using it lifted the larger model's cap anchor
    to about $2,000/MWh on the strength of a single scarce interval.
    """
    floor = max(cost_basis_per_mwh, realised_mean_excess_per_mwh)
    hours = 8760.0
    loading_per_mwh = risk_loading(payoffs_per_mw, weights, writer_risk_aversion,
                                   settings) / hours
    return floor + loading_per_mwh


def realised_mean_excess(price: np.ndarray, strike: float) -> float:
    """Mean excess over the strike, over every hour of the year.

    The full series, never a sampled duration curve.
    """
    return float(np.mean(np.clip(price - strike, 0.0, None)))


def block_prices_of(settings: Settings, price: np.ndarray) -> dict[str, float]:
    return {b: float(price[block_mask(settings, b, len(price))].mean())
            for b in settings.blocks()}
