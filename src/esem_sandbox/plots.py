"""Charts. Every one is captioned illustrative, because it is."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402
import numpy as np  # noqa: E402

from .core.report import duration_curve  # noqa: E402
from .core.windows import Window  # noqa: E402

CAPTION = "Illustrative only. A stylised one-region system, not a forecast."

# One typeface across every chart. Named with a fallback chain rather than set
# outright: the figures are rendered here and committed, so the reader never needs
# the font, but continuous integration regenerates them on a machine that may not
# have it, and an unsatisfiable font family makes matplotlib warn on every call.
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = [
    "Open Sans", "DejaVu Sans", "Liberation Sans", "FreeSans", "sans-serif",
]

# Matplotlib's own grounds, taken from its stylesheets rather than mixed by hand: the
# default style for light, dark_background for dark. Read out of matplotlib at import
# so they cannot drift from what it actually ships, and so a reader can check the
# claim rather than take it.
_D = plt.rcParamsDefault
_DK = matplotlib.style.library["dark_background"]
_hex = matplotlib.colors.to_hex

# Six groups, not the fleet's 16 rows. More than about seven colours carrying meaning
# stops being readable, and nobody reading this needs to tell two coal stations apart.
TECH_GROUP = {
    "coal": "coal", "ccgt": "gas", "ocgt": "gas", "hydro": "hydro", "phes": "hydro",
    "battery": "storage", "wind": "wind", "solar": "solar",
}
TECH_ORDER = ("coal", "gas", "hydro", "storage", "wind", "solar")

# Matplotlib ships a different colour cycle for each ground: tab10 with the default
# style, and a paler set with dark_background. Both themes here take the cycle that
# belongs to their own ground, so a colour only ever has to be legible against the
# ground it is drawn on.
#
# The first two slots go to the legs. Technologies take six of the rest, chosen for
# contrast against that ground and ordered so that matplotlib's red never sits beside
# its green, which is the pair a red-green colour blindness cannot separate. On white
# only five of the eight remaining slots clear 3:1, so solar takes the olive at 2.01
# and carries its identity in the label written inside its band. On black every slot
# clears 3:1 with room to spare.
_TECH_SLOTS = {"light": (7, 3, 4, 5, 2, 8), "dark": (2, 3, 4, 7, 6, 5)}


def _palette(style, which: str) -> dict:
    cycle = tuple(_hex(c) for c in style["axes.prop_cycle"].by_key()["color"])
    return {
        "SURFACE": _hex(style["figure.facecolor"]),
        "INK": _hex(style["text.color"]),
        "INK_2": _hex(style["axes.labelcolor"]),
        "INK_MUTED": _hex(style["xtick.color"]),
        "GRID": _hex(style["grid.color"]),
        "SERIES": cycle,
        "LEG_COLOUR": {"merchant": cycle[0], "esem": cycle[1]},
        "TECH_COLOUR": {t: cycle[i] for t, i in zip(TECH_ORDER, _TECH_SLOTS[which])},
    }


_LIGHT = _palette(_D, "light")
_DARK = _palette(_DK, "dark")
# dark_background's grid is white, which at full strength draws a cage over the data
# on charts carrying this many gridlines. Its own colour, dimmed.
_DARK["GRID"] = "#4d4d4d"

SURFACE = _LIGHT["SURFACE"]
INK = _LIGHT["INK"]
INK_2 = _LIGHT["INK_2"]
INK_MUTED = _LIGHT["INK_MUTED"]
GRID = _LIGHT["GRID"]
SERIES = _LIGHT["SERIES"]
LEG_COLOUR = _LIGHT["LEG_COLOUR"]
TECH_COLOUR = _LIGHT["TECH_COLOUR"]


class theme:
    """Draw on a dark ground inside this block. Restores the palette on exit."""

    def __init__(self, name: str = "light"):
        self.want = _DARK if name == "dark" else _LIGHT

    def __enter__(self):
        globals().update(self.want)
        return self

    def __exit__(self, *exc):
        globals().update(_LIGHT)
        return False


LEG_LABEL = {"merchant": "merchant", "esem": "with the scheme"}

# Identity is never carried by colour alone. Each leg also gets its own marker, which
# matters more here than usual: for most of a run the two legs sit on exactly the same
# number, and one line hidden under another reads as a missing series rather than as
# an identical one.
LEG_MARKER = {"merchant": "o", "esem": "s"}


def _luminance(hex_colour: str) -> float:
    """Relative luminance of a colour, on the WCAG definition."""
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                for c in (r, g, b)]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _readable_on(hex_colour: str) -> str:
    """Black or white, whichever can be read on this fill.

    Some categorical hues sit below 3:1 against the chart surface, which obliges
    visible labels wherever they carry meaning, and a label is only visible if it is
    the right way round on its own fill.

    The two candidates are black and white rather than the theme's ink, which under
    the dark theme is white and so left both branches returning the same colour: the
    palest fills carried white labels on a pale ground. The crossover, where black
    and white give equal contrast against the same fill, is at luminance 0.179.
    """
    return "#000000" if _luminance(hex_colour) > 0.179 else "#ffffff"


def _years(ax) -> None:
    """Whole years on a year axis.

    Matplotlib will happily put a tick at 2027.5, which is not a year, and a reader
    who sees one starts wondering what happened in the middle of it.
    """
    ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=8))


def _style(ax) -> None:
    """Recessive axes and grid. The data is the thing with contrast."""
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    # Font sizes are for a figure that GitHub will scale DOWN to its column width.
    # A wide chart loses more, so charts meant for the documents are kept narrow and
    # tall rather than wide, and these sizes survive the scaling.
    ax.tick_params(colors=INK_2, labelsize=10, length=3, color=GRID)
    ax.grid(True, color=GRID, lw=0.8, alpha=0.9)
    ax.set_axisbelow(True)
    ax.title.set_color(INK)
    ax.title.set_fontsize(12.5)
    ax.xaxis.label.set_color(INK_2)
    ax.yaxis.label.set_color(INK_2)
    ax.xaxis.label.set_fontsize(10)
    ax.yaxis.label.set_fontsize(10)


def titled(ax, text, **kw):
    """A title that keeps its colour.

    set_title AFTER _style resets the colour to the default, which is black. On a
    pale ground that is invisible only to a careful eye; on the dark one it is
    invisible to everybody, and every chart here is served in both.
    """
    ax.set_title(text, color=INK, **kw)


def worst_week(result, window: Window, firm_capacity_mw: float, path: str) -> str:
    """Residual demand against the stack through the located worst window.

    The chart the duration-curve exercise is built on: it shows storage
    draining, and the hours where nothing physical is left to dispatch.
    """
    sel = window.hours
    residual = result.residual_mw[sel]
    price = result.price[sel]
    hours = np.arange(len(residual))

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(8.2, 6.2), sharex=True, facecolor=SURFACE,
        gridspec_kw={"height_ratios": [2, 1]})
    # Both axes go through _style, which is what puts the theme's surface behind
    # them. A chart that sets its own colours instead draws white boxes on a dark
    # figure.
    for a in (ax, ax2):
        _style(a)
    ax.fill_between(hours, 0, np.minimum(residual, firm_capacity_mw),
                    color=SERIES[0], alpha=0.55, label="met by the stack")
    ax.fill_between(hours, np.minimum(residual, firm_capacity_mw), residual,
                    where=residual > firm_capacity_mw, color=SERIES[1],
                    interpolate=True, label="above the stack")
    ax.axhline(firm_capacity_mw, color=INK, lw=1.4, ls="--",
               label="firm capacity")
    ax.set_ylabel("residual demand, MW")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=3,
              frameon=False, fontsize=9.5, labelcolor=INK)
    titled(ax, f"Worst window: {window.days} days from day {window.start_day}",
           loc="left")

    ax2.plot(hours, price, color=SERIES[2], lw=1.4)
    ax2.set_yscale("symlog", linthresh=100)
    ax2.set_ylabel("price, dollars per MWh")
    ax2.set_xlabel("hour of the window")
    fig.text(0.01, 0.01, CAPTION, fontsize=8, color=INK_MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)
    return path


def price_duration(results: dict[str, object], path: str) -> str:
    """Price duration curves, log price axis, top 10 per cent of hours."""
    fig, ax = plt.subplots(figsize=(7.6, 4.8), facecolor=SURFACE)
    _style(ax)
    # A sequential scale, not the categorical cycle. Two reasons, and the comment
    # that used to sit here claimed the first while the code did the opposite.
    #
    # The shape-years are ORDERED, mild through to the lull-on-heat year, so a scale
    # that runs one way says something true about them that five unrelated hues do
    # not. The default cycle puts its green at index 2 and its red at index 3, so
    # the one chart in this module that draws five series was drawing a green curve
    # next to a red one.
    shades = plt.get_cmap("viridis")(np.linspace(0.08, 0.92, max(len(results), 2)))
    for i, (label, res) in enumerate(results.items()):
        curve = duration_curve(res.price)
        share = np.arange(len(curve)) / len(curve) * 100.0
        keep = share <= 10.0
        ax.plot(share[keep], np.clip(curve[keep], 1.0, None), lw=1.6,
                color=shades[i], label=label)
    ax.set_yscale("log")
    ax.set_xlabel("per cent of hours at or above this price")
    ax.set_ylabel("price, dollars per MWh")
    ax.legend(frameon=False, fontsize=9.5, labelcolor=INK)
    titled(ax, "Price duration, dearest tenth of the year", loc="left")
    fig.text(0.01, 0.01, CAPTION, fontsize=8, color=INK_MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)
    return path


def _fleet_by_group(tick) -> dict[str, float]:
    out = {name: 0.0 for name in TECH_ORDER}
    for tech, mw in tick.capacity_by_technology.items():
        group = TECH_GROUP.get(tech)
        if group:
            out[group] += mw
    return out


def _panel_capacity(ax, legs) -> None:
    """The fleet in service in the final year. Magnitude and identity, so a stacked
    bar.

    In service, which is not the same as decided: plant committed in the last few
    years of a run is still being built when the run ends, and a panel titled for
    what was built would be counting something the chart does not show.
    """
    labels, bottoms = [], []
    for name, result in legs.items():
        labels.append(LEG_LABEL[name])
        bottoms.append(_fleet_by_group(result.ticks[-1]))
    # Measured against the TALLEST STACK, not against the running base. Using the
    # base meant a band was compared with whatever had been drawn under it so far, so
    # hydro at 1.9 GW cleared the bar while sitting in a 70 GW column and its label
    # was written across a sliver too thin to hold it.
    tallest = max(sum(b[g] for g in TECH_ORDER) / 1000.0 for b in bottoms)
    base = np.zeros(len(labels))
    for group in TECH_ORDER:
        values = np.array([b[group] / 1000.0 for b in bottoms])
        # A two-point gap of surface colour between segments, so the boundary is a
        # gap rather than a colour change nobody can see.
        ax.bar(labels, values, bottom=base, color=TECH_COLOUR[group], width=0.55,
               edgecolor=SURFACE, linewidth=2, label=group)
        for x, (v, b) in enumerate(zip(values, base)):
            # A label only goes inside a segment big enough to hold it, and "big
            # enough" is a share of the axis rather than a number of gigawatts: on a
            # 70 GW stack a 1.9 GW slice is a two-millimetre band, and a label
            # written across it lands on its neighbours.
            if v > 0.055 * tallest:
                ax.text(x, b + v / 2, f"{group} {v:,.1f}", ha="center", va="center",
                        fontsize=9.5, color=_readable_on(TECH_COLOUR[group]))
        base = base + values
    # Whatever was too thin to label inside gets named in a legend instead, so no
    # segment is identified by its colour alone.
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, ncol=3,
              loc="upper left", handlelength=1.0, columnspacing=0.9,
              handletextpad=0.35, borderaxespad=0.2)
    for x, total in enumerate(base):
        ax.text(x, total * 1.02, f"{total:,.1f} GW", ha="center", va="bottom",
                fontsize=11, color=INK)
    ax.set_ylabel("installed capacity, GW")
    titled(ax, "The fleet at the end")
    ax.set_ylim(0, base.max() * 1.40)   # headroom for the legend and the totals


def _panel_unserved(ax, legs, standard) -> None:
    """The reliability outcome, against the standard it is measured by."""
    for name, result in legs.items():
        years = [t.year for t in result.ticks]
        share = [t.unserved_fraction / standard for t in result.ticks]
        ax.plot(years, share, lw=2.4 if name == "merchant" else 1.8,
                color=LEG_COLOUR[name], label=LEG_LABEL[name],
                marker=LEG_MARKER[name], markersize=5, markeredgecolor=SURFACE,
                markeredgewidth=1.2)
    ax.axhline(1.0, color=INK_MUTED, lw=1.4, ls="--")
    ax.text(years[0], 1.15, "the reliability standard", fontsize=9.5, color=INK_2)
    ax.set_ylabel("unserved energy, times the standard")
    titled(ax, "Reliability, each year")
    _years(ax)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2)


def _panel_duration(ax, legs, year_index, year) -> None:
    """Price duration for the year the two legs differ most, both of them.

    The year the MERCHANT leg does worst is the obvious choice and the wrong one:
    early in a run it is a year whose awards have not been built yet, so the two
    curves lie exactly on top of each other and the panel reads as a missing series.
    The year they differ most is the year the mechanism did something.
    """
    for name, result in legs.items():
        curve = result.ticks[year_index].price_duration
        share = np.arange(len(curve)) / len(curve) * 100.0
        keep = share <= 5.0
        ax.plot(share[keep], np.clip(curve[keep], 1.0, None),
                lw=2.6 if name == "merchant" else 1.8,
                color=LEG_COLOUR[name], label=LEG_LABEL[name])
    ax.set_yscale("log")
    ax.set_xlabel("per cent of hours at or above this price")
    ax.set_ylabel("price, \\$/MWh")
    titled(ax, f"Price duration in {year}, dearest twentieth")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2)


def _panel_hurdle(ax, legs) -> None:
    """Every build, as the rent it expected against the hurdle it had to clear.

    A point above the diagonal is a plant that got built and why. The diagonal is
    the decision itself, so it is drawn rather than described.
    """
    for name, result in legs.items():
        x = [b.hurdle_per_mw_year / 1000.0 for t in result.ticks for b in t.builds]
        y = [b.expected_rent_per_mw_year / 1000.0
             for t in result.ticks for b in t.builds]
        if not x:
            continue
        ax.scatter(x, y, s=26, color=LEG_COLOUR[name], label=LEG_LABEL[name],
                   alpha=0.75, edgecolor=SURFACE, linewidth=1.2, zorder=3)
    lim = max(ax.get_xlim()[1], ax.get_ylim()[1])
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.plot([0, lim], [0, lim], color=INK_MUTED, lw=1.4, ls="--", zorder=2)
    ax.fill_between([0, lim], [0, lim], [lim, lim], color=SERIES[0], alpha=0.16,
                    zorder=1)
    ax.text(0.03, 0.95, "anything in the shaded half was worth building",
            transform=ax.transAxes, fontsize=7.5, color=INK_2, va="top")
    ax.set_xlabel("hurdle, \\$000 per MW-year")
    ax.set_ylabel("expected rent, \\$000 per MW-year")
    titled(ax, "Every build, and the test it passed")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2, loc="lower right",
              handletextpad=0.4)


def _panel_cap(ax, legs) -> None:
    """What insurance cost, year by year."""
    for name, result in legs.items():
        years = [t.year for t in result.ticks]
        ax.plot(years, [t.cap_premium_per_mwh for t in result.ticks], lw=2,
                color=LEG_COLOUR[name], label=LEG_LABEL[name])
    ax.set_ylabel("cap premium, \\$/MWh")
    titled(ax, "What a cap cost")
    _years(ax)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2)


def _panel_levy(ax, esem) -> None:
    """One series, so no legend: the title names it."""
    years = [t.year for t in esem.ticks]
    ax.bar(years, [t.levy_per_mwh for t in esem.ticks], color=SERIES[1], width=0.7,
           edgecolor=SURFACE, linewidth=1.5)
    ax.set_ylabel("levy, \\$/MWh")
    titled(ax, "What consumers paid the scheme")
    _years(ax)


def _panel_costs(ax, legs, settings) -> None:
    """The headline, and the reason it needs two bars rather than one.

    A bill is mostly a payment from consumers to producers. A scheme that builds
    capacity lowers the pool price and cuts the bill by far more than it costs, and
    that reduction is a transfer rather than a saving. Showing the bill alone would
    report the transfer as a benefit, so both are here and the gap between them is
    labelled.
    """
    names = list(legs)
    width = 0.36
    x = np.arange(2)
    bills = [legs[n].consumer_cost(settings) / 1e9 for n in names]
    real = [legs[n].resource_cost(settings) / 1e9 for n in names]
    for i, n in enumerate(names):
        ax.bar(x[0] + (i - 0.5) * width, bills[i], width, color=LEG_COLOUR[n],
               edgecolor=SURFACE, linewidth=2, label=LEG_LABEL[n])
        ax.bar(x[1] + (i - 0.5) * width, real[i], width, color=LEG_COLOUR[n],
               edgecolor=SURFACE, linewidth=2)
    top = max(bills + real)
    for i in range(2):
        for j, value in enumerate([bills, real][i]):
            ax.text(x[i] + (j - 0.5) * width, value + top * 0.015, f"{value:,.0f}",
                    ha="center", fontsize=8, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels(["the bill", "the resource cost"])
    ax.set_ylabel("\\$bn over the horizon")
    titled(ax, "What it costs, two ways", pad=16)
    # BELOW the axes. The caveat needs the top of the panel and is four lines wide,
    # so a legend in the upper corner covered its right-hand end: the note read
    # "the bill moves $38.9bn and the resource cost $1.4b" with the rest under the
    # legend box.
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, loc="upper center",
              bbox_to_anchor=(0.5, -0.09), ncol=2, handletextpad=0.4)
    moved = bills[0] - bills[1]
    saved = real[0] - real[1]
    # Dollar signs are escaped everywhere text is drawn. Unescaped, matplotlib reads
    # the span between two of them as mathtext and silently italicises the words in
    # between, which turned this note into "bill moves 2.9bn, resourcecost1.2bn".
    # Above the axes rather than inside them. Inside, it competed with the legend
    # for the only empty corner, and the loser was whichever was drawn first.
    # The caveat goes on the picture, not in a footnote somebody reads afterwards:
    # a room shown the left-hand pair without it takes away a number this is one
    # draw of. It is written as an INSTRUCTION rather than as a claim about what the
    # seeds show, because a claim about what the seeds show goes stale the moment
    # anybody recalibrates the fleet, and a chart carrying a sentence that used to be
    # true is worse than one carrying none.
    # INSIDE the axes, under the title. At 1.01 it sat in the same strip the title
    # occupies and the two printed over each other.
    ax.text(0.02, 0.97,
            f"the bill moves \\${abs(moved):,.1f}bn and the resource cost "
            f"\\${abs(saved):,.1f}bn.\nThe \\${abs(moved - saved):,.1f}bn "
            "between them is a transfer.\n"
            "One weather sequence. Read the ten-seed envelope\nbefore quoting "
            "the resource-cost line.",
            transform=ax.transAxes, fontsize=9.5, color=INK_2, va="top")
    ax.set_ylim(0, top * 1.55)


def _panel_lane(ax, esem) -> None:
    """What the scheme sought, and what it contracted."""
    years = [t.year for t in esem.ticks]
    sought = [t.lane_volume_mw for t in esem.ticks]
    got = [sum(a.firm_mw for a in t.awards) for t in esem.ticks]
    ax.bar(years, sought, color=SERIES[2], width=0.7, edgecolor=SURFACE,
           linewidth=1.5, label="sought, firm MW")
    ax.plot(years, got, lw=2, color=SERIES[1], marker="o", markersize=4,
            markeredgecolor=SURFACE, markeredgewidth=1.2, label="contracted, firm MW")
    ax.set_ylabel("firm capacity, MW")
    titled(ax, "What the lane asked for, and got")
    _years(ax)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2)


def dashboard(legs: dict, settings, path: str) -> str:
    """Eight panels, one picture, both legs of a paired run."""
    standard = settings.reliability["standard_use_fraction"]
    esem = legs["esem"]
    gap = [abs(a.unserved_fraction - b.unserved_fraction)
           for a, b in zip(legs["merchant"].ticks, legs["esem"].ticks)]
    worst = int(np.argmax(gap)) if max(gap) > 0 else int(
        np.argmax([t.unserved_fraction for t in legs["merchant"].ticks]))

    # Four rows of two, not two of four. GitHub scales a figure down to its column
    # width, so a 22-inch-wide picture arrives with 4-point type on it. Tall and
    # narrow loses far less, and the panels are read in order anyway.
    fig, axes = plt.subplots(4, 2, figsize=(12.5, 17.5), facecolor=SURFACE)
    fig.subplots_adjust(hspace=0.38, wspace=0.22, top=0.945, bottom=0.035)
    flat = axes.ravel()
    for ax in flat:
        _style(ax)
    _panel_capacity(flat[0], legs)
    _panel_unserved(flat[1], legs, standard)
    _panel_duration(flat[2], legs, worst, legs["merchant"].ticks[worst].year)
    _panel_hurdle(flat[3], legs)
    _panel_costs(flat[4], legs, settings)
    _panel_lane(flat[5], esem)
    _panel_levy(flat[6], esem)
    _panel_cap(flat[7], legs)

    horizon = len(legs["merchant"].ticks)
    fig.suptitle(f"One region, {horizon} years, with and without the procurement "
                 "scheme",
                 fontsize=17, color=INK, x=0.011, ha="left", y=0.985)
    fig.text(0.011, 0.962,
             f"{legs['merchant'].draw.growth_path} demand growth at "
             f"{legs['merchant'].draw.annual_growth:.1%} a year, one weather sequence "
             "shared by both legs.", fontsize=11, color=INK_2, ha="left")
    fig.text(0.011, 0.012, CAPTION, fontsize=8.5, color=INK_MUTED, ha="left")
    fig.savefig(path, dpi=130, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return path
