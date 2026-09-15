"""When each leg's firm capacity arrives, against the years the market is short in.

Runs the canonical pair (seed 20260904, 20 years, about four minutes) and draws two
panels on one year axis: the firm megawatts each leg has commissioned so far, on the
table basis, and the energy each leg shed in that year. It also prints the figures
the limitations page quotes for the reallocation result: what each leg built by
technology, and the firm capacity arriving in the years the merchant leg sheds in.
"""

import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

from esem_sandbox import plots
from esem_sandbox.config import load_settings
from esem_sandbox.core.simulate import ESEM, MERCHANT, run
from esem_sandbox.plots import LEG_COLOUR, LEG_LABEL, LEG_MARKER, finish, theme, titled

OUT = "outputs/canonical"
SEED = 20260904


def arrivals(settings, result) -> dict[int, float]:
    """Firm megawatts commissioned in each year, builds and awards at the table factor."""
    factor = lambda tech: settings.tech(tech).firm_factor
    by_year: dict[int, float] = defaultdict(float)
    for t in result.ticks:
        for b in t.builds:
            by_year[b.commissioned_year] += b.capacity_mw * factor(b.technology)
        for a in t.awards:
            by_year[a.commissioning_year] += a.capacity_mw * factor(a.technology)
    return dict(by_year)


def built_by_technology(settings, result) -> dict[str, tuple[float, float]]:
    """(unsubsidised, awarded) megawatts per technology."""
    out = {t.technology: [0.0, 0.0] for t in settings.tech_costs}
    for t in result.ticks:
        for b in t.builds:
            out[b.technology][0] += b.capacity_mw
        for a in t.awards:
            out[a.technology][1] += a.capacity_mw
    return {k: tuple(v) for k, v in out.items()}


def arrival_figure(settings, legs, path: str) -> str:
    years = [t.year for t in legs[MERCHANT].ticks]
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(7.6, 6.4), sharex=True, facecolor=plots.SURFACE,
        gridspec_kw={"height_ratios": (3, 2)})
    for ax in (top, bottom):
        plots._style(ax)
    last = years[-1]
    ends = {}
    for leg in (MERCHANT, ESEM):
        arr = arrivals(settings, legs[leg])
        cum, series = 0.0, []
        for y in years:
            cum += arr.get(y, 0.0)
            series.append(cum / 1000.0)
        top.step(years, series, where="post", color=LEG_COLOUR[leg], lw=2,
                 marker=LEG_MARKER[leg], markersize=4.5, markeredgecolor=plots.SURFACE,
                 label=LEG_LABEL[leg])
        ends[leg] = series[-1]
    # The two legs can end within a label's height of each other, so the labels
    # are pushed apart rather than written on top of one another.
    order = sorted(ends, key=ends.get)
    gap = ends[order[1]] - ends[order[0]]
    nudge = max(0.0, 0.9 - gap) / 2
    for k, leg in enumerate(order):
        top.text(last + 0.3, ends[leg] + (k - 0.5) * 2 * nudge, f"{ends[leg]:.1f} GW",
                 color=plots.INK, fontsize=9, va="center")
    top.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(2))
    top.set_ylabel("firm capacity commissioned so far, GW on the table")
    titled(top, "Firm capacity arrives later without the scheme", fontsize=11.5)

    w = 0.38
    for k, leg in enumerate((MERCHANT, ESEM)):
        vals = [t.unserved_gwh for t in legs[leg].ticks]
        bottom.bar([y + (k - 0.5) * w for y in years], vals, width=w,
                   color=LEG_COLOUR[leg], edgecolor=plots.SURFACE, linewidth=1)
    bottom.set_ylabel("energy shed, GWh")
    bottom.set_xlabel("year")
    bottom.set_xlim(years[0] - 0.7, last + 2.2)
    titled(bottom, "and the years the market is short in are the ones it misses",
           fontsize=11.5)
    finish(fig, legend_from=top, ncol=2)
    fig.savefig(path, dpi=150, facecolor=plots.SURFACE)
    plt.close(fig)
    return path


def main(ticks: int = 20) -> int:
    settings = load_settings()
    legs = {leg: run(settings, ticks=ticks, seed=SEED, leg=leg)
            for leg in (MERCHANT, ESEM)}
    for suffix, name in (("", "light"), ("_dark", "dark")):
        with theme(name):
            p = arrival_figure(settings, legs, f"{OUT}/arrival{suffix}.png")
        print(f"wrote {p}")

    factor = {t.technology: t.firm_factor for t in settings.tech_costs}
    print(f"\n{'technology':<11} {'merchant MW':>11} | {'scheme built':>12} "
          f"{'awarded':>8} {'total':>8} | firm on the table, merchant / scheme")
    m, e = built_by_technology(settings, legs[MERCHANT]), built_by_technology(settings, legs[ESEM])
    for tech in factor:
        print(f"{tech:<11} {m[tech][0]:>11,.0f} | {e[tech][0]:>12,.0f} {e[tech][1]:>8,.0f} "
              f"{sum(e[tech]):>8,.0f} | {m[tech][0] * factor[tech]:,.0f} / "
              f"{sum(e[tech]) * factor[tech]:,.0f}")
    years = [t.year for t in legs[MERCHANT].ticks]
    short = [t.year for t in legs[MERCHANT].ticks if t.unserved_gwh > 0.05]
    print(f"\nyears the merchant leg sheds more than 0.05 GWh in: {short}")
    for leg in (MERCHANT, ESEM):
        arr = arrivals(settings, legs[leg])
        total = sum(arr.values())
        late = sum(v for y, v in arr.items() if y >= 2040)
        print(f"{leg}: {total:,.0f} firm MW in all, {late:,.0f} commissioned from 2040 on; "
              + ", ".join(f"{y}: {arr.get(y, 0.0):,.0f}" for y in years if y in short))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 20))
