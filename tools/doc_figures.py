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
import matplotlib.ticker
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from esem_sandbox.config import load_settings  # noqa: E402
from esem_sandbox.core.dispatch import dispatch_year  # noqa: E402
from esem_sandbox.core.weather import generate_bundle  # noqa: E402
from esem_sandbox import plots  # noqa: E402
from esem_sandbox.plots import _style, finish, theme, titled  # noqa: E402

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
    ax.annotate(f"The packaged fleet: {base_u:,.1f} GWh", (base_f, base_u),
                textcoords="offset points", xytext=(4, -14), fontsize=9.5,
                color=plots.INK, ha="right", va="top")
    ax.annotate(f"{1-scales[-1]:.0%} less firm plant: {unserved[-1]:,.1f} GWh, "
                f"{unserved[-1] / base_u:.0f} times as much",
                (firm[-1], unserved[-1]), textcoords="offset points",
                xytext=(10, -4), fontsize=9.5, color=plots.INK, ha="left", va="top")
    ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
    ax.set_xlabel("Firm capacity, MW")
    ax.set_ylabel("Unserved energy, GWh")
    titled(ax, "A small change in firm capacity is a large change in blackouts",
                 loc="left")
    finish(fig)
    fig.savefig(path, dpi=150, facecolor=plots.SURFACE)
    plt.close(fig)
    return path, list(zip(firm, unserved))


def price_stack(settings, path):
    """The offer stack the model prices an hour from: every price-setting offer in
    the packaged fleet, cheapest first, with the demand-response rungs and the
    market price cap above it. Hydro and storage are scheduled against a budget and
    on quantities rather than offered at a price, so they are not on it."""
    from esem_sandbox.core.dispatch import _offer_stack

    units = [u for u in settings.fleet if u.in_service(2026) and u.technology != "hydro"]
    prices, caps, labels = _offer_stack(list(units), settings)
    by_unit = {u.unit: u for u in units}
    floor = settings.dispatch["must_run_offer_per_mwh"]
    # A dollar sign is escaped because two of them in one string read as maths.
    money = lambda v: f"-\\${-v:,.0f}" if v < 0 else f"\\${v:,.0f}"

    fig, ax = plt.subplots(figsize=(7.6, 5.6), facecolor=plots.SURFACE)
    _style(ax)
    ax.set_yscale("symlog", linthresh=100, linscale=0.8)
    colour_of = {"wind": plots.TECH_COLOUR["wind"], "solar": plots.TECH_COLOUR["solar"],
                 "coal": plots.TECH_COLOUR["coal"], "ccgt": plots.TECH_COLOUR["gas"],
                 "ocgt": plots.TECH_COLOUR["gas"], "import": plots.TECH_COLOUR["hydro"]}
    legend_name = {"wind": "Wind", "solar": "Solar", "coal": "Coal", "ccgt": "Gas",
                   "import": "Imports"}
    seen = set()

    def band(x, width, price, tech):
        label = legend_name.get(tech if tech != "ocgt" else "ccgt")
        if label in seen:
            label = None
        seen.add(label)
        ax.bar(x, price if price != 0 else 1.0, width=width, align="edge",
               color=colour_of[tech], edgecolor=plots.SURFACE, linewidth=1, label=label)

    x = 0.0
    vre = sorted((u for u in units if u.technology in ("wind", "solar")),
                 key=lambda u: u.srmc_per_mwh)
    for u in vre:
        band(x, u.capacity_mw, u.srmc_per_mwh, u.technology)
        ax.text(x + u.capacity_mw / 2, u.srmc_per_mwh - 8, money(u.srmc_per_mwh),
                ha="center", va="top", fontsize=8.5, color=plots.INK)
        x += u.capacity_mw
    # Price labels sit above the wide bands; the steep, narrow top of the stack is
    # read off the note at the upper left instead, where there is room.
    top = []
    for price, cap, label in zip(prices, caps, labels):
        u = by_unit[label]
        band(x, cap, price, u.technology)
        if u.technology == "coal":
            if price == floor and "floor" not in seen:
                seen.add("floor")
                ax.text(x + cap / 2, price - 8, f"must-run band {money(price)}",
                        ha="left", va="top", fontsize=8.5, color=plots.INK)
            elif price != floor and "coal_price" not in seen:
                seen.add("coal_price")
                ax.text(x + cap / 2, price + 6, f"{money(price)} to {money(52)}", ha="center",
                        va="bottom", fontsize=8.5, color=plots.INK)
        else:
            name = {"ccgt": "combined-cycle gas", "import": "imports",
                    "ocgt": "open-cycle gas"}[u.technology]
            if u.unit == "peaker_dist":
                name = "high-cost peaker"
            top.append(f"{name} {money(price)}")
        x += cap
    x_end = x
    ax.text(150, 230, "Top of the stack, left to right:\n" + "\n".join(top),
            fontsize=8.5, color=plots.INK, va="bottom", linespacing=1.35)
    # The demand-response rungs and the cap, as lines to the right of the stack:
    # the rungs are 1 to 364 MW wide, too thin to draw to scale on this axis.
    for t in settings.dsr:
        ax.hlines(t.price_per_mwh, x_end + 200, x_end + 1_400, color=plots.INK, lw=1.6)
        ax.text(x_end + 1_500, t.price_per_mwh,
                f"Demand response {money(t.price_per_mwh)}, {t.capacity_mw:,.0f} MW",
                fontsize=8.5, color=plots.INK, va="center")
    cap_price = settings.market["market_price_cap_per_mwh"]
    ax.axhline(cap_price, color=plots.INK_2, lw=1.2, ls="--")
    ax.text(150, cap_price * 1.12, f"Market price cap {money(cap_price)}", fontsize=8.5,
            color=plots.INK_2, va="bottom")
    ax.axhline(0, color=plots.GRID, lw=0.8)
    ax.set_xlim(0, x_end + 6_000)
    ax.set_ylim(-130, cap_price * 2.4)
    ax.set_yticks([-50, 0, 50, 100, 300, 1000, 3000, 10000, 20300])
    ax.set_yticklabels(["-50", "0", "50", "100", "300", "1,000", "3,000", "10,000", "20,300"])
    ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
    ax.set_xlabel("Megawatts offered, cheapest first")
    ax.set_ylabel("Offer, $ per MWh (log scale above 100)")
    titled(ax, "What sets the price in an hour: the offer stack, and the rungs above it",
           loc="left", fontsize=11.5)
    finish(fig, legend_from=ax, ncol=5)
    fig.savefig(path, dpi=150, facecolor=plots.SURFACE)
    plt.close(fig)
    return path


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
                    label=f"What the cap pays: {payout:,.0f} dollars per MW")
    ax.axhline(strike, color=plots.SERIES[0], lw=1.6, zorder=4,
               label=f"The strike: {strike:,.0f} dollars per MWh")
    ax.axhline(price.mean(), color=plots.INK, lw=1.4, ls="--", zorder=4,
               label=f"The year's average: {price.mean():,.0f}, below the strike, "
                     f"so averaging first pays nothing")
    ax.set_xlim(0, show)
    ax.set_xlabel(f"The dearest {show} hours of the year "
                  f"(only {above} clear the strike; the other "
                  f"{len(price) - show:,} hours are not drawn)")
    ax.set_ylabel("Dollars per MWh, log scale")
    titled(ax, "Almost all of a cap's money is in a handful of hours", loc="left")
    finish(fig, legend_from=ax, ncol=1)
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
    from esem_sandbox.core.simulate import with_tail
    from esem_sandbox.core.investment import (build_size_mw, evaluate,
                                              residual_exposure)

    cells = cell_plan(settings)
    offsets = list(settings.forward["anchor_offsets"])
    # The view the run's investors read: the years past the last projection year
    # pay the cost of entry plus the market's own loading.
    view = with_tail(settings, forward_view(settings, settings.fleet, bundle,
                                            year=2026, peak_mw=12_500.0,
                                            entry=EntryState()), default_roster())
    tech = settings.tech(tech_name)
    agent = [a for a in default_roster() if a.kind == PRODUCER][0]
    rents = view.lifetime_rent(tech)
    weights = view.weights
    mean = float(rents @ weights)
    size = build_size_mw(12_500.0, tech, settings)
    bare = evaluate(view, tech, agent, settings, exposure=1.0, capacity_mw=size)
    # The contracted firm holds the longest cover the model writes: a scheme award
    # on all of its output for the award tenor. An exposure no contract in the
    # model can produce would draw a benefit the run's own contracts never deliver.
    tenor = int(settings.esem["contract_tenor_years"])
    awarded = residual_exposure(settings, tech.life_years, award_years=tenor,
                                award_cover=1.0)
    hedged = evaluate(view, tech, agent, settings, exposure=awarded, capacity_mw=size)

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
    ax1.text(0, -0.95, f"the same {len(cells)} possible futures, dispatched at each "
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
             f"the same investor, under a {tenor}-year award  "
             f"${hedged.certainty_equivalent_per_mw_year:,.0f}")):
        ax2.axvline(x / 1e6, color=colour, lw=1.6, zorder=4)
        ax2.plot([], [], color=colour, lw=1.6, label=label)
    ax2.set_xlabel("$m per megawatt per year, in each future")
    ax2.set_ylabel(f"The {len(rents)} futures, poorest first")
    ax2.set_yticks([])
    titled(ax2, "A contract is worth the gap it closes", loc="left")

    finish(fig, legend_from=ax2, ncol=1)
    fig.savefig(path, dpi=150, facecolor=plots.SURFACE)
    plt.close(fig)
    return path, mean, bare.certainty_equivalent_per_mw_year, \
        hedged.certainty_equivalent_per_mw_year, len(cells), len(offsets)


def what_hesitancy_costs(settings, bundle, path, tech_name="ocgt"):
    """How much of the bar a plant must clear is caution rather than cost.

    Each producer here has its own tolerance for uncertainty, and that tolerance is
    most of what it demands. The bar is the fixed cost of owning the plant plus what
    the investor charges itself for carrying an uncertain income; the marker is the
    same investor once all of its output is under a scheme award.
    """
    from esem_sandbox.core.agents import PRODUCER, default_roster
    from esem_sandbox.core.forward import EntryState, forward_view
    from esem_sandbox.core.simulate import with_tail
    from esem_sandbox.core.investment import (build_size_mw, evaluate,
                                              residual_exposure)

    view = with_tail(settings, forward_view(settings, settings.fleet, bundle,
                                            year=2026, peak_mw=12_500.0,
                                            entry=EntryState()), default_roster())
    tech = settings.tech(tech_name)
    size = build_size_mw(12_500.0, tech, settings)
    producers = [a for a in default_roster() if a.kind == PRODUCER]
    producers.sort(key=lambda a: a.risk_aversion)
    tenor = int(settings.esem["contract_tenor_years"])
    # The marker is the same firm under the longest cover the model writes, a
    # scheme award on all of its output for the award tenor.
    awarded = residual_exposure(settings, tech.life_years, award_years=tenor,
                                award_cover=1.0)

    names, fixed, caution, contracted = [], [], [], []
    for a in producers:
        bare = evaluate(view, tech, a, settings, exposure=1.0, capacity_mw=size)
        hedged = evaluate(view, tech, a, settings, exposure=awarded, capacity_mw=size)
        shown = a.name.replace("_", " ").capitalize()
        shown = shown[:-1] + shown[-1].upper() if shown[-2:] in (" a", " b") else shown
        names.append(f"{shown}\n(caution {a.risk_aversion:.2f})")
        fixed.append(bare.fixed_cost_per_mw_year / 1e3)
        caution.append(bare.risk_discount_per_mw_year / 1e3)
        contracted.append(hedged.hurdle_per_mw_year / 1e3)

    fig, ax = plt.subplots(figsize=(7.4, 4.8), facecolor=plots.SURFACE)
    _style(ax)
    y = np.arange(len(names))
    ax.barh(y, fixed, color=plots.SERIES[0], height=0.55, label="What it costs to own")
    ax.barh(y, caution, left=fixed, color=plots.SERIES[1], height=0.55,
            label="What the uncertainty costs")
    # Rimmed in the surface colour: on the dark ground the ink is white and the
    # bar it sits on is pale, so an unrimmed marker disappears into it.
    ax.scatter(contracted, y, color=plots.INK, zorder=5, s=56, marker="D",
               edgecolor=plots.SURFACE, linewidths=1.4,
               label=f"The same firm, all of its output under a {tenor}-year award")
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("$ thousand per megawatt per year")
    titled(ax, "What a gas peaker must earn to be built, and why",
           loc="left")
    finish(fig, legend_from=ax, ncol=2, handletextpad=0.6, columnspacing=2.4)
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
            p5 = price_stack(settings, f"{OUT}/price_stack{suffix}.png")
        print(f"wrote {p1}, {p2}, {p3}, {p4} and {p5}")
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
