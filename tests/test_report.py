"""Blocks, duration curves and the calibration report."""

import numpy as np
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
