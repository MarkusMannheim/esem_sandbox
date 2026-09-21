"""Changing one thing from the command line and from the notebook.

``--set``, ``sweep`` and the notebook all go through ``explore``, so what is
tested here is the path a reader takes when they move a number: the string they
type becomes the override the strict loader accepts, a misspelt key fails loudly,
and a sweep's rows differ in the swept number and in nothing else.
"""

import argparse
import csv
import pathlib

import pytest

from esem_sandbox import cli, explore
from esem_sandbox.config import SECTIONS, load_settings
from esem_sandbox.core.forward import cell_plan
from esem_sandbox.core.simulate import ESEM, MERCHANT


def test_values_are_read_as_toml_would_read_them():
    assert explore.parse_value("6") == 6 and isinstance(explore.parse_value("6"), int)
    assert explore.parse_value("0.1") == 0.1
    assert explore.parse_value("true") is True
    assert explore.parse_value("[4, 8]") == [4, 8]
    assert explore.parse_value('"warehouse"') == "warehouse"
    # A bare word is a string; nobody should have to quote a conduct's name.
    assert explore.parse_value("warehouse") == "warehouse"


def test_overrides_stack_on_the_scenario_and_the_loader_checks_them():
    base = {"esem": {"contract_tenor_years": 6}}
    out = explore.overrides_from(
        ["investment.risk_premium=0.1", "esem.recycling_conduct=fire_sale"], base)
    assert out == {"esem": {"contract_tenor_years": 6,
                            "recycling_conduct": "fire_sale"},
                   "investment": {"risk_premium": 0.1}}
    assert base == {"esem": {"contract_tenor_years": 6}}, "the scenario's own "\
        "mapping must not be written into"
    settings = load_settings(out)
    assert settings.investment["risk_premium"] == 0.1
    assert settings.esem["contract_tenor_years"] == 6
    with pytest.raises(ValueError, match="unknown key"):
        load_settings(explore.overrides_from(["investment.risk_premum=0.1"]))
    with pytest.raises(ValueError, match="section.key=value"):
        explore.overrides_from(["risk_premium=0.1"])


def test_the_quick_lattice_is_two_weather_years_of_the_five():
    settings = load_settings()
    quick = explore.quick_cells(settings)
    assert {c.shape_year for c in quick} == set(explore.QUICK_SHAPE_YEARS)
    assert len(quick) * 5 == len(cell_plan(settings)) * 2


def test_a_pair_shares_one_draw_and_summarises_to_signed_moves():
    settings = load_settings()
    legs = explore.run_pair(settings, ticks=2, seed=7, quick=True)
    assert set(legs) == {MERCHANT, ESEM}
    assert legs[MERCHANT].draw == legs[ESEM].draw
    s = explore.summarise(settings, legs)
    m, e = legs[MERCHANT], legs[ESEM]
    assert s["bill_move"] == pytest.approx(m.consumer_cost(settings)
                                           - e.consumer_cost(settings))
    assert s["transfer"] == pytest.approx(s["bill_move"] - s["resource_cost_move"])
    assert s["outage_avoided"] + s["plant_and_fuel_saved"] == \
        pytest.approx(s["resource_cost_move"])
    assert s["awarded_mw"] == sum(a.capacity_mw for t in e.ticks for a in t.awards)


def test_a_sweep_changes_one_number_and_reports_it_in_front():
    rows = explore.sweep("esem.contract_tenor_years", [6, 12], ticks=2, seed=7,
                         quick=True)
    assert [r["value"] for r in rows] == [6, 12]
    assert all(r["parameter"] == "esem.contract_tenor_years" for r in rows)
    # The merchant leg does not read the ESEM tenor, so it is the same run in
    # both rows: the sweep changed one number and nothing else.
    assert rows[0]["merchant_unserved_gwh"] == rows[1]["merchant_unserved_gwh"]
    assert rows[0]["merchant_bill"] == rows[1]["merchant_bill"]
    with pytest.raises(ValueError, match="section.key"):
        explore.sweep("contract_tenor_years", [6], ticks=1)


def test_the_command_line_sets_a_setting_and_sweeps_one(tmp_path, capsys):
    out = tmp_path / "sweep"
    rc = cli.main(["sweep", "esem.contract_tenor_years", "6", "12", "--ticks", "2",
                   "--seed", "7", "--quick", "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "esem.contract_tenor_years at 2 values" in printed
    assert "(quick lattice)" in printed
    with open(out / "sweep.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["value"] for r in rows] == ["6", "12"]
    assert (out / "sweep.png").exists() and (out / "sweep_dark.png").exists()

    with pytest.raises(SystemExit, match="not a setting"):
        cli.main(["sweep", "esem.tenor", "6", "--ticks", "1", "--quick",
                  "--out", str(out)])


def test_the_command_line_run_options_reach_the_run(tmp_path):
    """A scenario file's keys and the flags that replace them land on the same
    run options, and a flag typed wins over the file."""
    scenario = tmp_path / "s.toml"
    scenario.write_text('[run]\nleg = "esem"\ninvestment = "sequential"\n'
                        'retire = { coal_b = 2028 }\n'
                        '[esem]\ncontract_tenor_years = 6\n')
    args = argparse.Namespace(
        scenario=str(scenario), set=["investment.risk_premium=0.1"],
        ticks=2, year=2026, peak=12_500.0, seed=7, quick=True, retire=None,
        clearing=None, scheme=False, investment=None, _argv=[])
    settings, overrides, options = cli._settings_and_options(args)
    assert settings.esem["contract_tenor_years"] == 6
    assert settings.investment["risk_premium"] == 0.1
    assert options["investment"] == "sequential"
    assert options["retire"] == {"coal_b": 2028}
    assert options["quick"] is True

    typed = argparse.Namespace(
        scenario=str(scenario), set=None, ticks=2, year=2026, peak=12_500.0,
        seed=7, quick=False, retire=["coal_a=2030"], clearing="crossing",
        scheme=True, investment="simultaneous",
        _argv=["--investment", "simultaneous", "--retire", "coal_a=2030"])
    _, _, options = cli._settings_and_options(typed)
    assert options["investment"] == "simultaneous", "typed wins over the file"
    assert options["retire"] == {"coal_a": 2030}
    assert options["clearing"] == "crossing" and options["scheme"] is True


def test_every_setting_is_documented_in_parameters_md():
    """PARAMETERS.md is the list a reader sweeps from, so a key the loader
    accepts and the page does not name is a knob no one can find."""
    page = (pathlib.Path(__file__).resolve().parents[1] / "PARAMETERS.md").read_text()
    missing = [f"{section}.{key}" for section, keys in SECTIONS.items()
               for key in sorted(keys) if f"`{section}.{key}`" not in page]
    assert not missing, f"not in PARAMETERS.md: {', '.join(missing)}"
