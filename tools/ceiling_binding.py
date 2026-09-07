"""What share of all build happened at the annual ceiling, rather than below it?

settings.toml sets this test itself: a ceiling that binds everywhere means the model
is reporting its own ceiling rather than its market. Counts technology-years at the
cap and megawatts at the cap, on both legs and at more than one ceiling value.

The mechanism to weigh the answer against is that each candidate is priced as a
marginal addition to a market that does not contain the others, so the price feedback
that should discipline build volume is real but weak: about $50,000 per MW-year off
the next block against an opening gap of
$367,000, so it would take some 4,000 MW to close and the ceiling stops it at 1,200 -
and each producer wants exactly one block, so four of them picking the same winner
fill a ceiling that allows two.

Run it after any change to the investment rule, the cost table or the build settings.
"""
from esem_sandbox.config import load_settings
from esem_sandbox.core.investment import build_ceiling_mw
from esem_sandbox.core.simulate import ESEM, MERCHANT, run

for ceiling in (2, 4):
    s = load_settings({"investment": {"concurrent_builds_per_year": ceiling}})
    for leg in (MERCHANT, ESEM):
        r = run(s, ticks=20, seed=20260904, leg=leg)
        total = at_cap = 0.0
        techyears = capped = 0
        for t in r.ticks:
            by_tech: dict[str, float] = {}
            for b in t.builds:
                by_tech[b.technology] = by_tech.get(b.technology, 0.0) + b.capacity_mw
            for k, mw in by_tech.items():
                total += mw
                techyears += 1
                if mw >= build_ceiling_mw(12_500.0, s.tech(k), s) - 1e-6:
                    at_cap += mw
                    capped += 1
        print(f"ceiling {ceiling} {leg:>9}: {at_cap:>8,.0f} of {total:>8,.0f} MW built "
              f"at the cap = {at_cap/total:>5.1%}   "
              f"({capped} of {techyears} technology-years)", flush=True)
