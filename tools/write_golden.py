"""Regenerate the golden fingerprint.

Run this ONLY when a change to the model was meant to move these numbers, and put
the diff in the commit that made the change. A golden file that is regenerated
without a reason is a test that has been switched off.
"""

import json
import sys

from esem_sandbox.config import load_settings
from esem_sandbox.core.forward import cell_plan
from esem_sandbox.core.simulate import ESEM, MERCHANT, run

SEED = 20260904
TICKS = 6


def fingerprint() -> dict:
    settings = load_settings()
    fast = tuple(c for c in cell_plan(settings) if c.shape_year == 0)
    out: dict = {"seed": SEED, "ticks": TICKS, "cells": len(fast)}
    for leg in (MERCHANT, ESEM):
        result = run(settings, ticks=TICKS, seed=SEED, cells=fast, leg=leg)
        out[leg] = {
            "growth_path": result.draw.growth_path,
            "mean_price": [round(t.mean_price, 6) for t in result.ticks],
            "unserved_gwh": [round(t.unserved_gwh, 6) for t in result.ticks],
            "built_mw": [round(sum(b.capacity_mw for b in t.builds), 3)
                         for t in result.ticks],
            "live_contracts": [t.live_contracts for t in result.ticks],
            "lane_volume_mw": [round(t.lane_volume_mw, 3) for t in result.ticks],
            "levy_per_mwh": [round(t.levy_per_mwh, 6) for t in result.ticks],
            "bill": round(result.consumer_cost(settings), 3),
            "resource_cost": round(result.resource_cost(settings), 3),
            "built_by_technology": {k: round(v, 3) for k, v in
                                    sorted(result.built_by_technology().items())},
        }
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "tests/golden/run_fingerprint.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(fingerprint(), fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {path}")
