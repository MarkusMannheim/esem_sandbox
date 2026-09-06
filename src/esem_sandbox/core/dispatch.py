"""Hourly dispatch, pricing and the scarcity ladder.

One region, 8,760 hourly steps. The price each hour is the offer of the unit
that meets residual demand on the cumulative available-capacity stack. Above
the last physical unit the price climbs the demand-response ladder, then the
reliability response tranche, then the value of lost load, and the administered
cap applies once the rolling cumulative price threshold is breached.

Energy-limited plant is scheduled against its budget rather than offered and
hoped for: hydro shaves the residual down to a threshold chosen so the year's
budget is spent exactly. An offer alone could only move it among a handful of
discrete thermal steps, and delivered 40 to 50 per cent of the budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config import STORAGE_ROUND_TRIP, Settings, Unit

HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365

_THERMAL = ("coal", "ccgt", "ocgt", "import")
_STORAGE = ("battery", "phes")


@dataclass
class DispatchResult:
    """One simulated year."""

    price: np.ndarray                      # $/MWh, 8760
    residual_mw: np.ndarray                # after VRE and storage, 8760
    demand_mw: np.ndarray                  # native demand before rooftop, 8760
    operational_demand_mw: np.ndarray = field(  # net of rooftop: what the grid serves
        default_factory=lambda: np.zeros(0))
    generation_mwh: dict[str, np.ndarray] = field(default_factory=dict)
    unserved_mwh: np.ndarray = field(default_factory=lambda: np.zeros(0))
    ladder_mw: np.ndarray = field(default_factory=lambda: np.zeros(0))
    administered_hours: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    firm_capacity_mw: float = 0.0          # the stack the ladder measured against
    water_value_per_mwh: float = 0.0

    @property
    def total_unserved_gwh(self) -> float:
        return float(self.unserved_mwh.sum()) / 1000.0

    @property
    def total_demand_gwh(self) -> float:
        return float(self.demand_mw.sum()) / 1000.0

    @property
    def unserved_fraction(self) -> float:
        """Unserved energy over OPERATIONAL demand, not native demand.

        Unserved energy is a shortfall in what the grid was asked to serve. Rooftop
        output never reaches the grid, so including the load it meets behind the
        meter puts numerator and denominator on different bases and flatters the
        ratio. Here that understated every reliability figure by about a quarter.
        """
        total = self.operational_demand_mw.sum()
        return float(self.unserved_mwh.sum() / total) if total else 0.0


def _in_service(settings: Settings, year: int) -> list[Unit]:
    return [u for u in settings.fleet if u.in_service(year)]


def _offer_stack(units: list[Unit], settings: Settings,
                 extra: dict[str, float] | None = None
                 ) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Offer prices, capacities and labels for everything that sets a price.

    A coal unit is split in two: the band it bids hardest to keep running offers at its
    must-run price, and the rest offers at its own short run cost. Those are
    different economics from a curtailing wind farm, so they are different numbers:
    a coal unit bids low to avoid a shutdown and restart, a wind farm bids down to
    roughly minus the certificate revenue it would forgo.
    """
    floor = settings.dispatch["must_run_offer_per_mwh"]
    prices: list[float] = []
    caps: list[float] = []
    labels: list[str] = []
    for u in units:
        if u.technology in _STORAGE or u.technology in ("wind", "solar", "rooftop"):
            continue
        available = u.available_mw
        if u.technology == "hydro":
            price = (extra or {}).get("water_value", u.srmc_per_mwh)
            prices.append(price)
            caps.append(available)
            labels.append(u.unit)
            continue
        must_run = min(u.must_run_mw, available)
        if must_run > 0:
            prices.append(floor)
            caps.append(must_run)
            labels.append(u.unit)
        if available - must_run > 0:
            prices.append(u.srmc_per_mwh)
            caps.append(available - must_run)
            labels.append(u.unit)
    order = np.argsort(np.asarray(prices, dtype=float), kind="stable")
    p = np.asarray(prices, dtype=float)[order]
    c = np.asarray(caps, dtype=float)[order]
    lab = [labels[i] for i in order]
    return p, c, lab


def _price_from_stack(residual: np.ndarray, prices: np.ndarray,
                      caps: np.ndarray, floor: float,
                      surplus_price: np.ndarray | None = None,
                      must_run_floor_mw: float = 0.0) -> np.ndarray:
    """Marginal offer meeting the residual; the surplus price when nothing is needed.

    ``surplus_price`` is the curtailment merit order's answer for hours with more
    generation than load. Without it every surplus hour would clear at one constant,
    which puts a flat step of identical negative prices across a fifth of the year.
    """
    cum = np.cumsum(caps)
    idx = np.searchsorted(cum, np.clip(residual, 0.0, None), side="left")
    out = np.full(residual.shape, prices[-1] if len(prices) else floor)
    inside = idx < len(prices)
    out[inside] = prices[idx[inside]]
    # Withdrawal begins at the must-run floor, not at zero residual. Below that
    # floor the cheapest thing left in the stack is a coal band bidding to avoid a
    # shutdown, and it bids BELOW wind and solar. Pricing that region off the stack
    # cleared 1,131 hours a year at the coal band's offer while wind and solar,
    # which had offered more, were still generating: plant running below its own
    # offer. The withdrawal order runs from the least negative offer to the most.
    spare = residual <= float(must_run_floor_mw)
    out[spare] = floor if surplus_price is None else surplus_price[spare]
    return out


def _curtailment(surplus_mw: np.ndarray, tiers: list[tuple[str, float, np.ndarray]]
                 ) -> dict[str, np.ndarray]:
    """How much each technology is curtailed in a surplus hour.

    Withdrawal follows the same order as the price: the plant willing to accept
    least is curtailed last. Without this the reported fleet output is the
    unconstrained profile, which does not add up to what the system served.
    """
    out: dict[str, np.ndarray] = {}
    left = surplus_mw.copy()
    for name, _offer, available in sorted(tiers, key=lambda t: -t[1]):
        cut = np.minimum(left, available)
        out[name] = cut
        left = left - cut
    return out


def _curtailment_price(surplus_mw: np.ndarray, tiers: list[tuple[float, np.ndarray]],
                       market_floor: float) -> np.ndarray:
    """The offer of the plant on the margin of curtailment.

    When generation exceeds load the price falls until enough of it withdraws. The
    plant that withdraws last is the one willing to accept the lowest price, so the
    tiers are walked from the least negative offer to the most negative and the
    marginal tier sets the price. Past the last tier nothing else will withdraw and
    the price is the market floor.
    """
    price = np.full(surplus_mw.shape, market_floor)
    cum = np.zeros_like(surplus_mw)
    assigned = np.zeros(surplus_mw.shape, dtype=bool)
    for offer, available in sorted(tiers, key=lambda t: -t[0]):
        cum = cum + available
        hit = (~assigned) & (surplus_mw <= cum)
        price[hit] = offer
        assigned |= hit
    return price


def _hydro_schedule(residual: np.ndarray, hydro_mw: float, budget_mwh: float,
                    prices: np.ndarray, caps: np.ndarray, floor: float,
                    surplus_price: np.ndarray | None = None
                    ) -> tuple[np.ndarray, float]:
    """Allocate hydro's annual energy by peak shaving, and price it at its margin.

    Hydro is energy limited, so the question is which hours to spend water in. The
    answer is the dearest ones, and the classical way to find them is a residual
    threshold: run hydro on whatever sits above the threshold, up to its capacity,
    and lower the threshold until the year's budget is exactly spent. The offer that
    rationalises that schedule is the thermal price at the threshold, which is the
    cost of the unit hydro displaces at the margin.

    The previous version chose an offer price and let the merit order decide the
    rest. That could not work: a price offer only moves hydro's position among nine
    discrete thermal offers, so between two of them the delivered energy does not
    change at all. It under-spent the budget by 40 to 50 per cent, and quadrupling
    the budget changed neither the offer nor the delivery.

    Returns the hourly schedule and the water value.
    """
    if hydro_mw <= 0 or not budget_mwh:
        return np.zeros_like(residual), 0.0

    # Bisect the threshold. Generation is monotone decreasing in the threshold, so
    # a plain bisection is exact to within a MWh in a few dozen iterations.
    def delivered(threshold: float) -> float:
        return float(np.clip(residual - threshold, 0.0, hydro_mw).sum())

    low, high = float(min(residual.min(), 0.0)), float(residual.max())
    if delivered(low) <= budget_mwh:
        # Even shaving everything down to the lowest residual cannot spend it: the
        # budget exceeds what the year can absorb, so hydro runs as hard as it can.
        schedule = np.clip(residual - low, 0.0, hydro_mw)
        return schedule, float(_price_from_stack(
            np.array([low]), prices, caps, floor,
            None if surplus_price is None else np.array([surplus_price.min()]))[0])

    for _ in range(60):
        mid = 0.5 * (low + high)
        if delivered(mid) > budget_mwh:
            low = mid
        else:
            high = mid
    threshold = 0.5 * (low + high)
    schedule = np.clip(residual - threshold, 0.0, hydro_mw)

    # Scale off any residual overshoot from the bisection so the budget is exact.
    total = schedule.sum()
    if total > 0:
        schedule *= budget_mwh / total

    water = float(_price_from_stack(np.array([threshold]), prices, caps, floor)[0])
    return schedule, water


def _balance_level(day: np.ndarray, power: float, rte: float) -> np.ndarray:
    """Per day, the single level at which filling below it exactly feeds shaving
    above it, net of the round trip.

    This is the level a store with unlimited energy would flatten the day to. It
    matters because it bounds how much a store can usefully do in a day: above this
    throughput the charge level would have to rise past the discharge level, which
    is not a schedule, it is a contradiction. Finding it is one bisection, because
    filling rises and shaving falls as the level rises, so their difference crosses
    zero exactly once.
    """
    lo = np.full(len(day), day.min(axis=1))
    hi = np.full(len(day), day.max(axis=1))
    for _ in range(20):
        mid = 0.5 * (lo + hi)
        fill = np.clip(mid[:, None] - day, 0.0, power).sum(axis=1)
        shave = np.clip(day - mid[:, None], 0.0, power).sum(axis=1)
        low = fill * rte < shave
        lo = np.where(low, mid, lo)
        hi = np.where(low, hi, mid)
    return 0.5 * (lo + hi)


def _fill_threshold(day: np.ndarray, power: float, target: np.ndarray) -> np.ndarray:
    """Per day, the level a store fills the trough up to, to absorb ``target`` MWh.

    ``sum(clip(level - r, 0, power))`` rises with the level, so a bisection finds it.
    Vectorised across days, because only the state of charge is genuinely sequential.
    """
    lo = np.full(len(day), day.min(axis=1))
    hi = np.full(len(day), day.max(axis=1))
    for _ in range(20):
        mid = 0.5 * (lo + hi)
        got = np.clip(mid[:, None] - day, 0.0, power).sum(axis=1)
        under = got < target
        lo = np.where(under, mid, lo)
        hi = np.where(under, hi, mid)
    return 0.5 * (lo + hi)


def _shave_threshold(day: np.ndarray, power: float, target: np.ndarray) -> np.ndarray:
    """Per day, the level a store shaves the peak down to, to deliver ``target`` MWh."""
    lo = np.full(len(day), day.min(axis=1))
    hi = np.full(len(day), day.max(axis=1))
    for _ in range(20):
        mid = 0.5 * (lo + hi)
        got = np.clip(day - mid[:, None], 0.0, power).sum(axis=1)
        over = got > target
        lo = np.where(over, mid, lo)
        hi = np.where(over, hi, mid)
    return 0.5 * (lo + hi)


def _run_storage(units: list[Unit], price_of, residual_mw: np.ndarray,
                 settings: Settings) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Daily cycling by shaving quantities, not by ranking prices.

    A store fills the trough up to a level and shaves the peak down to a level, with
    the two levels chosen so the energy balances across the round trip. It is the
    two-sided version of what the hydro schedule already does here, and the reason
    to prefer it is not elegance.

    **Ranking prices makes storage able to cause a shortage.** The rule this
    replaces gave every unit the same price series, so every unit picked the same
    cheapest hours and charged at full power in all of them, with nothing anywhere
    asking whether the system could serve that load. Ten gigawatts of four-hour
    batteries added to the packaged fleet lifted peak net load from 9,605 MW to
    20,880 and took unserved energy from 0.005 per cent of demand to 22.8. Storage
    was manufacturing the scarcity it was built to relieve, and the investment rule
    downstream then read the resulting prices as a reason to build more of it.

    Shaving quantities cannot do that, and the reason is structural rather than
    tuned. Charging fills the trough to a level at or below the discharge level, and
    discharging lowers the peak to that level, so the post-storage residual can
    never exceed the pre-storage peak. **A store cannot make the peak worse.** The
    same construction makes it impossible for a unit to charge and discharge in the
    same hour, which was a separate defect fixed by hand in week one and is now
    ruled out by the shape of the rule.

    Units are scheduled in order of duration, longest first, each against the
    residual left by the ones before it. Two stores shaving the same peak
    independently would each believe it had the whole peak to itself.

    **There is no iteration here, and there no longer needs to be.** The quantities
    depend on the residual and on the unit, never on the price, so the only thing
    the price decides is whether a day is worth buying into. ``price_of`` turns the
    residual a unit actually faces into the price it would face, so each store judges
    against the market the ones before it have already left behind, and nothing in
    the schedule depends on the answer the schedule produces.

    The rule this replaced could not say that. It ranked a price that its own
    schedule then moved, so the dispatch had to iterate to a fixed point that
    sometimes did not exist: adding four gigawatts of batteries to this fleet put the
    loop into a two-cycle it never left, and the reported year was whichever phase
    the sixth pass happened to land on.
    """
    spread = settings.dispatch["storage_spread_per_mwh"]
    n = len(residual_mw)
    n_days = n // HOURS_PER_DAY
    net_load = np.zeros(n)
    per_unit: dict[str, np.ndarray] = {}
    if n_days == 0:
        return net_load, per_unit

    usable = n_days * HOURS_PER_DAY
    working = residual_mw.astype(float).copy()

    # Stores that are alike are scheduled as one. Two four-hour batteries with the
    # same round trip behave identically per MW, so netting one against the other
    # would only decide, by the arbitrary order they were built in, which of them
    # gets the deeper half of the peak. Scheduling their combined power once and
    # splitting the answer pro rata removes that arbitrariness, and it keeps the
    # day scan from growing with a fleet that acquires a new battery every few
    # years: a twenty-year run ends with more storage rows than it started with,
    # and the scan is the one part of a dispatched year that is not vectorised.
    groups: dict[tuple[float, float], list[Unit]] = {}
    for u in units:
        if u.technology not in _STORAGE or not u.duration_h or u.available_mw <= 0:
            continue
        key = (float(u.duration_h), float(u.round_trip_efficiency or STORAGE_ROUND_TRIP))
        groups.setdefault(key, []).append(u)

    for (duration, rte), members in sorted(groups.items(), key=lambda kv: -kv[0][0]):
        power = sum(m.available_mw for m in members)
        energy_cap = power * duration
        if power <= 0 or energy_cap <= 0:
            continue
        day = working[:usable].reshape(n_days, HOURS_PER_DAY)
        price_by_day = price_of(working)[:usable].reshape(n_days, HOURS_PER_DAY)

        # How much is worth moving today. A store big enough to flatten the day
        # entirely stops at the level where filling feeds shaving exactly; a smaller
        # one runs a full cycle and leaves the day still peaked.
        #
        # Targeting a full cycle unconditionally is wrong, and not harmlessly so.
        # The twelve-hour pumped hydro cannot charge for fifteen hours and discharge
        # for twelve inside one day, so its charge level was pushed above its
        # discharge level, the day was rejected as incoherent, and the unit sat idle
        # for all three hundred and sixty-five days of the year while the model
        # reported it as part of the fleet.
        # A store too small to flatten a day is energy limited on every day of the
        # year, and then the balance level is computed and thrown away. Testing that
        # first costs two reductions instead of a twenty-step search, and it is
        # exact rather than a heuristic: if shaving to the day's mean already needs
        # more energy than the store holds, and filling to the mean feeds more than
        # that shaving, then the balance level lies at or below the mean and the
        # energy to flatten the day is at least what shaving to the mean takes.
        # Every candidate the forward view prices is one megawatt, so this is the
        # path that runs whenever the model is valuing a battery rather than
        # dispatching one.
        mean = day.mean(axis=1)
        shave_mean = np.clip(day - mean[:, None], 0.0, power).sum(axis=1)
        fill_mean = np.clip(mean[:, None] - day, 0.0, power).sum(axis=1)
        if bool(np.all(shave_mean >= energy_cap)) and \
                bool(np.all(fill_mean * rte >= shave_mean)):
            level = mean
            limited = np.ones(n_days, dtype=bool)
            target = np.full(n_days, energy_cap)
        else:
            level = _balance_level(day, power, rte)
            flat_out = np.clip(day - level[:, None], 0.0, power).sum(axis=1)
            limited = flat_out > energy_cap
            target = np.where(limited, energy_cap, flat_out)

        if limited.any():
            lo = np.where(limited, _fill_threshold(day, power, target / rte), level)
            charge = np.clip(lo[:, None] - day, 0.0, power)
            hi = np.where(limited, _shave_threshold(day + charge, power, target), level)
        else:
            lo = hi = level
            charge = np.clip(lo[:, None] - day, 0.0, power)
        discharge = np.clip(day + charge - hi[:, None], 0.0, power)

        # The viability test gates BUYING, not selling. A store only charges when the
        # day's spread covers the round trip, so a lull with no cheap hours leaves it
        # empty, which is the behaviour the worst-week chart exists to show. But what
        # it already holds it may always deliver.
        #
        # Gating both was wrong in the one hour that matters. On the hottest day of
        # the drought year the overnight load is high enough that a store cannot
        # charge, so the day failed the test and the store was barred from
        # discharging a reserve it was already carrying. Adding four gigawatts of
        # batteries to this fleet then moved prices enough to fail that test for the
        # incumbent stores, and 1,354 MW that had been covering the evening peak
        # stopped covering it: more storage, a higher peak. What limits discharge is
        # the state of charge, and that is enforced below.
        charged = charge.sum(axis=1)
        delivered = discharge.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            buy = np.where(charged > 0, (price_by_day * charge).sum(axis=1) / charged, 0.0)
            sell = np.where(delivered > 0,
                            (price_by_day * discharge).sum(axis=1) / delivered, 0.0)
        worth_buying = (charged > 0) & (delivered > 0) & (sell > buy / rte + spread)
        charge[~worth_buying] = 0.0
        discharge = np.clip(day + charge - hi[:, None], 0.0, power)

        # The state of charge is the one genuinely sequential part, so it is the
        # only thing done day by day. Each day's schedule is scaled rather than
        # truncated, which keeps it inside the thresholds and so keeps the peak
        # guarantee.
        #
        # The check is HOURLY within the day, not on the day's totals. Charging
        # lands in the trough and discharging on the peak, but a day's trough can
        # fall after its peak on the clock - an evening peak at six followed by a
        # late trough at eleven - and a store balanced across the day as a whole
        # then delivers in the evening energy it will not store until that night.
        # Checking totals cannot see that; checking the running total can. Both
        # scale factors are exact rather than iterated, because scaling one side of
        # the day by a constant moves the running total linearly.
        #
        # Empty at the start of the year, not half full. A store that opens with a
        # free half charge can deliver energy it never stored, and with charging
        # scheduled ahead of discharging inside each day it would do so on day one.
        soc = 0.0
        filled_all = np.cumsum(charge * rte, axis=1)
        drawn_all = np.cumsum(discharge, axis=1)
        excursion = filled_all - drawn_all
        high = excursion.max(axis=1)         # furthest above the day's opening charge
        low = (-excursion).max(axis=1)       # furthest below it
        net = excursion[:, -1]
        scale_c = np.ones(n_days)
        scale_d = np.ones(n_days)
        for d in range(n_days):
            # Most days do not bind, and testing that with two scalars rather than
            # two array reductions is the difference between a dispatched year at
            # 138 milliseconds and one at 50.
            if high[d] <= energy_cap - soc and low[d] <= soc:
                soc += net[d]
                continue
            fa = filled_all[d]
            da = drawn_all[d]
            if fa[-1] > 0:
                room = energy_cap - soc + da
                f = np.min(np.where(fa > 0, room / np.maximum(fa, 1e-12), 1.0))
                scale_c[d] = float(np.clip(f, 0.0, 1.0))
                fa = fa * scale_c[d]
            if da[-1] > 0:
                have = soc + fa
                f = np.min(np.where(da > 0, have / np.maximum(da, 1e-12), 1.0))
                scale_d[d] = float(np.clip(f, 0.0, 1.0))
            soc += float(fa[-1] - da[-1] * scale_d[d])
        charge *= scale_c[:, None]
        discharge *= scale_d[:, None]

        flat_charge = charge.reshape(-1)
        flat_discharge = discharge.reshape(-1)
        net_load[:usable] += flat_charge - flat_discharge
        working[:usable] += flat_charge - flat_discharge
        combined = np.zeros(n)
        combined[:usable] = flat_discharge - flat_charge
        for m in members:
            per_unit[m.unit] = combined * (m.available_mw / power)
    return net_load, per_unit


def storage_schedule(units: list[Unit], price: np.ndarray, residual_mw: np.ndarray,
                     settings: Settings) -> dict[str, np.ndarray]:
    """Schedule storage against a given price series, per unit.

    The seam the forward view values a candidate battery through. It is the same
    scheduler the dispatch uses, deliberately: a candidate valued by a cleaner rule
    than the one that will govern it once built would be valued at a spread it can
    never realise, and the heuristic's known cost would be hidden from the
    investment decision instead of being carried into it.

    The residual is required, not optional. Storage here is scheduled against
    quantities rather than against a ranking of prices, so a caller that has a price
    series and no residual is a caller that cannot value a store: what a battery is
    worth depends on the shape of the load it is shaving, not only on the prices
    that shape produced.

    The price is taken as given, which is what valuing a marginal addition to an
    existing market means: the candidate is a price taker, and the market it would
    join is the one the dispatch already produced.

    Positive is discharge, negative is charge, so ``sum(schedule * price)`` is
    revenue net of the cost of the energy bought.
    """
    return _run_storage(units, lambda _level: price, residual_mw, settings)[1]


def _apply_ladder(residual: np.ndarray, stack_price: np.ndarray,
                  firm_capacity: float, settings: Settings
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The scarcity ladder, call-hour budgets and the administered cap.

    Sequential in time because both the tier budgets and the rolling threshold
    depend on what has already happened this year.
    """
    mpc = settings.market["market_price_cap_per_mwh"]
    apc = settings.market["administered_price_cap_per_mwh"]
    threshold = settings.hourly_price_threshold
    window = int(settings.market["cumulative_price_window_hours"])

    price = stack_price.copy()
    unserved = np.zeros_like(residual)
    ladder_mw = np.zeros_like(residual)
    administered = np.zeros(residual.shape, dtype=bool)

    tiers = list(settings.dsr)
    remaining_hours = [t.call_hours for t in tiers]
    short = residual - firm_capacity

    # Fast path: if no hour is short and the rolling sum can never reach the
    # threshold, the sequential pass has nothing to do.
    if short.max() <= 0:
        # Trailing sums over min(h + 1, window) hours, matching the sequential loop
        # exactly. A full-window convolution tests only whole 168-hour windows, so a
        # breach inside the year's first 167 hours would be skipped here and caught
        # by the loop, which is a fast path that changes the answer.
        csum = np.concatenate(([0.0], np.cumsum(price)))
        idx = np.arange(len(price))
        starts = np.maximum(0, idx + 1 - window)
        roll = csum[idx + 1] - csum[starts]
        if roll.size == 0 or roll.max() < threshold:
            return price, unserved, ladder_mw, administered

    running = 0.0
    for h in range(len(residual)):
        if short[h] > 0:
            unmet = short[h]
            hour_price = price[h]
            for i, tier in enumerate(tiers):
                if unmet <= 0:
                    break
                if remaining_hours[i] <= 0:
                    continue
                used = min(unmet, tier.capacity_mw)
                if used <= 0:
                    continue
                unmet -= used
                ladder_mw[h] += used
                remaining_hours[i] -= 1
                hour_price = tier.price_per_mwh
            if unmet > 0:
                unserved[h] = unmet
                hour_price = mpc
            price[h] = hour_price
        # Incremental rolling sum: O(1) an hour rather than O(window).
        running += price[h]
        if h >= window:
            running -= price[h - window]
        if running >= threshold:
            capped = min(price[h], apc)
            price[h] = capped
            administered[h] = True
    return price, unserved, ladder_mw, administered


def dispatch_year(settings: Settings, year: int, demand_mw: np.ndarray,
                  wind_cf: np.ndarray, solar_cf: np.ndarray,
                  rooftop_cf: np.ndarray | None = None) -> DispatchResult:
    """Dispatch and price one year."""
    units = _in_service(settings, year)
    floor = settings.dispatch["must_run_offer_per_mwh"]

    # Profiles are per UNIT, not per technology. While the fleet held one wind row
    # and one solar row the two were the same thing; the moment a second wind farm
    # is built they are not, and giving each row the whole technology's output would
    # let every wind unit claim the fleet's entire generation, curtail the fleet's
    # entire surplus, and be paid for both.
    cf_of = {"wind": wind_cf, "solar": solar_cf,
             "rooftop": rooftop_cf if rooftop_cf is not None else solar_cf}
    unit_profile = {u.unit: cf_of[u.technology] * u.capacity_mw
                    for u in units if u.technology in cf_of}
    rooftop = sum((unit_profile[u.unit] for u in units if u.technology == "rooftop"),
                  start=np.zeros_like(demand_mw))
    vre_units = [u for u in units
                 if u.technology in ("wind", "solar") and u.capacity_mw > 0]
    vre_mw = sum((unit_profile[u.unit] for u in vre_units),
                 start=np.zeros_like(demand_mw))
    residual = demand_mw - rooftop - vre_mw

    # Curtailment merit order for surplus hours. Rooftop is not in it: it sits behind
    # the meter, does not bid, and is netted off demand. Utility wind and solar do
    # bid, and their offers differ, so the surplus price varies with how deep the
    # surplus is instead of being one constant.
    labelled_tiers = [(u.unit, u.srmc_per_mwh, unit_profile[u.unit]) for u in vre_units]
    market_floor = settings.market["minimum_price_per_mwh"]
    # The must-run band is the last thing to withdraw, so it is the final tier of
    # the price ladder but never a source of curtailed VRE energy.
    must_run_total = float(sum(min(u.must_run_mw, u.available_mw)
                               for u in units if u.must_run_mw > 0))
    curtail_tiers = [(offer, mw) for _n, offer, mw in labelled_tiers]
    curtail_tiers = curtail_tiers + [(floor, np.full_like(residual, must_run_total))]

    # Energy-limited hydro is scheduled against its budget, not offered into the
    # stack and hoped for. Every hydro row is scheduled on its own budget: pricing
    # them all off the first row's number was one more way the budget went unspent.
    # Only hydro rows that declare an energy budget are scheduled against one. A row
    # without a budget is not energy limited, so it belongs in the stack like any
    # other plant. Excluding every hydro row from the stack and then skipping the
    # unbudgeted ones made such a row disappear: never scheduled, never offered,
    # never generating.
    hydro_units = [u for u in units
                   if u.technology == "hydro" and u.energy_budget_gwh]
    scheduled = {u.unit for u in hydro_units}
    thermal_only = [u for u in units if u.unit not in scheduled]
    p_nh, c_nh, _ = _offer_stack(thermal_only, settings)
    hydro_gen: dict[str, np.ndarray] = {}
    hydro_total = np.zeros_like(residual)
    water = 0.0
    for u in hydro_units:
        schedule, unit_water = _hydro_schedule(
            residual - hydro_total, u.available_mw,
            u.energy_budget_gwh * 1000.0, p_nh, c_nh, floor)
        hydro_gen[u.unit] = schedule
        hydro_total = hydro_total + schedule
        water = unit_water if water == 0.0 else water

    residual = residual - hydro_total
    prices, caps, labels = _offer_stack(thermal_only, settings)

    def price_of(level: np.ndarray) -> np.ndarray:
        return _price_from_stack(
            level, prices, caps, floor,
            _curtailment_price(np.clip(must_run_total - level, 0.0, None),
                               curtail_tiers, market_floor),
            must_run_total)

    # One pass. Storage is scheduled by shaving quantities off the residual, and the
    # residual does not depend on the price, so there is no fixed point left to
    # chase. The loop that used to be here existed because the schedule was chosen by
    # ranking a price the schedule then moved; on a fleet with four gigawatts of
    # batteries added it entered a two-cycle and reported convergence as false.
    storage_net, storage_gen = _run_storage(units, price_of, residual, settings)

    net_residual = residual + storage_net
    stack_price = _price_from_stack(
        net_residual, prices, caps, floor,
        _curtailment_price(np.clip(must_run_total - net_residual, 0.0, None),
                           curtail_tiers, market_floor),
        must_run_total)
    firm_capacity = float(caps.sum())
    # The market price floor is a rule, not a decoration. It is applied BEFORE the
    # ladder so the cumulative threshold sums the series the market would actually
    # settle; applying it afterwards would test the threshold against prices that
    # never existed.
    stack_price = np.maximum(stack_price, settings.market["minimum_price_per_mwh"])
    price, unserved, ladder_mw, administered = _apply_ladder(
        net_residual, stack_price, firm_capacity, settings)

    # Curtailment lifts the residual back to the must-run floor, so the plant in the
    # stack is dispatched against the POST-curtailment residual. Attributing it
    # against the pre-curtailment residual leaves the must-run band showing zero
    # output in exactly the hours it is the thing keeping the system balanced, and
    # the year then fails to balance by the size of that band.
    cut = _curtailment(np.clip(must_run_total - net_residual, 0.0, None),
                       labelled_tiers)
    cut_total = sum(cut.values()) if cut else np.zeros_like(net_residual)
    dispatch_residual = net_residual + cut_total
    generation = _unit_generation(dispatch_residual, prices, caps, labels)
    for name, series in storage_gen.items():
        generation[name] = series
    for name, series in hydro_gen.items():
        generation[name] = series

    # The renewable fleet is reported net of curtailment. It was omitted entirely,
    # so nothing added up to what the system actually served and every revenue
    # figure for wind and solar was silently absent.
    for u in vre_units:
        generation[u.unit] = unit_profile[u.unit] - cut.get(u.unit, 0.0)
    for u in units:
        if u.technology == "rooftop":
            generation[u.unit] = unit_profile[u.unit]

    return DispatchResult(
        price=price,
        residual_mw=net_residual,
        demand_mw=demand_mw,
        operational_demand_mw=demand_mw - rooftop,
        generation_mwh=generation,
        unserved_mwh=unserved,
        ladder_mw=ladder_mw,
        administered_hours=administered,
        firm_capacity_mw=firm_capacity,
        water_value_per_mwh=water,
    )


def _unit_generation(residual: np.ndarray, prices: np.ndarray, caps: np.ndarray,
                     labels: list[str]) -> dict[str, np.ndarray]:
    """Output per unit, sharing a partly loaded price band pro rata to capacity.

    The tie-break matters: per-plant revenue, and the energy margin a cap writer
    nets off its premium, both depend on how a marginal band is split.
    """
    out: dict[str, np.ndarray] = {}
    need = np.clip(residual, 0.0, None)
    cum_before = 0.0
    i = 0
    while i < len(prices):
        j = i
        while j + 1 < len(prices) and prices[j + 1] == prices[i]:
            j += 1
        band = caps[i:j + 1]
        band_cap = float(band.sum())
        served = np.clip(need - cum_before, 0.0, band_cap)
        for k in range(i, j + 1):
            share = caps[k] / band_cap if band_cap else 0.0
            out[labels[k]] = out.get(labels[k], 0.0) + served * share
        cum_before += band_cap
        i = j + 1
    return out
