"""Every declared setting must be consumed, or explicitly declared as not yet.

The larger model this one simplifies had a critical defect of exactly this shape:
the forward lattice computed probability weights for each cell and every consumer
outside one function then reduced the cells with a plain arithmetic mean, so a
one-in-ten-year scenario entered at one in three. The weights were declared, and
silently never applied.

A setting that nothing reads is a claim the model does not honour. This test makes
that impossible to introduce by accident: a key must be listed as consumed, with
where, or listed as staged, with why.
"""

import tomllib
from importlib import resources

import pytest

from esem_sandbox.config import load_settings

# Keys the model actually reads, and where.
CONSUMED = {
    "market_price_cap_per_mwh": "dispatch._apply_ladder, as the price of unserved energy",
    "administered_price_cap_per_mwh": "dispatch._apply_ladder, once the threshold is breached",
    "cumulative_price_threshold": "config.hourly_price_threshold",
    "cumulative_price_threshold_intervals_per_hour": "config.hourly_price_threshold",
    "cumulative_price_window_hours": "dispatch._apply_ladder, the rolling window",
    "minimum_price_per_mwh": "dispatch.dispatch_year, enforced on the settled series",
    "standard_use_fraction": "cli, to say whether a year sits inside the standard",
    "must_run_offer_per_mwh": "dispatch._offer_stack, the price of a coal must-run band",
    "storage_spread_per_mwh": "dispatch._run_storage, the round-trip viability test",
    "max_storage_passes": "dispatch.dispatch_year, the re-stack loop",
    "storage_price_tolerance": "dispatch.dispatch_year, the re-stack convergence test",
    "block_overnight": "config.blocks, then report.block_mask",
    "block_morning": "config.blocks, then report.block_mask",
    "block_solar": "config.blocks, then report.block_mask",
    "block_peak": "config.blocks, then report.block_mask",
    "shape_years": "cli, the number of years dispatched",
    "hours_per_year": "cli, passed to the weather generator which validates it",
    "seed": "cli, the weather bundle",
}

# Keys committed ahead of the code that will read them. Each needs a reason, and
# each is a promise that the value has not been quietly relied on in the meantime.
STAGED = {
    "interim_measure_use_fraction":
        "the interim reliability measure becomes a lever when the reliability view "
        "is built; nothing reads it today and no result depends on it",
    "peak_band_multipliers":
        "peak uncertainty enters the forward lattice in week three; declared here so "
        "the lattice and the realised draw cannot disagree about the bands later",
    "peak_band_weights":
        "the probabilities attached to those bands; the defect this test exists to "
        "prevent is precisely these being declared and then never applied",
}


def _declared_keys() -> set[str]:
    with (resources.files("esem_sandbox") / "data" / "settings.toml").open("rb") as fh:
        raw = tomllib.load(fh)
    return {k for section in raw.values() for k in section}


def test_every_declared_setting_is_consumed_or_explicitly_staged():
    declared = _declared_keys()
    accounted = set(CONSUMED) | set(STAGED)
    unaccounted = declared - accounted
    assert not unaccounted, (
        f"settings declared but neither consumed nor staged: {sorted(unaccounted)}. "
        "Wire it up, or add it to STAGED with a reason."
    )
    stale = accounted - declared
    assert not stale, f"listed here but no longer declared: {sorted(stale)}"


def test_staged_settings_carry_a_reason():
    for key, reason in STAGED.items():
        assert len(reason) > 40, f"{key} needs a real reason, not a placeholder"


def test_the_market_price_floor_is_actually_enforced():
    """It was declared for a while and never applied; the binding floor was the VRE
    offer instead, which is a different number and a different rule."""
    import numpy as np
    from esem_sandbox.core.dispatch import dispatch_year
    from esem_sandbox.core.weather import generate_bundle

    s = load_settings({"dispatch": {"must_run_offer_per_mwh": -5000.0}})
    b = generate_bundle(s.weather["seed"], 1)
    shape = b["demand_shape"][0]
    res = dispatch_year(s, 2026, shape * (12500.0 / shape.max()),
                        b["wind_cf"][0], b["solar_cf"][0])
    floor = s.market["minimum_price_per_mwh"]
    assert res.price.min() >= floor, (
        "an offer below the market price floor must be clipped to it"
    )
    assert np.isclose(res.price.min(), floor), (
        "with a -$5,000 offer the floor should bind at exactly the floor"
    )
