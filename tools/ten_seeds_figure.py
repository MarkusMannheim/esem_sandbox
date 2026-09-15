"""The ten-seed envelope as a picture: what the scheme avoided and what it spent.

Reads the committed `outputs/canonical/ten_seeds.csv`, so it needs no simulation and
regenerates in a second. Each seed's resource-cost move is split into the outage the
scheme avoided, valued at the market price cap, and everything else: fuel, fixed
costs and capital. The total is the sum of the two. Seeds are grouped by the growth
path the run drew, slow at the top, so the sort by growth reads down the page.
"""

import csv
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from esem_sandbox import plots
from esem_sandbox.config import load_settings
from esem_sandbox.plots import finish, theme, titled

OUT = "outputs/canonical"
PATHS = ("low", "central", "high")
PATH_LABEL = {"low": "low growth", "central": "central growth", "high": "high growth"}


def rows(path: str, cap: float) -> list[dict]:
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        m, e = float(r["merchant_unserved_gwh"]), float(r["esem_unserved_gwh"])
        total = (float(r["merchant_resource_cost"]) - float(r["esem_resource_cost"])) / 1e9
        outage = (m - e) * 1e3 * cap / 1e9
        out.append({"seed": r["seed"], "path": r["growth_path"], "total": total,
                    "outage": outage, "rest": total - outage})
    # Slow growth at the top of the chart, and within a path the largest outage
    # avoided first, so the eye reads one sort.
    out.sort(key=lambda r: (PATHS.index(r["path"]), -r["outage"]))
    return out


def ten_seeds_figure(data: list[dict], path: str) -> str:
    fig, ax = plt.subplots(figsize=(7.6, 6.0), facecolor=plots.SURFACE)
    plots._style(ax)
    ax.grid(False, axis="y")
    n = len(data)
    y = list(range(n))[::-1]
    h = 0.36
    outage_c, rest_c = plots.SERIES[4], plots.SERIES[5]
    ax.barh([v + h / 2 for v in y], [r["outage"] for r in data], height=h,
            color=outage_c, edgecolor=plots.SURFACE, linewidth=1,
            label="outage the scheme avoided")
    ax.barh([v - h / 2 for v in y], [r["rest"] for r in data], height=h,
            color=rest_c, edgecolor=plots.SURFACE, linewidth=1,
            label="fuel, fixed costs and capital, saved")
    ax.scatter([r["total"] for r in data], y, marker="D", s=34, color=plots.INK,
               zorder=4, label="the two together")
    ax.axvline(0, color=plots.INK_2, lw=1.0)
    # Rows are numbered in the order drawn; the seed behind each is in the csv,
    # and the tool prints the mapping. A seed number tells a reader nothing.
    ax.set_yticks(y)
    ax.set_yticklabels([f"draw {i + 1}" for i in range(n)], fontsize=9)
    lo, hi = ax.get_xlim()
    ax.set_xlim(lo - 0.3, max(hi + 0.3, 1.7))
    # The growth path each band of seeds drew: a rule between bands, and the
    # path's name at the right-hand end of the band's first row.
    for p in PATHS:
        idx = [i for i, r in enumerate(data) if r["path"] == p]
        if idx:
            top = y[idx[0]] + 0.5
            if idx[0] > 0:
                ax.axhline(top, color=plots.GRID, lw=0.8)
            ax.text(ax.get_xlim()[1], top - 0.1, PATH_LABEL[p], fontsize=9,
                    color=plots.INK_2, va="top", ha="right", style="italic")
    for i, r in enumerate(data):
        ax.text(r["total"] + (0.12 if r["total"] >= 0 else -0.12), y[i],
                f"{r['total']:+.2f}", fontsize=8.5, color=plots.INK, va="center",
                ha="left" if r["total"] >= 0 else "right")
    ax.set_xlabel("$bn over 20 years; positive means the scheme saved it")
    titled(ax, "What the scheme avoided and what it spent, on ten weather draws",
           fontsize=11.5)
    finish(fig, legend_from=ax, ncol=3)
    fig.savefig(path, dpi=150, facecolor=plots.SURFACE)
    plt.close(fig)
    return path


def main(csv_path: str = f"{OUT}/ten_seeds.csv") -> int:
    settings = load_settings()
    data = rows(csv_path, settings.market["market_price_cap_per_mwh"])
    for suffix, name in (("", "light"), ("_dark", "dark")):
        with theme(name):
            p = ten_seeds_figure(data, f"{OUT}/ten_seeds{suffix}.png")
        print(f"wrote {p}")
    for i, r in enumerate(data):
        print(f"  draw {i + 1:>2}: seed {r['seed']} ({r['path']} growth)")
    better = sum(r["outage"] > 0 for r in data)
    cheaper = sum(r["total"] > 0 for r in data)
    print(f"reliability better on {better} of {len(data)}, "
          f"resource cost lower on {cheaper} of {len(data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:2]))
