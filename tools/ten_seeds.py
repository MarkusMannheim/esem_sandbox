"""A ten-seed pass: what survives the weather draw, and what was one run's luck.

Writes one line per seed as it finishes, so a pass that is interrupted leaves the
seeds it did get through rather than nothing. The output is committed as a canonical
artefact, because the notebook's first exercise asks a reader to change the seed and
a workshop should read an envelope rather than wait for one.
"""

import csv
import sys
import time

from esem_sandbox.config import load_settings
from esem_sandbox.core.simulate import ESEM, MERCHANT, run

SEEDS = (20260904, 20260101, 19990101, 7, 424242, 20301231, 111, 20260606,
         98765, 31415926)
FIELDS = ("seed", "growth_path", "annual_growth", "merchant_unserved_gwh",
          "esem_unserved_gwh", "merchant_bill", "esem_bill",
          "merchant_resource_cost", "esem_resource_cost", "awarded_mw",
          "levy_total", "transfer")


def main(path: str, ticks: int = 20) -> int:
    settings = load_settings()
    started = time.perf_counter()
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for seed in SEEDS:
            legs = {leg: run(settings, ticks=ticks, seed=seed, leg=leg)
                    for leg in (MERCHANT, ESEM)}
            m, e = legs[MERCHANT], legs[ESEM]
            bill = m.consumer_cost(settings) - e.consumer_cost(settings)
            real = m.resource_cost(settings) - e.resource_cost(settings)
            writer.writerow({
                "seed": seed,
                "growth_path": m.draw.growth_path,
                "annual_growth": round(m.draw.annual_growth, 4),
                "merchant_unserved_gwh": round(m.total_unserved_gwh, 3),
                "esem_unserved_gwh": round(e.total_unserved_gwh, 3),
                "merchant_bill": round(m.consumer_cost(settings)),
                "esem_bill": round(e.consumer_cost(settings)),
                "merchant_resource_cost": round(m.resource_cost(settings)),
                "esem_resource_cost": round(e.resource_cost(settings)),
                "awarded_mw": round(e.total_awarded_mw),
                "levy_total": round(e.total_levy),
                "transfer": round(bill - real),
            })
            fh.flush()
            print(f"seed {seed} done at {time.perf_counter() - started:.0f}s: "
                  f"unserved {m.total_unserved_gwh:8.1f} -> {e.total_unserved_gwh:8.1f} GWh, "
                  f"resource cost moves {real / 1e9:+7.2f}bn, "
                  f"transfer {(bill - real) / 1e9:+7.2f}bn", flush=True)
    return 0


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "outputs/ten_seeds.csv"
    raise SystemExit(main(out, int(sys.argv[2]) if len(sys.argv) > 2 else 20))


def envelope(path: str) -> dict:
    """Read a finished pass and reduce it to what a reader should take away.

    The point of ten seeds is to separate what the model says from what one weather
    sequence said. A result that changes sign across the seeds is not a result, and
    this is the function that refuses to let one be reported as though it were.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return {}
    unserved = [(float(r["merchant_unserved_gwh"]), float(r["esem_unserved_gwh"]))
                for r in rows]
    resource = [float(r["merchant_resource_cost"]) - float(r["esem_resource_cost"])
                for r in rows]
    transfer = [float(r["transfer"]) for r in rows]
    improved = sum(1 for m, e in unserved if e < m)
    cheaper = sum(1 for r in resource if r > 0)
    return {
        "seeds": len(rows),
        "unserved_improved": improved,
        "resource_cost_lower": cheaper,
        "resource_cost_min": min(resource),
        "resource_cost_max": max(resource),
        "transfer_min": min(transfer),
        "transfer_max": max(transfer),
        "robust_on_reliability": improved == len(rows),
        "robust_on_resource_cost": cheaper in (0, len(rows)),
    }
