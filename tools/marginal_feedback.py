"""What one producer decides, as plant is added to the forecast it reads.

Whether the annual build ceiling binds because no price feedback exists, or because
the feedback exists and is too weak to bite first. Adds capacity to the projection a
block at a time and prints what each block does to the next block's rent and to the
hurdle it must clear.

Re-run after any change to the cost table, the risk settings or the investment rule.
"""
from dataclasses import replace

from esem_sandbox.config import load_settings
from esem_sandbox.core.forward import EntryState, cell_plan, forward_view
from esem_sandbox.core.investment import (
    build_size_mw, evaluate, rank_candidates, residual_exposure,
)
from esem_sandbox.core.agents import PRODUCER, default_roster
from esem_sandbox.core.weather import generate_bundle

s = load_settings()
bundle = generate_bundle(s.weather["seed"], s.weather["shape_years"])
plan = tuple(c for c in cell_plan(s) if c.shape_year == 0)
wind = s.tech("wind")
agent = [a for a in default_roster() if a.kind == PRODUCER][0]
print(f"producer: {agent.name}, risk aversion {agent.risk_aversion}")
print(f"wind fixed cost ${wind.fixed_cost_per_mw_year:,.0f}/MW-yr\n")
print(f"{'wind added':>12}{'hurdle':>14}{'valued at':>14}{'builds?':>10}"
      f"{'in the top few?':>17}")
extra = ()
for n in range(0, 6):
    view = forward_view(s, s.fleet + extra, bundle, year=2026, peak_mw=12_500.0,
                        cells=plan, entry=EntryState())
    # Price wind DIRECTLY. Reading it out of rank_candidates meant the row appeared
    # only while wind was among the few candidates a producer considers, so when it
    # stopped being one this probe printed a header and no rows at all: silence that
    # looked like a broken script rather than an answer. Whether wind is ranked is
    # itself worth reporting, so it is now a column instead of a filter.
    x = evaluate(view, wind, agent, s,
                 exposure=residual_exposure(s, wind.life_years),
                 capacity_mw=build_size_mw(12_500.0, wind, s))
    ranked = any(c.technology == "wind" for c in rank_candidates(
        view, agent, s, peak_mw=12_500.0))
    print(f"{n*600:>9,d} MW{x.hurdle_per_mw_year:>14,.0f}"
          f"{x.expected_rent_per_mw_year:>14,.0f}"
          f"{'  yes' if x.builds else '  NO':>10}"
          f"{'  yes' if ranked else '  no':>17}", flush=True)
    extra = extra + (replace(s.fleet[0], unit=f"w{n}", technology="wind",
                             capacity_mw=600.0, srmc_per_mwh=0.0, must_run_mw=0.0,
                             energy_budget_gwh=None, duration_h=None,
                             round_trip_efficiency=None, retirement_year=9999,
                             availability=wind.availability,
                             firm_factor=wind.firm_factor,
                             fom_per_kw_year=wind.fom_per_kw_year),)
