"""Reports: block prices, duration curves, revenue and the calibration check."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import Settings

HOURS_PER_DAY = 24


def block_mask(settings: Settings, name: str, n_hours: int) -> np.ndarray:
    """Hours belonging to a time-of-day block. Blocks may wrap past midnight."""
    start, end = settings.blocks()[name]
    hod = np.arange(n_hours) % HOURS_PER_DAY
    return (hod >= start) | (hod < end) if start > end else (hod >= start) & (hod < end)


def block_prices(settings: Settings, price: np.ndarray) -> dict[str, float]:
    return {name: float(price[block_mask(settings, name, len(price))].mean())
            for name in settings.blocks()}


# Day-of-year on which each quarter starts, for a 365-day (non-leap) year.
_QUARTER_STARTS = (0, 31 + 28 + 31, 31 + 28 + 31 + 30 + 31 + 30,
                   31 + 28 + 31 + 30 + 31 + 30 + 31 + 31 + 30)


def quarter_of_hour(n_hours: int) -> np.ndarray:
    """Calendar quarter index 0..3 for each hour of a 365-day year.

    Uses real month lengths. Deriving month starts from an average 30.44-day month
    misplaces them by up to two days, so days at the end of March, June and
    September fall on the wrong side of a quarter boundary and quarterly contracts
    would settle against the wrong quarter's prices.
    """
    day = np.arange(n_hours) // HOURS_PER_DAY
    return np.searchsorted(np.array(_QUARTER_STARTS), day, side="right") - 1


def duration_curve(price: np.ndarray, points: int = 0) -> np.ndarray:
    """Prices sorted high to low. Full length by default.

    Sampling this to a fixed number of points and then integrating over the
    samples is how a single scarce interval comes to be paid as if it lasted for
    tens of hours, so anything that settles money uses the full series.
    """
    ordered = np.sort(price)[::-1]
    if points and points < len(ordered):
        idx = np.linspace(0, len(ordered) - 1, points).astype(int)
        return ordered[idx]
    return ordered


def unit_revenue(price: np.ndarray, generation_mwh: dict[str, np.ndarray],
                 settings: Settings) -> dict[str, dict[str, float]]:
    """Energy revenue, cost and net rent per unit, in dollars for the year."""
    srmc = {u.unit: u.srmc_per_mwh for u in settings.fleet}
    # Rooftop sits behind the meter. It never offers into the pool and is never
    # settled at the spot price; it reduces the bill of the household it sits on.
    # Booking it spot revenue credited it with $55m across five shape-years for
    # energy it never sold.
    behind_the_meter = {u.unit for u in settings.fleet if u.technology == "rooftop"}
    out: dict[str, dict[str, float]] = {}
    for name, gen in generation_mwh.items():
        if name in behind_the_meter:
            continue
        energy = float(np.sum(gen))
        revenue = float(np.sum(gen * price))
        # Fuel is burnt only when generating, and only by plant with a positive
        # short run cost. A curtailment offer is negative and is an opportunity
        # cost, not a fuel bill; a store's net energy is negative and would
        # otherwise book its variable cost as a credit.
        run_cost = max(srmc.get(name, 0.0), 0.0)
        cost = float(np.sum(np.clip(gen, 0.0, None))) * run_cost
        out[name] = {
            "energy_mwh": energy,
            "revenue": revenue,
            "fuel_and_vom": cost,
            "net_rent": revenue - cost,
        }
    return out


@dataclass
class Calibration:
    """A reported check, never a tuning target.

    If the ladder alone leaves the tail implausibly thin against public
    statistics, that is a finding to put on a slide, not a knob to turn.
    """

    days_with_300_hour: float
    hours_at_or_above_300: int
    mean_excess_over_300: float
    hours_at_voll: int
    administered_hours: int
    mean_price: float
    unserved_gwh: float
    unserved_fraction: float

    def lines(self) -> list[str]:
        return [
            f"mean price                  ${self.mean_price:,.2f}/MWh",
            f"days holding a $300 hour    {self.days_with_300_hour:.1%}",
            f"hours at or above $300      {self.hours_at_or_above_300}",
            f"mean excess over $300       ${self.mean_excess_over_300:,.2f}/MWh"
            f"  (averaged over every hour of the year, not only the dear ones)",
            f"hours at the price cap      {self.hours_at_voll}",
            f"administered hours          {self.administered_hours}",
            f"unserved energy             {self.unserved_gwh:.3f} GWh "
            f"({self.unserved_fraction:.5%} of demand)",
        ]


def calibration(price: np.ndarray, unserved_mwh: np.ndarray,
                administered: np.ndarray, operational_demand_mw: np.ndarray,
                settings: Settings) -> Calibration:
    """The calibration statistics, in days rather than hours where it matters.

    A single hot afternoon puts several hours above $300 at once, so counting
    hours overstates how often the market is tight. Days is the honest unit.
    """
    mpc = settings.market["market_price_cap_per_mwh"]
    n_days = len(price) // HOURS_PER_DAY
    by_day = price[:n_days * HOURS_PER_DAY].reshape(n_days, HOURS_PER_DAY)
    excess = np.clip(price - 300.0, 0.0, None)
    demand_total = float(operational_demand_mw.sum())
    return Calibration(
        days_with_300_hour=float((by_day.max(axis=1) >= 300.0).mean()),
        hours_at_or_above_300=int((price >= 300.0).sum()),
        mean_excess_over_300=float(excess.mean()),
        hours_at_voll=int((price >= mpc).sum()),
        administered_hours=int(administered.sum()),
        mean_price=float(price.mean()),
        unserved_gwh=float(unserved_mwh.sum()) / 1000.0,
        unserved_fraction=(float(unserved_mwh.sum()) / demand_total
                           if demand_total else 0.0),
    )
