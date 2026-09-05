"""Command line entry point.

``esem-sandbox run`` dispatches the packaged shape-years and writes a CSV, a
calibration report and two charts.
"""

from __future__ import annotations

import argparse
import csv
import os

import numpy as np

from .config import load_settings
from .core.simulate import run as run_simulation
from .core.dispatch import dispatch_year
from .core.report import block_prices, calibration, unit_revenue
from .core.weather import generate_bundle
from .core.windows import locate_worst_window
from . import plots

DEFAULT_PEAK_MW = 12500.0


def run(args: argparse.Namespace) -> int:
    settings = load_settings()
    bundle = generate_bundle(settings.weather["seed"],
                             settings.weather["shape_years"],
                             settings.weather["hours_per_year"])
    os.makedirs(args.out, exist_ok=True)

    results = {}
    rows = []
    for y in range(settings.weather["shape_years"]):
        shape = bundle["demand_shape"][y]
        demand = shape * (args.peak / shape.max())
        res = dispatch_year(settings, args.year, demand,
                            bundle["wind_cf"][y], bundle["solar_cf"][y])
        results[f"shape year {y}"] = res
        cal = calibration(res.price, res.unserved_mwh, res.administered_hours,
                          res.operational_demand_mw, settings)
        blocks = block_prices(settings, res.price)
        rows.append({
            "shape_year": y,
            "mean_price": round(cal.mean_price, 2),
            **{f"block_{k}": round(v, 2) for k, v in blocks.items()},
            "hours_ge_300": cal.hours_at_or_above_300,
            "days_with_300_hour": round(cal.days_with_300_hour, 4),
            "hours_at_cap": cal.hours_at_voll,
            "administered_hours": cal.administered_hours,
            "unserved_gwh": round(cal.unserved_gwh, 4),
            "unserved_fraction": round(cal.unserved_fraction, 8),
            "water_value": round(res.water_value_per_mwh, 2),
        })

    path = os.path.join(args.out, "dispatch_summary.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    worst_label = max(results, key=lambda k: results[k].total_unserved_gwh)
    worst = results[worst_label]
    # The firm capacity comes from the dispatch that produced this result, not
    # from a second sum over the fleet. Hydro is scheduled against its budget and
    # netted out of the residual, so a threshold that adds it back double counts
    # it: the worst-window search and the chart were measuring against 1,235 MW
    # the residual no longer contained.
    firm = worst.firm_capacity_mw
    window = locate_worst_window(worst.residual_mw, firm)
    plots.worst_week(worst, window, firm, os.path.join(args.out, "worst_week.png"))
    plots.price_duration(results, os.path.join(args.out, "price_duration.png"))

    standard = settings.reliability["standard_use_fraction"]
    print(f"esem-sandbox: {len(results)} shape-years, {args.year}, "
          f"peak {args.peak:,.0f} MW")
    print(f"firm dispatchable capacity {firm:,.0f} MW")
    for label, res in results.items():
        cal = calibration(res.price, res.unserved_mwh, res.administered_hours,
                          res.operational_demand_mw, settings)
        flag = "over the standard" if cal.unserved_fraction > standard else "within"
        print(f"  {label}: mean ${cal.mean_price:7.2f}/MWh   "
              f"unserved {cal.unserved_gwh:6.3f} GWh   {flag}")
    print(f"\nworst window: {window.days} days from day {window.start_day} "
          f"of {worst_label}, peak residual {window.peak_residual_mw:,.0f} MW")
    print("\ncalibration, reported not tuned:")
    cal = calibration(worst.price, worst.unserved_mwh, worst.administered_hours,
                      worst.operational_demand_mw, settings)
    for line in cal.lines():
        print("  " + line)
    print(f"\nwrote {path} and two charts to {args.out}/")
    return 0


def _by_technology(builds) -> str:
    """Builds summed per technology. Two producers each building 500 MW of the same
    thing is one thousand megawatts of it, not two entries that look like a bug."""
    totals: dict[str, float] = {}
    for b in builds:
        totals[b.technology] = totals.get(b.technology, 0.0) + b.capacity_mw
    return " ".join(f"{t}:{mw:.0f}" for t, mw in sorted(totals.items()))


def simulate(args: argparse.Namespace) -> int:
    """Twenty annual steps of dispatch, contracting, investment and exit."""
    settings = load_settings()
    os.makedirs(args.out, exist_ok=True)
    result = run_simulation(settings, ticks=args.ticks, start_year=args.year,
                            peak_mw=args.peak, seed=args.seed)
    standard = settings.reliability["standard_use_fraction"]

    rows = []
    for tick in result.ticks:
        rows.append({
            "year": tick.year,
            "peak_mw": round(tick.peak_mw),
            "mean_price": round(tick.mean_price, 2),
            **{f"block_{k}": round(v, 2) for k, v in tick.block_prices.items()},
            "unserved_gwh": round(tick.unserved_gwh, 4),
            "unserved_fraction": round(tick.unserved_fraction, 8),
            "times_the_standard": round(tick.unserved_fraction / standard, 2),
            "expected_unserved_fraction_ahead": round(
                tick.expected_unserved_fraction, 8),
            "firm_capacity_mw": round(tick.firm_capacity_mw),
            "built_mw": round(sum(b.capacity_mw for b in tick.builds)),
            "built": _by_technology(tick.builds),
            "notices": " ".join(tick.notices),
            "live_contracts": tick.live_contracts,
            "peaker_rent_less_fixed_cost": round(
                tick.peaker_missing_money_per_mw_year),
        })
    path = os.path.join(args.out, "run_summary.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"esem-sandbox: {args.ticks} years from {args.year}, "
          f"peak {args.peak:,.0f} MW growing on the {result.draw.growth_path} path "
          f"({result.draw.annual_growth:.1%} a year)")
    print(f"{'year':>6}{'mean $/MWh':>12}{'unserved':>11}{'x standard':>12}"
          f"{'built MW':>10}  what was built")
    for tick, row in zip(result.ticks, rows):
        print(f"{tick.year:>6}{tick.mean_price:>12.2f}"
              f"{tick.unserved_gwh:>10.2f}G{row['times_the_standard']:>12.2f}"
              f"{row['built_mw']:>10}  {row['built'] or '-'}")
    print(f"\nunserved energy over the run  {result.total_unserved_gwh:,.1f} GWh")
    print("built in all               ", {k: round(v) for k, v in
                                          sorted(result.built_by_technology().items())})
    print("\nIllustrative. Not a forecast of anything.")
    print(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="esem-sandbox")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="dispatch the packaged shape-years")
    r.add_argument("--year", type=int, default=2026)
    r.add_argument("--peak", type=float, default=DEFAULT_PEAK_MW,
                   help="system peak demand in MW")
    r.add_argument("--out", default="outputs", help="output directory")
    r.set_defaults(func=run)
    m = sub.add_parser("simulate", help="run the market forward, year by year")
    m.add_argument("--year", type=int, default=2026, help="first year")
    m.add_argument("--ticks", type=int, default=20)
    m.add_argument("--peak", type=float, default=DEFAULT_PEAK_MW)
    m.add_argument("--seed", type=int, default=None)
    m.add_argument("--out", default="outputs")
    m.set_defaults(func=simulate)
    args = parser.parse_args(argv)
    return args.func(args)
