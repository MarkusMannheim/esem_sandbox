"""Would the scheme do better if it knew which future it was in?

The tempting explanation for the scheme costing more on slow-growing draws is that
the lane is sized from a forward view that keeps its growth priors whatever the
realised path has been doing, so a scheme that cannot learn which future it is in
keeps buying for the average of them.

That can be tested without a design change: collapse the priors onto the path each
run actually drew, so the forward view knows what the run knows, and compare. The
realised weather and the realised growth path are held identical, which the probe
asserts rather than assumes.
"""

import csv
import os
import sys
from dataclasses import replace

from esem_sandbox.config import GrowthPath, load_settings
from esem_sandbox.core.forward import cell_plan
from esem_sandbox.core.simulate import ESEM, MERCHANT, draw_sequence, run

ENVELOPE = "outputs/canonical/ten_seeds.csv"


def certain(settings, path: str):
    """The same settings with all the prior weight on one growth path."""
    return replace(settings, growth=tuple(
        GrowthPath(path=g.path, weight=1.0 if g.path == path else 0.0,
                   annual_growth=g.annual_growth)
        for g in settings.growth))


def main(ticks: int = 20, reduced: bool = True) -> int:
    s = load_settings()
    seeds = [int(r["seed"]) for r in csv.DictReader(open(ENVELOPE))] \
        if os.path.exists(ENVELOPE) else [20260904, 20260101, 111, 19990101]
    voll = s.market["market_price_cap_per_mwh"]

    print(f"{'seed':>10}{'path':>8}{'priors':>18}{'awarded MW':>12}"
          f"{'resource move':>15}{'outage avoided':>16}")
    for seed in seeds:
        drew = draw_sequence(s, seed, ticks)
        known = certain(s, drew.growth_path)
        # The point of the probe is that ONLY the priors move.
        after = draw_sequence(known, seed, ticks)
        assert after.growth_path == drew.growth_path, "the realised path moved"
        assert after.shape_years == drew.shape_years, "the realised weather moved"
        assert after.peak_bands == drew.peak_bands, "the realised peak bands moved"

        for label, cfg in (("as they are", s), ("knowing the path", known)):
            # Build the lattice from THIS configuration. cell_plan carries the growth
            # weights, so passing a plan built from the unmodified settings meant the
            # collapsed priors never reached the forward view at all and the two rows
            # came back identical to the last digit. A probe whose control and
            # treatment agree exactly is reporting its own wiring, not a result.
            cells = tuple(c for c in cell_plan(cfg) if c.shape_year == 0) \
                if reduced else None
            m = run(cfg, ticks=ticks, seed=seed, cells=cells, leg=MERCHANT)
            e = run(cfg, ticks=ticks, seed=seed, cells=cells, leg=ESEM)
            move = (m.resource_cost(cfg) - e.resource_cost(cfg)) / 1e9
            outage = (m.total_unserved_gwh - e.total_unserved_gwh) * 1000 * voll / 1e9
            print(f"{seed if label == 'as they are' else '':>10}"
                  f"{drew.growth_path if label == 'as they are' else '':>8}"
                  f"{label:>18}{e.total_awarded_mw:>12,.0f}"
                  f"{move:>+14.2f}bn{outage:>+15.2f}bn", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 20))
