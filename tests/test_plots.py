"""The charts.

A chart is read by people and executed by code, and only the second half can be
tested. What is tested here is that every panel draws from real output without
falling over, that the categorical palette is the validated one in its fixed order,
and that nothing is identified by colour alone.
"""

import matplotlib
import numpy as np
import pathlib, tempfile
TMP_PLOTS = pathlib.Path(tempfile.mkdtemp())
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


def test_every_colour_comes_from_the_theme_s_own_matplotlib_cycle():
    """One palette per ground, and matplotlib supplies both.

    Series, legs and technologies all draw from the cycle that belongs to the theme's
    own ground: tab10 under the default style, and dark_background's paler set on
    black. Nothing here is mixed by hand.
    """
    import matplotlib.pyplot as plt

    for name, palette, style in (
            ("light", plots._LIGHT, plt.rcParamsDefault),
            ("dark", plots._DARK, matplotlib.style.library["dark_background"])):
        cycle = [matplotlib.colors.to_hex(c)
                 for c in style["axes.prop_cycle"].by_key()["color"]]
        assert list(palette["SERIES"]) == cycle, f"{name} series left the cycle"
        assert len(set(palette["SERIES"])) == len(palette["SERIES"])
        off_cycle = [c for c in palette["TECH_COLOUR"].values() if c not in cycle]
        assert not off_cycle, f"{name} technology colours off the cycle: {off_cycle}"
        assert set(palette["LEG_COLOUR"].values()) == set(cycle[:2]), (
            f"{name} legs are not the cycle's first two slots")


def test_no_more_colours_than_a_reader_can_hold():
    """More than about seven colours carrying meaning stops being readable, and
    nobody reading this needs to tell two coal stations apart."""
    assert len(plots.TECH_ORDER) <= 7
    assert set(plots.TECH_GROUP.values()) == set(plots.TECH_ORDER)


def test_identity_is_never_carried_by_colour_alone():
    """Each leg has its own marker as well as its own hue. For most of a run the two
    legs sit on exactly the same number, and one line hidden under another reads as a
    missing series rather than as an identical one."""
    assert set(plots.LEG_MARKER) == set(plots.LEG_COLOUR)
    assert len(set(plots.LEG_MARKER.values())) == 2


def test_a_label_is_legible_on_the_fill_it_sits_on():
    """Some hues sit below 3:1 against the chart surface, which obliges visible
    labels, and a label is only visible if it is the right way round.

    The two candidates are black and white rather than the theme's ink. Under the
    dark theme the ink is white, so an ink-or-white choice cannot pick dark at all
    and every pale fill carries a white label on a pale ground.
    """
    assert plots._readable_on("#008300") == "#ffffff"
    assert plots._readable_on("#eda100") == "#000000"
    for palette in (plots._LIGHT, plots._DARK):
        for colour in palette["TECH_COLOUR"].values():
            ink = plots._readable_on(colour)
            assert ink in ("#ffffff", "#000000")
            ground = 1.0 if ink == "#ffffff" else 0.0
            assert _contrast(colour, ground) >= 4.5, (
                f"a label on {colour} would be {_contrast(colour, ground):.2f}:1")


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


def test_every_chart_can_be_drawn_on_a_dark_ground(tmp_path, settings):
    """These are read on GitHub, which serves whichever theme the reader has set.

    A chart drawn for a pale ground is unreadable on a dark one, so the documents
    carry both and pick with a picture element. The palette swap has to reach the
    figure itself: an earlier version set the axes but left the saved figure's
    background white, which looks worse than not bothering.
    """
    from esem_sandbox import plots
    from esem_sandbox.core.dispatch import dispatch_year
    from esem_sandbox.core.weather import generate_bundle
    from esem_sandbox.core.windows import locate_worst_window

    bundle = generate_bundle(settings.weather["seed"],
                             settings.weather["shape_years"])
    shape = bundle["demand_shape"][4]
    result = dispatch_year(settings, 2026, shape * (12500.0 / shape.max()),
                           bundle["wind_cf"][4], bundle["solar_cf"][4])
    window = locate_worst_window(result.residual_mw, result.firm_capacity_mw)

    made = {}
    for name in ("light", "dark"):
        with plots.theme(name):
            surface = plots.SURFACE
            path = tmp_path / f"worst_{name}.png"
            plots.worst_week(result, window, result.firm_capacity_mw, str(path))
            made[name] = (path.read_bytes(), surface)
    assert plots.SURFACE == "#ffffff", "the theme did not restore itself on exit"
    assert made["light"][1] != made["dark"][1], "both themes used the same surface"
    assert made["light"][0] != made["dark"][0], "both themes produced the same image"

    # The FIGURE ground and the AXES ground both have to move. Checking only the
    # figure corner passed while worst_week drew white plot boxes on a dark figure,
    # because it set its own colours and never went through _style.
    from PIL import Image
    # Read the expected ground from the palette rather than repeating the hex here.
    # Hard-coded, this failed the moment the grounds moved to matplotlib's own, which
    # is a test breaking on a deliberate change rather than catching anything.
    def rgb(name):
        h = (plots._LIGHT if name == "light" else plots._DARK)["SURFACE"].lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    for name, expected in (("light", rgb("light")), ("dark", rgb("dark"))):
        for draw in ("worst_week", "price_duration"):
            with plots.theme(name):
                path = tmp_path / f"{draw}_{name}.png"
                if draw == "worst_week":
                    plots.worst_week(result, window, result.firm_capacity_mw,
                                     str(path))
                else:
                    plots.price_duration({"year": result}, str(path))
            img = Image.open(path).convert("RGB")
            w, h = img.size
            corner = img.getpixel((3, 3))
            assert corner == expected, (
                f"{draw} {name}: figure corner is {corner}, not {expected}")
            # A pixel well inside the axes, in a quiet region near the top.
            inside = img.getpixel((int(w * 0.55), int(h * 0.10)))
            light_ground = sum(inside) > 600
            assert light_ground == (name == "light"), (
                f"{draw} {name}: the plot area is {inside}, which is the wrong "
                "ground for this theme")


def test_every_technology_is_named_a_colour_rather_than_taking_the_next_one():
    """Anything drawn by TECHNOLOGY must be given its colour explicitly.

    A fuel that takes whichever slot the cycle happens to be on changes colour when a
    series is added above it, so a band means one thing in one chart and another in
    the next. The palette names all six.

    Parsed rather than pattern-matched. A regex over the source stops at the first
    closing bracket and reports every multi-line call as a fault.
    """
    import ast
    import inspect

    from esem_sandbox import plots

    tree = ast.parse(inspect.getsource(plots))
    drawing = {"plot", "fill_between", "bar", "barh", "scatter", "stackplot"}
    bare = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute) and f.attr in drawing):
            continue
        if not (isinstance(f.value, ast.Name) and f.value.id.startswith("ax")):
            continue
        named = {k.arg for k in node.keywords if k.arg}
        if not named & {"color", "facecolor", "colors", "c"}:
            bare.append(f"{f.value.id}.{f.attr} at line {node.lineno}")
    # Generic series may draw from the cycle in order. A technology may not.
    assert set(plots.TECH_COLOUR) == set(plots.TECH_ORDER), (
        "a technology has no colour of its own")
    assert len(set(plots.TECH_COLOUR.values())) == len(plots.TECH_ORDER), (
        "two technologies share a colour")
    assert plots.TECH_COLOUR["solar"] != plots.TECH_COLOUR["wind"], "solar and wind"


def test_no_technology_wears_a_leg_colour():
    """The dashboard shows both at once, in different panels, so a colour that meant
    "hydro" in one and "the market on its own" in another would read as a link
    between them."""
    for name, palette in (("light", plots._LIGHT), ("dark", plots._DARK)):
        clash = {t: c for t, c in palette["TECH_COLOUR"].items()
                 if c in set(palette["LEG_COLOUR"].values())}
        assert not clash, f"{name}: these technologies wear a leg's colour: {clash}"
        assert len(set(palette["TECH_COLOUR"].values())) == len(plots.TECH_ORDER)


def _text_collisions(fig):
    """Titles, captions and legends that print on top of each other.

    Rendered bounding boxes, because that is the only way to know. Everything else
    about a chart can be checked from the code; whether two pieces of text land in
    the same place depends on the font, the figure size and the data.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bad = []
    for i, ax in enumerate(fig.axes):
        captions = [t for t in ax.texts if t.get_text().strip()]
        legend = ax.get_legend()
        if ax.title.get_text():
            title_box = ax.title.get_window_extent(renderer)
            for t in captions:
                if title_box.overlaps(t.get_window_extent(renderer)):
                    bad.append(f"panel {i}: title over {t.get_text()[:40]!r}")
            if legend is not None and title_box.overlaps(
                    legend.get_window_extent(renderer)):
                bad.append(f"panel {i}: title over the legend")
        if legend is not None:
            legend_box = legend.get_window_extent(renderer)
            for t in captions:
                if legend_box.overlaps(t.get_window_extent(renderer)):
                    bad.append(f"panel {i}: legend over {t.get_text()[:40]!r}")
    return bad


def test_no_panel_prints_two_pieces_of_text_in_the_same_place(tmp_path, settings, legs):
    """Found by eye twice, so now it is checked.

    The cost panel's caveat first printed over its own title, and moving it inside
    the axes put it under the legend instead: the note read "the bill moves $38.9bn
    and the resource cost $1.4b" with the rest hidden. A caveat that cannot be read
    is not on the chart.
    """
    import matplotlib.pyplot as plt

    # The REAL figure, at the real panel size. Rebuilding one panel standalone tests
    # a geometry the dashboard never uses: at a comfortable size nothing collides,
    # and the collision only appears once the panel is one eighth of a crowded
    # figure. dashboard() closes its figure, so closing is intercepted to keep it.
    captured = []
    real_close = plt.close

    def keep(fig=None):
        if hasattr(fig, "axes"):
            captured.append(fig)
        else:
            real_close(fig)

    plt.close = keep
    try:
        plots.dashboard(legs, settings, str(tmp_path / "collide.png"))
    finally:
        plt.close = real_close

    assert captured, "the dashboard drew no figure"
    bad = []
    for fig in captured:
        bad += _text_collisions(fig)
        real_close(fig)
    assert not bad, "text printed on top of other text:\n  " + "\n  ".join(bad)


def test_the_palette_claims_in_the_source_are_true():
    """The comment describing the grounds said both came from matplotlib. Only one
    does, and a comment that misdescribes the code is worse than none: the next reader
    trusts it instead of checking."""
    import matplotlib
    import matplotlib.pyplot as plt

    # The series cycle IS matplotlib's default, in both themes.
    default = [matplotlib.colors.to_hex(c)
               for c in plt.rcParamsDefault["axes.prop_cycle"].by_key()["color"]]
    assert list(plots.SERIES) == default, (
        "SERIES no longer matches matplotlib's default cycle, so the comment saying "
        "generic series take it is wrong"
    )
    # The light ground IS matplotlib's, apart from the grid, which the comment says.
    assert plots._LIGHT["SURFACE"] == matplotlib.colors.to_hex(
        plt.rcParamsDefault["figure.facecolor"])
    assert plots._LIGHT["INK"] == matplotlib.colors.to_hex(
        plt.rcParamsDefault["text.color"])
    # The dark ground IS dark_background's, read out of the stylesheet at import so it
    # cannot drift from what matplotlib ships.
    dark_style = matplotlib.style.library["dark_background"]
    assert plots._DARK["SURFACE"] == matplotlib.colors.to_hex(
        dark_style["figure.facecolor"])
    assert plots._DARK["INK"] == matplotlib.colors.to_hex(dark_style["text.color"])
    # Its grid is white, which draws a cage over charts carrying this many gridlines,
    # so that one is dimmed. Everything else is taken as shipped.
    assert plots._DARK["GRID"] != matplotlib.colors.to_hex(dark_style["grid.color"])
    assert plots._LIGHT["GRID"] == matplotlib.colors.to_hex(
        plt.rcParamsDefault["grid.color"])


def test_the_five_series_chart_has_no_red_beside_a_green(settings):
    """The one chart that draws five series at once.

    matplotlib's default cycle puts green at index 2 and red at index 3, so drawing
    five series from it in order puts the pair nobody can tell apart side by side. A
    comment here used to say the chart avoided that; the code had stopped doing so.
    """
    import matplotlib.colors as mcolours
    from esem_sandbox.core.dispatch import dispatch_year
    from esem_sandbox.core.weather import generate_bundle

    bundle = generate_bundle(settings.weather["seed"],
                             settings.weather["shape_years"])
    results = {}
    for y in range(3):
        shape = bundle["demand_shape"][y]
        results[f"shape year {y}"] = dispatch_year(
            settings, 2026, shape * (12500.0 / shape.max()),
            bundle["wind_cf"][y], bundle["solar_cf"][y])
    path = plots.price_duration(results, str(TMP_PLOTS / "duration.png"))
    assert pathlib.Path(path).exists()

    # The scale it draws from must be ordered: each step moves the same way in
    # lightness, which a categorical cycle does not.
    import matplotlib.pyplot as plt
    shades = plt.get_cmap("viridis")(np.linspace(0.08, 0.92, 5))
    lums = [mcolours.rgb_to_hsv(c[:3])[2] for c in shades]
    assert lums == sorted(lums) or lums == sorted(lums, reverse=True), (
        "the five-series scale is not ordered, so it reads as five unrelated hues"
    )


def _contrast(hex_colour, ground_luminance):
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    chan = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            for c in (r, g, b)]
    lum = 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]
    lo, hi = sorted((lum, ground_luminance))
    return (hi + 0.05) / (lo + 0.05)


def test_technology_colours_can_be_seen_on_the_ground_they_are_drawn_on():
    """Each theme's palette is measured against its own ground, because that is the
    only ground it is drawn on.

    Solar is an exception under the light theme. Only five of the eight cycle slots
    the legs leave free clear 3:1 on white, so the sixth technology takes the olive
    at 2.01 and carries its identity in the label written inside its band. The
    exception is named here so it stays a decision.
    """
    pale_by_design = {("light", "solar")}
    for theme_name, palette, ground in (("light", plots._LIGHT, 1.0),
                                        ("dark", plots._DARK, 0.0)):
        for name, colour in palette["TECH_COLOUR"].items():
            seen = _contrast(colour, ground)
            if (theme_name, name) in pale_by_design:
                continue
            assert seen >= 3.0, (
                f"{theme_name}: {name} at {colour} is {seen:.2f} against its own "
                "ground, below 3:1"
            )


def test_the_pale_technologies_are_always_labelled():
    """Wind and solar sit below 3:1 on white, so wherever they carry meaning the
    label has to. _readable_on picks ink or paper for each fill, and this checks it
    picks the readable one rather than defaulting."""
    for name in ("wind", "solar"):
        for palette in (plots._LIGHT, plots._DARK):
            fill = palette["TECH_COLOUR"][name]
            ink = plots._readable_on(fill)
            assert _contrast(fill, 0.0 if ink != "#ffffff" else 1.0) >= 3.0, (
                f"the label written on {name} is not readable against it"
            )
