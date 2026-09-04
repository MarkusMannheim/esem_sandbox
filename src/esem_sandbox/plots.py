"""Charts. Every one is captioned illustrative, because it is."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .core.report import duration_curve  # noqa: E402
from .core.windows import Window  # noqa: E402

CAPTION = "Illustrative only. A stylised one-region system, not a forecast."


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
    ax2.set_ylabel("price, $/MWh")
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
    ax.set_ylabel("price, $/MWh")
    ax.legend(frameon=False, fontsize=9)
    ax.set_title("Price duration, dearest tenth of the year")
    fig.text(0.01, 0.01, CAPTION, fontsize=8, color="#5A6D6F")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path
