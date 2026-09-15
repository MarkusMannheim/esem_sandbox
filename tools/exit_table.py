"""How close does any plant come to an economic exit, on either leg?

The exit rule needs two consecutive years in which a plant's going-forward value
is negative. This prints, per plant, the worst going-forward value it reaches over
the run and the year it reaches it, on both legs, so the claim that the rule never
fires on the packaged fleet carries its own measurement. Nothing about the run is
changed: the exit rule is wrapped, read, and then called as it stands.

Usage: exit_table.py [ticks]   (default 10)
"""
import sys

from esem_sandbox.config import load_settings
from esem_sandbox.core import investment as investment_rule
from esem_sandbox.core import simulate
from esem_sandbox.core.simulate import ESEM, MERCHANT, run

TICKS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
SEED = 20260904

s = load_settings()
worst: dict[tuple[str, str], tuple[float, int]] = {}
real_exit_notices = investment_rule.exit_notices


def watched_exit_notices(fleet, view, settings, year, ledger, _leg=[MERCHANT]):
    notice = int(settings.investment["exit_notice_years"])
    for unit in fleet:
        if unit.technology not in investment_rule.EXIT_ELIGIBLE \
                or not unit.in_service(year) \
                or unit.retirement_year <= year + notice:
            continue
        # A plant absent from any anchor's dispatch (it retires before that anchor)
        # is not measurable, which the rule reads as no reason to exit. Left out
        # here rather than shown as a value of zero.
        if not any(all(unit.unit in o.unit_rent_per_mw_year for o in a.outcomes)
                   for a in view.anchors):
            continue
        value = investment_rule.going_forward_npv_per_mw(unit, view, settings, year)
        key = (_leg[0], unit.unit)
        if key not in worst or value < worst[key][0]:
            worst[key] = (value, year)
    return real_exit_notices(fleet, view, settings, year, ledger)


simulate.exit_notices = watched_exit_notices
notices: dict[str, list] = {}
for leg in (MERCHANT, ESEM):
    watched_exit_notices.__defaults__[0][0] = leg
    result = run(s, ticks=TICKS, seed=SEED, leg=leg)
    notices[leg] = [(t.year, list(t.notices)) for t in result.ticks if t.notices]

print(f"{TICKS} years from 2026, seed {SEED}, both legs. Going-forward value per MW "
      "at its worst, and the year.\n")
print(f"{'plant':<36}{'merchant':>16}{'in':>6}{'with the scheme':>18}{'in':>6}")
names = sorted({u for _leg, u in worst})
for name in names:
    m = worst.get((MERCHANT, name))
    e = worst.get((ESEM, name))
    cell = lambda v: (f"{v[0]:>+16,.0f}{v[1]:>6}" if v else f"{'absent':>16}{'':>6}")
    print(f"{name:<36}{cell(m)}{cell(e)}")
for leg in (MERCHANT, ESEM):
    print(f"\nexit notices on the {leg} leg: {notices[leg] or 'none'}")
