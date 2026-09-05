"""Blocks, duration curves and the calibration report."""

import numpy as np
from pathlib import Path
import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.report import (
    block_mask, block_prices, calibration, duration_curve, unit_revenue,
)


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def test_blocks_partition_the_day_exactly_once(settings):
    n = 240
    total = np.zeros(n, dtype=int)
    for name in settings.blocks():
        total += block_mask(settings, name, n).astype(int)
    assert (total == 1).all(), "every hour belongs to exactly one block"


def test_overnight_block_wraps_past_midnight(settings):
    mask = block_mask(settings, "overnight", 24)
    assert mask[23] and mask[0] and mask[5]
    assert not mask[6] and not mask[12]


def test_sampling_a_duration_curve_misprices_a_single_scarce_hour():
    """Why money is settled on the full series and never on a sampled curve.

    One hour at the cap in a year is one hour. Sampling the sorted series to 101
    points makes that hour the top point at one per cent weight, so integrating
    over the samples pays it as if it lasted for tens of hours.
    """
    price = np.full(8760, 50.0)
    price[0] = 20300.0
    strike = 300.0

    exact = np.clip(price - strike, 0.0, None).mean()
    sampled = np.clip(duration_curve(price, points=101) - strike, 0.0, None).mean()

    assert exact == pytest.approx((20300.0 - 300.0) / 8760)
    assert sampled > exact * 40, "the sampled basis overstates by more than 40x"
    assert len(duration_curve(price)) == 8760


def test_duration_curve_is_sorted_high_to_low():
    curve = duration_curve(np.array([1.0, 9.0, 5.0]))
    np.testing.assert_array_equal(curve, [9.0, 5.0, 1.0])


def test_unit_revenue_nets_fuel_from_energy_revenue(settings):
    price = np.array([100.0, 100.0])
    gen = {"ocgt_a": np.array([10.0, 10.0])}
    out = unit_revenue(price, gen, settings)["ocgt_a"]
    srmc = next(u.srmc_per_mwh for u in settings.fleet if u.unit == "ocgt_a")
    assert out["energy_mwh"] == 20.0
    assert out["revenue"] == 2000.0
    assert out["net_rent"] == pytest.approx(2000.0 - 20.0 * srmc)


def test_calibration_counts_days_not_only_hours(settings):
    """A hot afternoon puts several hours over $300 at once, so counting hours
    overstates how often the market is actually tight."""
    price = np.full(8760, 50.0)
    price[10:16] = 500.0          # six hours, but only one day
    cal = calibration(price, np.zeros(8760), np.zeros(8760, bool),
                      np.full(8760, 1000.0), settings)
    assert cal.hours_at_or_above_300 == 6
    assert cal.days_with_300_hour == pytest.approx(1 / 365)


def test_calibration_reports_unserved_as_a_fraction_of_demand(settings):
    unserved = np.zeros(8760)
    unserved[0] = 100.0
    cal = calibration(np.full(8760, 50.0), unserved, np.zeros(8760, bool),
                      np.full(8760, 1000.0), settings)
    assert cal.unserved_gwh == pytest.approx(0.1)
    assert cal.unserved_fraction == pytest.approx(100.0 / 8_760_000)


def test_quarters_have_real_month_lengths():
    """Deriving months from an average 30.44-day month drifts four days by
    December, so quarterly contracts settle against the wrong quarter's prices."""
    from esem_sandbox.core.report import quarter_of_hour
    q = quarter_of_hour(8760)
    days = [int((q == i).sum()) // 24 for i in range(4)]
    assert days == [90, 91, 92, 92], f"got {days}"
    assert q[89 * 24] == 0, "31 March belongs to the first quarter"
    assert q[90 * 24] == 1, "1 April belongs to the second"
    assert q[180 * 24] == 1, "30 June belongs to the second"
    assert q[181 * 24] == 2, "1 July belongs to the third"


def test_a_curtailment_offer_is_not_booked_as_a_fuel_bill(settings):
    """Wind's negative short run cost is an opportunity cost. Multiplying it by
    output would book a credit and overstate the fleet's net rent."""
    price = np.array([50.0, 50.0])
    gen = {"wind_a": np.array([100.0, 100.0])}
    out = unit_revenue(price, gen, settings)["wind_a"]
    assert out["fuel_and_vom"] == 0.0
    assert out["net_rent"] == pytest.approx(10_000.0)


def test_a_store_is_not_credited_for_the_energy_it_consumes(settings):
    """A store's net energy is negative. Costing the net would turn its variable
    cost into a credit.

    Uses a unit with a POSITIVE short run cost, because the battery rows carry zero
    and the assertion was therefore true of any implementation.
    """
    import dataclasses
    fleet = tuple(dataclasses.replace(u, srmc_per_mwh=9.0)
                  if u.unit == "battery_2h" else u for u in settings.fleet)
    s = dataclasses.replace(settings, fleet=fleet)
    price = np.array([100.0, 20.0])
    gen = {"battery_2h": np.array([50.0, -60.0])}      # discharge then charge
    out = unit_revenue(price, gen, s)["battery_2h"]
    assert out["fuel_and_vom"] == pytest.approx(50 * 9.0), (
        "fuel is burnt on the 50 MWh sent out, not on the -10 MWh net"
    )
    assert out["revenue"] == pytest.approx(50 * 100 - 60 * 20)
    assert out["net_rent"] == pytest.approx(50 * 100 - 60 * 20 - 50 * 9.0)


def test_behind_the_meter_generation_is_not_settled_at_spot(settings):
    """Rooftop never offers into the pool, so it cannot earn the pool price."""
    price = np.full(10, 100.0)
    gen = {"rooftop": np.full(10, 500.0), "coal_a": np.full(10, 500.0)}
    out = unit_revenue(price, gen, settings)
    assert "rooftop" not in out
    assert "coal_a" in out


def test_every_reported_unserved_fraction_uses_the_same_denominator():
    """The printed headline and the CSV must not disagree about the same quantity.

    They did: a search-and-replace matched two call sites reading `res.demand_mw`
    and missed a third reading `worst.demand_mw`, so the headline reported unserved
    energy against native demand while the CSV used operational demand. The two
    differ by about a quarter, which is the size of the rooftop fleet.
    """
    import re
    from esem_sandbox import cli
    src = Path(cli.__file__).read_text(encoding="utf-8")
    calls = re.findall(r"calibration\((.*?)settings\)", src, flags=re.S)
    assert calls, "no calibration call sites found"
    for call in calls:
        assert "operational_demand_mw" in call, (
            "a calibration call site is passing native demand: " + " ".join(call.split())
        )
        assert not re.search(r"\.demand_mw\b", call.replace("operational_demand_mw", "")), (
            "a calibration call site still passes native demand"
        )
