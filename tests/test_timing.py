"""A regression guard on speed.

The requirement is that a paired run finishes inside a workshop exercise, which a
few minutes satisfies. A dispatched year costs about 22 ms, so a twenty-year leg
with the forty-five cell lattice at three anchors projects to somewhere near a
minute. There is no tighter target than that.

It cost about 40 ms until storage stopped being scheduled by ranking prices, and it
now costs less rather than more. Shaving quantities needs a threshold search and an
hourly state-of-charge scan that ranking did not, but the schedule no longer depends
on the price it produces, so the re-stack loop that used to run four to six times a
year is gone. Correcting the rule made the model faster, which is not the usual
direction and is worth saying.

Dispatch is the unit that gets multiplied by ticks, legs and forward cells, so
it is the one worth holding a budget on. The budget below is deliberately loose:
it exists to catch something going quadratic, not to police a stopwatch.
"""

import time

import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.dispatch import dispatch_year
from esem_sandbox.core.weather import generate_bundle

BUDGET_MS = 60.0        # headroom over the measured ~22 ms, for slow CI hardware


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
