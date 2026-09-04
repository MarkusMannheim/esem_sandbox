"""The weather bundle must be deterministic, correctly sized and calibrated."""

import numpy as np
import pytest

from esem_sandbox.core.weather import HOURS_PER_YEAR, generate_bundle

SEED = 20260904


@pytest.fixture(scope="module")
def bundle():
    return generate_bundle(SEED)


def test_always_8760_hours_never_8784(bundle):
    # A generator that sometimes emitted a leap year would silently misalign
    # every downstream array.
    for key, arr in bundle.items():
        assert arr.shape[1] == HOURS_PER_YEAR, key
        assert arr.shape[1] != 8784


def test_deterministic_in_the_seed():
    a, b = generate_bundle(SEED), generate_bundle(SEED)
    for key in a:
        np.testing.assert_array_equal(a[key], b[key])
    other = generate_bundle(SEED + 1)
    assert not np.array_equal(a["wind_cf"], other["wind_cf"])


def test_shapes_are_demand_neutral(bundle):
    # Peak uncertainty enters as a peak-weighted multiplier later. If the shapes
    # also differed in annual energy the two would double count.
    assert np.allclose(bundle["demand_shape"].mean(axis=1), 1.0)


def test_calibrated_against_published_statistics(bundle):
    peak_to_average = bundle["demand_shape"].max(axis=1)
    assert np.all((peak_to_average > 1.7) & (peak_to_average < 2.1))
    solar = bundle["solar_cf"].mean(axis=1)
    assert np.all((solar > 0.20) & (solar < 0.29))
    wind = bundle["wind_cf"].mean(axis=1)
    assert np.all((wind > 0.30) & (wind < 0.42))


def test_at_least_one_year_holds_a_multi_day_wind_lull(bundle):
    # Without a lull nothing ever empties storage, and the worst-week chart has
    # nothing to show.
    lulls = [
        np.convolve(bundle["wind_cf"][y], np.ones(72) / 72, "valid").min()
        for y in range(bundle["wind_cf"].shape[0])
    ]
    assert min(lulls) < 0.05
