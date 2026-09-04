"""Locating the worst window of a year.

The drought is found, not authored. Given the fleet in hand, the worst
contiguous run of days is the one with the highest residual demand net of what
the fleet can cover, clamped to three to seven days. That window is telemetry:
it draws the worst-week chart and sets the days parameter of a storage unit's
firm contribution.

Because it is measured after dispatch it cannot move prices, so re-selecting it
each tick is safe.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

HOURS_PER_DAY = 24
MIN_DAYS = 3
MAX_DAYS = 7


@dataclass(frozen=True)
class Window:
    start_day: int
    days: int
    shortfall_mwh: float
    peak_residual_mw: float

    @property
    def hours(self) -> slice:
        return slice(self.start_day * HOURS_PER_DAY,
                     (self.start_day + self.days) * HOURS_PER_DAY)


def locate_worst_window(residual_mw: np.ndarray, firm_capacity_mw: float,
                        min_days: int = MIN_DAYS, max_days: int = MAX_DAYS) -> Window:
    """The contiguous run of days with the greatest energy above firm capacity.

    Falls back to the days around the single highest residual hour when nothing
    exceeds firm capacity, so a comfortable year still has a window to draw.
    """
    n_days = len(residual_mw) // HOURS_PER_DAY
    daily_short = np.array([
        np.clip(residual_mw[d * HOURS_PER_DAY:(d + 1) * HOURS_PER_DAY]
                - firm_capacity_mw, 0.0, None).sum()
        for d in range(n_days)
    ])
    best = None
    for days in range(min_days, max_days + 1):
        if days > n_days:
            break
        sums = np.convolve(daily_short, np.ones(days), mode="valid")
        i = int(np.argmax(sums))
        if best is None or sums[i] > best[2]:
            best = (i, days, float(sums[i]))
    start, days, short = best

    if short <= 0.0:
        peak_hour = int(np.argmax(residual_mw))
        peak_day = peak_hour // HOURS_PER_DAY
        days = min_days
        start = max(0, min(peak_day - days // 2, n_days - days))
        short = 0.0

    sel = residual_mw[start * HOURS_PER_DAY:(start + days) * HOURS_PER_DAY]
    return Window(start_day=start, days=days, shortfall_mwh=short,
                  peak_residual_mw=float(sel.max()))
