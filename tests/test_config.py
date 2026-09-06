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

    files = sorted(glob.glob("src/esem_sandbox/scenarios/*.toml"))
    assert len(files) >= 6, f"expected the packaged scenarios, found {files}"
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


def test_a_packaged_scenario_can_be_named_rather_than_found():
    """The scenarios ship inside the wheel. Without that, the only ones a reader
    could run would be the ones they had cloned the repository for, and the command
    naming them would be in a README they could not follow."""
    from esem_sandbox.cli import _scenario, scenario_names

    names = scenario_names()
    assert {"merchant", "scheme"} <= set(names)
    for name in names:
        overrides, options = _scenario(name)
        load_settings(overrides)
        assert options.get("leg") in ("merchant", "esem"), name


def test_a_path_still_works_and_wins_over_a_name(tmp_path):
    from esem_sandbox.cli import _scenario

    local = tmp_path / "scheme.toml"
    local.write_text('[run]\nleg = "merchant"\nticks = 3\n')
    _, options = _scenario(str(local))
    assert options == {"leg": "merchant", "ticks": 3}


def test_every_packaged_data_row_carries_its_derivation():
    """The repository's own rule, enforced rather than trusted.

    DATA_SOURCES.md says a new data file needs a row in its table and a derivation
    column. A rule that lives only in a document is a rule that lasts until the next
    person in a hurry, and the whole provenance claim of this repository rests on
    every row being able to say where it came from.
    """
    from importlib import resources

    from esem_sandbox.config import read_csv

    folder = resources.files("esem_sandbox") / "data"
    names = sorted(p.name for p in folder.iterdir() if p.name.endswith(".csv"))
    assert len(names) >= 5, names
    for name in names:
        rows = read_csv(name)
        assert rows, f"{name} is empty"
        assert "derivation" in rows[0], f"{name} has no derivation column"
        for i, row in enumerate(rows):
            assert (row.get("derivation") or "").strip(), (
                f"{name} row {i} does not say where it came from"
            )


def test_every_packaged_data_file_is_named_in_data_sources():
    """A file that ships without a row in the table is a file whose terms nobody
    stated."""
    import pathlib
    from importlib import resources

    doc = (pathlib.Path(__file__).resolve().parents[1] / "DATA_SOURCES.md").read_text()
    folder = resources.files("esem_sandbox") / "data"
    for path in sorted(folder.iterdir()):
        if path.name.endswith((".csv", ".toml")):
            assert f"`{path.name}`" in doc, f"{path.name} is not in DATA_SOURCES.md"


def test_the_architecture_note_names_every_module():
    """A map with a missing road is worse than no map. The model is meant to be
    understood in an hour, and a reader who finds a module nobody mentioned has to
    work out on their own whether it matters."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    doc = (root / "ARCHITECTURE.md").read_text()
    modules = sorted(p.name for p in (root / "src/esem_sandbox/core").glob("*.py")
                     if p.name != "__init__.py")
    missing = [m for m in modules if m not in doc]
    assert not missing, f"ARCHITECTURE.md does not mention {missing}"
