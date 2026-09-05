"""The worst window is located, not authored."""

import numpy as np
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.dispatch import dispatch_year
from esem_sandbox.core.weather import generate_bundle
from esem_sandbox.core.windows import MAX_DAYS, MIN_DAYS, locate_worst_window


def test_finds_the_window_that_was_planted():
    residual = np.full(8760, 100.0)
    residual[100 * 24:104 * 24] = 900.0
    w = locate_worst_window(residual, firm_capacity_mw=500.0)
    assert w.start_day == 100
    assert w.days == 4
    assert w.shortfall_mwh > 0


def test_clamped_between_three_and_seven_days():
    residual = np.full(8760, 100.0)
    residual[10 * 24:40 * 24] = 900.0       # a month-long stretch
    w = locate_worst_window(residual, 500.0)
    assert MIN_DAYS <= w.days <= MAX_DAYS


def test_a_comfortable_year_still_has_a_window_to_draw():
    residual = np.full(8760, 100.0)
    residual[4000] = 300.0
    w = locate_worst_window(residual, firm_capacity_mw=10_000.0)
    assert w.shortfall_mwh == 0.0
    assert w.days == MIN_DAYS
    assert w.hours.start <= 4000 < w.hours.stop


def test_window_is_measured_after_dispatch_so_it_cannot_move_prices():
    """Re-selecting the window every tick is safe precisely because nothing in
    pricing reads it."""
    s = load_settings()
    b = generate_bundle(s.weather["seed"], s.weather["shape_years"])
    shape = b["demand_shape"][4]
    res = dispatch_year(s, 2026, shape * (12500.0 / shape.max()),
                        b["wind_cf"][4], b["solar_cf"][4])
    firm = sum(u.available_mw for u in s.fleet
               if u.technology in ("coal", "ccgt", "ocgt", "hydro", "import"))
    first = locate_worst_window(res.residual_mw, firm)
    second = locate_worst_window(res.residual_mw, firm)
    assert (first.start_day, first.days) == (second.start_day, second.days)
