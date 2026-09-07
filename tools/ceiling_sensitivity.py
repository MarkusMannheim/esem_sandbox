"""Does the annual build ceiling decide the scheme's reliability result?

The auction runs before the investment step, so an award consumes build room the
merchant rule would otherwise have used. That makes the ceiling a candidate cause
whenever the two legs' reliability differs, in either direction, and it is a pacing
choice rather than an economic force - so a result that turns on it is a result
about a parameter.

The test is to run the same paired comparison at two ceilings and watch the
DIFFERENCE between the legs, not either leg's level: raising the ceiling moves both.
Seeds default to the four in the canonical ten-seed pass where the scheme made
reliability worse, plus one where it helped, as a control.
"""

import csv
import os
import sys

from esem_sandbox.config import load_settings
from esem_sandbox.core.simulate import ESEM, MERCHANT, run

ENVELOPE = "outputs/canonical/ten_seeds.csv"


def seeds_to_probe(path: str = ENVELOPE) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """The seeds where the scheme made reliability WORSE, plus one where it helped.

    READ from the ten-seed envelope rather than hardcoded. This list used to be four
    literal seeds with a comment saying they were the ones where the scheme made
    reliability worse in "the canonical ten-seed pass". That is a measured result
    baked into source: rerunning the model could never update it, and after the model
    changed, two of the four had flipped to the scheme making reliability BETTER, so
    the probe was spending an hour of simulation on the wrong question.
    """
    if not os.path.exists(path):
        raise SystemExit(
            f"no envelope at {path}. Run tools/ten_seeds.py first: this probe asks "
            "why the scheme worsened reliability on the seeds where it did, and it "
            "cannot know which those are without it."
        )
    rows = list(csv.DictReader(open(path)))
    worse, helped = [], []
    for r in rows:
        gap = float(r["esem_unserved_gwh"]) - float(r["merchant_unserved_gwh"])
        (worse if gap > 0 else helped).append((abs(gap), int(r["seed"])))
    worse.sort(reverse=True)
    helped.sort(reverse=True)
    if not worse:
        print("NOTE: the scheme did not worsen reliability on ANY seed in the "
              "envelope, so the question this probe was built to answer does not "
              "arise. Probing the seeds where it helped LEAST instead, which is the "
              "nearest thing to the original question.", flush=True)
        helped.sort()
        return tuple(s for _g, s in helped[:4]), tuple(s for _g, s in helped[-1:])
    return tuple(s for _g, s in worse[:4]), tuple(s for _g, s in helped[:1])


def main(ticks: int = 20, ceilings: tuple[int, ...] = (2, 4)) -> int:
    worse, control = seeds_to_probe()
    print(f"probing {worse} against a control of {control}", flush=True)
    print(f"{'seed':>10}{'ceiling':>9}{'merchant':>10}{'esem':>10}"
          f"{'esem - merchant':>17}{'built m':>10}{'built e':>10}")
    for seed in worse + control:
        for ceiling in ceilings:
            s = load_settings(
                {"investment": {"concurrent_builds_per_year": ceiling}})
            m = run(s, ticks=ticks, seed=seed, leg=MERCHANT)
            e = run(s, ticks=ticks, seed=seed, leg=ESEM)
            # The scheme leg's total is its merchant build PLUS what it awarded:
            # awards are recorded separately from builds and are not in either.
            bm = sum(b.capacity_mw for t in m.ticks for b in t.builds)
            be = sum(b.capacity_mw for t in e.ticks
                     for b in t.builds) + e.total_awarded_mw
            print(f"{seed:>10}{ceiling:>9}{m.total_unserved_gwh:>10.1f}"
                  f"{e.total_unserved_gwh:>10.1f}"
                  f"{e.total_unserved_gwh - m.total_unserved_gwh:>+17.1f}"
                  f"{bm:>10,.0f}{be:>10,.0f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 20))
