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


def test_market_settings_come_from_one_year_not_several():
    """The cap and the threshold are indexed together and their ratio decides when
    the market is suspended, so mixing years silently changes the model's rules.
    $20,300 and $1,823,600 are both the values applying from 1 July 2025."""
    s = load_settings()
    assert s.market["market_price_cap_per_mwh"] == 20_300.0
    assert s.market["cumulative_price_threshold"] == 1_823_600.0


def test_the_threshold_is_converted_on_five_minute_intervals():
    """The published threshold sums TRADING INTERVAL prices, and a trading interval
    is five minutes. An hourly interval therefore stands for twelve of them."""
    s = load_settings()
    assert s.market["cumulative_price_threshold_intervals_per_hour"] == 12
    assert s.hourly_price_threshold == pytest.approx(1_823_600.0 / 12)
    hours = s.hourly_price_threshold / s.market["market_price_cap_per_mwh"]
    assert hours == pytest.approx(7.5, abs=0.05), (
        "the AEMC glosses this pair as 7.5 hours at the cap"
    )


def test_demand_response_tiers_are_increments_not_cumulative_bands():
    s = load_settings()
    caps = [t.capacity_mw for t in s.dsr]
    assert caps == sorted(caps), "tiers should increase with price"
    assert sum(caps) < 600.0, (
        "tiers are increments differenced from the published cumulative bands; "
        "summing the cumulative bands instead would multiply the ladder"
    )


def test_every_packaged_scenario_loads_and_is_strict():
    """A typo in a scenario file must fail loudly rather than leaving a default
    quietly in place, which is the same rule the settings loader follows."""
    import glob
    import pytest as _pytest
    from esem_sandbox.cli import _scenario

    files = sorted(glob.glob("scenarios/*.toml"))
    assert len(files) >= 4, f"expected the packaged scenarios, found {files}"
    for path in files:
        overrides, options = _scenario(path)
        load_settings(overrides)
        assert options.get("leg") in ("merchant", "esem"), path


def test_a_scenario_with_a_bad_setting_is_rejected(tmp_path):
    from esem_sandbox.cli import _scenario

    bad = tmp_path / "bad.toml"
    bad.write_text('[esem]\ncontract_tenor_yars = 6\n')
    overrides, _ = _scenario(str(bad))
    with pytest.raises(ValueError, match="unknown key"):
        load_settings(overrides)


def test_a_scenario_with_a_bad_run_option_is_rejected(tmp_path):
    from esem_sandbox.cli import _scenario

    bad = tmp_path / "bad.toml"
    bad.write_text('[run]\nlegg = "esem"\n')
    with pytest.raises(ValueError, match="unknown key"):
        _scenario(str(bad))
