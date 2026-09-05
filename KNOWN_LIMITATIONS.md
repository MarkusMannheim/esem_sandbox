# Known limitations

Things this model gets wrong on purpose, or cannot get right in its current form.
They are listed because a teaching model that hides its own limits teaches the wrong
lesson. Each one is measured, not asserted.

## Storage is scheduled against a price it then moves

Storage picks its charging and discharging hours by ranking a price, and the
resulting schedule changes that price. The dispatch loop damps successive iterates
until the peak-block price settles, which converges, but the schedule finally
reported was made against the previous iterate while settlement prices the current
one.

**Measured:** about 32 per cent of discharged energy lands in an hour priced below an
hour the same store charged in, with a worst inversion near $89/MWh. A test bounds
this at 40 per cent so it cannot quietly worsen.

This cannot be patched. Running one more scheduling pass against the settled price
makes it worse, because that pass moves the price again: it is a cobweb. A genuine
fixed point needs storage co-optimised inside the clearing, which is what a linear
program does and a schedule-then-reprice heuristic cannot.

**A second symptom of the same cause.** Within the hours it does pick, the store
spreads its energy evenly rather than concentrating power where the system is
tightest. In the eight load-shedding hours of the drought shape-year the three
storage units deliver 456 MW of 570, 416 of 490 and 666 of 784, so roughly 300 MW of
rated power sits idle in exactly the hours unserved energy is being counted. An
optimiser would move energy from a merely expensive hour into the shedding one; a
rank-and-spread rule cannot see the difference.

**The fix, when it is worth the complexity,** is to stop ranking prices and start
shaving quantities, exactly as hydro already does here: choose a discharge level and
a charging level such that the energy balances across the round trip, then dispatch
against those levels. Because the price is monotone in residual demand, a store that
shaves the peak and fills the trough is consistent with the price it produces by
construction, and the inversion becomes impossible rather than merely small.

## What the simplification costs elsewhere

One region, so nothing locational: no interconnectors, no transmission build, no
regional price divergence. Synthetic weather, so the probability of the drought year
is stipulated at one in five rather than measured. A stylised fleet of about fifteen
rows, so no unit-level commitment, no minimum stable levels and no outage draws. The
reliability standard is held flat across the whole horizon rather than stepped.

## What is deliberately exact

The energy balance closes to the floating-point limit in every hour: generation net
of curtailment, plus the demand-response ladder, plus unserved energy, equals
operational demand. Hydro delivers its stated annual budget exactly. No unit
generates at a price below its own offer. These are tested, and they are the
properties the model's conclusions actually rest on.
