"""Does the scheme's story survive at the OTHER end of the build-volume bracket?

Both legs use the same investment rule, so the comparison is internally consistent
under either. What this checks is whether the scheme's effect keeps its sign when the
rule changes, because a result that does not is a result about the rule.
"""
from esem_sandbox.config import load_settings
from esem_sandbox.core.forward import cell_plan
from esem_sandbox.core.simulate import ESEM, MERCHANT, run

s = load_settings()
FAST = tuple(c for c in cell_plan(s) if c.shape_year == 0)

print(f"{'rule':>14}{'merchant':>11}{'esem':>10}{'unserved move':>15}"
      f"{'resource bn':>13}{'awarded MW':>12}")
for rule in ("simultaneous", "sequential"):
    m = run(s, ticks=20, seed=20260904, cells=FAST, leg=MERCHANT, investment=rule)
    e = run(s, ticks=20, seed=20260904, cells=FAST, leg=ESEM, investment=rule)
    real = m.resource_cost(s) - e.resource_cost(s)
    print(f"{rule:>14}{m.total_unserved_gwh:>11.1f}{e.total_unserved_gwh:>10.1f}"
          f"{e.total_unserved_gwh - m.total_unserved_gwh:>+15.1f}"
          f"{real/1e9:>13.2f}{e.total_awarded_mw:>12,.0f}", flush=True)
