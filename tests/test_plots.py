"""The charts.

A chart is read by people and executed by code, and only the second half can be
tested. What is tested here is that every panel draws from real output without
falling over, that the categorical palette is the validated one in its fixed order,
and that nothing is identified by colour alone.
"""

import matplotlib
import numpy as np
import pytest

from esem_sandbox import plots
from esem_sandbox.config import load_settings
from esem_sandbox.core.forward import cell_plan
from esem_sandbox.core.simulate import ESEM, MERCHANT, run
from esem_sandbox.core.windows import locate_worst_window


@pytest.fixture(scope="module")
def settings():
    return load_settings()


@pytest.fixture(scope="module")
def legs(settings):
    small = tuple(c for c in cell_plan(settings) if c.shape_year == 0)
    return {leg: run(settings, ticks=4, seed=20260904, cells=small, leg=leg)
            for leg in (MERCHANT, ESEM)}


def test_the_dashboard_draws_every_panel(tmp_path, settings, legs):
    path = plots.dashboard(legs, settings, str(tmp_path / "dashboard.png"))
    assert (tmp_path / "dashboard.png").stat().st_size > 50_000, (
        "a dashboard that small did not draw"
    )
    assert path.endswith("dashboard.png")


def test_the_palette_is_the_validated_one_in_its_fixed_order():
    """Assigned in fixed order and never cycled. These are the six slots the
    validator passed: worst adjacent colour-vision separation 9.1 against a floor of
    8, worst normal-vision separation 19.6 against a floor of 15. Changing one
    without re-running the validator is how a palette quietly stops being readable.
    """
    assert plots.SERIES == ("#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                            "#e87ba4", "#008300")
    assert len(set(plots.SERIES)) == len(plots.SERIES)
    assert list(plots.TECH_COLOUR.values()) == list(plots.SERIES)


def test_no_more_colours_than_a_reader_can_hold():
    """More than about seven colours carrying meaning stops being readable, and
    nobody in a workshop needs to tell two coal stations apart."""
    assert len(plots.TECH_ORDER) <= 7
    assert set(plots.TECH_GROUP.values()) == set(plots.TECH_ORDER)


def test_identity_is_never_carried_by_colour_alone():
    """Each leg has its own marker as well as its own hue. For most of a run the two
    legs sit on exactly the same number, and one line hidden under another reads as a
    missing series rather than as an identical one."""
    assert set(plots.LEG_MARKER) == set(plots.LEG_COLOUR)
    assert len(set(plots.LEG_MARKER.values())) == 2


def test_a_label_is_legible_on_the_fill_it_sits_on():
    """Three of the six hues sit below 3:1 against the chart surface, which obliges
    visible labels. A label is only visible if it is the right way round."""
    assert plots._readable_on("#008300") == "#ffffff"
    assert plots._readable_on("#eda100") == plots.INK
    for colour in plots.SERIES:
        assert plots._readable_on(colour) in ("#ffffff", plots.INK)


def test_the_charts_carry_the_caption_they_are_required_to():
    assert "not a forecast" in plots.CAPTION.lower()


def test_the_worst_week_chart_still_draws(tmp_path, settings, legs):
    from esem_sandbox.core.dispatch import dispatch_year
    from esem_sandbox.core.weather import generate_bundle

    bundle = generate_bundle(settings.weather["seed"], settings.weather["shape_years"])
    shape = bundle["demand_shape"][4]
    res = dispatch_year(settings, 2026, shape * (12500.0 / shape.max()),
                        bundle["wind_cf"][4], bundle["solar_cf"][4])
    window = locate_worst_window(res.residual_mw, res.firm_capacity_mw)
    path = plots.worst_week(res, window, res.firm_capacity_mw,
                            str(tmp_path / "worst.png"))
    assert (tmp_path / "worst.png").stat().st_size > 20_000


def test_the_cost_panel_carries_the_one_seed_caveat():
    """The picture is what a room sees. Across ten seeds the resource-cost line
    changes sign while the reliability line does not, and a chart that showed the
    pair without saying so would hand an audience a number the model does not
    support."""
    import inspect

    source = inspect.getsource(plots._panel_costs)
    assert "One weather sequence" in source
    assert "ten-seed envelope" in source
    assert "changes sign" not in source.split("ax.text")[1], (
        "the caveat must be an instruction, not a claim about what the seeds show: "
        "a claim goes stale the moment anybody recalibrates the fleet"
    )


def test_the_envelope_refuses_to_call_a_sign_change_a_result(tmp_path):
    """What ten seeds are for. A number that changes sign across the draws is not
    the model's answer, and the reducer's job is to say so rather than to average
    it into one."""
    import csv
    import sys

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]
                           / "tools"))
    from ten_seeds import FIELDS, envelope

    path = tmp_path / "seeds.csv"
    rows = [
        # merchant better off on cost in one, worse in the other: a sign change.
        dict(seed=1, growth_path="high", annual_growth=0.033,
             merchant_unserved_gwh=50, esem_unserved_gwh=30,
             merchant_bill=100, esem_bill=90,
             merchant_resource_cost=100, esem_resource_cost=99,
             awarded_mw=1000, levy_total=5, transfer=9),
        dict(seed=2, growth_path="low", annual_growth=0.005,
             merchant_unserved_gwh=10, esem_unserved_gwh=5,
             merchant_bill=100, esem_bill=90,
             merchant_resource_cost=100, esem_resource_cost=104,
             awarded_mw=1000, levy_total=5, transfer=14),
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    result = envelope(str(path))
    assert result["seeds"] == 2
    assert result["unserved_improved"] == 2
    assert result["robust_on_reliability"] is True
    assert result["resource_cost_lower"] == 1
    assert result["robust_on_resource_cost"] is False, (
        "one seed cheaper and one dearer is a sign change, not an answer"
    )
    assert result["resource_cost_min"] < 0 < result["resource_cost_max"]


def test_the_decomposition_separates_the_outage_from_everything_else(tmp_path):
    """The split that explains why a resource-cost total changes sign across seeds.

    Unserved energy priced at the value of lost load is one of the four terms in the
    resource cost, so subtracting it leaves fuel, fixed costs and capital together.
    It needs no extra runs, and it is the difference between reporting that a result
    is unstable and saying why.
    """
    import csv
    import sys

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]
                           / "tools"))
    from ten_seeds import FIELDS, decompose

    path = tmp_path / "seeds.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(dict(
            seed=1, growth_path="high", annual_growth=0.033,
            merchant_unserved_gwh=50.0, esem_unserved_gwh=30.0,
            merchant_bill=0, esem_bill=0,
            merchant_resource_cost=1_000_000_000.0, esem_resource_cost=0.0,
            awarded_mw=1000, levy_total=0, transfer=0))
    row = decompose(str(path))[0]
    assert row["outage_avoided"] == pytest.approx(20.0 * 1000.0 * 20_300.0)
    assert row["resource_cost_moved"] == pytest.approx(1e9)
    assert row["everything_else"] == pytest.approx(
        row["resource_cost_moved"] - row["outage_avoided"])
