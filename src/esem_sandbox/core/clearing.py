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

from ..config import Settings, Unit
from .agents import PRODUCER, RETAILER
from .contracts import CAP, SWAP, Contract
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

    Two things here are the fix to defects this function shipped with.

    **The frame is shifted to the WORST cell, not the best.** The identity holds for
    any shift, so the original choice was not wrong arithmetic; it was the
    overflow-prone one, in a function whose docstring said it had been chosen to
    prevent overflow. Shifting by the maximum makes every exponent non-negative and
    the largest of them ``a`` times the spread, so a distribution containing one
    year of rent at the value of lost load overflows to infinity and the certainty
    equivalent comes back as minus infinity. Shifting by the minimum makes every
    exponent non-positive: the worst cell contributes exactly one, better cells
    underflow harmlessly toward zero, and the result is bounded below by the worst
    cell, which is the property the whole construction rests on.

    **Weights must be a probability distribution, and this checks.** Weights that
    sum to something other than one do not raise, they quietly shift the answer by
    ``ln(sum)/a``: at a fifth of the weight and this model's coefficients that is
    $134,000 per MW-year, enough to return a certainty equivalent ABOVE the largest
    payoff in the distribution and to hand a producer a negative hurdle. The model
    this one simplifies carried a defect of exactly this family, where per-cell
    weights were computed, passed everywhere, and then never applied.
    """
    total = float(np.sum(weights))
    if not np.isclose(total, 1.0, atol=1e-9):
        raise ValueError(
            f"weights sum to {total!r}, not 1. A certainty equivalent over weights "
            "that are not a probability distribution is off by ln(sum)/a, which is "
            "a plausible-looking number rather than an error."
        )
    if a <= 0:
        return float(payoffs @ weights)
    shift = float(payoffs.min())
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
                      half_life_years: float) -> float:
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


def _pro_rata(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()} if total > 0 else {}


def clear_bilateral(settings: Settings, roster, fleet, history: list[dict[str, float]],
                    *, year: int, start_year: int, tenor_years: int,
                    average_load_mw: float,
                    peak_load_mw: float, cap_payoffs_per_mw, cap_weights,
                    cap_cost_basis_per_mwh: float,
                    already_covered_mw: dict[str, float] | None = None
                    ) -> list[Contract]:
    """One tick's bilateral market, cleared at the lane anchors.

    Four swap lanes, one per time-of-day block, and one cap lane. Retailers are
    short energy and long customers, so they buy; producers are long energy, so they
    write. Volumes are allocated across writers pro rata to what each has to sell:
    available capacity for swaps, and cap-eligible firm capacity for caps, because a
    plant that cannot be relied on in a scarce hour has no business writing
    insurance against one.

    **Retailers hedge on a ladder.** Each tick a retailer writes a strip of
    ``tenor_years`` sized at one third of its target cover, so three overlapping
    strips carry the target in steady state and the book ages rather than lurching.
    That is what a board mandate produces in practice, and it is also what makes the
    exposure measure mean anything: a book that was written all at once and expired
    all at once would swing a producer between fully covered and naked.

    Legs are quarterly on a flat strip from the start, because the duration-curve
    exercise depends on being able to look at one quarter at a time.
    """
    half_life = float(settings.contracts["anchor_half_life_years"])
    strike = float(settings.contracts["cap_strike_per_mwh"])
    retailers = [a for a in roster if a.kind == RETAILER]
    producers = [a for a in roster if a.kind == PRODUCER]
    if not retailers or not producers or not history:
        return []

    live = {u.unit: u for u in fleet if u.in_service(year)}
    owner = {unit: a.name for a in producers for unit in a.units}
    swap_share = _pro_rata({
        a.name: sum(live[u].available_mw for u in a.units if u in live)
        for a in producers})
    cap_share = _pro_rata({
        a.name: sum(live[u].available_mw * live[u].firm_factor
                    for u in a.units if u in live and live[u].cap_eligible)
        for a in producers})
    if not swap_share:
        return []

    energy_margin = 0.0                     # supplied through the cost basis
    anchor_cap = cap_anchor(cap_cost_basis_per_mwh,
                            float(np.mean(cap_payoffs_per_mw)) / 8760.0,
                            cap_payoffs_per_mw, cap_weights,
                            max(a.risk_aversion for a in producers), settings)

    out: list[Contract] = []
    covered = already_covered_mw or {}
    for retailer in retailers:
        target = retailer.swap_cover * retailer.load_share * average_load_mw
        # Cover bought elsewhere is cover. A retailer that took a recycled strip
        # from the administrator this year does not need the same megawatts from a
        # producer as well, and letting it buy both would have it hedge one load
        # twice and report itself twice as covered as it is.
        target = max(0.0, target - covered.get(retailer.name, 0.0))
        for block in settings.blocks():
            anchor = ewma_block_anchor(history, block, half_life)
            volume = target / max(1, tenor_years)
            for writer, share in swap_share.items():
                if share <= 0 or volume <= 0:
                    continue
                for quarter in range(4):
                    out.append(Contract(
                        kind=SWAP, holder=retailer.name, writer=writer,
                        strike_per_mwh=anchor, volume_mw=volume * share,
                        start_year=start_year, tenor_years=tenor_years,
                        block=block, quarter=quarter))
        volume = (retailer.cap_cover * retailer.load_share * peak_load_mw
                  / max(1, tenor_years))
        for writer, share in cap_share.items():
            if share <= 0 or volume <= 0 or anchor_cap <= 0:
                continue
            for quarter in range(4):
                out.append(Contract(
                    kind=CAP, holder=retailer.name, writer=writer,
                    strike_per_mwh=strike, volume_mw=volume * share,
                    start_year=start_year, tenor_years=tenor_years,
                    premium_per_mwh=anchor_cap, quarter=quarter))
    return out
