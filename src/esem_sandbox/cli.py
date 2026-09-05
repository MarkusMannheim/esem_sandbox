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
from .core.dispatch import dispatch_year
from .core.report import block_prices, calibration, unit_revenue
from .core.weather import generate_bundle
from .core.windows import locate_worst_window
from . import plots

DEFAULT_PEAK_MW = 12500.0


def _firm_capacity(settings, year: int) -> float:
    return sum(u.available_mw for u in settings.fleet
               if u.in_service(year)
               and u.technology in ("coal", "ccgt", "ocgt", "hydro", "import"))


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
                          res.demand_mw, settings)
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

    firm = _firm_capacity(settings, args.year)
    worst_label = max(results, key=lambda k: results[k].total_unserved_gwh)
    worst = results[worst_label]
    window = locate_worst_window(worst.residual_mw, firm)
    plots.worst_week(worst, window, firm, os.path.join(args.out, "worst_week.png"))
    plots.price_duration(results, os.path.join(args.out, "price_duration.png"))

    standard = settings.reliability["standard_use_fraction"]
    print(f"esem-sandbox: {len(results)} shape-years, {args.year}, "
          f"peak {args.peak:,.0f} MW")
    print(f"firm dispatchable capacity {firm:,.0f} MW")
    for label, res in results.items():
        cal = calibration(res.price, res.unserved_mwh, res.administered_hours,
                          res.demand_mw, settings)
        flag = "over the standard" if cal.unserved_fraction > standard else "within"
        print(f"  {label}: mean ${cal.mean_price:7.2f}/MWh   "
              f"unserved {cal.unserved_gwh:6.3f} GWh   {flag}")
    print(f"\nworst window: {window.days} days from day {window.start_day} "
          f"of {worst_label}, peak residual {window.peak_residual_mw:,.0f} MW")
    print("\ncalibration, reported not tuned:")
    cal = calibration(worst.price, worst.unserved_mwh, worst.administered_hours,
                      worst.demand_mw, settings)
    for line in cal.lines():
        print("  " + line)
    print(f"\nwrote {path} and two charts to {args.out}/")
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
    args = parser.parse_args(argv)
    return args.func(args)
