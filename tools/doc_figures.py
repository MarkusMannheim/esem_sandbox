"""Figures for the documentation, generated from the model.

Two things in these documents are much easier to see than to read, and both were
prose only. They are drawn from a live run rather than authored, so they cannot drift
away from what the model does: regenerate with `python tools/doc_figures.py`.

1. Reliability against firm capacity. The single most counter-intuitive result here
   is that taking a few per cent of firm plant away multiplies blackouts. A table of
   six rows states it; a curve shows why the argument about capacity adequacy is
   ferocious.
2. Where a cap's money is. A cap written at $300/MWh earns almost all of it in a
   handful of hours, which is the reason contracts settle hour by hour rather than
   against an average. The shaded area is the payout; the dashed line is what
   averaging the year first would have suggested.
"""

from dataclasses import replace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from esem_sandbox.config import load_settings  # noqa: E402
from esem_sandbox.core.dispatch import dispatch_year  # noqa: E402
from esem_sandbox.core.weather import generate_bundle  # noqa: E402
from esem_sandbox import plots  # noqa: E402
from esem_sandbox.plots import CAPTION, _style, theme, titled  # noqa: E402

OUT = "outputs/canonical"
VARIABLE = {"wind", "solar", "rooftop"}


def _year(settings, bundle, scale=1.0, shape=4, peak=12_500.0):
    fleet = tuple(u if u.technology in VARIABLE
                  else replace(u, capacity_mw=u.capacity_mw * scale)
                  for u in settings.fleet)
    demand = bundle["demand_shape"][shape]
    demand = demand * (peak / demand.max())
    return dispatch_year(replace(settings, fleet=fleet), 2026, demand,
                         bundle["wind_cf"][shape], bundle["solar_cf"][shape])


def reliability_curve(settings, bundle, path):
    scales = (1.00, 0.97, 0.94, 0.91, 0.88, 0.85)
    firm, unserved = [], []
    for s in scales:
        r = _year(settings, bundle, s)
        firm.append(r.firm_capacity_mw)
        unserved.append(r.unserved_mwh.sum() / 1000.0)
    fig, ax = plt.subplots(figsize=(7.4, 4.6), facecolor=plots.SURFACE)
    _style(ax)
    ax.plot(firm, unserved, color=plots.SERIES[0], lw=2.2, marker="o", ms=5, zorder=3)
    base_f, base_u = firm[0], unserved[0]
    ax.annotate(f"{base_u:,.1f} GWh", (base_f, base_u), textcoords="offset points",
                xytext=(6, 10), fontsize=9.5, color=plots.INK)
    ax.annotate(f"{unserved[-1]:,.1f} GWh\nat {1-scales[-1]:.0%} less firm plant",
                (firm[-1], unserved[-1]), textcoords="offset points",
                xytext=(-12, -34), fontsize=9.5, color=plots.INK, ha="right")
    # The axis runs BACKWARDS on purpose, so the eye travels the way the sentence
    # does: take plant away, and blackouts rise. Unmarked, a reader who does not
    # notice reads the curve as the opposite claim, so the label says which way it
    # goes rather than leaving it to the tick values.
    ax.set_xlabel("firm capacity (MW), falling to the right")
    ax.set_ylabel("unserved energy (GWh)")
    titled(ax, "A small change in firm capacity is a large change in blackouts",
                 loc="left")
    ax.invert_xaxis()
    fig.text(0.01, 0.015, CAPTION, fontsize=8, color=plots.INK_MUTED)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=150, facecolor=plots.SURFACE)
    plt.close(fig)
    return path, list(zip(firm, unserved))


def where_a_cap_pays(settings, bundle, path):
    """A cap's whole value is in a few hours, so it cannot be settled on an average.

    Only the dearest 250 hours are drawn. The other 8,510 sit below the strike and
    pay nothing, and including them makes the part that matters one pixel wide.
    """
    strike = float(settings.contracts["cap_strike_per_mwh"])
    price = np.sort(np.asarray(_year(settings, bundle).price))[::-1]
    payout = float(np.clip(price - strike, 0.0, None).sum())
    naive = max(0.0, price.mean() - strike) * len(price)
    above = int((price > strike).sum())
    show = 250
    hours = np.arange(1, show + 1)
    head = price[:show]

    fig, ax = plt.subplots(figsize=(7.4, 4.6), facecolor=plots.SURFACE)
    _style(ax)
    ax.set_yscale("log")
    ax.plot(hours, np.maximum(head, 1.0), color=plots.INK_2, lw=1.6, zorder=3)
    ax.fill_between(hours, strike, np.maximum(head, strike), color=plots.SERIES[1],
                    alpha=0.6, zorder=2,
                    label=f"what the cap pays: {payout:,.0f} dollars per MW")
    ax.axhline(strike, color=plots.SERIES[0], lw=1.6, zorder=4,
               label=f"the strike: {strike:,.0f} dollars per MWh")
    ax.axhline(price.mean(), color=plots.INK, lw=1.4, ls="--", zorder=4,
               label=f"the year's average: {price.mean():,.0f}, below the strike, "
                     f"so averaging first pays nothing")
    ax.set_xlim(0, show)
    ax.set_xlabel(f"the dearest {show} hours of the year "
                  f"(only {above} clear the strike; the other "
                  f"{len(price) - show:,} hours are not drawn)")
    ax.set_ylabel("dollars per MWh, log scale")
    titled(ax, "Almost all of a cap's money is in a handful of hours", loc="left")
    ax.legend(frameon=False, fontsize=9.5, loc="upper center",
              bbox_to_anchor=(0.5, -0.22), ncol=1, labelcolor=plots.INK)
    fig.text(0.01, 0.015, CAPTION, fontsize=8, color=plots.INK_MUTED)
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    fig.savefig(path, dpi=150, facecolor=plots.SURFACE)
    plt.close(fig)
    return path, payout, naive, above


def the_forward_view(settings, bundle, path, tech_name="ocgt"):
    """What an investor looks at before deciding, and what caution costs them.

    The left panel is the enumeration: every future, priced at every distance ahead.
    The right is what comes out of it for one technology, and where a cautious
    investor's own valuation sits against the plain average.
    """
    from esem_sandbox.core.agents import PRODUCER, default_roster
    from esem_sandbox.core.forward import EntryState, cell_plan, forward_view
    from esem_sandbox.core.investment import build_size_mw, evaluate

    cells = cell_plan(settings)
    offsets = list(settings.forward["anchor_offsets"])
    view = forward_view(settings, settings.fleet, bundle, year=2026,
                        peak_mw=12_500.0, entry=EntryState())
    tech = settings.tech(tech_name)
    agent = [a for a in default_roster() if a.kind == PRODUCER][0]
    rents = view.lifetime_rent(tech)
    weights = view.weights
    mean = float(rents @ weights)
    size = build_size_mw(12_500.0, tech, settings)
    bare = evaluate(view, tech, agent, settings, exposure=1.0, capacity_mw=size)
    hedged = evaluate(view, tech, agent, settings, exposure=0.4, capacity_mw=size)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.4, 7.6),
                                   facecolor=plots.SURFACE,
                                   gridspec_kw={"height_ratios": [1, 1.35]})
    for ax in (ax1, ax2):
        _style(ax)

    # Left: the enumeration, drawn to scale.
    rows, cols = 5, 9
    for i in range(len(cells)):
        r, c = divmod(i, cols)
        for j, off in enumerate(offsets):
            # One colour for all three blocks. Three colours said the horizons hold
            # DIFFERENT futures; they hold the same 45, dispatched three times.
            ax1.add_patch(plt.Rectangle((c + j * (cols + 1.4), rows - 1 - r),
                                        0.82, 0.82, facecolor=plots.SERIES[0],
                                        alpha=0.85, edgecolor="none"))
    for j, off in enumerate(offsets):
        ax1.text(j * (cols + 1.4) + cols / 2 - 0.5, rows + 0.35,
                 f"+{off} years", ha="center", fontsize=10.5, color=plots.INK)
    ax1.set_xlim(-0.6, 3 * cols + 2 * 1.4)
    ax1.set_ylim(-1.4, rows + 1.1)
    ax1.set_aspect("equal", adjustable="box")
    ax1.set_anchor("N")            # keep the two panel titles on one line
    ax1.set_xticks([]); ax1.set_yticks([])
    ax1.grid(False)
    for side in ("left", "bottom"):
        ax1.spines[side].set_visible(False)
    ax1.text(0, -0.95, f"the SAME {len(cells)} possible futures, dispatched at each "
             f"distance:\n{len(cells) * len(offsets)} whole years, every year of the run",
             fontsize=10, color=plots.INK_2, va="top")
    titled(ax1, "Every tick, the model prices the future by enumerating it",
                  loc="left")

    # Right: what that produces for one technology.
    order = np.argsort(rents)
    ax2.scatter(rents[order] / 1e6, np.arange(len(rents)), s=16,
                color=plots.SERIES[0], zorder=3, alpha=0.85)
    for x, colour, label in (
            (mean, plots.INK, f"plain average  ${mean:,.0f}"),
            (bare.certainty_equivalent_per_mw_year, plots.SERIES[3],
             f"what a cautious investor counts on  "
             f"${bare.certainty_equivalent_per_mw_year:,.0f}"),
            (hedged.certainty_equivalent_per_mw_year, plots.SERIES[4],
             f"the same investor, 60% contracted  "
             f"${hedged.certainty_equivalent_per_mw_year:,.0f}")):
        ax2.axvline(x / 1e6, color=colour, lw=1.6, zorder=4)
        ax2.plot([], [], color=colour, lw=1.6, label=label)
    ax2.set_xlabel("$m per megawatt per year, in each future")
    ax2.set_ylabel(f"the {len(rents)} futures, poorest first")
    ax2.set_yticks([])
    ax2.legend(frameon=False, fontsize=9.5, loc="lower right",
               labelcolor=plots.INK)
    titled(ax2, "A contract is worth the gap it closes", loc="left")

    fig.text(0.01, 0.015, CAPTION, fontsize=8, color=plots.INK_MUTED)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, dpi=150, facecolor=plots.SURFACE)
    plt.close(fig)
    return path, mean, bare.certainty_equivalent_per_mw_year, \
        hedged.certainty_equivalent_per_mw_year, len(cells), len(offsets)


def what_hesitancy_costs(settings, bundle, path, tech_name="ocgt"):
    """How much of the bar a plant must clear is caution rather than cost.

    Each producer here has its own tolerance for uncertainty, and that tolerance is
    most of what it demands. The bar is the fixed cost of owning the plant plus what
    the investor charges itself for carrying an uncertain income; the marker is the
    same investor once most of its output is sold forward.
    """
    from esem_sandbox.core.agents import PRODUCER, default_roster
    from esem_sandbox.core.forward import EntryState, forward_view
    from esem_sandbox.core.investment import build_size_mw, evaluate

    view = forward_view(settings, settings.fleet, bundle, year=2026,
                        peak_mw=12_500.0, entry=EntryState())
    tech = settings.tech(tech_name)
    size = build_size_mw(12_500.0, tech, settings)
    producers = [a for a in default_roster() if a.kind == PRODUCER]
    producers.sort(key=lambda a: a.risk_aversion)

    names, fixed, caution, contracted = [], [], [], []
    for a in producers:
        bare = evaluate(view, tech, a, settings, exposure=1.0, capacity_mw=size)
        hedged = evaluate(view, tech, a, settings, exposure=0.4, capacity_mw=size)
        names.append(f"{a.name.replace('_', ' ')}\n(caution {a.risk_aversion:.2f})")
        fixed.append(bare.fixed_cost_per_mw_year / 1e3)
        caution.append(bare.risk_discount_per_mw_year / 1e3)
        contracted.append(hedged.hurdle_per_mw_year / 1e3)

    fig, ax = plt.subplots(figsize=(7.4, 4.8), facecolor=plots.SURFACE)
    _style(ax)
    y = np.arange(len(names))
    ax.barh(y, fixed, color=plots.SERIES[0], height=0.55, label="what it costs to own")
    ax.barh(y, caution, left=fixed, color=plots.SERIES[1], height=0.55,
            label="what the uncertainty costs")
    ax.scatter(contracted, y, color=plots.INK, zorder=5, s=42, marker="D",
               label="the same firm, 60% sold forward")
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("$ thousand per megawatt per year")
    titled(ax, "What a gas peaker must earn to be built, and why",
           loc="left")
    ax.legend(frameon=False, fontsize=9.5, loc="upper center",
              bbox_to_anchor=(0.5, -0.16), ncol=2, labelcolor=plots.INK,
              handletextpad=0.6, columnspacing=2.4)
    fig.text(0.01, 0.015, CAPTION, fontsize=8, color=plots.INK_MUTED)
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    fig.savefig(path, dpi=150, facecolor=plots.SURFACE)
    plt.close(fig)
    return path, fixed[0] * 1e3, min(caution) * 1e3, max(caution) * 1e3


def main() -> int:
    settings = load_settings()
    bundle = generate_bundle(settings.weather["seed"], settings.weather["shape_years"])
    # Both themes. GitHub serves whichever the reader has set, and a chart drawn for
    # one is unreadable in the other.
    for suffix, name in (("", "light"), ("_dark", "dark")):
        with theme(name):
            p1, pts = reliability_curve(
                settings, bundle, f"{OUT}/reliability_curve{suffix}.png")
            p2, payout, naive, n = where_a_cap_pays(
                settings, bundle, f"{OUT}/cap_payout{suffix}.png")
            p3, mean, ce, ce_h, ncells, nyears = the_forward_view(
                settings, bundle, f"{OUT}/forward_view{suffix}.png")
            p4, cost, lo, hi = what_hesitancy_costs(
                settings, bundle, f"{OUT}/hesitancy{suffix}.png")
        print(f"wrote {p1}, {p2}, {p3} and {p4}")
    for f, u in pts:
        print(f"    {f:>9,.0f} MW  {u:>8.2f} GWh")
    print(f"    cap pays ${payout:,.0f}/MW-year from {n} hours; "
          f"averaging the year first would pay ${naive:,.0f}")
    print(f"    forward view: {ncells} futures x {nyears} distances = "
          f"{ncells * nyears} dispatched years a tick")
    print(f"    average ${mean:,.0f}, cautious ${ce:,.0f}, "
          f"contracted ${ce_h:,.0f}; the contract returns ${ce_h - ce:,.0f}")
    print(f"    hesitancy: cost ${cost:,.0f}, caution adds ${lo:,.0f} to ${hi:,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
