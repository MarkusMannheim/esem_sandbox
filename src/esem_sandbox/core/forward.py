"""The forward view: what investors think the next twelve years look like.

Nobody in this model forecasts by solving anything. They enumerate a small set of
futures, dispatch each one, and average the answers at the probabilities they
attach to them. That is the whole of the forward view, and it is enumerated rather
than sampled so the same settings always give the same picture: no seed enters
here.

**The lattice.** Forty-five cells, the product of three axes: five weather
shape-years, three demand growth paths and three peak bands. Weights are the
product of the marginals and sum to one. The axes are chosen so that each carries
one thing and nothing carries two: weather carries shape, growth carries the level
of demand years out, and the peak band carries how hot the hottest hours get. The
shape-years are demand-neutral by construction and the peak band scales the peak
while holding annual energy, so stacking the two cannot double count.

**Three anchors,** at four, eight and twelve years ahead. A plant decided today
commissions inside the first anchor and lives well past the last, so the anchors
bracket the years the decision turns on. Beyond the last anchor the model claims no
information and assumes each technology earns exactly its own long-run cost, which
is zero economic profit. That is a statement about ignorance, not a forecast, and
it is deliberately not a flat dollars-per-MWh constant: such a constant sits below
a peaker's break-even and quietly makes peaking plant unbuildable for reasons that
have nothing to do with the market being modelled.

**One difference from the model this simplifies.** There, administered pricing was
left out of forward cells because running a sequential loop inside every cell was
too slow. Here it runs, because the speed target that forced that compromise was
withdrawn. A forward cell is therefore priced under exactly the rules a realised
year is priced under, which is one fewer place where the forward and the realised
market can disagree about what the rules are.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from ..config import Settings, TechCost, Unit
from .dispatch import dispatch_year, storage_schedule
from .report import block_prices

PROJECTED_ENTRY_TECHNOLOGY = "ocgt"
PROJECTED_ENTRY_UNIT = "projected_entry_ocgt"


@dataclass(frozen=True)
class Cell:
    """One future, and the probability of it.

    ``weight`` is the product of the three axes' marginal weights. Every reduction
    over cells is weighted by it, without exception: the model this one simplifies
    computed these weights, passed them everywhere, and then reduced with a plain
    arithmetic mean, so a one-in-ten-year peak entered at one in three.
    """

    shape_year: int
    growth_path: str
    peak_band: int
    weight: float
    annual_growth: float
    peak_multiplier: float

    @property
    def label(self) -> str:
        return f"{self.shape_year}/{self.growth_path}/{self.peak_band}"


def cell_plan(settings: Settings) -> tuple[Cell, ...]:
    """The full Cartesian product of the three axes, at product-of-marginal weights.

    Cells with no weight are dropped rather than carried at zero, because a cell
    that cannot happen should not appear in a count of the futures considered.
    """
    shapes = int(settings.weather["shape_years"])
    bands = list(settings.weather["peak_band_multipliers"])
    band_weights = list(settings.weather["peak_band_weights"])
    if len(bands) != len(band_weights):
        raise ValueError(
            f"{len(bands)} peak band multipliers against {len(band_weights)} weights"
        )
    cells: list[Cell] = []
    for s in range(shapes):
        for g in settings.growth:
            for b, (mult, bw) in enumerate(zip(bands, band_weights)):
                w = (1.0 / shapes) * g.weight * bw
                if w <= 0.0:
                    continue
                cells.append(Cell(shape_year=s, growth_path=g.path, peak_band=b,
                                  weight=w, annual_growth=g.annual_growth,
                                  peak_multiplier=mult))
    total = sum(c.weight for c in cells)
    if total <= 0.0:
        raise ValueError("every cell has zero weight: the lattice is empty")
    return tuple(replace(c, weight=c.weight / total) for c in cells)


def peak_banded(demand_mw: np.ndarray, multiplier: float) -> np.ndarray:
    """Scale the peak by ``multiplier`` while holding annual energy exactly.

    Peak bands differ in peak, not in energy. A plain scalar multiple would move
    both, so a one-in-ten-year peak band would also be a one-in-ten-year energy
    year, and the demand axis would be carrying two kinds of uncertainty at once
    while the model reported only one.

    The transform is a fan about the annual mean: ``mean + (d - mean) * k`` with
    ``k`` chosen so the maximum lands on ``multiplier`` times the old maximum. The
    mean is fixed by construction, so annual energy is preserved to the floating
    point limit rather than approximately.
    """
    mean = float(demand_mw.mean())
    peak = float(demand_mw.max())
    if peak <= mean:
        return demand_mw.copy()
    k = (multiplier * peak - mean) / (peak - mean)
    return mean + (demand_mw - mean) * k


def rent_per_mw_year(price: np.ndarray, tech: TechCost, settings: Settings,
                     capacity_factor: np.ndarray | None = None) -> float:
    """What one MW of this technology earns above its own running cost, in a year.

    Three shapes, one for each kind of plant:

    *Dispatchable*: the positive part of price less short run cost, times
    availability. It runs when the price covers its cost and not otherwise.

    *Variable*: the same positive part, weighted hour by hour by the capacity
    factor. Note which cost is used. A wind row in ``fleet.csv`` offers at minus
    forty-five dollars, but that is a curtailment offer, not a cost: it is what the
    plant will pay to keep running rather than forfeit a certificate this model
    does not represent. Using it as the rent basis would credit a candidate wind
    farm about $138,000 per MW-year of revenue that does not exist here. The cost
    is the running cost from ``tech_costs.csv``, which is zero, so curtailment is
    priced rather than scheduled: in a surplus hour the price is below the
    candidate's cost and it earns nothing, which is what withdrawal means for a
    plant that takes the price.

    *Storage*: the spread it actually realises, from the same daily scheduler the
    dispatch uses, so a candidate battery is valued by the rule that will govern it
    once built rather than by a cleaner one it will never enjoy.
    """
    if tech.duration_h:
        unit = Unit(
            unit="candidate", technology="battery", capacity_mw=1.0,
            availability=tech.availability, srmc_per_mwh=0.0,
            retirement_year=9999, commissioned_year=0, must_run_mw=0.0,
            energy_budget_gwh=None, duration_h=tech.duration_h,
            round_trip_efficiency=0.85, firm_factor=tech.firm_factor,
            cap_eligible=tech.cap_eligible,
        )
        schedule = storage_schedule([unit], price, settings).get("candidate")
        if schedule is None:
            return 0.0
        # Charging hours carry negative energy, so this is revenue net of the cost
        # of the energy bought, per MW of rated power.
        return float(np.sum(schedule * price))
    margin = np.clip(price - tech.srmc_per_mwh, 0.0, None)
    if capacity_factor is not None:
        return float(np.sum(margin * capacity_factor))
    return float(np.sum(margin) * tech.availability)


@dataclass(frozen=True)
class CellOutcome:
    """One dispatched cell, reduced to what the forward view needs from it."""

    cell: Cell
    rent_per_mw_year: dict[str, float]
    block_prices: dict[str, float]
    mean_price: float
    unserved_mwh: float
    unserved_fraction: float
    peak_shortfall_mw: float


@dataclass(frozen=True)
class Anchor:
    """Every cell dispatched at one point in the future."""

    offset: int
    year: int
    outcomes: tuple[CellOutcome, ...]
    entry_mw: float = 0.0

    @property
    def weights(self) -> np.ndarray:
        return np.array([o.cell.weight for o in self.outcomes])

    def rents(self, technology: str) -> np.ndarray:
        return np.array([o.rent_per_mw_year[technology] for o in self.outcomes])

    def expected(self, values: np.ndarray) -> float:
        """The probability weighted mean. Never a plain mean over cells."""
        return float(values @ self.weights)

    @property
    def expected_rent(self) -> dict[str, float]:
        return {t: self.expected(self.rents(t))
                for t in self.outcomes[0].rent_per_mw_year}

    @property
    def expected_unserved_fraction(self) -> float:
        return self.expected(np.array([o.unserved_fraction for o in self.outcomes]))

    @property
    def expected_peak_shortfall_mw(self) -> float:
        return self.expected(np.array([o.peak_shortfall_mw for o in self.outcomes]))

    @property
    def expected_block_prices(self) -> dict[str, float]:
        return {b: self.expected(np.array([o.block_prices[b] for o in self.outcomes]))
                for b in self.outcomes[0].block_prices}


def _projected_entry_unit(mw: float, tech: TechCost, year: int) -> Unit:
    """The plant the projection assumes somebody else builds.

    It is a real row in the anchor fleet, not a subtraction from demand, so it
    competes on the stack at its own offer and its effect on the price is whatever
    the merit order says it is.
    """
    return Unit(
        unit=PROJECTED_ENTRY_UNIT, technology=tech.technology, capacity_mw=mw,
        availability=tech.availability, srmc_per_mwh=tech.srmc_per_mwh,
        retirement_year=9999, commissioned_year=year, must_run_mw=0.0,
        energy_budget_gwh=None, duration_h=None, round_trip_efficiency=None,
        firm_factor=tech.firm_factor, cap_eligible=tech.cap_eligible,
    )


def anchor_fleet(fleet: tuple[Unit, ...], year: int, entry_mw: float,
                 settings: Settings) -> tuple[Unit, ...]:
    """Today's fleet, less what has retired by ``year``, plus projected entry."""
    live = tuple(u for u in fleet if u.in_service(year))
    if entry_mw > 0.0:
        tech = settings.tech(PROJECTED_ENTRY_TECHNOLOGY)
        live = live + (_projected_entry_unit(entry_mw, tech, year),)
    return live


def dispatch_anchor(settings: Settings, fleet: tuple[Unit, ...], bundle: dict,
                    *, offset: int, year: int, peak_mw: float,
                    cells: tuple[Cell, ...], entry_mw: float = 0.0) -> Anchor:
    """Dispatch every cell of the lattice at one anchor."""
    live = anchor_fleet(fleet, year, entry_mw, settings)
    at_anchor = replace(settings, fleet=live)
    outcomes: list[CellOutcome] = []
    for cell in cells:
        shape = bundle["demand_shape"][cell.shape_year]
        wind = bundle["wind_cf"][cell.shape_year]
        solar = bundle["solar_cf"][cell.shape_year]
        grown = peak_mw * (1.0 + cell.annual_growth) ** offset
        demand = peak_banded(shape * (grown / shape.max()), cell.peak_multiplier)
        res = dispatch_year(at_anchor, year, demand, wind, solar)
        cf = {"wind": wind, "solar": solar}
        rents = {
            t.technology: rent_per_mw_year(res.price, t, at_anchor,
                                           cf.get(t.technology))
            for t in settings.tech_costs
        }
        outcomes.append(CellOutcome(
            cell=cell,
            rent_per_mw_year=rents,
            block_prices=block_prices(at_anchor, res.price),
            mean_price=float(res.price.mean()),
            unserved_mwh=float(res.unserved_mwh.sum()),
            unserved_fraction=res.unserved_fraction,
            peak_shortfall_mw=float(res.unserved_mwh.max()),
        ))
    return Anchor(offset=offset, year=year, outcomes=tuple(outcomes),
                  entry_mw=entry_mw)


@dataclass
class EntryBelief:
    """What the projection assumes about entry at one anchor, and what it has
    learned about where the truth lies.

    ``lo_mw`` is the most assumed entry known to still leave a peaker earning its
    cost; ``hi_mw`` is the least known to push it below. Between them lies the free
    entry fixed point.
    """

    mw: float = 0.0
    lo_mw: float | None = None
    hi_mw: float | None = None
    step_mw: float = 0.0


@dataclass
class EntryState:
    """How much plant the projection assumes somebody else builds, by anchor.

    This is carried on the run rather than in a module global. The model this one
    simplifies keeps it in module state, which means two legs of a paired run share
    one belief about entry and a test leaves its state behind for the next test.
    """

    by_offset: dict[int, EntryBelief] = field(default_factory=dict)

    def at(self, offset: int) -> float:
        return self.by_offset.get(offset, EntryBelief()).mw

    def belief(self, offset: int) -> EntryBelief:
        return self.by_offset.get(offset, EntryBelief())

    def settled(self, offset: int, resolution_mw: float) -> bool:
        b = self.by_offset.get(offset)
        if b is None or b.lo_mw is None or b.hi_mw is None:
            return False
        return (b.hi_mw - b.lo_mw) <= resolution_mw

    def copy(self) -> "EntryState":
        return EntryState({k: EntryBelief(v.mw, v.lo_mw, v.hi_mw, v.step_mw)
                           for k, v in self.by_offset.items()})


def update_projected_entry(state: EntryState, anchors: list[Anchor],
                           settings: Settings, *,
                           threshold_loading_per_mw_year: float = 0.0) -> EntryState:
    """One adaptive step of the free-entry fixed point.

    Where a peaker's projected rent clears its own fixed cost, the projection grows
    the plant it assumes will be built; where it does not, the assumption decays.
    At the fixed point rent sits at the threshold, which is what free entry means.

    **Why this converges in megawatts and not in dollars.** The obvious rule, and
    the one this is drawn from, grows by a step sized to the projected shortfall,
    decays by halving the state, and stops when rent lands within a tolerance of
    break-even. On this fleet it never stops. The eight-year anchor settles into a
    four-cycle at 3,548 - 5,871 - 7,070 - 3,535 MW and the expected unserved energy
    it reports swings between 0.02 and 0.49 per cent depending only on which phase
    of the cycle a tick lands in. Damping the step reduces the amplitude and does
    not remove the cycle.

    The cause is not the step size. Rent is a step function of assumed entry,
    because the price is set by a merit order and a ladder of discrete tranches:
    between 6,243 and 6,676 MW of assumed entry the peaker's rent falls thirty
    thousand dollars at once. There is no quantity of entry at which rent sits
    within a two per cent band of break-even, so a rule that keeps moving until it
    lands in that band moves for ever. A tolerance on rent is a stopping test that
    the model's own arithmetic cannot satisfy.

    So the state brackets instead. Each observation tells it which side of the
    fixed point the current assumption lies on, the bracket narrows by halving, and
    it stops when the bracket is narrower than one generating unit, which is the
    finest distinction entry can actually be built in. It settles on the lower
    edge: the largest assumed entry at which the last entrant still covers its own
    cost, which is what free entry means. This is the technique the hydro schedule
    already uses here, for the same reason - a threshold search against a discrete
    stack - and it is exact where a tolerance rule is not.

    Two rules keep it honest. No anchor closer than the technology's lead time can
    gain new assumed entry, because the decision that would deliver it lies in the
    past and the past is not a thing a projection gets to change. And where entry
    cannot earn its cost anywhere, the state falls to zero and the projected
    unserved energy stays visible: that shortfall is the finding, and assuming it
    away is how a model comes to report that a market is adequate because it
    assumed the capacity that would have made it so.

    ``threshold_loading_per_mw_year`` is the risk premium a merchant entrant would
    demand on top of break-even. It is passed in rather than computed here so the
    threshold matches the leg's own investment test: a projection that assumes
    entry the leg itself would reject is not a projection of that leg.
    """
    tech = settings.tech(PROJECTED_ENTRY_TECHNOLOGY)
    threshold = tech.fixed_cost_per_mw_year + threshold_loading_per_mw_year
    step_min = float(settings.forward["entry_step_min_mw"])
    decay = float(settings.forward["entry_decay"])
    resolution = tech.unit_size_mw
    out = state.copy()
    for anchor in anchors:
        prior = state.belief(anchor.offset)
        here = prior.mw
        pays = anchor.expected_rent[tech.technology] >= threshold

        # Read the bracket off this observation, discarding any prior edge the
        # observation contradicts. Rent falls as assumed entry rises, so an edge
        # on the far side of the current point survives and one on the near side
        # is superseded by it.
        if pays:
            lo: float | None = here
            hi = prior.hi_mw if (prior.hi_mw is not None and prior.hi_mw > here) else None
        else:
            hi = here
            lo = prior.lo_mw if (prior.lo_mw is not None and prior.lo_mw < here) else None

        if lo is not None and hi is not None:
            nxt = lo if (hi - lo) <= resolution else 0.5 * (lo + hi)
            step = prior.step_mw
        elif hi is None:
            # Never yet seen enough entry to satisfy the market: climb, sized to
            # the shortfall, doubling while the bracket stays open.
            step = max(step_min, 0.5 * anchor.expected_peak_shortfall_mw,
                       prior.step_mw * 2.0 if prior.step_mw else 0.0)
            nxt = here + step
        else:
            # Even this little assumed entry is too much: retreat. Nothing is known
            # about the lower edge, so the retreat is proportional to the state.
            step = max(step_min, here * decay)
            nxt = max(0.0, here - step)

        if nxt > here and anchor.offset < tech.lead_years:
            continue                       # no new entry inside the build lead
        out.by_offset[anchor.offset] = EntryBelief(mw=nxt, lo_mw=lo, hi_mw=hi,
                                                   step_mw=step)
    return out


def interpolated_rent(anchors: dict[int, float], offset: float,
                      terminal: float) -> float:
    """Rent in a year between, before or after the anchors.

    Before the first anchor the first anchor's value stands: a lead time can be
    shorter than the nearest anchor, and inventing a fourth anchor to cover two
    years of a twenty-five year life would cost a third of the forward's runtime
    to move a discounted number very little.

    After the last anchor the terminal applies as a step, not a fade. The step is
    the honest shape: the model does not know less and less about years thirteen
    through twenty-five, it knows nothing about any of them, and a fade would dress
    that up as a trend.
    """
    if not anchors:
        return terminal
    keys = sorted(anchors)
    if offset <= keys[0]:
        return anchors[keys[0]]
    if offset > keys[-1]:
        return terminal
    for lo, hi in zip(keys, keys[1:]):
        if lo <= offset <= hi:
            if hi == lo:
                return anchors[lo]
            f = (offset - lo) / (hi - lo)
            return anchors[lo] * (1.0 - f) + anchors[hi] * f
    return terminal


def lifetime_rent_per_mw_year(anchor_rents: dict[int, float], tech: TechCost) -> float:
    """The NPV weighted mean rent over the plant's operating life.

    Both this and the fixed cost it will be compared against are per MW-year, so no
    capacity factor enters the comparison and a peaker running two per cent of the
    year is tested against its own costs rather than against a common denominator.

    Discounting is to the decision year, so the early well-resolved years carry
    most of the weight and the assumed tail fades.
    """
    life = max(1, int(tech.life_years))
    r = tech.wacc
    terminal = tech.fixed_cost_per_mw_year
    num = den = 0.0
    for u in range(tech.lead_years, tech.lead_years + life):
        disc = (1.0 + r) ** -u
        num += interpolated_rent(anchor_rents, u, terminal) * disc
        den += disc
    return num / den if den else 0.0


def lifetime_rent_by_cell(anchors: list[Anchor], tech: TechCost) -> np.ndarray:
    """Lifetime rent per cell, holding each cell fixed across the anchors.

    A cell is one coherent future, so the growth path and weather that produced the
    rent at four years is the same one that produced it at twelve. Averaging over
    cells first and interpolating the averages afterwards would collapse the
    distribution before the risk measure ever saw it, and the risk measure is the
    entire point of the investment rule.
    """
    ordered = sorted(anchors, key=lambda a: a.offset)
    n = len(ordered[0].outcomes)
    for a in ordered:
        if len(a.outcomes) != n:
            raise ValueError("anchors disagree about how many cells there are")
    out = np.empty(n)
    for i in range(n):
        rents = {a.offset: a.outcomes[i].rent_per_mw_year[tech.technology]
                 for a in ordered}
        out[i] = lifetime_rent_per_mw_year(rents, tech)
    return out


@dataclass(frozen=True)
class ForwardView:
    """Every anchor of one tick's forward view, and the belief that produced it."""

    anchors: tuple[Anchor, ...]
    entry: EntryState

    def anchor(self, offset: int) -> Anchor:
        for a in self.anchors:
            if a.offset == offset:
                return a
        raise KeyError(f"no anchor at +{offset} years")

    @property
    def nearest(self) -> Anchor:
        return min(self.anchors, key=lambda a: a.offset)

    @property
    def weights(self) -> np.ndarray:
        return self.nearest.weights

    @property
    def expected_unserved_fraction(self) -> float:
        """Measured at the nearest anchor, which is the one a reliability
        obligation would be written against."""
        return self.nearest.expected_unserved_fraction

    def lifetime_rent(self, tech: TechCost) -> np.ndarray:
        return lifetime_rent_by_cell(list(self.anchors), tech)


def forward_view(settings: Settings, fleet: tuple[Unit, ...], bundle: dict, *,
                 year: int, peak_mw: float, entry: EntryState,
                 cells: tuple[Cell, ...] | None = None) -> ForwardView:
    """Dispatch the whole lattice at every anchor, at the entry currently believed in.

    The belief is an input rather than something computed here, so that the view a
    decision was made against can be reproduced exactly from the state that
    produced it.
    """
    plan = cells if cells is not None else cell_plan(settings)
    anchors = tuple(
        dispatch_anchor(settings, fleet, bundle, offset=int(offset),
                        year=year + int(offset), peak_mw=peak_mw, cells=plan,
                        entry_mw=entry.at(int(offset)))
        for offset in settings.forward["anchor_offsets"]
    )
    return ForwardView(anchors=anchors, entry=entry)
