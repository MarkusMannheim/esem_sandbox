"""The tick loop: 20 years, one year at a time.

Each tick, in this order and for reasons:

1. Plant decided years ago and finished this year enters service.
2. The year is dispatched and priced.
3. Contracts written in earlier ticks settle against that price.
4. The book ages: what has finished delivering leaves it.
5. The forward view is rebuilt, and the guess at how much plant everybody else
   builds is revised once.
6. The administrator offers its position back, and then the bilateral market covers
   whatever the retailers still need.
7. The scheme's auction runs, when the scheme is on, awarding at final investment
   decision.
8. Exit notices are given, and then entry is decided.

Three of those orderings carry weight, and the reasons follow.

The administrator sells before the bilateral market rather than after, because a
retailer that bought a recycled strip does not also need the same cover from a
producer. The other way round it hedges one load twice and reports itself twice as
covered as it is, which feeds straight into the exposure term the investment rule
turns on.

Exit comes before entry, because a plant giving notice this year is part of the
fleet an entrant is deciding against; the other way round an entrant prices a market
that still contains plant everyone knows is leaving.

Contracts struck at a tick first settle at the next, because a contract signed in
December does not settle the year it was signed in.

Nothing here forecasts. The anchors are exponentially weighted averages of
prices that have already happened, and the forward view is an enumeration of
futures with fixed probabilities. That is the whole mechanism behind the
boom-and-bust exercise: when scarcity lifts prices, investors extrapolate, all of
them build, and the plant arrives together three years later into a market that no
longer needs it.
"""

from __future__ import annotations

from collections.abc import Callable
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
from .contracts import CAP, SWAP, Contract, age, settle_book
from .dispatch import DispatchResult, dispatch_year
from .forward import (
    Cell, EntryState, ForwardView, cell_plan, forward_view, peak_banded,
    update_projected_entry,
)
from .esem import (
    ADMINISTRATOR, Administrator, Bid, AwardLine, award_block_mw,
    award_contracts,
    blended_wacc, clear_pay_as_bid, eligible_technologies,
    firm_contribution_mw, lane_volume_mw, levy_per_mwh,
    long_run_cost_per_mw_year, recycle, reserve_margin_gap_mw, screen,
)
from .scheme import (
    BUILD_CEILING, MET, SCHEME_COUNTERPARTY, SchemeYear, clear_scheme, load_scheme,
    scheme_contracts, summarise, truncate_to_ceiling,
)
from .investment import (
    ExitLedger, achieved_swap_cover, build_ceiling_mw, build_size_mw,
    cara_coefficient, exit_notices, rank_candidates, residual_exposure,
)
from .report import block_mask, block_prices, duration_curve
from .weather import generate_bundle
from .clearing import cara_certainty_equivalent

BOOTSTRAP_YEARS = 3

# The two legs. Merchant is the policy-free counterfactual: the market on its own,
# with no scheme and no underwrite. ESEM is the same market with the procurement
# scheme switched on. Nothing is on by default, because a mechanism this
# consequential running unasked would make every result an argument for itself.
MERCHANT = "merchant"
ESEM = "esem"




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

    The peak band has its own random stream, so that a short run is a prefix of a
    long one on the same seed. Sharing a stream with the shape years would make each
    band depend on how many shapes had been drawn before it, and a four-year run and
    a 20-year run would see different bands in the same calendar years.
    """
    n = ticks + BOOTSTRAP_YEARS
    rng = np.random.default_rng(seed)
    band_rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(1)[0])
    shapes = int(settings.weather["shape_years"])
    bands = list(settings.weather["peak_band_weights"])
    paths = [g.path for g in settings.growth]
    weights = np.array([g.weight for g in settings.growth])
    chosen = int(rng.choice(len(paths), p=weights / weights.sum()))
    return Draw(
        shape_years=tuple(int(i) for i in rng.integers(0, shapes, n)),
        peak_bands=tuple(int(i) for i in
                         band_rng.choice(len(bands), n,
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
    # FOR CHARTS ONLY, and sampled, which nothing that settles money may be. The
    # rule this model keeps is that a cap payout and a cap premium read the full
    # hourly series; a picture of a duration curve is the one place a sample is the
    # right object, because the eye cannot read 8,760 points anyway.
    price_duration: np.ndarray = field(default_factory=lambda: np.zeros(0))
    cap_premium_per_mwh: float = 0.0
    fuel_and_vom: float = 0.0
    fixed_cost_of_fleet: float = 0.0
    annualised_capex_of_new_build: float = 0.0
    scheme_year: SchemeYear | None = None
    lane_volume_mw: float = 0.0
    reserve_margin_gap_mw: float = 0.0
    awards: tuple[Award, ...] = ()
    scheme_cost: float = 0.0
    levy_per_mwh: float = 0.0
    administrator_net: float = 0.0
    administrator_overhead: float = 0.0
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
    # (commissioning year, retirement year, annualised capital cost) for every plant
    # this run decided to build. Existing plant is not here: its capital is sunk, and
    # charging a run for capital spent before it started would compare two legs on
    # money neither of them moved.
    new_capital: list[tuple[int, int, float]] = field(default_factory=list)
    # Nameplate megawatts the state scheme has contracted, by technology. Its
    # milestones are a stock, so each year it buys the gap rather than the whole
    # figure again.
    scheme_awarded: dict[str, float] = field(default_factory=dict)


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
        generators to consumers, not a saving. On the packaged fleet it is $20
        billion of transfer against half a billion of genuinely avoided
        outage, and a comparison that reported only the bill would attribute the
        whole of it to the policy.

        Existing plant's capital is not counted: it is sunk, and charging a run for
        money spent before it started would compare two legs on cashflows neither of
        them moved.

        What it costs to run the administrator IS counted. Consumers pay it through
        the levy, and staffing a statutory body consumes real resources whoever
        writes the cheque, so leaving it out here would class it as a transfer and
        the two views would disagree about a cost that nobody recovers.
        """
        return (sum(t.fuel_and_vom for t in self.ticks)
                + sum(t.fixed_cost_of_fleet for t in self.ticks)
                + sum(t.annualised_capex_of_new_build for t in self.ticks)
                + sum(t.administrator_overhead for t in self.ticks)
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


def forced_retirements(fleet: tuple[Unit, ...], retire: dict[str, int] | None,
                       start_year: int) -> tuple[Unit, ...]:
    """Close plant because somebody decided to, not because it stopped paying.

    Separate from the economic exit rule and deliberately so. Exit is a decision a
    firm takes when the going-forward position turns negative twice; this is a
    closure the world imposes, and the two must not be gated by the same switch or
    a run with economic exit turned off would quietly ignore a policy as well.

    The exercise it exists for is the boom and the bust: pull a coal retirement
    forward against a two-year gas lead and watch entry cluster, arrive late, and
    overshoot. That is worth being able to do in one line of a scenario file, and it
    is worth failing loudly when the line names a plant that is not there.
    """
    if not retire:
        return fleet
    known = {u.unit for u in fleet}
    unknown = set(retire) - known
    if unknown:
        raise ValueError(
            f"cannot retire plant that does not exist: {', '.join(sorted(unknown))}. "
            f"The fleet holds {', '.join(sorted(known))}"
        )
    early = {u: y for u, y in retire.items() if y < start_year}
    if early:
        raise ValueError(
            f"cannot retire plant before the run starts in {start_year}: {early}. "
            "A plant that never operates should be taken out of the fleet, not "
            "retired in the past, or the run will report capacity it never had"
        )
    return tuple(replace(u, retirement_year=int(retire[u.unit]))
                 if u.unit in retire else u for u in fleet)


def _demand(bundle: dict, shape_year: int, peak_mw: float,
            peak_multiplier: float) -> np.ndarray:
    shape = bundle["demand_shape"][shape_year]
    return peak_banded(shape * (peak_mw / shape.max()), peak_multiplier)


def _new_unit(tech: TechCost, mw: float, name: str, decided_year: int) -> Unit:
    commissioned = decided_year + tech.lead_years
    return Unit(
        unit=name,
        technology=tech.dispatch_technology,
        capacity_mw=mw, availability=tech.availability,
        srmc_per_mwh=tech.srmc_per_mwh,
        retirement_year=commissioned + tech.life_years,
        commissioned_year=commissioned, must_run_mw=0.0, energy_budget_gwh=None,
        duration_h=tech.duration_h,
        round_trip_efficiency=tech.round_trip_efficiency,
        firm_factor=tech.firm_factor, cap_eligible=tech.cap_eligible,
        fom_per_kw_year=tech.fom_per_kw_year,
    )


def _cap_payoff_per_mw_year(price: np.ndarray, strike: float) -> float:
    return float(np.clip(price - strike, 0.0, None).sum())


def _merchant_entry_loading(settings: Settings, view: ForwardView,
                            roster: tuple[Agent, ...]) -> dict[str, float]:
    """The risk premium a representative merchant would want, per technology.

    The projection is only allowed to assume entry that the leg's own investment
    test would actually take. A projection of a merchant market that assumed
    break-even entry would be projecting a market with a different investor in it.

    Per technology, because the projection now chooses one rather than being told
    which. A peaker and a battery do not carry the same spread across futures, so
    they do not carry the same loading, and using one number for both would decide
    the choice between them on the wrong quantity.
    """
    producers = [a for a in roster if a.kind == PRODUCER]
    if not producers:
        return {}
    representative = max(a.risk_aversion for a in producers)
    a = cara_coefficient(representative, 1.0, settings)
    weights = view.weights
    out: dict[str, float] = {}
    for tech in settings.tech_costs:
        rents = view.lifetime_rent(tech)
        out[tech.technology] = float(rents @ weights) - cara_certainty_equivalent(
            rents, weights, a)
    return out


def run(settings: Settings, *, ticks: int = 20, start_year: int = 2026,
        peak_mw: float = 12_500.0, seed: int | None = None,
        cells: tuple[Cell, ...] | None = None, leg: str = MERCHANT,
        retire: dict[str, int] | None = None, clearing: str = "anchor",
        scheme: bool = False, bundle: dict | None = None,
        investment: str = "simultaneous") -> RunResult:
    """One leg of a run: dispatch, contract, invest, 20 times over.

    ``leg`` selects the counterfactual. Both legs draw the same weather from the same
    seed, so a comparison between them is a comparison of the mechanism and of
    nothing else.
    """
    if leg not in (MERCHANT, ESEM):
        raise ValueError(f"unknown leg {leg!r}: expected {MERCHANT!r} or {ESEM!r}")
    if investment not in ("simultaneous", "sequential"):
        raise ValueError(
            f"unknown investment rule {investment!r}: expected 'simultaneous', "
            "where every producer is priced against one forecast, or 'sequential', "
            "where the forward is rebuilt between them"
        )
    seed = int(settings.weather["seed"]) if seed is None else seed
    bundle = bundle if bundle is not None else generate_bundle(
        seed, int(settings.weather["shape_years"]))
    plan = cells if cells is not None else cell_plan(settings)
    draw = draw_sequence(settings, seed, ticks)
    bands = list(settings.weather["peak_band_multipliers"])

    roster = default_roster()
    check_roster(roster, ownable_units(settings.fleet))
    state = RunState(year=start_year,
                     fleet=forced_retirements(settings.fleet, retire, start_year),
                     roster=roster)

    scheme_row = load_scheme(settings) if scheme else None
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
                                 peak_mw=level, ocgt=ocgt, clearing=clearing))

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
        #
        # Keep the belief this view was built on. The sequential investment rule
        # rebuilds the forward after each producer decides, and it must differ from
        # what the previous producer saw by the PLANT JUST DECIDED and by nothing
        # else. Reading state.entry at that point instead picked up the step taken on
        # the line below, so the second producer faced a market containing the first
        # producer's plant AND a whole extra step of assumed entry by everybody else.
        # That is not the mechanism the rule exists to isolate, and the rule is one
        # end of the bracket this model reports on how much a market builds.
        belief_behind_view = state.entry
        view = forward_view(live, state.fleet, bundle, year=year, peak_mw=level,
                            entry=belief_behind_view, cells=plan)
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
            # The market price for what is being sold, which is a hedge for a
            # delivery year still ahead. That is the forward view's expectation,
            # the same basis the award was struck on. A trailing average of prices
            # that have already happened is a different market.
            near = view.nearest
            strips = recycle(
                state.admin, settings, year=year, buyers=buyers,
                market_per_mwh=near.expected_block_prices,
                market_cap_premium_per_mwh=(float(np.mean(state.cap_payoffs[-5:]))
                                            / 8760.0 if state.cap_payoffs else 0.0))
            state.book.extend(strips)
            # Cover already held, on the same basis the bilateral target is set on:
            # averaged over the delivery years the rung written below will cover,
            # and weighted by each strip's share of the year's hours. Counting only
            # the strip that starts next year leaves the later years of the rung
            # netting against nothing, so the retailer buys the same cover twice.
            # A cap is not price-certain cover and does not count here at all.
            covered_years = range(year + 1, year + 1 + tenor)
            for c in strips:
                if c.kind != SWAP or c.start_year not in covered_years:
                    continue
                share = float(block_mask(settings, c.block, 8760).sum()) / 8760.0 \
                    if c.block else 1.0
                recycled_mw[c.holder] = recycled_mw.get(c.holder, 0.0) + \
                    c.volume_mw * share / tenor

        written = _clear(settings, state, res, year=year,
                         start_year=year + 1, tenor_years=tenor,
                         peak_mw=level, ocgt=ocgt,
                         already_covered_mw=recycled_mw, clearing=clearing)
        state.book.extend(written)

        # 7. The auction, when the scheme is on. New entrants only, sized on the
        #    near anchor's shortfall, cleared pay-as-bid, awarded at final
        #    investment decision so the plant is committed now and arrives after
        #    its lead time.
        awards: list[Award] = []
        built_this_year: dict[str, float] = {}
        lane_mw = 0.0
        margin_gap = 0.0
        awarded_this_year = False
        if leg == ESEM:
            near = view.nearest
            lane_mw = lane_volume_mw(near, settings)
            margin_gap = reserve_margin_gap_mw(
                near, res.firm_capacity_mw, level,
                float(settings.esem["reserve_margin"]))
            awards = _auction(settings, state, view, res, year=year,
                              peak_mw=level, lane_mw=lane_mw, built=built_this_year,
                              tick=t)
            awarded_this_year = bool(awards)

        # 7b. The state scheme, when one is running. Its quantity comes from a
        #     policy rather than from the system, so it runs whatever the market is
        #     doing and can miss its milestone; which constraint missed it is the
        #     output.
        scheme_year = None
        if scheme_row is not None:
            scheme_year, scheme_lines = _scheme_round(
                settings, state, view, scheme_row, year=year, peak_mw=level,
                built=built_this_year, tick=t)
            expected = view.nearest.expected_block_prices
            for line in scheme_lines:
                _commit_scheme_award(settings, state, line, scheme_row, year=year,
                                     expected_price=expected,
                                     built=built_this_year, peak_mw=level)
                awarded_this_year = True

        # The auction and the scheme commit plant at step 7, and the forward view was
        # built at step 5. Entry would otherwise price a market that does not contain
        # capacity committed minutes earlier, at horizons where it is certainly
        # running. That gap falls on the scheme's leg alone, so it would read as a
        # difference between the two legs that the mechanism did not create.
        # Rebuilt only in years something was awarded, which is what it costs.
        if awarded_this_year:
            view = forward_view(live, state.fleet, bundle, year=year, peak_mw=level,
                                entry=belief_behind_view, cells=plan)

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

        def _reprice(new_units: list[Unit]) -> ForwardView:
            """The forward as it stands once this year's decisions so far exist.

            Rebuilt from the fleet PLUS what has been decided, because plant decided
            now is in service at every anchor the decision turns on. It is the
            expensive call in a tick, which is the honest cost of the repair.
            """
            return forward_view(live, state.fleet + tuple(new_units), bundle,
                                year=year, peak_mw=level, entry=belief_behind_view,
                                cells=plan)

        builds = _invest(settings, state, view, res, year=year, peak_mw=level,
                         cover=cover, tick=t, leg=leg, built=built_this_year,
                         reprice=_reprice if investment == "sequential" else None)
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
        overhead = float(settings.esem["overhead_per_year"]) if leg == ESEM else 0.0
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
            # Energy actually DELIVERED, which the model's own balance identity
            # defines: operational demand less what the demand-response ladder shed
            # and less what went unserved. Billing the whole of operational demand
            # charged consumers for both. The unserved half was charged twice over,
            # because consumer_cost adds the same megawatt hours again at the value
            # of lost load on the line below. The shed half was charged to consumers
            # and paid to nobody: ladder_mw reaches no cashflow anywhere in the
            # model, which is its own gap and is written up in KNOWN_LIMITATIONS.
            wholesale_cost=float((res.price * (res.operational_demand_mw
                                               - res.ladder_mw
                                               - res.unserved_mwh)).sum()),
            price_duration=duration_curve(res.price, points=600),
            cap_premium_per_mwh=float(np.mean([
                c.premium_per_mwh for c in written if c.kind == CAP] or [0.0])),
            fuel_and_vom=fuel,
            fixed_cost_of_fleet=fixed,
            annualised_capex_of_new_build=capital,
            scheme_year=scheme_year,
            lane_volume_mw=lane_mw,
            reserve_margin_gap_mw=margin_gap,
            awards=tuple(awards),
            scheme_cost=sum(a.firm_mw * a.price_per_mw_year for a in awards),
            levy_per_mwh=levy,
            administrator_net=admin_net,
            administrator_overhead=overhead,
            warehoused_mw=warehoused,
        ))
    return RunResult(ticks=tuple(results), draw=draw, fleet=state.fleet,
                     roster=state.roster, book=tuple(state.book), leg=leg)


def _clear(settings: Settings, state: RunState, res: DispatchResult, *,
           year: int, start_year: int, tenor_years: int, peak_mw: float,
           ocgt: TechCost, already_covered_mw: dict[str, float] | None = None,
           clearing: str = "anchor") -> list[Contract]:
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
        already_covered_mw=already_covered_mw or {}, clearing=clearing)


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
        # The basis has to be the technology's own. Pricing every candidate's pool
        # earnings with the dispatchable formula credits an eight-hour battery with
        # $438,060 per MW-year against the $194,791 its own scheduler delivers,
        # because a store does not run 8,760 hours at full power. That exceeded its
        # entire fixed cost, so it bid zero and won every megawatt of the lane.
        #
        # And it has to be a certainty equivalent, not an expectation. At the
        # free-entry fixed point expected rent equals fixed cost by construction, so
        # a risk-neutral bid is zero and the scheme appears to buy capacity for
        # nothing. That is the wrong question rather than a finding: what stops this
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
        # The firm megawatts are scaled with the truncation, not carried across it.
        # Clearing hands back a part-filled bid, and rounding that down to whole
        # generating units shrinks the plant; keeping the pre-rounding firm figure
        # made the scheme report contracting more capacity than it built AND pay for
        # it, because the strike spreads the bid over the contracted volume and the
        # bid was sized on firm megawatts that no longer existed.
        shrink = capacity / line.capacity_mw if line.capacity_mw > 0 else 0.0
        line = AwardLine(bid=line.bid, firm_mw=line.firm_mw * shrink,
                         capacity_mw=capacity,
                         price_per_mw_year=line.price_per_mw_year)
        commissioning = year + tech.lead_years
        # A tenor of zero means no contract at all, so the scheme is an auction and
        # nothing else. That is a documented exercise: it separates what the lane
        # buys from what a long contract does to the cost of capital, by removing
        # the second. Writing a zero-year contract instead raised "tenor must be at
        # least one year" partway through the run, so the exercise the notebook and
        # short_tenor.toml both describe could not actually be run.
        written: list[Contract] = []
        if tenor >= 1:
            payoffs = state.cap_payoffs[-5:] or [0.0]
            written = award_contracts(
                line, generator=line.bid.bidder,
                commissioning_year=commissioning, tenor_years=tenor,
                tech=tech, settings=settings,
                expected_payout_per_mw=float(np.mean(payoffs)),
                expected_block_prices=near.expected_block_prices,
                block_mw=award_block_mw(settings, tech, capacity_mw=capacity))
            state.admin.awards.extend(written)
            state.book.extend(written)
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
        # One strike for the record, volume weighted across whatever the award
        # wrote. A cap and four block swaps do not share a strike, and the reported
        # figure is a summary rather than a term of any contract.
        volume = sum(c.volume_mw for c in written)
        strike = (sum(c.strike_per_mwh * c.volume_mw for c in written) / volume
                  if volume > 0 else 0.0)
        out.append(Award(bidder=line.bid.bidder, technology=tech.technology,
                         capacity_mw=capacity, firm_mw=line.firm_mw,
                         price_per_mw_year=line.price_per_mw_year,
                         strike_per_mwh=strike, commissioning_year=commissioning))
    return out


def _scheme_held_mw(state: RunState) -> float:
    """Nameplate megawatts the scheme has already contracted, against a stock target."""
    return sum(state.scheme_awarded.values())


def _scheme_round(settings: Settings, state: RunState, view: ForwardView,
                  row, *, year: int, peak_mw: float, built: dict[str, float],
                  tick: int):
    """One year of the state scheme, bid for in NAMEPLATE megawatts.

    The reliability lane buys delivered firm capacity because that is what closes a
    reliability gap. A capacity target is written in nameplate, so that is what is
    bid and cleared here, and the two must not be added together: nine gigawatts of
    nameplate wind at a firm factor of a tenth is 900 megawatts of firm
    capacity.
    """
    tenor = int(settings.esem["contract_tenor_years"])
    producers = [a for a in state.roster if a.kind == PRODUCER]
    if not producers:
        return clear_scheme(row, [], year, _scheme_held_mw(state))[0], []
    rotation = tick % len(producers)
    ordered = producers[rotation:] + producers[:rotation]
    representative = max(a.risk_aversion for a in producers)

    bids: list[Bid] = []
    for name in row.technologies:
        try:
            tech = settings.tech(name)
        except KeyError:
            continue
        capacity = build_size_mw(peak_mw, tech, settings)
        room = build_ceiling_mw(peak_mw, tech, settings) - built.get(name, 0.0)
        capacity = min(capacity, room)
        if capacity < tech.unit_size_mw:
            continue
        capacity = (capacity // tech.unit_size_mw) * tech.unit_size_mw
        share = min(1.0, row.tenor_years / max(1, tech.life_years))
        exposure = residual_exposure(settings, tech.life_years,
                                     award_years=row.tenor_years, award_cover=1.0)
        rents = view.lifetime_rent(tech)
        a = cara_coefficient(representative, exposure, settings)
        bankable = cara_certainty_equivalent(rents, view.weights, a)
        price = long_run_cost_per_mw_year(
            tech, blended_wacc(tech, settings, share), bankable)
        for agent in ordered:
            bids.append(Bid(bidder=agent.name, technology=name,
                            capacity_mw=capacity, firm_mw=capacity,
                            price_per_mw_year=price, lead_years=tech.lead_years))
    year_record, lines = clear_scheme(row, bids, year,
                                      _scheme_held_mw(state))
    # The ceiling binds on what is AWARDED, not only on what may be offered: every
    # producer bids the same size, so clearing several of them can total more than
    # a year can build.
    room = {name: build_ceiling_mw(peak_mw, settings.tech(name), settings)
                  - built.get(name, 0.0)
            for name in row.technologies if _has_tech(settings, name)}
    sizes = {name: settings.tech(name).unit_size_mw for name in room}
    lines, ceiling_bound = truncate_to_ceiling(lines, room, sizes)
    if ceiling_bound and year_record.binding == MET:
        year_record = summarise(row, year, year_record.sought_mw, lines,
                                BUILD_CEILING)
    else:
        year_record = summarise(row, year, year_record.sought_mw, lines,
                                year_record.binding)
    return year_record, lines


def _has_tech(settings: Settings, name: str) -> bool:
    try:
        settings.tech(name)
    except KeyError:
        return False
    return True


def _commit_scheme_award(settings: Settings, state: RunState, line, row, *,
                         year: int, expected_price: dict[str, float],
                         built: dict[str, float], peak_mw: float) -> None:
    """Build what the scheme contracted, and hold the contract to maturity.

    The scheme draws on the SAME annual build ceiling as everything else. One supply
    chain builds a scheme's wind farm and a merchant's, and letting a scheme build on
    top of the ceiling rather than inside it would make a policy look like it added
    capacity when what it added was permission the model had not granted anybody
    else.
    """
    tech = settings.tech(line.bid.technology)
    room = build_ceiling_mw(peak_mw, tech, settings) \
        - built.get(tech.technology, 0.0)
    units = int(min(line.capacity_mw, room) // tech.unit_size_mw)
    if units < 1:
        return
    capacity = units * tech.unit_size_mw
    built[tech.technology] = built.get(tech.technology, 0.0) + capacity
    name = f"{tech.technology}_{year}_{line.bid.bidder}_scheme"
    unit = _new_unit(tech, capacity, name, year)
    state.new_capital.append((unit.commissioned_year, unit.retirement_year,
                              capacity * tech.capex_per_kw * 1000.0 * tech.crf))
    state.fleet = state.fleet + (unit,)
    state.roster = tuple(
        replace(a, units=a.units + (name,)) if a.name == line.bid.bidder else a
        for a in state.roster)
    sized = AwardLine(bid=line.bid, firm_mw=capacity, capacity_mw=capacity,
                      price_per_mw_year=line.price_per_mw_year)
    state.book.extend(scheme_contracts(
        [sized], row, expected_block_prices=expected_price,
        commissioning={tech.technology: unit.commissioned_year},
        settings=settings))
    state.scheme_awarded[tech.technology] = \
        state.scheme_awarded.get(tech.technology, 0.0) + capacity


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
            built: dict[str, float] | None = None,
            reprice: "Callable[[list[Unit]], ForwardView] | None" = None,
            ) -> list[tuple[Build, Unit]]:
    """Every producer's decisions for one tick, against the annual build ceiling.

    The ceiling is shared across producers rather than held per producer. Two firms
    building the same technology draw on one supply chain, and a per-producer
    ceiling would let a market with more firms in it build faster for no reason
    anybody could point at.

    Producers are taken in an order that rotates with the tick. Sharing the ceiling
    means whoever is asked first gets it, and a fixed order hands it to the same two
    firms every year: over 20 years the merchant and the regional merchant, who
    are the archetypes the whole risk story is about, built almost nothing while the
    two gentailers built almost everything, for no reason other than where they sat
    in a tuple. Rotating does not decide who should win, which is not a question this
    model has an answer to; it stops the tuple deciding.

    ``reprice``, when given, is called after each producer that built anything and
    returns a forward view that INCLUDES what has been decided so far this year. That
    is the difference between four decisions taken against one forecast and four taken
    in sequence, and it is the same repair entry and exit already have. Without it,
    the price feedback that should make the second block less attractive is
    real but far too weak to bind: measured on this fleet, each 600 MW of wind cuts
    the next block's value by about $50,000 per MW-year and lifts its hurdle by about
    $6,000, against an opening gap of $367,000. Closing that gap takes roughly 4,000
    MW, more than three times the annual ceiling of 1,200 MW, so the ceiling always
    bites first.

    Each producer wants exactly one block, so what actually fills the ceiling is
    four producers picking the same winner: the first two get their block and the
    rest are shut out. That is why, measured, every megawatt of build lands on the
    ceiling.
    """
    built = {} if built is None else built
    out: list[tuple[Build, Unit]] = []
    producers = [a for a in state.roster if a.kind == PRODUCER]
    order = producers[tick % len(producers):] + producers[:tick % len(producers)] \
        if producers else []
    for agent in order:
        before = len(out)
        # A MERCHANT candidate carries no award, whoever is building it. The risk
        # an award removes is applied where it belongs, on the bid the awarded plant
        # makes, and a producer that won an auction last year has not thereby hedged
        # the unrelated plant it is pricing this year. A per-producer flag would
        # price every later merchant project of an auction winner as though 85 per
        # cent of its output were sold forward for 12 years, on the ESEM leg only,
        # which is one half of the comparison the model exists to make.
        award_years = 0
        award_cover = 0.0
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
        if reprice is not None and len(out) > before:
            view = reprice([u for _, u in out])
    return out
