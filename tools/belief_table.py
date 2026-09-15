"""Where does the guess at what everyone else builds go, given time to settle?

A run gives the belief one step a year against a fleet that moves every year. This
freezes the packaged fleet, switches the risk loading off, and lets the step run for
a number of passes on the full lattice, printing the assumed entry at each
projection year as it goes: total megawatts, whether every candidate there is
settled or gated, and the largest surplus any candidate still shows, in dollars per
megawatt-year over its fixed cost. A projection year that stops moving with a
positive surplus left at it is stalled, not settled.

Usage: belief_table.py [passes]   (default 40; about six seconds a pass)
"""
import sys

from esem_sandbox.config import load_settings
from esem_sandbox.core.forward import (EntryState, cell_plan, forward_view,
                                       update_projected_entry)
from esem_sandbox.core.investment import build_ceiling_mw
from esem_sandbox.core.weather import generate_bundle

PASSES = int(sys.argv[1]) if len(sys.argv) > 1 else 40
PEAK = 12_500.0

s = load_settings()
bundle = generate_bundle(int(s.weather["seed"]), int(s.weather["shape_years"]))
plan = cell_plan(s)
offsets = [int(o) for o in s.forward["anchor_offsets"]]
resolution = {t.technology: t.unit_size_mw for t in s.tech_costs}
report_at = {1, 5, 10, 20, 30, 40, PASSES}

print(f"frozen packaged fleet, {len(plan)} cells, risk loading off, {PASSES} passes")
print(f"{'pass':>5}" + "".join(f"{f'{o} years':>34}" for o in offsets))
print(f"{'':>5}" + "".join(f"{'MW':>12}{'at rest':>9}{'surplus $/MW-yr':>13}"
                            for _ in offsets))

state = EntryState()
for p in range(1, PASSES + 1):
    view = forward_view(s, s.fleet, bundle, year=2026, peak_mw=PEAK,
                        entry=state, cells=plan)
    state = update_projected_entry(state, list(view.anchors), s,
                                   threshold_loading_per_mw_year=0.0)
    if p in report_at:
        cells = []
        for o in offsets:
            rest = "yes" if state.settled(o, resolution) else "no"
            cells.append(f"{state.at(o):>12,.0f}{rest:>9}"
                         f"{state.largest_surplus.get(o, 0.0):>13,.0f}")
        print(f"{p:>5}" + "".join(cells), flush=True)

print("\nassumed entry by technology after the last pass, MW (each projection "
      "year's own increment):")
for o in offsets:
    mix = {t: round(state.at(o, t)) for t in resolution if state.at(o, t) > 0}
    print(f"  {o} years: {mix or 'none'}")
print("\nin service by projection year, cumulative across the years, MW:")
for o in offsets:
    print(f"  {o} years: {sum(state.mix(o).values()):,.0f}")
ceiling = sum(build_ceiling_mw(PEAK, t, s) for t in s.tech_costs)
print(f"\nthe annual build ceiling across all technologies is {ceiling:,.0f} MW")
