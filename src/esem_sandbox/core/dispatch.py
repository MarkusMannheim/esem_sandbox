"""Hourly dispatch, pricing and the scarcity ladder.

One region, 8,760 hourly steps. The price each hour is the offer of the unit
that meets residual demand on the cumulative available-capacity stack. Above
the last physical unit the price climbs the demand-response ladder, then the
reliability response tranche, then the value of lost load, and the administered
cap applies once the rolling cumulative price threshold is breached.

Energy-limited plant offers at opportunity cost rather than being placed with
perfect foresight. Without that the duration curve has two steps and cap
contracts pay nothing in a normal year.
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
    generation_mwh: dict[str, np.ndarray] = field(default_factory=dict)
    unserved_mwh: np.ndarray = field(default_factory=lambda: np.zeros(0))
    ladder_mw: np.ndarray = field(default_factory=lambda: np.zeros(0))
    administered_hours: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    water_value_per_mwh: float = 0.0
    storage_passes: int = 0

    @property
    def total_unserved_gwh(self) -> float:
        return float(self.unserved_mwh.sum()) / 1000.0

    @property
    def total_demand_gwh(self) -> float:
        return float(self.demand_mw.sum()) / 1000.0

    @property
    def unserved_fraction(self) -> float:
        total = self.demand_mw.sum()
        return float(self.unserved_mwh.sum() / total) if total else 0.0


def _in_service(settings: Settings, year: int) -> list[Unit]:
    return [u for u in settings.fleet if u.in_service(year)]


def _offer_stack(units: list[Unit], settings: Settings,
                 extra: dict[str, float] | None = None
                 ) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Offer prices, capacities and labels for everything that sets a price.

    A coal unit is split in two: its must-run floor offers at the floor price so
    the solar block can collapse below zero, and the rest offers at its own short
    run cost.
    """
    floor = settings.dispatch["vre_offer_per_mwh"]
    prices: list[float] = []
    caps: list[float] = []
    labels: list[str] = []
    for u in units:
        if u.technology in _STORAGE or u.technology in ("wind", "solar", "rooftop"):
            continue
        available = u.available_mw
        if u.technology == "hydro":
            price = (extra or {}).get("water_value", 0.0)
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
                      caps: np.ndarray, floor: float) -> np.ndarray:
    """Marginal offer meeting the residual, or the floor when nothing is needed."""
    cum = np.cumsum(caps)
    idx = np.searchsorted(cum, np.clip(residual, 0.0, None), side="left")
    out = np.full(residual.shape, prices[-1] if len(prices) else floor)
    inside = idx < len(prices)
    out[inside] = prices[idx[inside]]
    out[residual <= 0.0] = floor
    return out


def _water_value(residual: np.ndarray, hydro_mw: float, budget_mwh: float,
                 prices: np.ndarray, caps: np.ndarray, floor: float) -> float:
    """The offer that spends hydro's annual energy in the dearest hours.

    Prices the year without hydro, then runs hydro down that merit order until
    the budget is gone. The marginal hour's price is the water value: the cost of
    the thermal unit hydro displaces at that point.
    """
    if hydro_mw <= 0 or not budget_mwh:
        return 0.0
    thermal_price = _price_from_stack(residual, prices, caps, floor)
    order = np.argsort(-thermal_price, kind="stable")
    full_hours = int(budget_mwh // hydro_mw)
    if full_hours <= 0:
        return float(thermal_price[order[0]])
    full_hours = min(full_hours, len(order) - 1)
    return float(thermal_price[order[full_hours]])


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
        slots = max(1, min(HOURS_PER_DAY // 2, int(round(float(u.duration_h)))))

        # Rank every day at once.
        desc = np.argsort(-by_day, axis=1, kind="stable")[:, :slots]
        asc = np.argsort(by_day, axis=1, kind="stable")[:, :slots]
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
        roll = np.convolve(price, np.ones(window), mode="valid")
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
            running -= price[h] - capped
            price[h] = capped
            administered[h] = True
    return price, unserved, ladder_mw, administered


def dispatch_year(settings: Settings, year: int, demand_mw: np.ndarray,
                  wind_cf: np.ndarray, solar_cf: np.ndarray,
                  rooftop_cf: np.ndarray | None = None) -> DispatchResult:
    """Dispatch and price one year."""
    units = _in_service(settings, year)
    floor = settings.dispatch["vre_offer_per_mwh"]

    def cap_of(tech: str) -> float:
        return sum(u.capacity_mw for u in units if u.technology == tech)

    rooftop = (rooftop_cf if rooftop_cf is not None else solar_cf) * cap_of("rooftop")
    vre = wind_cf * cap_of("wind") + solar_cf * cap_of("solar")
    residual = demand_mw - rooftop - vre

    hydro = next((u for u in units if u.technology == "hydro"), None)
    prices0, caps0, _ = _offer_stack(units, settings, {"water_value": 0.0})
    water = 0.0
    if hydro is not None and hydro.energy_budget_gwh:
        stack_no_hydro = [u for u in units if u.technology != "hydro"]
        p_nh, c_nh, _ = _offer_stack(stack_no_hydro, settings)
        water = _water_value(residual, hydro.available_mw,
                             hydro.energy_budget_gwh * 1000.0, p_nh, c_nh, floor)

    prices, caps, labels = _offer_stack(units, settings, {"water_value": water})

    provisional = _price_from_stack(residual, prices, caps, floor)
    storage_net = np.zeros_like(residual)
    storage_gen: dict[str, np.ndarray] = {}
    passes = 0
    peak_before = None
    for passes in range(1, int(settings.dispatch["max_storage_passes"]) + 1):
        storage_net, storage_gen = _run_storage(units, provisional, settings)
        net_residual = residual + storage_net
        provisional = _price_from_stack(net_residual, prices, caps, floor)
        peak = float(provisional.mean())
        if peak_before is not None and abs(peak - peak_before) < settings.dispatch[
                "storage_price_tolerance"]:
            break
        peak_before = peak

    net_residual = residual + storage_net
    stack_price = _price_from_stack(net_residual, prices, caps, floor)
    firm_capacity = float(caps.sum())
    price, unserved, ladder_mw, administered = _apply_ladder(
        net_residual, stack_price, firm_capacity, settings)
    # The market price floor is a rule, not a decoration: enforce it on the settled
    # series rather than declaring it in settings and never applying it.
    price = np.maximum(price, settings.market["minimum_price_per_mwh"])

    generation = _unit_generation(net_residual, prices, caps, labels)
    for name, series in storage_gen.items():
        generation[name] = series

    return DispatchResult(
        price=price,
        residual_mw=net_residual,
        demand_mw=demand_mw,
        generation_mwh=generation,
        unserved_mwh=unserved,
        ladder_mw=ladder_mw,
        administered_hours=administered,
        water_value_per_mwh=water,
        storage_passes=passes,
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
