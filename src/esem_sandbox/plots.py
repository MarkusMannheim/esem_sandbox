"""Charts. Every one is captioned illustrative, because it is."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .core.report import duration_curve  # noqa: E402
from .core.windows import Window  # noqa: E402

CAPTION = "Illustrative only. A stylised one-region system, not a forecast."

# The chart surface and the ink that sits on it. Text wears text colours, never a
# series colour: a coloured mark beside a label carries the identity, and a coloured
# label carries nothing except a reading difficulty.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_MUTED = "#8a8985"
GRID = "#e3e2dd"

# Categorical slots, in FIXED ORDER. A seventh series is never a generated hue: it
# folds into "other" or gets its own panel. Validated rather than eyeballed: worst
# adjacent colour-vision separation 9.1, worst normal-vision separation 19.6, both
# clear of their floors. Three of the six sit below 3:1 against this surface, which
# obliges visible labels wherever they carry meaning, and they have them.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300")

LEG_LABEL = {"merchant": "merchant", "esem": "with the scheme"}
LEG_COLOUR = {"merchant": SERIES[0], "esem": SERIES[1]}

# Six groups, not the fleet's fifteen rows. More than about seven colours carrying
# meaning stops being readable, and nobody in a workshop needs to tell two coal
# stations apart.
TECH_GROUP = {
    "coal": "coal", "ccgt": "gas", "ocgt": "gas", "hydro": "hydro", "phes": "hydro",
    "battery": "storage", "wind": "wind", "solar": "solar",
}
TECH_ORDER = ("coal", "gas", "hydro", "storage", "wind", "solar")
TECH_COLOUR = dict(zip(TECH_ORDER, SERIES))

# Identity is never carried by colour alone. Each leg also gets its own marker, which
# matters more here than usual: for most of a run the two legs sit on exactly the same
# number, and one line hidden under another reads as a missing series rather than as
# an identical one.
LEG_MARKER = {"merchant": "o", "esem": "s"}


def _readable_on(hex_colour: str) -> str:
    """Ink or paper, whichever can be read on this fill.

    Three of the six categorical hues sit below 3:1 against the chart surface, which
    obliges visible labels wherever they carry meaning. A label is only visible if it
    is the right way round on its own fill, so this works it out rather than
    assuming white.
    """
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                for c in (r, g, b)]
    luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    return INK if luminance > 0.42 else "#ffffff"


def _style(ax) -> None:
    """Recessive axes and grid. The data is the thing with contrast."""
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=8, length=3, color=GRID)
    ax.grid(True, color=GRID, lw=0.8, alpha=0.9)
    ax.set_axisbelow(True)
    ax.title.set_color(INK)
    ax.title.set_fontsize(10)
    ax.xaxis.label.set_color(INK_2)
    ax.yaxis.label.set_color(INK_2)
    ax.xaxis.label.set_fontsize(8)
    ax.yaxis.label.set_fontsize(8)


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
        2, 1, figsize=(11, 6.5), sharex=True,
        gridspec_kw={"height_ratios": [2, 1]})
    ax.fill_between(hours, 0, np.minimum(residual, firm_capacity_mw),
                    color="#9DB0AF", label="met by the stack")
    ax.fill_between(hours, np.minimum(residual, firm_capacity_mw), residual,
                    where=residual > firm_capacity_mw, color="#E05500",
                    label="above the stack")
    ax.axhline(firm_capacity_mw, color="#0C4E55", lw=1.4, ls="--",
               label="firm capacity")
    ax.set_ylabel("residual demand, MW")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.set_title(f"Worst window: {window.days} days from day {window.start_day}")

    ax2.plot(hours, price, color="#0C4E55", lw=1.2)
    ax2.set_yscale("symlog", linthresh=100)
    ax2.set_ylabel("price, \\$/MWh")
    ax2.set_xlabel("hour of the window")
    fig.text(0.01, 0.01, CAPTION, fontsize=8, color="#5A6D6F")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def price_duration(results: dict[str, object], path: str) -> str:
    """Price duration curves, log price axis, top 10 per cent of hours."""
    fig, ax = plt.subplots(figsize=(9, 5))
    for label, res in results.items():
        curve = duration_curve(res.price)
        share = np.arange(len(curve)) / len(curve) * 100.0
        keep = share <= 10.0
        ax.plot(share[keep], np.clip(curve[keep], 1.0, None), lw=1.5, label=label)
    ax.set_yscale("log")
    ax.set_xlabel("per cent of hours at or above this price")
    ax.set_ylabel("price, \\$/MWh")
    ax.legend(frameon=False, fontsize=9)
    ax.set_title("Price duration, dearest tenth of the year")
    fig.text(0.01, 0.01, CAPTION, fontsize=8, color="#5A6D6F")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=140)
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
    """What each leg ended up with. Magnitude and identity, so a stacked bar."""
    labels, bottoms = [], []
    for name, result in legs.items():
        labels.append(LEG_LABEL[name])
        bottoms.append(_fleet_by_group(result.ticks[-1]))
    base = np.zeros(len(labels))
    for group in TECH_ORDER:
        values = np.array([b[group] / 1000.0 for b in bottoms])
        # A two-point gap of surface colour between segments, so the boundary is a
        # gap rather than a colour change nobody can see.
        ax.bar(labels, values, bottom=base, color=TECH_COLOUR[group], width=0.55,
               edgecolor=SURFACE, linewidth=2, label=group)
        for x, (v, b) in enumerate(zip(values, base)):
            if v > 1.5:
                ax.text(x, b + v / 2, f"{group} {v:,.1f}", ha="center", va="center",
                        fontsize=7.5, color=_readable_on(TECH_COLOUR[group]))
        base = base + values
    for x, total in enumerate(base):
        ax.text(x, total * 1.02, f"{total:,.1f} GW", ha="center", va="bottom",
                fontsize=9, color=INK)
    ax.set_ylabel("installed capacity, GW")
    ax.set_title("What each leg built")
    ax.set_ylim(0, base.max() * 1.15)


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
    ax.text(years[0], 1.15, "the reliability standard", fontsize=7.5, color=INK_2)
    ax.set_ylabel("unserved energy, times the standard")
    ax.set_title("Reliability, each year")
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
    ax.set_title(f"Price duration in {year}, dearest twentieth")
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
    ax.fill_between([0, lim], [0, lim], [lim, lim], color=SERIES[0], alpha=0.05,
                    zorder=1)
    ax.text(0.03, 0.95, "anything in the shaded half was worth building",
            transform=ax.transAxes, fontsize=7.5, color=INK_2, va="top")
    ax.set_xlabel("hurdle, \\$000 per MW-year")
    ax.set_ylabel("expected rent, \\$000 per MW-year")
    ax.set_title("Every build, and the test it passed")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2, loc="lower right",
              handletextpad=0.4)


def _panel_cap(ax, legs) -> None:
    """What insurance cost, year by year."""
    for name, result in legs.items():
        years = [t.year for t in result.ticks]
        ax.plot(years, [t.cap_premium_per_mwh for t in result.ticks], lw=2,
                color=LEG_COLOUR[name], label=LEG_LABEL[name])
    ax.set_ylabel("cap premium, \\$/MWh")
    ax.set_title("What a cap cost")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2)


def _panel_levy(ax, esem) -> None:
    """One series, so no legend: the title names it."""
    years = [t.year for t in esem.ticks]
    ax.bar(years, [t.levy_per_mwh for t in esem.ticks], color=SERIES[1], width=0.7,
           edgecolor=SURFACE, linewidth=1.5)
    ax.set_ylabel("levy, \\$/MWh")
    ax.set_title("What consumers paid the scheme")


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
    ax.set_title("What it costs, two ways")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2, loc="upper right",
              handletextpad=0.4)
    moved = bills[0] - bills[1]
    saved = real[0] - real[1]
    # Dollar signs are escaped everywhere text is drawn. Unescaped, matplotlib reads
    # the span between two of them as mathtext and silently italicises the words in
    # between, which turned this note into "bill moves 2.9bn, resourcecost1.2bn".
    ax.text(0.02, 0.97,
            f"bill moves \\${abs(moved):,.1f}bn, resource cost "
            f"\\${abs(saved):,.1f}bn\n"
            f"the \\${abs(moved - saved):,.1f}bn between them is a transfer",
            transform=ax.transAxes, fontsize=7.5, color=INK_2, va="top")
    ax.set_ylim(0, top * 1.30)


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
    ax.set_title("What the lane asked for, and got")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2)


def dashboard(legs: dict, settings, path: str) -> str:
    """Eight panels, one picture, both legs of a paired run."""
    standard = settings.reliability["standard_use_fraction"]
    esem = legs["esem"]
    gap = [abs(a.unserved_fraction - b.unserved_fraction)
           for a, b in zip(legs["merchant"].ticks, legs["esem"].ticks)]
    worst = int(np.argmax(gap)) if max(gap) > 0 else int(
        np.argmax([t.unserved_fraction for t in legs["merchant"].ticks]))

    fig, axes = plt.subplots(2, 4, figsize=(22, 10.5), facecolor=SURFACE)
    fig.subplots_adjust(hspace=0.32, wspace=0.26)
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

    fig.suptitle("One region, twenty years, with and without the procurement scheme",
                 fontsize=14, color=INK, x=0.011, ha="left", y=0.985)
    fig.text(0.011, 0.955,
             f"{legs['merchant'].draw.growth_path} demand growth at "
             f"{legs['merchant'].draw.annual_growth:.1%} a year, one weather sequence "
             "shared by both legs.", fontsize=9, color=INK_2, ha="left")
    fig.text(0.011, 0.012, CAPTION, fontsize=8.5, color=INK_MUTED, ha="left")
    fig.savefig(path, dpi=130, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return path
