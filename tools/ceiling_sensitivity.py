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

import sys

from esem_sandbox.config import load_settings
from esem_sandbox.core.simulate import ESEM, MERCHANT, run

WORSE = (20260101, 424242, 111, 98765)
CONTROL = (19990101,)


def main(ticks: int = 20, ceilings: tuple[int, ...] = (2, 4)) -> int:
    print(f"{'seed':>10}{'ceiling':>9}{'merchant':>10}{'esem':>10}"
          f"{'esem - merchant':>17}{'built m':>10}{'built e':>10}")
    for seed in WORSE + CONTROL:
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
