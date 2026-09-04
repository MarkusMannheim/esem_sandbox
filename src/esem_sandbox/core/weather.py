"""Synthetic hourly weather shapes.

Five shape-years of demand, solar and wind, generated from one seed so the
repository needs no downloaded traces. The shapes are demand-neutral: peak
uncertainty enters later as a peak-weighted multiplier, never here, so that
authoring a hot year and stacking a peak band on top cannot double count.

Each year is exactly 8,760 hours. Leap years are not represented; a generator
that sometimes emitted 8,784 would silently misalign every downstream array.
"""

from __future__ import annotations

import numpy as np

HOURS_PER_YEAR = 8760
HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365


def _ar1(rng: np.random.Generator, n: int, rho: float, sigma: float) -> np.ndarray:
    """A stationary first-order autoregressive series with zero mean."""
    noise = rng.normal(0.0, sigma, n)
    out = np.empty(n)
    out[0] = noise[0] / np.sqrt(1.0 - rho**2)
    for i in range(1, n):
        out[i] = rho * out[i - 1] + noise[i]
    return out


def _diurnal_demand() -> np.ndarray:
    """One day of demand shape: an overnight trough, a morning shoulder and an
    evening peak. Normalised to mean 1."""
    hod = np.arange(HOURS_PER_DAY)
    shape = (
        1.0
        + 0.16 * np.exp(-0.5 * ((hod - 8.0) / 2.0) ** 2)
        + 0.42 * np.exp(-0.5 * ((hod - 18.0) / 2.2) ** 2)
        - 0.22 * np.exp(-0.5 * ((hod - 3.5) / 3.0) ** 2)
    )
    return shape / shape.mean()


def _seasonal_demand(day: np.ndarray) -> np.ndarray:
    """Summer-peaking with a secondary winter peak, southern hemisphere."""
    summer = np.cos(2.0 * np.pi * day / DAYS_PER_YEAR)
    winter = np.cos(2.0 * np.pi * (day - 182.0) / DAYS_PER_YEAR)
    return 1.0 + 0.16 * summer + 0.07 * winter


def generate_year(
    rng: np.random.Generator,
    *,
    heat_windows: int = 1,
    wind_lull: bool = False,
    lull_on_heat: bool = False,
) -> dict[str, np.ndarray]:
    """One shape-year.

    ``heat_windows`` multi-day hot spells lift demand. ``wind_lull`` inserts a
    multi-day low-wind spell; ``lull_on_heat`` places it over the first heat
    window, which is the combination that empties storage.
    """
    hours = np.arange(HOURS_PER_YEAR)
    day = hours // HOURS_PER_DAY
    hod = hours % HOURS_PER_DAY

    demand = _seasonal_demand(day) * _diurnal_demand()[hod]
    demand *= 1.0 + _ar1(rng, HOURS_PER_YEAR, 0.94, 0.010)

    # Heat windows: 3 to 5 consecutive days, in the summer halves of the year.
    heat_starts: list[int] = []
    for _ in range(heat_windows):
        start_day = int(rng.choice(np.r_[0:55, 330:363]))
        length = int(rng.integers(3, 6))
        heat_starts.append(start_day)
        sel = np.isin(day, np.arange(start_day, start_day + length) % DAYS_PER_YEAR)
        # The lift is concentrated in the afternoon and evening.
        lift = 0.30 * np.exp(-0.5 * ((hod - 17.0) / 4.0) ** 2)
        demand[sel] *= 1.0 + lift[sel]

    # Solar: clear-sky times a cloud factor.
    daylight = np.clip(np.sin(np.pi * (hod - 6.0) / 12.0), 0.0, None)
    season_sun = 1.0 + 0.30 * np.cos(2.0 * np.pi * day / DAYS_PER_YEAR)
    cloud = np.clip(0.78 + _ar1(rng, HOURS_PER_YEAR, 0.90, 0.10), 0.05, 1.0)
    solar_cf = np.clip(daylight * season_sun * cloud * 1.02, 0.0, 1.0)

    # Wind: a logistic transform of an autoregressive series.
    latent = (
        _ar1(rng, HOURS_PER_YEAR, 0.965, 0.30)
        + 0.55 * np.cos(2.0 * np.pi * (day - 250.0) / DAYS_PER_YEAR)
        - 0.55
    )
    wind_cf = np.clip(1.0 / (1.0 + np.exp(-1.35 * latent)) * 0.92, 0.0, 1.0)

    if wind_lull:
        start_day = heat_starts[0] if (lull_on_heat and heat_starts) else int(
            rng.integers(0, DAYS_PER_YEAR - 6)
        )
        length = int(rng.integers(4, 7))
        sel = np.isin(day, np.arange(start_day, start_day + length) % DAYS_PER_YEAR)
        wind_cf[sel] *= 0.10

    return {
        "demand_shape": demand / demand.mean(),
        "solar_cf": solar_cf,
        "wind_cf": wind_cf,
    }


def generate_bundle(seed: int, shape_years: int = 5) -> dict[str, np.ndarray]:
    """The packaged bundle: ``shape_years`` years stacked, deterministic in ``seed``.

    Year 0 is mild. Years 2 and 4 carry a wind lull, and in year 4 the lull sits
    on the heat window: that is the year in which storage can be emptied and
    unserved energy can appear.
    """
    rng = np.random.default_rng(seed)
    plan = [
        dict(heat_windows=1, wind_lull=False, lull_on_heat=False),
        dict(heat_windows=2, wind_lull=False, lull_on_heat=False),
        dict(heat_windows=1, wind_lull=True, lull_on_heat=False),
        dict(heat_windows=2, wind_lull=False, lull_on_heat=False),
        dict(heat_windows=2, wind_lull=True, lull_on_heat=True),
    ]
    years = [generate_year(rng, **plan[i % len(plan)]) for i in range(shape_years)]
    return {
        key: np.stack([y[key] for y in years]).astype(np.float64)
        for key in ("demand_shape", "solar_cf", "wind_cf")
    }
