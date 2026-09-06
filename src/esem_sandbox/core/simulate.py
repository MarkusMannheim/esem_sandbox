"""The tick loop: twenty years, one year at a time.

Each tick, in this order and for reasons:

1. Plant decided years ago and finished this year enters service.
2. The year is dispatched and priced.
3. Contracts written in earlier ticks settle against that price.
4. The book ages: what has expired leaves it.
5. The forward view is rebuilt and the free-entry belief takes one step.
6. The bilateral market clears against the anchors the realised year just moved.
7. Exit notices are given, and then entry is decided.

Exit comes before entry within a tick because a plant giving notice this year is
part of the fleet an entrant is deciding against, and the other way round an
entrant would be pricing a market that still contained plant everyone knew was
leaving. Contracts struck at a tick first settle at the next, because a contract
signed in December does not settle the year it was signed in.

**Nothing here forecasts.** The anchors are exponentially weighted averages of
prices that have already happened, and the forward view is an enumeration of
futures with fixed probabilities. That is the whole mechanism behind the
boom-and-bust exercise: when scarcity lifts prices, investors extrapolate, all of
them build, and the plant arrives together three years later into a market that no
longer needs it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from ..config import Settings, TechCost, Unit
from .agents import (
    Agent, PRODUCER, RETAILER, check_roster, default_roster, ownable_units,
)
from .clearing import (
    cap_cost_basis, clear_bilateral, energy_margin_per_mw_year,
    ewma_block_anchor,
)
from .contracts import Contract, age, settle_book
from .dispatch import DispatchResult, dispatch_year
from .forward import (
    Cell, EntryState, ForwardView, cell_plan, forward_view, peak_banded,
    update_projected_entry,
)
from .esem import (
    ADMINISTRATOR, Administrator, Bid, AwardLine, award_contract,
    award_strike_per_mwh, blended_wacc, clear_pay_as_bid, eligible_technologies,
    firm_contribution_mw, lane_volume_mw, levy_per_mwh,
    long_run_cost_per_mw_year, recycle, reserve_margin_gap_mw, screen,
)
from .investment import (
    ExitLedger, achieved_swap_cover, build_ceiling_mw, build_size_mw,
    cara_coefficient, exit_notices, rank_candidates, residual_exposure,
)
from .report import block_prices
from .weather import generate_bundle
from .clearing import cara_certainty_equivalent

BOOTSTRAP_YEARS = 3

# The two legs. Merchant is the policy-free counterfactual: the market on its own,
# with no scheme and no underwrite. ESEM is the same market with the procurement
# scheme switched on. Nothing is on by default, because a mechanism this
# consequential running unasked would make every result an argument for itself.
MERCHANT = "merchant"
ESEM = "esem"

# tech_costs.csv names storage by duration, because a two-hour and an eight-hour
# battery are different investments. The dispatcher cares only that a thing is a
# store, so a built unit carries the dispatch technology and its duration.
_DISPATCH_TECHNOLOGY = {"battery_2h": "battery", "battery_4h": "battery",
                        "battery_8h": "battery"}


@dataclass(frozen=True)
class Draw:
    """The weather and growth sequence for one run.

    Drawn once from the seed and handed to every leg, so that two legs differ by
    the mechanism under test and by nothing else. A leg that drew its own weather
    would report the difference between two climates as the effect of a policy.
    """

    shape_years: tuple[int, ...]
    peak_bands: tuple[int, ...]
    growth_path: str
    annual_growth: float


def draw_sequence(settings: Settings, seed: int, ticks: int) -> Draw:
    """Draw a realised sequence from the same distribution the lattice enumerates.

    The growth path is drawn once for the run, not once a year: a path is a path.
    The weather shape and the peak band are drawn each year from the same marginals
    the lattice weights its cells by, so a large number of realised runs reproduces
    the lattice's expected unserved energy, and a test says so.
    """
    rng = np.random.default_rng(seed)
    shapes = int(settings.weather["shape_years"])
    bands = list(settings.weather["peak_band_weights"])
    paths = [g.path for g in settings.growth]
    weights = np.array([g.weight for g in settings.growth])
    chosen = int(rng.choice(len(paths), p=weights / weights.sum()))
    return Draw(
        shape_years=tuple(int(i) for i in rng.integers(0, shapes, ticks + BOOTSTRAP_YEARS)),
        peak_bands=tuple(int(i) for i in
                         rng.choice(len(bands), ticks + BOOTSTRAP_YEARS,
                                    p=np.array(bands) / sum(bands))),
        growth_path=paths[chosen],
        annual_growth=settings.growth[chosen].annual_growth,
    )


@dataclass(frozen=True)
class Build:
    unit: str
    technology: str
    capacity_mw: float
    owner: str
    decided_year: int
    commissioned_year: int
    hurdle_per_mw_year: float
    expected_rent_per_mw_year: float
    contracted_share: float


@dataclass(frozen=True)
class Award:
    """One line of one year's auction."""

    bidder: str
    technology: str
    capacity_mw: float
    firm_mw: float
    price_per_mw_year: float
    strike_per_mwh: float
    commissioning_year: int


@dataclass(frozen=True)
class TickResult:
    """One year, reduced to what a chart or a slide would want from it."""

    year: int
    peak_mw: float
    mean_price: float
    block_prices: dict[str, float]
    unserved_gwh: float
    unserved_fraction: float
    expected_unserved_fraction: float
    firm_capacity_mw: float
    capacity_by_technology: dict[str, float]
    entry_belief_mw: dict[int, float]
    builds: tuple[Build, ...]
    notices: tuple[str, ...]
    live_contracts: int
    swap_cover: dict[str, float]      # each producer's contracted share of output
    cashflows: dict[str, float]
    peaker_missing_money_per_mw_year: float
    consumed_mwh: float = 0.0
    wholesale_cost: float = 0.0
    fuel_and_vom: float = 0.0
    fixed_cost_of_fleet: float = 0.0
    annualised_capex_of_new_build: float = 0.0
    lane_volume_mw: float = 0.0
    reserve_margin_gap_mw: float = 0.0
    awards: tuple[Award, ...] = ()
    scheme_cost: float = 0.0
    levy_per_mwh: float = 0.0
    administrator_net: float = 0.0
    warehoused_mw: float = 0.0


@dataclass
class RunState:
    year: int
    fleet: tuple[Unit, ...]
    roster: tuple[Agent, ...]
    book: list[Contract] = field(default_factory=list)
    history: list[dict[str, float]] = field(default_factory=list)
    cap_payoffs: list[float] = field(default_factory=list)
    entry: EntryState = field(default_factory=EntryState)
    exit_ledger: ExitLedger = field(default_factory=ExitLedger)
    admin: Administrator = field(default_factory=Administrator)
    awarded_share: dict[str, float] = field(default_factory=dict)
    # (commissioning year, retirement year, annualised capital cost) for every plant
    # this run decided to build. Existing plant is not here: its capital is sunk, and
    # charging a run for capital spent before it started would compare two legs on
    # money neither of them moved.
    new_capital: list[tuple[int, int, float]] = field(default_factory=list)


@dataclass(frozen=True)
class RunResult:
    ticks: tuple[TickResult, ...]
    draw: Draw
    fleet: tuple[Unit, ...]
    roster: tuple[Agent, ...]
    book: tuple[Contract, ...]
    leg: str = MERCHANT

    @property
    def total_unserved_gwh(self) -> float:
        return sum(t.unserved_gwh for t in self.ticks)

    @property
    def total_built_mw(self) -> float:
        return sum(b.capacity_mw for t in self.ticks for b in t.builds)

    @property
    def total_levy(self) -> float:
        """What consumers paid the scheme over the run, in dollars."""
        return sum(t.levy_per_mwh * t.consumed_mwh for t in self.ticks)

    @property
    def total_wholesale_cost(self) -> float:
        return sum(t.wholesale_cost for t in self.ticks)

    def unserved_valued_at_the_cap(self, settings: Settings) -> float:
        """Unserved energy priced at the value of lost load.

        A reliability failure is a cost even though nobody invoices for it, and a
        comparison that left it out would show the leg that sheds load as the cheap
        one. This is the line that stops a bill view being an argument for
        unreliability.
        """
        return sum(t.unserved_gwh * 1000.0 for t in self.ticks) * \
            float(settings.market["market_price_cap_per_mwh"])

    def consumer_cost(self, settings: Settings) -> float:
        """What the whole thing costs the people who use the electricity.

        A BILL, not a cost. Most of it is a payment from consumers to producers, and
        a scheme that lowers the pool price lowers this figure by moving money rather
        than by saving any. Read it beside the resource cost below or it will flatter
        whichever leg happens to transfer more.
        """
        return (self.total_wholesale_cost + self.total_levy
                + self.unserved_valued_at_the_cap(settings))

    def resource_cost(self, settings: Settings) -> float:
        """What the whole thing costs the economy: fuel, fixed costs, new capital,
        and the energy nobody got.

        The line that stops a bill view being an argument. A scheme that builds
        capacity pushes the pool price down, which cuts the wholesale bill by far
        more than the scheme costs - but that reduction is a transfer from
        generators to consumers, not a saving. On the packaged fleet it is twenty
        billion dollars of transfer against half a billion of genuinely avoided
        outage, and a comparison that reported only the bill would attribute the
        whole of it to the policy.

        Existing plant's capital is not counted: it is sunk, and charging a run for
        money spent before it started would compare two legs on cashflows neither of
        them moved.
        """
        return (sum(t.fuel_and_vom for t in self.ticks)
                + sum(t.fixed_cost_of_fleet for t in self.ticks)
                + sum(t.annualised_capex_of_new_build for t in self.ticks)
                + self.unserved_valued_at_the_cap(settings))

    @property
    def total_awarded_mw(self) -> float:
        return sum(a.capacity_mw for t in self.ticks for a in t.awards)

    def built_by_technology(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for t in self.ticks:
            for b in t.builds:
                out[b.technology] = out.get(b.technology, 0.0) + b.capacity_mw
        return out


def _demand(bundle: dict, shape_year: int, peak_mw: float,
            peak_multiplier: float) -> np.ndarray:
    shape = bundle["demand_shape"][shape_year]
    return peak_banded(shape * (peak_mw / shape.max()), peak_multiplier)


def _new_unit(tech: TechCost, mw: float, name: str, decided_year: int) -> Unit:
    commissioned = decided_year + tech.lead_years
    return Unit(
        unit=name,
        technology=_DISPATCH_TECHNOLOGY.get(tech.technology, tech.technology),
        capacity_mw=mw, availability=tech.availability,
        srmc_per_mwh=tech.srmc_per_mwh,
        retirement_year=commissioned + tech.life_years,
        commissioned_year=commissioned, must_run_mw=0.0, energy_budget_gwh=None,
        duration_h=tech.duration_h,
        round_trip_efficiency=0.85 if tech.duration_h else None,
        firm_factor=tech.firm_factor, cap_eligible=tech.cap_eligible,
        fom_per_kw_year=tech.fom_per_kw_year,
    )


def _cap_payoff_per_mw_year(price: np.ndarray, strike: float) -> float:
    return float(np.clip(price - strike, 0.0, None).sum())


def _merchant_entry_loading(settings: Settings, view: ForwardView,
                            roster: tuple[Agent, ...]) -> float:
    """The risk premium a representative merchant would want on top of break-even.

    The projection is only allowed to assume entry that the leg's own investment
    test would actually take. A projection of a merchant market that assumed
    break-even entry would be projecting a market with a different investor in it.
    """
    producers = [a for a in roster if a.kind == PRODUCER]
    if not producers:
        return 0.0
    tech = settings.tech("ocgt")
    rents = view.lifetime_rent(tech)
    weights = view.weights
    representative = max(a.risk_aversion for a in producers)
    a = cara_coefficient(representative, 1.0, settings)
    return float(rents @ weights) - cara_certainty_equivalent(rents, weights, a)


def run(settings: Settings, *, ticks: int = 20, start_year: int = 2026,
        peak_mw: float = 12_500.0, seed: int | None = None,
        cells: tuple[Cell, ...] | None = None, leg: str = MERCHANT,
        bundle: dict | None = None) -> RunResult:
    """One leg of a run: dispatch, contract, invest, twenty times over.

    ``leg`` selects the counterfactual. Both legs draw the same weather from the same
    seed, so a comparison between them is a comparison of the mechanism and of
    nothing else.
    """
    if leg not in (MERCHANT, ESEM):
        raise ValueError(f"unknown leg {leg!r}: expected {MERCHANT!r} or {ESEM!r}")
    seed = int(settings.weather["seed"]) if seed is None else seed
    bundle = bundle if bundle is not None else generate_bundle(
        seed, int(settings.weather["shape_years"]))
    plan = cells if cells is not None else cell_plan(settings)
    draw = draw_sequence(settings, seed, ticks)
    bands = list(settings.weather["peak_band_multipliers"])

    roster = default_roster()
    check_roster(roster, ownable_units(settings.fleet))
    state = RunState(year=start_year, fleet=settings.fleet, roster=roster)

    strike = float(settings.contracts["cap_strike_per_mwh"])
    tenor = int(settings.contracts["swap_tenor_years"])
    ocgt = settings.tech("ocgt")

    # Bootstrap. Three years of prices before the first tick, and three clears at
    # tenors one, two and three, so that tick zero opens on a laddered book rather
    # than on a market that has never traded and a producer who has never hedged.
    for k in range(BOOTSTRAP_YEARS, 0, -1):
        year = start_year - k
        level = peak_mw / (1.0 + draw.annual_growth) ** k
        i = BOOTSTRAP_YEARS - k
        res = dispatch_year(settings, year,
                            _demand(bundle, draw.shape_years[i], level,
                                    bands[draw.peak_bands[i]]),
                            bundle["wind_cf"][draw.shape_years[i]],
                            bundle["solar_cf"][draw.shape_years[i]])
        state.history.append(block_prices(settings, res.price))
        state.cap_payoffs.append(_cap_payoff_per_mw_year(res.price, strike))
        state.book.extend(_clear(settings, state, res, year=year,
                                 start_year=start_year, tenor_years=k,
                                 peak_mw=level, ocgt=ocgt))

    results: list[TickResult] = []
    pipeline: list[Unit] = []
    for t in range(ticks):
        year = start_year + t
        level = peak_mw * (1.0 + draw.annual_growth) ** t
        idx = BOOTSTRAP_YEARS + t
        shape_year = draw.shape_years[idx]

        # 1. Anything finished this year enters service. It is already in the fleet
        #    with a commissioning year; nothing to do but note it.
        live = replace(settings, fleet=state.fleet)

        # 2. The realised year.
        res = dispatch_year(live, year,
                            _demand(bundle, shape_year, level,
                                    bands[draw.peak_bands[idx]]),
                            bundle["wind_cf"][shape_year],
                            bundle["solar_cf"][shape_year])

        # 3. Settlement, then 4. ageing.
        cashflows = settle_book(settings, state.book, res.price, year)
        state.book = age(state.book, year)
        state.history.append(block_prices(settings, res.price))
        state.cap_payoffs.append(_cap_payoff_per_mw_year(res.price, strike))

        # 5. The forward signal, and one step of the free-entry belief.
        view = forward_view(live, state.fleet, bundle, year=year, peak_mw=level,
                            entry=state.entry, cells=plan)
        state.entry = update_projected_entry(
            state.entry, list(view.anchors), settings,
            threshold_loading_per_mw_year=_merchant_entry_loading(
                settings, view, state.roster))

        # 6. The administrator offers its position back first, then the bilateral
        #    market covers whatever is left. That order matters: a retailer that
        #    bought a recycled strip does not also need to buy the same cover from a
        #    producer, and running the bilateral market first would have it hedge
        #    the same load twice and look twice as covered as it is.
        recycled_mw: dict[str, float] = {}
        if leg == ESEM:
            average_load = float(res.operational_demand_mw.mean())
            buyers = [(a.name, a.swap_cover * a.load_share * average_load)
                      for a in state.roster if a.kind == RETAILER]
            anchor_price = ewma_block_anchor(
                state.history, "overnight",
                float(settings.contracts["anchor_half_life_years"]))
            strips = recycle(state.admin, settings, year=year,
                             anchor_per_mwh=anchor_price, buyers=buyers)
            state.book.extend(strips)
            for c in strips:
                if c.start_year == year + 1:
                    recycled_mw[c.holder] = recycled_mw.get(c.holder, 0.0) + c.volume_mw

        state.book.extend(_clear(settings, state, res, year=year,
                                 start_year=year + 1, tenor_years=tenor,
                                 peak_mw=level, ocgt=ocgt,
                                 already_covered_mw=recycled_mw))

        # 7. The auction, when the scheme is on. New entrants only, sized on the
        #    near anchor's shortfall, cleared pay-as-bid, awarded at final
        #    investment decision so the plant is committed now and arrives after
        #    its lead time.
        awards: list[Award] = []
        built_this_year: dict[str, float] = {}
        lane_mw = 0.0
        margin_gap = 0.0
        if leg == ESEM:
            near = view.nearest
            lane_mw = lane_volume_mw(near, settings)
            margin_gap = reserve_margin_gap_mw(
                near, res.firm_capacity_mw, level,
                float(settings.esem["reserve_margin"]))
            awards = _auction(settings, state, view, res, year=year,
                              peak_mw=level, lane_mw=lane_mw, built=built_this_year,
                              tick=t)

        # 8. Exit, then entry.
        notices = exit_notices(state.fleet, view, settings, year, state.exit_ledger)
        noticed = {u.unit for u, _ in notices}
        if noticed:
            state.fleet = tuple(
                replace(u, retirement_year=year + int(
                    settings.investment["exit_notice_years"]))
                if u.unit in noticed else u
                for u in state.fleet)

        cover = _cover(settings, state, res, year=year)
        builds = _invest(settings, state, view, res, year=year, peak_mw=level,
                         cover=cover, tick=t, leg=leg, built=built_this_year)
        for b, unit in builds:
            tech = settings.tech(b.technology)
            state.new_capital.append((
                unit.commissioned_year, unit.retirement_year,
                unit.capacity_mw * tech.capex_per_kw * 1000.0 * tech.crf))
            state.fleet = state.fleet + (unit,)
            state.roster = tuple(
                replace(a, units=a.units + (unit.unit,)) if a.name == b.owner else a
                for a in state.roster)

        levy = 0.0
        admin_net = cashflows.get(ADMINISTRATOR, 0.0) if leg == ESEM else 0.0
        warehoused = 0.0
        if leg == ESEM:
            consumed = float(res.operational_demand_mw.sum())
            levy = levy_per_mwh(admin_net, settings, consumed)
            state.admin.levy_paid.append(levy * consumed)
            warehoused = state.admin.warehoused_mw.get(year, 0.0)

        in_service = [u for u in state.fleet if u.in_service(year)]
        capacity: dict[str, float] = {}
        for u in in_service:
            capacity[u.technology] = capacity.get(u.technology, 0.0) + u.capacity_mw
        peaker_rent = energy_margin_per_mw_year(res.price, ocgt.srmc_per_mwh,
                                                ocgt.availability)
        # Fuel is burnt only by plant with a positive running cost, and only when it
        # is generating. A curtailment offer is negative and is an opportunity cost
        # rather than a fuel bill; a store's charging hours are negative energy and
        # would otherwise book its variable cost as a credit.
        fuel = 0.0
        for unit in in_service:
            cost = max(unit.srmc_per_mwh, 0.0)
            generated = res.generation_mwh.get(unit.unit)
            if cost <= 0.0 or generated is None:
                continue
            fuel += float(np.clip(generated, 0.0, None).sum()) * cost
        fixed = sum(u.fixed_cost_per_mw_year * u.capacity_mw for u in in_service)
        capital = sum(cost for start, end, cost in state.new_capital
                      if start <= year < end)
        results.append(TickResult(
            year=year, peak_mw=level, mean_price=float(res.price.mean()),
            block_prices=block_prices(settings, res.price),
            unserved_gwh=res.total_unserved_gwh,
            unserved_fraction=res.unserved_fraction,
            expected_unserved_fraction=view.expected_unserved_fraction,
            firm_capacity_mw=res.firm_capacity_mw,
            capacity_by_technology=capacity,
            entry_belief_mw={a.offset: state.entry.at(a.offset) for a in view.anchors},
            builds=tuple(b for b, _ in builds),
            notices=tuple(sorted(noticed)),
            live_contracts=len(state.book),
            swap_cover=cover,
            cashflows=cashflows,
            peaker_missing_money_per_mw_year=peaker_rent - ocgt.fixed_cost_per_mw_year,
            consumed_mwh=float(res.operational_demand_mw.sum()),
            wholesale_cost=float((res.price * res.operational_demand_mw).sum()),
            fuel_and_vom=fuel,
            fixed_cost_of_fleet=fixed,
            annualised_capex_of_new_build=capital,
            lane_volume_mw=lane_mw,
            reserve_margin_gap_mw=margin_gap,
            awards=tuple(awards),
            scheme_cost=sum(a.firm_mw * a.price_per_mw_year for a in awards),
            levy_per_mwh=levy,
            administrator_net=admin_net,
            warehoused_mw=warehoused,
        ))
    return RunResult(ticks=tuple(results), draw=draw, fleet=state.fleet,
                     roster=state.roster, book=tuple(state.book), leg=leg)


def _clear(settings: Settings, state: RunState, res: DispatchResult, *,
           year: int, start_year: int, tenor_years: int, peak_mw: float,
           ocgt: TechCost,
           already_covered_mw: dict[str, float] | None = None) -> list[Contract]:
    """Price and write this tick's bilateral contracts.

    The cap's cost basis nets the energy margin the peaker earned in the pool. That
    argument is required rather than defaulted, because forgetting it doubles the
    basis and prices the cap above anything it could be expected to pay.
    """
    payoffs = np.array(state.cap_payoffs[-5:]) if state.cap_payoffs else np.array([0.0])
    weights = np.full(len(payoffs), 1.0 / len(payoffs))
    margin = energy_margin_per_mw_year(res.price, ocgt.srmc_per_mwh, ocgt.availability)
    basis = cap_cost_basis(ocgt.capex_per_kw, ocgt.fom_per_kw_year, ocgt.wacc,
                           ocgt.life_years, ocgt.firm_factor, margin)
    return clear_bilateral(
        settings, state.roster, state.fleet, state.history,
        year=year, start_year=start_year, tenor_years=tenor_years,
        average_load_mw=float(res.operational_demand_mw.mean()),
        peak_load_mw=float(res.operational_demand_mw.max()),
        cap_payoffs_per_mw=payoffs, cap_weights=weights,
        cap_cost_basis_per_mwh=basis,
        already_covered_mw=already_covered_mw or {})


def _auction(settings: Settings, state: RunState, view: ForwardView,
             res: DispatchResult, *, year: int, peak_mw: float, lane_mw: float,
             built: dict[str, float], tick: int) -> list[Award]:
    """One year's lane: eligible new entrants bid, are screened, and clear pay-as-bid.

    Bids are the long-run cost of the plant at a cost of capital blended for the
    share of its life the award covers, net of what it expects to earn in the pool,
    restated per FIRM megawatt because that is the product the lane is buying. A
    peaker and an eight-hour battery offering the same capacity are not offering the
    same thing, and the lane pays for what it gets.

    An award is a final investment decision. The plant is committed in this year and
    arrives after its lead time, which is the whole reason a long-dated contract
    moves anything: it is not a subsidy paid to plant that would have been built, it
    is what lets a plant be built at all.
    """
    if lane_mw <= 0:
        return []
    near = view.nearest
    tenor = int(settings.esem["contract_tenor_years"])
    producers = [a for a in state.roster if a.kind == PRODUCER]
    if not producers:
        return []
    rotation = tick % len(producers)
    ordered = producers[rotation:] + producers[:rotation]
    representative_aversion = max(a.risk_aversion for a in producers)

    bids: list[Bid] = []
    priced: dict[str, tuple[TechCost, float, float]] = {}
    for tech in eligible_technologies(settings):
        capacity = build_size_mw(peak_mw, tech, settings)
        room = build_ceiling_mw(peak_mw, tech, settings) - built.get(tech.technology, 0.0)
        capacity = min(capacity, room)
        if capacity < tech.unit_size_mw:
            continue
        capacity = (capacity // tech.unit_size_mw) * tech.unit_size_mw
        firm = firm_contribution_mw(tech, capacity, near)
        if firm <= 0:
            continue
        share = min(1.0, tenor / max(1, tech.life_years))
        # What the plant can bank on earning in the pool, on ITS OWN basis and on
        # the SAME basis the investment rule uses: the certainty equivalent of
        # lifetime rent to an investor who will hold this award.
        #
        # Two things had to be got right here and one of them was wrong twice.
        #
        # The basis has to be the technology's own. Pricing every candidate's pool
        # earnings with the dispatchable formula credited an eight-hour battery with
        # $438,060 per MW-year against the $194,791 its own scheduler delivers,
        # because a store does not run 8,760 hours at full power. That exceeded its
        # entire fixed cost, so it bid zero and won every megawatt of the lane.
        #
        # And it has to be a certainty equivalent, not an expectation. At the
        # free-entry fixed point expected rent equals fixed cost by construction, so
        # a risk-neutral bid is zero and the scheme appears to buy capacity for
        # nothing. That is not a finding, it is the wrong question: what stops this
        # plant being built is not that the market is expected to underpay it, it is
        # that the market might, and the certainty equivalent is where that lives.
        # A scheme priced on expectations would report itself as free.
        exposure = residual_exposure(settings, tech.life_years,
                                     award_years=tenor, award_cover=1.0)
        rents = view.lifetime_rent(tech)
        a = cara_coefficient(representative_aversion, exposure, settings)
        bankable = cara_certainty_equivalent(rents, view.weights, a)
        cost = long_run_cost_per_mw_year(
            tech, blended_wacc(tech, settings, share), bankable)
        price = cost * capacity / firm
        priced[tech.technology] = (tech, capacity, firm)
        for agent in ordered:
            bids.append(Bid(bidder=agent.name, technology=tech.technology,
                            capacity_mw=capacity, firm_mw=firm,
                            price_per_mw_year=price, lead_years=tech.lead_years))

    kept = screen(bids, float(res.price.mean()), settings)
    expected_price = view.nearest.expected_block_prices["overnight"]
    out: list[Award] = []
    for line in clear_pay_as_bid(kept, lane_mw):
        tech, _cap, _firm = priced[line.bid.technology]
        # The ceiling binds on what is AWARDED, not only on what may be offered.
        # Every producer bids the same size, so clearing four of them awarded four
        # times the ceiling: 2,400 MW of eight-hour batteries against a limit of
        # 1,200. A supply chain does not get bigger because more firms asked.
        room = build_ceiling_mw(peak_mw, tech, settings) \
            - built.get(tech.technology, 0.0)
        units = int(min(line.capacity_mw, room) // tech.unit_size_mw)
        if units < 1:
            continue
        capacity = units * tech.unit_size_mw
        line = AwardLine(bid=line.bid, firm_mw=line.firm_mw, capacity_mw=capacity,
                         price_per_mw_year=line.price_per_mw_year)
        strike = award_strike_per_mwh(expected_price, line)
        commissioning = year + tech.lead_years
        contract = award_contract(line, strike, generator=line.bid.bidder,
                                  commissioning_year=commissioning,
                                  tenor_years=tenor)
        state.admin.awards.append(contract)
        state.book.append(contract)
        built[tech.technology] = built.get(tech.technology, 0.0) + capacity
        name = f"{tech.technology}_{year}_{line.bid.bidder}_awarded"
        unit = _new_unit(tech, capacity, name, year)
        state.new_capital.append((
            unit.commissioned_year, unit.retirement_year,
            capacity * tech.capex_per_kw * 1000.0 * tech.crf))
        state.fleet = state.fleet + (unit,)
        state.roster = tuple(
            replace(a, units=a.units + (name,)) if a.name == line.bid.bidder else a
            for a in state.roster)
        state.awarded_share[line.bid.bidder] = 1.0
        out.append(Award(bidder=line.bid.bidder, technology=tech.technology,
                         capacity_mw=capacity, firm_mw=line.firm_mw,
                         price_per_mw_year=line.price_per_mw_year,
                         strike_per_mwh=strike, commissioning_year=commissioning))
    return out


def _cover(settings: Settings, state: RunState, res: DispatchResult, *,
           year: int) -> dict[str, float]:
    """Each producer's contracted share of its own expected output.

    Measured against what its own plant generated, not against the system's. Prices
    being sensible says nothing about whether a volume was built off the right base,
    and a producer sized off system load would look hedged for owning nothing.
    """
    out: dict[str, float] = {}
    for agent in state.roster:
        if agent.kind != PRODUCER:
            continue
        expected_mwh = sum(
            float(np.clip(res.generation_mwh.get(u, 0.0), 0.0, None).sum())
            for u in agent.units)
        out[agent.name] = achieved_swap_cover(agent, state.book, settings, year + 1,
                                              expected_mwh)
    return out


def _invest(settings: Settings, state: RunState, view: ForwardView,
            res: DispatchResult, *, year: int, peak_mw: float,
            cover: dict[str, float], tick: int, leg: str = MERCHANT,
            built: dict[str, float] | None = None) -> list[tuple[Build, Unit]]:
    """Every producer's decisions for one tick, against the annual build ceiling.

    The ceiling is shared across producers rather than held per producer. Two firms
    building the same technology draw on one supply chain, and a per-producer
    ceiling would let a market with more firms in it build faster for no reason
    anybody could point at.

    Producers are taken in an order that rotates with the tick. Sharing the ceiling
    means whoever is asked first gets it, and a fixed order hands it to the same two
    firms every year: over twenty years the merchant and the regional merchant, who
    are the archetypes the whole risk story is about, built almost nothing while the
    two gentailers built almost everything, for no reason other than where they sat
    in a tuple. Rotating does not decide who should win, which is not a question this
    model has an answer to; it stops the tuple deciding.
    """
    built = {} if built is None else built
    out: list[tuple[Build, Unit]] = []
    producers = [a for a in state.roster if a.kind == PRODUCER]
    order = producers[tick % len(producers):] + producers[:tick % len(producers)] \
        if producers else []
    for agent in order:
        award_years = int(settings.esem["contract_tenor_years"]) \
            if leg == ESEM else 0
        award_cover = state.awarded_share.get(agent.name, 0.0) if leg == ESEM else 0.0
        for verdict in rank_candidates(view, agent, settings, peak_mw=peak_mw,
                                       swap_cover=cover.get(agent.name, 0.0),
                                       award_years=award_years,
                                       award_cover=award_cover):
            if not verdict.builds:
                continue
            tech = settings.tech(verdict.technology)
            room = build_ceiling_mw(peak_mw, tech, settings) \
                - built.get(tech.technology, 0.0)
            units = int(min(verdict.capacity_mw, room) // tech.unit_size_mw)
            if units < 1:
                continue
            mw = units * tech.unit_size_mw
            built[tech.technology] = built.get(tech.technology, 0.0) + mw
            name = f"{tech.technology}_{year}_{agent.name}"
            unit = _new_unit(tech, mw, name, year)
            out.append((Build(
                unit=name, technology=tech.technology, capacity_mw=mw,
                owner=agent.name, decided_year=year,
                commissioned_year=unit.commissioned_year,
                hurdle_per_mw_year=verdict.hurdle_per_mw_year,
                expected_rent_per_mw_year=verdict.expected_rent_per_mw_year,
                contracted_share=verdict.contracted_share), unit))
    return out
