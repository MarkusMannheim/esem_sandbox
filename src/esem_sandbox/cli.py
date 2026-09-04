"""Command line entry point.

``esem-sandbox run`` dispatches the packaged shape-years and writes a CSV, a
calibration report and two charts.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tomllib
from importlib import resources

import numpy as np

from .config import load_settings
from .core.simulate import ESEM, MERCHANT, run as run_simulation
from .core.dispatch import dispatch_year
from .core.report import block_prices, calibration, unit_revenue
from .core.weather import generate_bundle
from .core.windows import locate_worst_window
from . import plots

DEFAULT_PEAK_MW = 12500.0


def _scenario(path: str | None) -> tuple[dict, dict]:
    """Read a scenario into settings overrides and run options.

    A scenario is a TOML file with an optional ``[run]`` table naming the leg, the
    horizon, the peak, the seed, plant to close early and which market clears, plus
    any settings sections it wants to change. The overrides go through the same
    strict loader everything else does, so a typo in a scenario fails loudly rather
    than leaving a default quietly in place.

    Either a path or a packaged name. The packaged scenarios ship inside the wheel,
    so ``--scenario scheme`` works after a plain install; without that, the only
    scenarios a reader could run would be the ones they had cloned the repository
    for, and the command that names them would be in a README they could not follow.
    """
    if not path:
        return {}, {}
    packaged = resources.files("esem_sandbox") / "scenarios" / f"{path}.toml"
    if not os.path.exists(path) and packaged.is_file():
        raw = tomllib.loads(packaged.read_text(encoding="utf-8"))
        options = raw.pop("run", {})
        _check_run(options)
        return raw, options
    if not os.path.exists(path):
        # Named rather than opened, so a misspelling gets the list of valid names
        # instead of a FileNotFoundError traceback.
        raise SystemExit(
            f"no scenario named {path!r}. The packaged ones are: "
            f"{', '.join(scenario_names())}. Anything else has to be a path to a "
            "TOML file."
        )
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    options = raw.pop("run", {})
    _check_run(options)
    return raw, options


def _check_run(options: dict) -> None:
    unknown = set(options) - {"leg", "ticks", "peak", "seed", "year", "retire",
                              "clearing", "scheme", "investment"}
    if unknown:
        raise ValueError(f"unknown key(s) in [run]: {', '.join(sorted(unknown))}")


def scenario_names() -> list[str]:
    """What ships in the wheel, for the command line's help text."""
    folder = resources.files("esem_sandbox") / "scenarios"
    return sorted(p.name[:-5] for p in folder.iterdir() if p.name.endswith(".toml"))


def _apply(args: argparse.Namespace, options: dict) -> argparse.Namespace:
    """Command-line arguments win over the scenario file, so an exercise can change
    one thing without editing it.

    Which arguments were given is read off the argv the parser was handed, not off
    the process's own. A caller that passes an explicit list, which is what a test or
    another script does, would otherwise have its scenario keys compared against
    whatever happened to be on the real command line.
    """
    given = set(getattr(args, "_argv", None) or sys.argv[1:])
    for key, value in options.items():
        flag = f"--{key}"
        if flag not in given and not any(a.startswith(flag + "=") for a in given):
            setattr(args, key, value)
    return args


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
    # The firm capacity comes from the dispatch that produced this result, not from
    # a second sum over the fleet. Hydro is scheduled against its budget and netted
    # out of the residual, so a threshold that added it back would count 1,235 MW the
    # residual no longer contains.
    firm = worst.firm_capacity_mw
    window = locate_worst_window(worst.residual_mw, firm)
    # Both themes, because these are read on GitHub, which serves whichever one the
    # reader has set. A chart drawn for a pale ground is unreadable on a dark one.
    for suffix, name in (("", "light"), ("_dark", "dark")):
        with plots.theme(name):
            plots.worst_week(worst, window, firm,
                             os.path.join(args.out, f"worst_week{suffix}.png"))
            plots.price_duration(
                results, os.path.join(args.out, f"price_duration{suffix}.png"))

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


def _working(message: str) -> None:
    """Say what is happening, on STDERR.

    Both long commands run for minutes, so they say where they are up to rather than
    sitting silent. Progress goes to stderr and results to stdout, because the
    canonical recipe tees stdout into comparison.txt and a progress line is not part
    of that artefact.
    """
    print(message, file=sys.stderr, flush=True)


def _by_technology(builds) -> str:
    """Builds summed per technology. Two producers each building 500 MW of the same
    thing is one thousand megawatts of it, not two entries that look like a bug."""
    totals: dict[str, float] = {}
    for b in builds:
        totals[b.technology] = totals.get(b.technology, 0.0) + b.capacity_mw
    return " ".join(f"{t}:{mw:.0f}" for t, mw in sorted(totals.items()))


def simulate(args: argparse.Namespace) -> int:
    """Twenty annual steps of dispatch, contracting, investment and exit."""
    overrides, options = _scenario(getattr(args, "scenario", None))
    args = _apply(args, options)
    settings = load_settings(overrides)
    os.makedirs(args.out, exist_ok=True)
    _working(f"running {args.ticks} years, {getattr(args, 'leg', MERCHANT)} leg...")
    result = run_simulation(settings, ticks=args.ticks, start_year=args.year,
                            peak_mw=args.peak, seed=args.seed,
                            leg=getattr(args, "leg", MERCHANT),
                            retire=getattr(args, "retire", None),
                            clearing=getattr(args, "clearing", "anchor"),
                            scheme=bool(getattr(args, "scheme", False)),
                            investment=getattr(args, "investment", "simultaneous"))
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


def compare(args: argparse.Namespace) -> int:
    """Both legs on the same weather, and what the difference costs.

    The two legs draw one weather sequence from one seed, so the difference between
    them is the mechanism and nothing else. A leg that drew its own weather would
    report the difference between two climates as the effect of a policy.
    """
    overrides, options = _scenario(getattr(args, "scenario", None))
    args = _apply(args, options)
    settings = load_settings(overrides)
    os.makedirs(args.out, exist_ok=True)
    legs = {}
    for i, leg in enumerate((MERCHANT, ESEM), start=1):
        _working(f"running the {leg} leg, {args.ticks} years "
                 f"({i} of 2, several minutes each)...")
        legs[leg] = run_simulation(
            settings, ticks=args.ticks, start_year=args.year,
            peak_mw=args.peak, seed=args.seed, leg=leg,
            retire=getattr(args, "retire", None),
            clearing=getattr(args, "clearing", "anchor"),
            scheme=bool(getattr(args, "scheme", False)),
            investment=getattr(args, "investment", "simultaneous"))
    if legs[MERCHANT].draw != legs[ESEM].draw:
        raise AssertionError(
            "the two legs saw different weather; a comparison between them would be "
            "a comparison of climates rather than of mechanisms"
        )
    standard = settings.reliability["standard_use_fraction"]
    voll = settings.market["market_price_cap_per_mwh"]

    rows = []
    for a, b in zip(legs[MERCHANT].ticks, legs[ESEM].ticks):
        rows.append({
            "year": a.year,
            "merchant_unserved_gwh": round(a.unserved_gwh, 4),
            "merchant_times_standard": round(a.unserved_fraction / standard, 2),
            "esem_unserved_gwh": round(b.unserved_gwh, 4),
            "esem_times_standard": round(b.unserved_fraction / standard, 2),
            "lane_volume_mw": round(b.lane_volume_mw),
            "reserve_margin_gap_mw": round(b.reserve_margin_gap_mw),
            "awarded_mw": round(sum(x.capacity_mw for x in b.awards)),
            "scheme_cost": round(b.scheme_cost),
            "levy_per_mwh": round(b.levy_per_mwh, 4),
            "merchant_mean_price": round(a.mean_price, 2),
            "esem_mean_price": round(b.mean_price, 2),
        })
    path = os.path.join(args.out, "comparison.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    draw = legs[MERCHANT].draw
    print(f"esem-sandbox: {args.ticks} years from {args.year}, one weather sequence "
          f"shared by both legs ({draw.growth_path} growth, "
          f"{draw.annual_growth:.1%} a year)\n")
    print(f"{'year':>6}{'merchant':>19}{'ESEM':>19}{'lane MW':>10}{'levy $/MWh':>12}")
    for a, b, row in zip(legs[MERCHANT].ticks, legs[ESEM].ticks, rows):
        print(f"{a.year:>6}"
              f"{a.unserved_gwh:>12.2f} GWh{row['merchant_times_standard']:>6.1f}x"
              f"{b.unserved_gwh:>10.2f} GWh{row['esem_times_standard']:>6.1f}x"
              f"{b.lane_volume_mw:>10.0f}{b.levy_per_mwh:>12.2f}")

    print(f"\n{'':<34}{'merchant':>16}{'ESEM':>16}")
    def line(label, m, e, scale=1e9, unit="bn"):
        print(f"{label:<34}{m/scale:>14,.2f}{unit}{e/scale:>14,.2f}{unit}")
    m, e = legs[MERCHANT], legs[ESEM]
    print(f"{'unserved energy':<34}{m.total_unserved_gwh:>14,.1f}G"
          f"{e.total_unserved_gwh:>15,.1f}G")
    line("  valued at the price cap", m.unserved_valued_at_the_cap(settings),
         e.unserved_valued_at_the_cap(settings))
    line("wholesale energy cost", m.total_wholesale_cost, e.total_wholesale_cost)
    line("scheme levy", m.total_levy, e.total_levy)
    line("  the bill, all in", m.consumer_cost(settings),
         e.consumer_cost(settings))
    print()
    line("fuel and variable cost", sum(t.fuel_and_vom for t in m.ticks),
         sum(t.fuel_and_vom for t in e.ticks))
    line("fixed cost of the fleet", sum(t.fixed_cost_of_fleet for t in m.ticks),
         sum(t.fixed_cost_of_fleet for t in e.ticks))
    line("capital of new build", sum(t.annualised_capex_of_new_build for t in m.ticks),
         sum(t.annualised_capex_of_new_build for t in e.ticks))
    line("  the resource cost, all in", m.resource_cost(settings),
         e.resource_cost(settings))

    # What each leg built, so the reallocation the scheme causes is reproducible
    # rather than asserted. Nameplate and firm are reported on separate lines: the
    # lane buys firm megawatts and the fleet is counted in nameplate ones, and the
    # two differ by a factor of ten for wind.
    print()
    built = lambda r: sum(b.capacity_mw for t in r.ticks for b in t.builds)
    firm_of = lambda r: sum(b.capacity_mw * settings.tech(b.technology).firm_factor
                            for t in r.ticks for b in t.builds)
    awarded = sum(a.capacity_mw for t in e.ticks for a in t.awards)
    awarded_firm = sum(a.firm_mw for t in e.ticks for a in t.awards)
    print(f"{'unsubsidised build, nameplate MW':<38}"
          f"{built(m):>14,.0f}{built(e):>16,.0f}")
    print(f"{'awarded by the scheme, nameplate':<38}{0:>14,.0f}{awarded:>16,.0f}")
    print(f"{'  new plant in total':<38}"
          f"{built(m):>14,.0f}{built(e) + awarded:>16,.0f}")
    print(f"{'the same plant as firm MW':<38}"
          f"{firm_of(m):>14,.0f}{firm_of(e) + awarded_firm:>16,.0f}")

    bill = m.consumer_cost(settings) - e.consumer_cost(settings)
    real = m.resource_cost(settings) - e.resource_cost(settings)
    transfer = bill - real
    outage = m.unserved_valued_at_the_cap(settings) - \
        e.unserved_valued_at_the_cap(settings)
    print(f"\nthe scheme moves the bill by ${abs(bill)/1e9:,.2f}bn "
          f"({'down' if bill > 0 else 'up'}) and the resource cost by "
          f"${abs(real)/1e9:,.2f}bn ({'down' if real > 0 else 'up'}).")
    print(f"the difference, ${abs(transfer)/1e9:,.2f}bn, is a transfer: more capacity "
          f"lowers the pool\nprice, which moves money from generators to consumers "
          "without saving any of it.\nA comparison that showed only the bill would "
          "report the transfer as a benefit.")
    # Signed, because the two parts often run in opposite directions and wrapping
    # them in abs() printed a pair that did not add up to the move above.
    money = lambda v: f"{'-' if v < 0 else ''}${abs(v)/1e9:,.2f}bn"
    print(f"of that resource-cost move, {money(outage)} is outage the scheme "
          f"avoided\nand {money(real - outage)} is fuel, fixed costs and capital: "
          "what got built\ninstead of what would have been. The two add to the move "
          "above, and a negative\nfigure ran against it.")
    print(f"unserved energy is valued at the market price cap of ${voll:,.0f}/MWh. "
          "That is\na regulatory figure standing in for what an outage costs, not a "
          "measurement of one.")
    # No counts here. This command runs ONE seed, so any figure about how many of
    # ten went which way is a measurement this run did not make. A previous version
    # printed those counts as a string literal, which meant rerunning the model could
    # never update them and every reader was told them whatever the model now did.
    print("\nOne seed, and not much of it travels. Run the same comparison on another "
          "weather\nsequence and both the outage line and the cost line can change "
          "sign. Neither this\nrun's outage nor its total is therefore a property of "
          "the scheme, and neither should\nbe quoted as one. What travels better is "
          "the sort: the outage avoided is largest on\nthe fast-growing draws and "
          "smallest on the slow ones, where the scheme buys capacity\nthat has little "
          "to do. tools/ten_seeds.py runs the envelope and decomposes it, and a\n"
          "copy sits under outputs/canonical/ten_seeds.csv.")
    print("\nA stylised fleet. Illustrative, and not a forecast of anything.")
    with plots.theme("dark"):
        plots.dashboard(legs, settings,
                        os.path.join(args.out, "dashboard_dark.png"))
    picture = plots.dashboard(legs, settings,
                              os.path.join(args.out, "dashboard.png"))
    print(f"wrote {path}\n      {picture}")
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
    m.add_argument("--leg", choices=(MERCHANT, ESEM), default=MERCHANT,
                   help="the market on its own, or with the scheme switched on")
    m.add_argument("--scenario", help=f"a scenario file, or one of: {', '.join(scenario_names())}")
    m.set_defaults(func=simulate)
    c = sub.add_parser("compare", help="run both legs on the same weather")
    c.add_argument("--year", type=int, default=2026)
    c.add_argument("--ticks", type=int, default=20)
    c.add_argument("--peak", type=float, default=DEFAULT_PEAK_MW)
    c.add_argument("--seed", type=int, default=None)
    c.add_argument("--out", default="outputs")
    c.add_argument("--scenario", help=f"a scenario file, or one of: {', '.join(scenario_names())}")
    c.set_defaults(func=compare)
    args = parser.parse_args(argv)
    # Remember what was actually parsed, so _apply can tell a given flag from a
    # defaulted one without consulting the process.
    args._argv = list(argv) if argv is not None else list(sys.argv[1:])
    return args.func(args)
