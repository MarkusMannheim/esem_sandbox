"""The timing gate.

The whole design rests on a paired twenty-year run finishing in about a minute
on a laptop. Dispatch is the unit that gets multiplied by ticks, legs and
forward cells, so it is the one to hold a budget on. If this fails, the run that
the workshop depends on has stopped fitting in a coffee break.
"""

import time

import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.dispatch import dispatch_year
from esem_sandbox.core.weather import generate_bundle

BUDGET_MS = 60.0        # generous against continuous integration hardware


@pytest.fixture(scope="module")
def case():
    s = load_settings()
    b = generate_bundle(s.weather["seed"], s.weather["shape_years"])
    shape = b["demand_shape"][4]
    return s, shape * (12500.0 / shape.max()), b["wind_cf"][4], b["solar_cf"][4]


def test_a_dispatched_year_stays_inside_the_budget(case):
    settings, demand, wind, solar = case
    for _ in range(2):
        dispatch_year(settings, 2026, demand, wind, solar)
    start = time.perf_counter()
    runs = 10
    for _ in range(runs):
        dispatch_year(settings, 2026, demand, wind, solar)
    per_year_ms = (time.perf_counter() - start) / runs * 1000.0
    assert per_year_ms < BUDGET_MS, (
        f"{per_year_ms:.1f} ms a year against a {BUDGET_MS:.0f} ms budget"
    )


def test_the_weather_bundle_is_cheap_enough_to_regenerate(case):
    settings = case[0]
    start = time.perf_counter()
    generate_bundle(settings.weather["seed"], settings.weather["shape_years"])
    assert (time.perf_counter() - start) < 1.0
