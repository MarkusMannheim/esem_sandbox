"""How steeply does unserved energy rise as firm plant is taken away?

Dispatches one weather year with the dispatchable fleet scaled down in steps and
prints the curve, so that a small difference in capacity between two runs can be
read against the reliability difference it produces.
"""
from dataclasses import replace

from esem_sandbox.config import load_settings
from esem_sandbox.core.dispatch import dispatch_year
from esem_sandbox.core.weather import generate_bundle

s = load_settings()
b = generate_bundle(s.weather["seed"], s.weather["shape_years"])
VARIABLE = {"wind", "solar", "rooftop"}

print(f"{'firm capacity':>16}{'change':>10}{'unserved, GWh':>16}{'change':>10}")
base_unserved = base_firm = None
for scale in (1.00, 0.97, 0.94, 0.91, 0.89, 0.85):
    fleet = tuple(u if u.technology in VARIABLE
                  else replace(u, capacity_mw=u.capacity_mw * scale,
                               must_run_mw=u.must_run_mw * scale)
                  for u in s.fleet)
    cfg = replace(s, fleet=fleet)
    shape = b["demand_shape"][4]                      # the lull-on-heat year
    res = dispatch_year(cfg, 2026, shape * (12_500 / shape.max()),
                        b["wind_cf"][4], b["solar_cf"][4])
    # The dispatch's own figure, not a second sum over the fleet. Hydro is scheduled
    # against its annual budget and netted out of the residual, so adding its
    # nameplate back counts it twice: the two measures differ by about 3,000 MW on
    # this fleet, and both were being called "firm capacity" in the documents.
    firm = res.firm_capacity_mw
    gwh = float(res.unserved_mwh.sum()) / 1000.0
    if base_unserved is None:
        base_unserved, base_firm = gwh, firm
    print(f"{firm:>13,.0f} MW{firm/base_firm - 1:>+9.1%}{gwh:>16.2f}"
          f"{gwh/base_unserved:>9.1f}x", flush=True)
