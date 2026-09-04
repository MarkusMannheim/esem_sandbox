"""The settings loader is strict on purpose."""

import pytest

from esem_sandbox.config import load_settings


def test_loads_the_packaged_bundle():
    s = load_settings()
    assert len(s.fleet) > 10
    assert len(s.dsr) == 4
    assert s.market["market_price_cap_per_mwh"] == 20300.0


def test_unknown_key_raises_rather_than_being_ignored():
    # A typo that silently left a default in place would be invisible in the
    # results and blamed on the model.
    with pytest.raises(ValueError, match="unknown key"):
        load_settings({"market": {"market_price_kap_per_mwh": 1.0}})


def test_unknown_section_raises():
    with pytest.raises(ValueError, match="unknown settings section"):
        load_settings({"markets": {}})


def test_overrides_apply():
    s = load_settings({"dispatch": {"storage_spread_per_mwh": 25.0}})
    assert s.dispatch["storage_spread_per_mwh"] == 25.0


def test_the_hourly_threshold_is_the_published_one_halved():
    """The published threshold is $1,490,600 over 336 half-hourly intervals.
    Settling hourly without scaling it would fire the cap half as often and
    leave half the scarcity rent standing."""
    s = load_settings()
    assert s.market["cumulative_price_threshold"] == pytest.approx(1_490_600 / 2)
    assert s.market["cumulative_price_window_hours"] == 336 // 2


def test_demand_response_tiers_are_increments_not_cumulative_bands():
    s = load_settings()
    caps = [t.capacity_mw for t in s.dsr]
    assert caps == sorted(caps), "tiers should increase with price"
    assert sum(caps) < 600.0, (
        "tiers are increments differenced from the published cumulative bands; "
        "summing the cumulative bands instead would multiply the ladder"
    )
