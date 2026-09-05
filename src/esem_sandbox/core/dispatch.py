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

from ..config import Settings, Unit

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
    storage_passes: int = 0
    storage_converged: bool = False

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


def _run_storage(units: list[Unit], provisional_price: np.ndarray,
                 settings: Settings) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Greedy daily cycling against a provisional price.

    Each unit charges in its day's cheapest hours and discharges into its
    dearest, keeps state of charge across days, and only cycles when the spread
    covers the round trip. A lull with no cheap hours therefore leaves it empty,
    which is the behaviour the worst-week chart is there to show.

    The per-day ranking is vectorised over all days at once and only the state
    of charge recursion stays sequential, because it genuinely is. Doing the
    ranking day by day made this routine three quarters of a dispatch.
    """
    spread = settings.dispatch["storage_spread_per_mwh"]
    n = len(provisional_price)
    n_days = n // HOURS_PER_DAY
    net_load = np.zeros(n)
    per_unit: dict[str, np.ndarray] = {}
    if n_days == 0:
        return net_load, per_unit

    by_day = provisional_price[:n_days * HOURS_PER_DAY].reshape(n_days, HOURS_PER_DAY)

    for u in units:
        if u.technology not in _STORAGE or not u.duration_h:
            continue
        power = u.available_mw
        energy_cap = power * float(u.duration_h)
        rte = float(u.round_trip_efficiency or 0.85)
        # Capped at half a day so charge and discharge windows cannot overlap.
        slots = max(1, min(HOURS_PER_DAY // 2, int(round(float(u.duration_h)))))
        assert 2 * slots <= HOURS_PER_DAY

        # Rank every day once and take from both ends of the SAME ordering. Two
        # independent sorts, one of price and one of minus price, do not partition a
        # day when prices tie, and a curtailment merit order makes ties common: a
        # day can hold only a handful of distinct prices. The store was then
        # scheduled to charge and discharge in the same hour on most days.
        order = np.argsort(by_day, axis=1, kind="stable")
        asc = order[:, :slots]
        desc = order[:, -slots:]
        rows = np.arange(n_days)[:, None]
        disch_mean = by_day[rows, desc].mean(axis=1)
        chg_mean = by_day[rows, asc].mean(axis=1)
        viable = disch_mean > chg_mean / rte + spread

        gen = np.zeros(n)
        soc = energy_cap * 0.5
        base = np.arange(n_days) * HOURS_PER_DAY
        disch_idx = desc + base[:, None]
        chg_idx = asc + base[:, None]

        for d in range(n_days):
            if not viable[d]:
                continue
            can_discharge = min(soc, power * slots)
            if can_discharge > 0:
                each = can_discharge / slots
                idx = disch_idx[d]
                gen[idx] += each
                net_load[idx] -= each
                soc -= can_discharge
            room = energy_cap - soc
            can_charge = min(room / rte, power * slots)
            if can_charge > 0:
                each = can_charge / slots
                idx = chg_idx[d]
                gen[idx] -= each
                net_load[idx] += each
                soc += can_charge * rte
        per_unit[u.unit] = gen
    return net_load, per_unit


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

    def cap_of(tech: str) -> float:
        return sum(u.capacity_mw for u in units if u.technology == tech)

    rooftop = (rooftop_cf if rooftop_cf is not None else solar_cf) * cap_of("rooftop")
    wind_mw = wind_cf * cap_of("wind")
    solar_mw = solar_cf * cap_of("solar")
    residual = demand_mw - rooftop - wind_mw - solar_mw

    # Curtailment merit order for surplus hours. Rooftop is not in it: it sits behind
    # the meter, does not bid, and is netted off demand. Utility wind and solar do
    # bid, and their offers differ, so the surplus price varies with how deep the
    # surplus is instead of being one constant.
    profile = {"wind": wind_mw, "solar": solar_mw}
    vre_units = [u for u in units if u.technology in profile and cap_of(u.technology) > 0]
    labelled_tiers = [(u.unit, u.srmc_per_mwh, profile[u.technology]) for u in vre_units]
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

    surplus_now = _curtailment_price(np.clip(must_run_total - residual, 0.0, None),
                                     curtail_tiers, market_floor)
    provisional = _price_from_stack(residual, prices, caps, floor, surplus_now,
                                    must_run_total)
    storage_net = np.zeros_like(residual)
    storage_gen: dict[str, np.ndarray] = {}
    passes = 0
    converged = False

    # Convergence is tested on the peak-block price, which is what the tolerance is
    # named for and what storage is there to move. It previously tested the annual
    # mean, a different and far less sensitive quantity, and because the comparison
    # needs a previous pass it could only ever fire on the final iteration, so the
    # tolerance changed nothing at any value.
    peak_start, peak_end = settings.blocks()["peak"]
    hod = np.arange(len(residual)) % HOURS_PER_DAY
    peak_mask = ((hod >= peak_start) | (hod < peak_end)) if peak_start > peak_end \
        else ((hod >= peak_start) & (hod < peak_end))

    peak_before = None
    previous = None
    for passes in range(1, int(settings.dispatch["max_storage_passes"]) + 1):
        storage_net, storage_gen = _run_storage(units, provisional, settings)
        net_residual = residual + storage_net
        provisional = _price_from_stack(
            net_residual, prices, caps, floor,
            _curtailment_price(np.clip(must_run_total - net_residual, 0.0, None),
                               curtail_tiers, market_floor),
            must_run_total)
        # Damping. Storage schedules against a price and its schedule then moves
        # that price, which is a cobweb: undamped it oscillates in a two-cycle
        # between roughly $97 and $110 on the peak block and never settles, whatever
        # ceiling it is given. Averaging successive iterates is what makes the
        # tolerance meaningful rather than decorative.
        if previous is not None:
            provisional = 0.5 * (provisional + previous)
        previous = provisional
        peak = float(provisional[peak_mask].mean())
        if peak_before is not None and abs(peak - peak_before) < settings.dispatch[
                "storage_price_tolerance"]:
            converged = True
            break
        peak_before = peak

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
        generation[u.unit] = profile[u.technology] - cut.get(u.unit, 0.0)
    roof_cap = cap_of("rooftop")
    if roof_cap > 0:
        roof_unit = next(u for u in units if u.technology == "rooftop")
        generation[roof_unit.unit] = rooftop

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
        storage_passes=passes,
        storage_converged=converged,
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
