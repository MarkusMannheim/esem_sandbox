"""Who builds what, and who gives up.

The investment rule is the reason this model exists. Everything before it exists to
produce one number per candidate technology per possible future - the rent a
megawatt of it would earn in a year - and everything after it exists to move that
number around between the parties. The rule itself is four lines:

    CE_a(r) = -(1/a) ln sum_c w_c exp(-a r_c)      the certainty equivalent
    a       = 2 lambda x exposure x scale          lambda = risk aversion x premium
    fixed   = capex x CRF(wacc, life) + FOM        both sides per MW-year
    build if CE_a(r) >= fixed

Three things about it are load-bearing.

**Rent and cost are both per MW-year,** so no capacity factor enters the
comparison. A peaker running two per cent of the year and a wind farm running
thirty-five are each tested against their own costs, and the capacity-factor gap
that shows up in dispatch stays visible there instead of leaking into a bid.

**The certainty equivalent is exact, not a variance approximation.** A
mean-variance penalty is linear in variance and so quadratic in the price spread,
and with an honest distribution that reaches the value of lost load in a scarcity
year it explodes and prices out the very firm capacity that would have relieved the
scarcity. The exact certainty equivalent saturates: it can never fall below the
worst cell, so a risk-averse investor demands a bounded premium and treats a
scarcity windfall as upside rather than as symmetric risk, which is what it is.

**Risk is priced at the same scale everywhere in the model.** The coefficient here
is built from the constant the cap lane loads risk with. That is not tidiness. If a
firm valued the tail one way when writing a cap and another when building the
peaker that would cover it, it could arbitrage the difference between the two,
and the model would be generating trades out of its own inconsistency.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import Settings, TechCost, Unit
from .agents import Agent, PRODUCER
from .clearing import cara_certainty_equivalent, cara_coefficient
from .contracts import Contract, SWAP, hours_of
from .forward import ForwardView, interpolated_rent

# Only plant whose offer is a running cost is eligible to exit on economics. A wind
# row's offer is a curtailment offer, not a cost, so a rent measured against it
# would be an invention; and a battery's going-forward cost is small enough that an
# exit rule on it would only ever be noise.
EXIT_ELIGIBLE = ("coal", "ccgt", "ocgt")


# --------------------------------------------------------------------------
# Exposure: how much of the spot price this decision is actually taking


def achieved_swap_cover(agent: Agent, book: list[Contract], settings: Settings,
                        year: int, expected_output_mwh: float,
                        n_hours: int = 8760) -> float:
    """The fraction of a producer's expected output already sold forward at a fixed
    price, weighted by the hours each contract's block actually covers.

    Swaps only. A written cap does not fix the writer's price on its output below
    the strike, so it is not price-certain cover in the sense that matters to a
    financier; its income enters the decision as income, not as certainty.

    A peak-only swap covers six hours in twenty-four, and counting it as though it
    covered the day would overstate cover fourfold and buy down a hurdle that
    nothing had been done to buy down.
    """
    if expected_output_mwh <= 0.0:
        return 0.0
    covered = 0.0
    for c in book:
        if c.kind != SWAP or c.writer != agent.name or not c.in_force(year):
            continue
        covered += c.volume_mw * float(hours_of(settings, c, n_hours).sum())
    return max(0.0, min(1.0, covered / expected_output_mwh))


def residual_exposure(settings: Settings, life_years: int, *,
                      swap_cover: float = 0.0, award_years: int = 0,
                      award_cover: float = 0.0) -> float:
    """The share of the project's life still exposed to the spot price.

        exposure = 1 - h x D / L

    ``h`` is the fraction of output covered and ``D`` the tenor of the cover, in a
    life of ``L`` years. Three channels can supply cover, and the LARGEST applies
    rather than their sum, because they cover the same delivery years and adding
    them would let a producer count one year of certainty twice:

    * a bilateral swap book, at the standard bilateral tenor;
    * a capacity underwrite, which is off by default because the merchant leg is
      the policy-free counterfactual and turning it on quietly would make that leg
      a mild policy leg wearing the merchant label;
    * a long-dated award, which is what the scheme leg supplies.

    Cover is capped below one: a contract covers a FORECAST of output, and the
    forecast can be wrong, so no producer is ever fully hedged.
    """
    life = max(1, int(life_years))
    cap = float(settings.investment["hedge_fraction_cap"])
    channels = [
        min(swap_cover, cap) * min(int(settings.investment["bilateral_contract_years"]), life),
        cap * min(int(settings.investment["merchant_underwrite_years"]), life),
        min(award_cover, cap) * min(int(award_years), life),
    ]
    return max(0.0, min(1.0, 1.0 - max(channels) / life))


# --------------------------------------------------------------------------
# Pacing: how fast the fleet is allowed to change


def build_size_mw(peak_mw: float, tech: TechCost, settings: Settings) -> float:
    """One decision's worth of plant, rounded to whole generating units.

    A fraction of system peak, because a build has to be large enough to matter to
    the price it was justified by, and rounded because plant comes in units. Both
    the fraction and the unit size are choices rather than physics, and they live in
    settings.toml and tech_costs.csv where a workshop can see and change them.
    """
    target = peak_mw * float(settings.investment["build_fraction_of_peak"])
    units = max(1, int(round(target / tech.unit_size_mw)))
    return units * tech.unit_size_mw


def build_ceiling_mw(tech: TechCost, settings: Settings) -> float:
    """The most of one technology that can be built in one year.

    This is a damper, and it is here so that the bust in the boom-and-bust exercise
    comes from lead times, which are real, rather than from the absence of any
    limit at all, which is not a mechanism but an oversight.
    """
    return tech.max_annual_build_mw * float(
        settings.investment["build_ceiling_overshoot_factor"])


# --------------------------------------------------------------------------
# The decision


@dataclass(frozen=True)
class Verdict:
    """One candidate, evaluated. Every term the decision turned on is kept, because
    the panel that explains this to a room is the arithmetic itself."""

    technology: str
    capacity_mw: float
    expected_rent_per_mw_year: float
    certainty_equivalent_per_mw_year: float
    fixed_cost_per_mw_year: float
    exposure: float
    contracted_share: float
    builds: bool

    @property
    def risk_discount_per_mw_year(self) -> float:
        """What bearing the spread costs: expected rent less its certainty
        equivalent. Zero for a fully hedged producer."""
        return self.expected_rent_per_mw_year - self.certainty_equivalent_per_mw_year

    @property
    def hurdle_per_mw_year(self) -> float:
        """Fixed cost plus the risk discount: what rent has to reach to build.

        The same test read the other way round, and the way round a chart wants it:
        the effect of a contract is to lower this line, not to raise the bar.
        """
        return self.fixed_cost_per_mw_year + self.risk_discount_per_mw_year

    @property
    def surplus_per_mw_year(self) -> float:
        return self.certainty_equivalent_per_mw_year - self.fixed_cost_per_mw_year


def evaluate(view: ForwardView, tech: TechCost, agent: Agent, settings: Settings,
             *, exposure: float, capacity_mw: float,
             contracted_share: float = 0.0) -> Verdict:
    """One candidate technology, for one producer, against one forward view."""
    rents = view.lifetime_rent(tech)
    weights = view.weights
    a = cara_coefficient(agent.risk_aversion, exposure, settings)
    ce = cara_certainty_equivalent(rents, weights, a)
    fixed = tech.fixed_cost_per_mw_year
    return Verdict(
        technology=tech.technology,
        capacity_mw=capacity_mw,
        expected_rent_per_mw_year=float(rents @ weights),
        certainty_equivalent_per_mw_year=ce,
        fixed_cost_per_mw_year=fixed,
        exposure=exposure,
        contracted_share=contracted_share,
        builds=ce >= fixed,
    )


def rank_candidates(view: ForwardView, agent: Agent, settings: Settings, *,
                    peak_mw: float, swap_cover: float = 0.0,
                    award_years: int = 0, award_cover: float = 0.0
                    ) -> list[Verdict]:
    """Every candidate, best first, for one producer.

    A producer considers a fixed number of candidates a year, which is a pacing
    choice rather than physics. The limit is applied to decisions TAKEN, not to
    arithmetic done: every candidate is priced and the best few are returned.
    Selecting which few to price first would be a rule that quietly decides the
    answer, and nobody in the room could see it.
    """
    if agent.kind != PRODUCER:
        return []
    out: list[Verdict] = []
    for tech in settings.tech_costs:
        exposure = residual_exposure(settings, tech.life_years,
                                     swap_cover=swap_cover, award_years=award_years,
                                     award_cover=award_cover)
        out.append(evaluate(view, tech, agent, settings, exposure=exposure,
                            capacity_mw=build_size_mw(peak_mw, tech, settings),
                            contracted_share=1.0 - exposure))
    ranked = sorted(out, key=lambda v: v.surplus_per_mw_year, reverse=True)
    return ranked[:int(settings.investment["candidates_per_producer"])]


# --------------------------------------------------------------------------
# Exit


def unit_rent_per_mw_year(price: np.ndarray, unit: Unit) -> float:
    """What an existing plant earns above its own running cost, per MW of capacity.

    Only ever called for plant whose offer IS a running cost. See EXIT_ELIGIBLE.
    """
    return float(np.clip(price - unit.srmc_per_mwh, 0.0, None).sum() * unit.availability)


def going_forward_npv_per_mw(unit: Unit, view: ForwardView, settings: Settings,
                             year: int) -> float:
    """The plant's remaining life, valued on a going-forward basis.

    Capex is sunk for a plant that already exists, so the only question is whether
    the rent covers the cost of keeping it open. Rent per anchor is measured for
    THIS plant, at its own offer and its own availability, rather than borrowed
    from a technology row: a coal unit at $47/MWh and a combined cycle at $96 are
    not interchangeable, and using one as a proxy for the other would decide the
    retirement schedule on the wrong cost.

    Between and beyond the anchors the same interpolation applies as for a
    candidate, with the plant's own fixed operating cost as the terminal. That is
    the going-forward analogue of the zero-profit terminal: past the horizon the
    model assumes the plant covers its costs and no more, which is the assumption
    that neither retires it nor saves it on the strength of years nobody modelled.

    Incumbents discount at one market rate rather than at a project WACC. There is
    no project to finance, and inventing a capital structure for a decision that
    has none would be precision without content.
    """
    fom = unit.fixed_cost_per_mw_year
    anchors = {
        a.offset: a.expected(np.array(
            [o.unit_rent_per_mw_year[unit.unit] for o in a.outcomes]))
        for a in view.anchors
        if all(unit.unit in o.unit_rent_per_mw_year for o in a.outcomes)
    }
    if not anchors:
        return 0.0                          # not measurable: never a reason to exit
    remaining = max(0, unit.retirement_year - year)
    r = float(settings.investment["discount_rate"])
    return sum((interpolated_rent(anchors, u, fom) - fom) / (1.0 + r) ** u
               for u in range(remaining))


@dataclass
class ExitLedger:
    """How many consecutive years each plant has looked unviable.

    Two in a row, because one bad year is weather and the model has a
    one-in-five drought shape-year in it by construction. A single-year trigger
    would retire the fleet on the strength of a wind lull.
    """

    consecutive_negatives: dict[str, int]

    def __init__(self) -> None:
        self.consecutive_negatives = {}

    def observe(self, unit_name: str, npv: float) -> int:
        if npv < 0.0:
            self.consecutive_negatives[unit_name] = \
                self.consecutive_negatives.get(unit_name, 0) + 1
        else:
            self.consecutive_negatives[unit_name] = 0
        return self.consecutive_negatives[unit_name]


def exit_notices(fleet: tuple[Unit, ...], view: ForwardView, settings: Settings,
                 year: int, ledger: ExitLedger) -> list[tuple[Unit, float]]:
    """Which plants give notice this year, worst first.

    The cap on notices per year is not decoration. Each plant's exit is evaluated
    against a forward that holds the rest of the fleet fixed, so a whole cohort can
    each conclude it should leave against a picture in which the others all stayed.
    Staggering the notices lets the forward reprice between them, which is the
    difference between a market tightening and a market emptying in one tick.
    """
    scored: list[tuple[Unit, float]] = []
    for unit in fleet:
        if unit.technology not in EXIT_ELIGIBLE or not unit.in_service(year):
            continue
        if unit.retirement_year <= year + int(settings.investment["exit_notice_years"]):
            continue                       # already leaving; nothing left to notice
        npv = going_forward_npv_per_mw(unit, view, settings, year)
        run = ledger.observe(unit.unit, npv)
        if run >= int(settings.investment["exit_consecutive_negatives"]):
            scored.append((unit, npv))
    scored.sort(key=lambda p: p[1])
    return scored[:int(settings.investment["max_exit_notices_per_tick"])]
